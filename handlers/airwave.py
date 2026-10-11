try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    webdriver = None
    By = None
    WebDriverWait = None
    EC = None

import os
import re
import time
from datetime import datetime
from utils.airwave import (
    AirWaveClient,
    parse_airwave_device_info_html,
    parse_airwave_login_html,
)

# In-memory client cache per server
_airwave_clients = {}


def get_cached_airwave_client(host_or_url, username, password):
    key = (host_or_url, username)
    if key not in _airwave_clients:
        _airwave_clients[key] = AirWaveClient(host_or_url, username, password)
    return _airwave_clients[key]


def _login_airwave_webui(driver, base_url, username, password, host_label="AirWave"):
    """
    Automates login into Aruba AirWave WebUI.
    """
    print(f"[{host_label}] Checking AirWave login status...")
    driver.get(f"{base_url}/")
    time.sleep(2)

    # Check login page state via HTML parser
    login_state = parse_airwave_login_html(driver.page_source)
    if not login_state["has_login_dialog"]:
        print(f"[{host_label}] WebUI already authenticated or no login form.")
        return

    print(f"[{host_label}] Submitting WebUI credentials at {base_url}...")
    user_field = driver.find_element(By.ID, "login-username-id")
    user_field.clear()
    user_field.send_keys(username)

    pass_field = driver.find_element(By.ID, "login-password-id")
    pass_field.clear()
    pass_field.send_keys(password)

    login_btn = driver.find_element(By.ID, "login-button")
    login_btn.click()

    # Wait for login to complete or error to appear
    start_time = time.time()
    while time.time() - start_time < 20:
        state = parse_airwave_login_html(driver.page_source)
        if state["login_failed"] and state["error_message"]:
            raise Exception(f"AirWave WebUI authentication failed: {state['error_message']}")

        if state["is_logged_in"]:
            print(f"[{host_label}] WebUI login successful.")
            return

        time.sleep(1)

    raise Exception("Timeout waiting for AirWave WebUI login to complete.")


def handle(host, alert_info, options):
    """
    AirWave handler for Nagios-Sust.
    Resolves the device ID in AirWave API, logs into WebUI, captures the Device Info viewport,
    and scrapes system info.
    """
    raw_url = options.get("airwave_url") or options.get("url") or "https://airwave"
    base_url = raw_url.rstrip("/")
    if not base_url.startswith("http"):
        base_url = f"https://{base_url}"

    username = options.get("username")
    password = options.get("password")

    # If credentials are not provided via config, request them via the provider injected by main.py
    if not username or not password:
        if "credential_provider" in options:
            prov_user, prov_pass = options["credential_provider"]()
            username = username or prov_user
            password = password or prov_pass
        else:
            raise ValueError("Credentials are required but not provided in options.")

    result = {
        "host": host,
        "url": base_url,
        "wan_status": {},
        "system_info": {},
        "screenshot_path": None,
        "latencies": [],
        "has_failure": False,
        "error": None,
    }

    # 1. Resolve Device ID
    device_id = alert_info.get("device_id") if isinstance(alert_info, dict) else None
    device_data = None

    if not device_id:
        print(f"[{host}] Resolving device ID from AirWave API...")
        try:
            client = get_cached_airwave_client(base_url, username, password)
            device_data = client.get_device_by_host(host)
            if device_data:
                device_id = device_data.get("id")
                print(f"[{host}] Resolved AirWave device ID: {device_id}")
            else:
                err_msg = f"Device '{host}' not found in AirWave device enumeration."
                print(f"[{host}] Error: {err_msg}")
                result["error"] = err_msg
                result["has_failure"] = True
                return result
        except Exception as api_err:
            print(f"[{host}] AirWave API error: {api_err}")
            result["error"] = str(api_err)
            result["has_failure"] = True
            return result

    monitoring_url = f"{base_url}/ap_monitoring?id={device_id}"
    result["url"] = monitoring_url

    # 2. Selenium Web Automation
    driver = None
    try:
        driver_options = webdriver.ChromeOptions()
        driver_options.add_argument("--ignore-certificate-errors")

        driver = webdriver.Chrome(options=driver_options)

        # Authenticate via WebUI
        _login_airwave_webui(driver, base_url, username, password, host_label=host)

        # Navigate to Device Monitoring page
        print(f"[{host}] Navigating to device monitoring page: {monitoring_url}")
        driver.get(monitoring_url)

        # Wait for Device Info table to render
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#fragment_div_AP__Monitoring__InfoTable, .infoTableWrapper"))
        )
        time.sleep(2) # Allow data tables to finish asynchronous populating

        # 3. Viewport & Horizontal Scroll Handling for Screenshot
        if options.get("capture_screenshot", True):
            print(f"[{host}] Adjusting viewport for horizontal scroll table...")
            # Query content width to ensure no horizontal column clipping
            content_width = driver.execute_script("""
                let wrapper = document.querySelector('.infoTableWrapper');
                let table = document.querySelector('#fragment_div_AP__Monitoring__InfoTable table');
                let w = Math.max(
                    document.body.scrollWidth || 0,
                    wrapper ? wrapper.scrollWidth : 0,
                    table ? table.scrollWidth : 0,
                    1920
                );
                return w;
            """)

            target_width = max(int(content_width) + 80, 1920)
            target_height = 950 # Viewport framed on the Device Info table
            driver.set_window_size(target_width, target_height)

            # Ensure wrapper horizontal scroll position is reset to start
            driver.execute_script("""
                let wrapper = document.querySelector('.infoTableWrapper');
                if (wrapper) { wrapper.scrollLeft = 0; }
                let el = document.querySelector('#fragment_div_AP__Monitoring__InfoTable');
                if (el) { el.scrollIntoView({block: 'start'}); }
            """)
            time.sleep(1)

            # Prepare screenshot file path
            exec_timestamp = options.get("execution_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
            base_dir = options.get("base_dir", os.getcwd())
            screenshots_dir = os.path.join(base_dir, "screenshots", exec_timestamp, "airwave")
            os.makedirs(screenshots_dir, exist_ok=True)

            capture_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_filename = f"screenshot_{host}_{capture_timestamp}.png"
            screenshot_path = os.path.join(screenshots_dir, screenshot_filename)

            driver.save_screenshot(screenshot_path)
            result["screenshot_path"] = screenshot_path
            print(f"[{host}] Screenshot saved at {screenshot_path}")

        # 4. Scrape Device Info Table
        info_elements = driver.find_elements(By.ID, "fragment_div_AP__Monitoring__InfoTable")
        if info_elements:
            html_table = info_elements[0].get_attribute("outerHTML")
            scraped_info = parse_airwave_device_info_html(html_table, device_name=host)
            result["system_info"] = scraped_info

            status_val = scraped_info.get("status", "").upper()
            if status_val and "DOWN" in status_val:
                result["has_failure"] = True

            print(
                f"[{host}] System info: Model='{scraped_info.get('model')}', "
                f"S/N='{scraped_info.get('serial_number')}', "
                f"Version='{scraped_info.get('version')}', "
                f"Uptime='{scraped_info.get('uptime')}', "
                f"Status='{scraped_info.get('status')}'"
            )

    except Exception as e:
        print(f"[{host}] Error during AirWave automation: {e}")
        result["error"] = str(e)
        result["has_failure"] = True
    finally:
        if driver:
            driver.quit()

    return result
