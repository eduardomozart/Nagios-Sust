from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import time
import os
import re
from utils.network import ip_netmask_to_cidr, ping_host

def _get_wan_details(driver, interface_name):
    try:
        xpath = f"//*[contains(text(), '({interface_name})') or normalize-space(text())='{interface_name}']"
        
        # Find the element containing the exact interface name (with or without parenthesis, and handle leading/trailing spaces)
        elements = driver.find_elements(By.XPATH, xpath)
        
        # If not found, it might be lazy-loaded in a virtual table. Attempt to scroll down.
        if not elements:
            try:
                driver.execute_script("""
                    document.querySelectorAll('.table-container, .mutable-table-container, .mutable').forEach(c => {
                        c.scrollTop = c.scrollHeight;
                    });
                """)
                import time
                time.sleep(1.5) # Wait for virtual DOM to render the new rows
                elements = driver.find_elements(By.XPATH, xpath)
            except:
                pass
                
        for el in elements:
            try:
                # Go up the DOM tree to find the parent table row. Strictly match ' row ' to avoid stopping at 'row-cell' or 'row-inner-cell'.
                parent = el.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' row ')]")
                
                # Extract text from individual cells and join with spaces to prevent textContent from concatenating words, which breaks Regex \b boundaries
                cells = parent.find_elements(By.XPATH, ".//*[self::td or contains(concat(' ', normalize-space(@class), ' '), ' row-cell ')]")
                row_text = " ".join([c.get_attribute("textContent").strip() for c in cells])
                
                # If cells extraction failed (e.g., different DOM), fallback to the parent's textContent with relaxed Regex
                if not row_text:
                    row_text = parent.get_attribute("textContent")
                
                # Regex looking for an IP address (with optional subnet mask)
                match = re.search(r'(?:^|\b|\D)(\d{1,3}(?:\.\d{1,3}){3}(?:/(?:\d{1,3}(?:\.\d{1,3}){3}|\d{1,2}))?)', row_text)
                if match:
                    ip, mask = ip_netmask_to_cidr(match.group(1))
                    
                    latency = ping_host(ip)
                    return ip, mask, latency
            except:
                continue
        return "", "", ""
    except:
        return "", "", ""

def _extract_wan_status(driver, host):
    wan_status = {}
    try:
        wan1_element = driver.find_element(By.CSS_SELECTOR, "div[port-id='wan1']")
        wan1_status = wan1_element.get_attribute("link")
        wan_status["WAN1"] = wan1_status.upper() if wan1_status else "UNKNOWN"
        wan1_ip, wan1_mask, wan1_latency = _get_wan_details(driver, "wan1")
        wan_status["WAN1_IP"] = wan1_ip
        wan_status["WAN1_MASK"] = wan1_mask
        wan_status["WAN1_LATENCY"] = wan1_latency
    except Exception:
        wan_status["WAN1"] = "NOT FOUND"
        wan_status["WAN1_IP"] = ""
        wan_status["WAN1_MASK"] = ""
        wan_status["WAN1_LATENCY"] = ""
        
    try:
        wan2_element = driver.find_element(By.CSS_SELECTOR, "div[port-id='wan2']")
        wan2_status = wan2_element.get_attribute("link")
        wan_status["WAN2"] = wan2_status.upper() if wan2_status else "UNKNOWN"
        wan2_ip, wan2_mask, wan2_latency = _get_wan_details(driver, "wan2")
        wan_status["WAN2_IP"] = wan2_ip
        wan_status["WAN2_MASK"] = wan2_mask
        wan_status["WAN2_LATENCY"] = wan2_latency
    except Exception:
        wan_status["WAN2"] = "NOT FOUND"
        wan_status["WAN2_IP"] = ""
        wan_status["WAN2_MASK"] = ""
        wan_status["WAN2_LATENCY"] = ""
        
    wan3_configured = False
    wan3_name = "internal5"
    try:
        elements = driver.find_elements(By.XPATH, "//*[contains(text(), '(internal5)') or contains(text(), '(port5)') or normalize-space(text())='internal5' or normalize-space(text())='port5']")
        if elements:
            wan3_configured = True
            if 'port5' in elements[0].text:
                wan3_name = "port5"
    except Exception:
        pass

    try:
        try:
            wan3_element = driver.find_element(By.CSS_SELECTOR, "div[port-id='internal5' i]")
        except:
            wan3_element = driver.find_element(By.CSS_SELECTOR, "div[port-id='port5' i]")
            
        wan3_status = wan3_element.get_attribute("link")
        wan3_clean = wan3_status.strip().upper() if wan3_status else ""
        
        wan3_ip, wan3_mask, wan3_latency = _get_wan_details(driver, wan3_name)
        
        if wan3_clean == "UP":
            print(f"[{host}] Found port5/internal5 physically UP.")
            wan_status["WAN3"] = "UP"
            wan_status["WAN3_IP"] = wan3_ip
            wan_status["WAN3_MASK"] = wan3_mask
            wan_status["WAN3_LATENCY"] = wan3_latency
        elif wan3_configured:
            print(f"[{host}] Found port5/internal5 DOWN but it is configured in the table.")
            wan_status["WAN3"] = "DOWN"
            wan_status["WAN3_IP"] = wan3_ip
            wan_status["WAN3_MASK"] = wan3_mask
            wan_status["WAN3_LATENCY"] = wan3_latency
        else:
            print(f"[{host}] port5/internal5 is DOWN and not explicitly configured in the table. Ignoring.")
            
    except Exception as e:
        if wan3_configured:
            print(f"[{host}] Configured port5/internal5 not found in faceplate. Setting as UNKNOWN.")
            wan_status["WAN3"] = "UNKNOWN"
            
    return wan_status

