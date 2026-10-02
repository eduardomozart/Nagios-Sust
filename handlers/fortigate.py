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
        
        # If not found, it might be lazy-loaded in a virtual table. Attempt to scroll down incrementally.
        scroll_attempts = 0
        while not elements and scroll_attempts < 10:
            try:
                driver.execute_script("""
                    document.querySelectorAll('.table-container, .mutable-table-container, .mutable, .vertical-scroller, .scrollers').forEach(c => {
                        c.scrollTop += 350;
                        c.dispatchEvent(new Event('scroll', {bubbles: true}));
                    });
                """)
                import time
                time.sleep(0.6) # Wait for virtual DOM to render the new rows
                elements = driver.find_elements(By.XPATH, xpath)
                scroll_attempts += 1
            except:
                break
                
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
                    return ip, mask
            except Exception as row_e:
                print(f"DEBUG: Row processing exception for {interface_name}: {row_e}")
                continue
        return "", ""
    except:
        return "", ""

def _extract_wan_status(driver, host, options):
    wan_status = {}
    
    # Read configuration
    diagnose_intfs = options.get("diagnose_interfaces", ["wan1", "wan2", "internal5", "port5"])
    ping_intfs = options.get("ping_interfaces", ["wan1", "wan2"])
    ping_gateway = options.get("ping_gateway", False)
    
    # Default mappings to preserve backwards compatibility with DOCX templates (which expect WAN1, WAN2, WAN3)
    mapping = options.get("interface_mapping", {
        "wan1": "WAN1",
        "wan2": "WAN2",
        "internal5": "WAN3",
        "port5": "WAN3"
    })
    
    gateways = {}
    if ping_gateway and ping_intfs:
        print(f"[{host}] ping_gateway is enabled. Fetching static routes to find gateways...")
        try:
            driver.get(f"https://{host}/ng/routing/static/")
            time.sleep(3) # Wait for table load
            
            # Find the default routes (0.0.0.0/0)
            rows = driver.find_elements(By.XPATH, "//div[contains(concat(' ', normalize-space(@class), ' '), ' row ')]")
            for row in rows:
                try:
                    dst = row.find_element(By.CSS_SELECTOR, "div[column-id='dst']").text.strip()
                    if dst == "0.0.0.0/0":
                        gw = row.find_element(By.CSS_SELECTOR, "div[column-id='gateway']").text.strip()
                        intf_text = row.find_element(By.CSS_SELECTOR, "div[column-id='$intf']").text.strip()
                        
                        # Check which interface this default route belongs to
                        for intf in ping_intfs:
                            if f"({intf})" in intf_text or intf == intf_text or intf in intf_text:
                                gateways[intf.lower()] = gw
                except:
                    pass
            print(f"[{host}] Extracted gateways: {gateways}")
            
            # Navigate back to interface page
            driver.get(f"https://{host}/ng/interface")
            time.sleep(3)
        except Exception as e:
            print(f"[{host}] Failed to extract gateways: {e}")
            
    for intf in diagnose_intfs:
        intf_lower = intf.lower()
        key = mapping.get(intf_lower, intf.upper())
        
        try:
            # Locate the interface status box/icon
            el = driver.find_element(By.CSS_SELECTOR, f"div[port-id='{intf}' i]")
            status = el.get_attribute("link")
            status_clean = status.strip().upper() if status else "UNKNOWN"
            
            ip, mask = _get_wan_details(driver, intf)
            latency = ""
            
            # Only ping if requested AND if the physical status is UP
            if status_clean == "UP" and intf_lower in [p.lower() for p in ping_intfs]:
                target_ip = None
                if ping_gateway:
                    target_ip = gateways.get(intf_lower)
                    if target_ip:
                        print(f"[{host}] Pinging {intf} gateway -> {target_ip}")
                    else:
                        print(f"[{host}] Gateway for {intf} not found, falling back to interface IP -> {ip}")
                        target_ip = ip
                else:
                    target_ip = ip
                    print(f"[{host}] Pinging {intf} interface IP -> {target_ip}")
                
                if target_ip:
                    latency = ping_host(target_ip)
            
            # To avoid overwriting internal5 with port5 if both are passed and mapped to WAN3
            if key not in wan_status or wan_status[key] == "NOT FOUND":
                wan_status[key] = status_clean
                wan_status[f"{key}_IP"] = ip
                wan_status[f"{key}_MASK"] = mask
                wan_status[f"{key}_LATENCY"] = latency
                
        except Exception as e:
            if key not in wan_status:
                wan_status[key] = "NOT FOUND"
                wan_status[f"{key}_IP"] = ""
                wan_status[f"{key}_MASK"] = ""
                wan_status[f"{key}_LATENCY"] = ""

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
        
        # 3. Take Screenshot (if enabled)
        if options.get("capture_screenshot", True):
            exec_timestamp = options.get("execution_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
            # Use the current filename without extension (e.g. 'fortigate')
            handler_name = os.path.splitext(os.path.basename(__file__))[0]
            
            # Create nested screenshots directory: screenshots/<timestamp>/<handler_name>
            base_dir = options.get("base_dir", os.getcwd())
            screenshots_dir = os.path.join(base_dir, "screenshots", exec_timestamp, handler_name)
            os.makedirs(screenshots_dir, exist_ok=True)
            
            capture_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_filename = f"screenshot_{host}_{capture_timestamp}.png"
            screenshot_path = os.path.join(screenshots_dir, screenshot_filename)
            
            driver.save_screenshot(screenshot_path)
            result["screenshot_path"] = screenshot_path
            print(f"[{host}] Screenshot saved at {screenshot_path}")

        # 4. Extract Interface status and run latency checks
        result["wan_status"] = _extract_wan_status(driver, host, options)
        
        # Populate universal latencies array for exporters
        latencies = []
        for key, val in result["wan_status"].items():
            if key.endswith("_LATENCY") and val:
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