def handle(host, alert_info, options):
    url = options.get("url_template", "https://{host}/ng/interface").format(host=host)
    
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

    print(f"[{host}] Starting evidence collection at {url}")

    driver_options = webdriver.ChromeOptions()
    driver_options.add_argument('--ignore-certificate-errors')
    # Suppress console errors from Chrome to keep the terminal clean
    # driver_options.add_argument('--log-level=3')
    # driver_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    # driver_options.add_argument('--headless') # Uncomment to run headless without opening a window
    
    # Using Chrome. Ensure you have a compatible chromedriver installed and in PATH.
    driver = webdriver.Chrome(options=driver_options)

    result = {
        "host": host,
        "url": url,
        "wan_status": {},
        "screenshot_path": None,
        "error": None
    }

    try:
        driver.get(url)
        
        # 1. Perform Login
        print(f"[{host}] Waiting for login screen...")
        user_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "username")) 
        )
        user_field.clear()
        user_field.send_keys(username)
        
        pass_field = driver.find_element(By.ID, "secretkey")
        pass_field.clear()
        pass_field.send_keys(password)

        # Click the Login button based on the provided HTML
        try:
            login_btn = driver.find_element(By.ID, "login_button")
        except:
            login_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Login Read-Only']")
            
        login_btn.click()

        # 2. Wait for the interfaces table, FortiManager prompt, or Authentication failure
        print(f"[{host}] Login submitted. Waiting for authentication result...")
        
        start_time = time.time()
        fmg_handled = False
        login_success = False
        
        while time.time() - start_time < 30:
            # Check for authentication failure
            try:
                err_msg = driver.find_element(By.ID, "err_msg")
                if err_msg.is_displayed():
                    raise Exception("Authentication Failed. Skipping device.")
            except Exception as e:
                if str(e) == "Authentication Failed. Skipping device.":
                    raise
                pass

            # If the interfaces table has appeared, we are done waiting
            if driver.find_elements(By.CSS_SELECTOR, "table.portgroup") or driver.find_elements(By.CSS_SELECTOR, "div.mutable-table-container"):
                login_success = True
                break
                
            # If the FortiManager centrally managed prompt appears, click "Login Read-Only"
            if not fmg_handled:
                fmg_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Login Read-Only')]")
                if fmg_buttons:
                    print(f"[{host}] FortiManager interception detected. Clicking 'Login Read-Only'...")
                    try:
                        fmg_buttons[0].click()
                        fmg_handled = True
                    except Exception as e:
                        print(f"[{host}] Failed to click FortiManager prompt: {e}")
                        
            time.sleep(1)
        else:
            raise Exception("Timeout waiting for interfaces table to load after login.")
            
        if login_success:
            print(f"[{host}] Login successful. Proceeding to collect interfaces...")

        
        # Short pause to ensure rendering of icons/states
        time.sleep(3)
        
        # 3. Take Screenshot
        exec_timestamp = options.get("execution_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
        # Use the current filename without extension (e.g. 'fortigate')
        handler_name = os.path.splitext(os.path.basename(__file__))[0]
        
        # Create nested screenshots directory: screenshots/<timestamp>/<handler_name>
        screenshots_dir = os.path.join(os.getcwd(), "screenshots", exec_timestamp, handler_name)
        os.makedirs(screenshots_dir, exist_ok=True)
        
        capture_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_filename = f"screenshot_{host}_{capture_timestamp}.png"
        screenshot_path = os.path.join(screenshots_dir, screenshot_filename)
        
        driver.save_screenshot(screenshot_path)
        result["screenshot_path"] = screenshot_path
        print(f"[{host}] Screenshot saved at {screenshot_path}")

        # 4. Extract WAN1, WAN2 and conditionally WAN3 status
        result["wan_status"] = _extract_wan_status(driver, host)
        
        # Populate universal latencies array for exporters
        latencies = []
        for key in ["WAN1_LATENCY", "WAN2_LATENCY", "WAN3_LATENCY"]:
            val = result["wan_status"].get(key)
            if val:
                try:
                    latencies.append(int(val))
                except:
                    pass
        result["latencies"] = latencies

        wan_str = ", ".join([f"{k}={v}" for k, v in result["wan_status"].items()])
        print(f"[{host}] Collected status: {wan_str}")

    except Exception as e:
        print(f"[{host}] Error during automation: {e}")
        result["error"] = str(e)
    finally:
        driver.quit()

    return result
