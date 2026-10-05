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
        # Restrict search to the Name column to avoid false positives in the 'Members' column
        xpath = f"//*[contains(text(), '({interface_name})') or normalize-space(text())='{interface_name}'][ancestor::div[@column-id='name'] or ancestor::td[contains(@class, 'name') or count(preceding-sibling::td) < 2]]"
        
        # Find the element containing the exact interface name
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
    
    diagnose_intfs = options.get("diagnose_interfaces", ["wan1", "wan2"])
    ping_intfs = options.get("ping_interfaces", diagnose_intfs)
    ping_gateway = options.get("ping_gateway", False)
    
    # 1. We are already on /ng/interface. Extract IP, mask, and link status.
    intf_data = {}
    for intf_config in diagnose_intfs:
        # Support aliases like 'internal5|port5'
        aliases = [a.strip() for a in intf_config.split('|')]
        primary_intf = aliases[0]
        intf_lower = primary_intf.lower()
        key = primary_intf.upper()
        
        el = None
        used_alias = primary_intf
        
        for alias in aliases:
            try:
                el = driver.find_element(By.CSS_SELECTOR, f"div[port-id='{alias}' i]")
                used_alias = alias
                break
            except:
                pass
                
        try:
            if el:
                status = el.get_attribute("link")
                status_clean = status.strip().upper() if status else "UNKNOWN"
                ip, mask = _get_wan_details(driver, used_alias)
                
                intf_data[intf_lower] = {
                    "key": key,
                    "status": status_clean,
                    "ip": ip,
                    "mask": mask,
                    "aliases": aliases
                }
            else:
                raise Exception("Not found")
        except Exception:
            intf_data[intf_lower] = {
                "key": key,
                "status": "NOT FOUND",
                "ip": "",
                "mask": "",
                "aliases": aliases
            }

    # 2. If ping_gateway is enabled, go to static routing and find gateways.
    gateways = {}
    if ping_gateway:
        print(f"[{host}] ping_gateway is enabled. Fetching static routes to find gateways...")
        try:
            driver.get(f"https://{host}/ng/routing/static")
            time.sleep(3) # Wait for table load
            
            rows = driver.find_elements(By.XPATH, "//div[contains(concat(' ', normalize-space(@class), ' '), ' row ')]")
            
            # Group routes by primary interface lower name
            routes_by_intf = {p.split('|')[0].strip().lower(): [] for p in diagnose_intfs}
            
            for row in rows:
                try:
                    dst = row.find_element(By.CSS_SELECTOR, "div[column-id='dst']").text.strip()
                    gw = row.find_element(By.CSS_SELECTOR, "div[column-id='gateway']").text.strip()
                    intf_text = row.find_element(By.CSS_SELECTOR, "div[column-id='$intf']").text.strip().lower()
                    
                    for p_conf in diagnose_intfs:
                        p_aliases = [a.strip() for a in p_conf.split('|')]
                        p_primary = p_aliases[0].lower()
                        for alias in p_aliases:
                            alias_lower = alias.lower()
                            if f"({alias_lower})" in intf_text or alias_lower == intf_text or alias_lower in intf_text:
                                routes_by_intf[p_primary].append((dst, gw))
                                break
                except:
                    continue
                    
            import ipaddress
            
            for intf_primary, routes in routes_by_intf.items():
                if not routes:
                    continue
                    
                # Priority 1: Default route 0.0.0.0/0
                default_gw = next((gw for dst, gw in routes if dst == "0.0.0.0/0" and gw), None)
                if default_gw:
                    gateways[intf_primary] = default_gw
                    continue
                
                # Priority 2: Gateway matches the subnet of the interface IP
                data = intf_data.get(intf_primary)
                best_gw = None
                if data and data["ip"] and data["mask"]:
                    try:
                        intf_network = ipaddress.IPv4Network(f"{data['ip']}/{data['mask']}", strict=False)
                        for dst, gw in routes:
                            if not gw: continue
                            try:
                                gw_ip = ipaddress.IPv4Address(gw)
                                if gw_ip in intf_network:
                                    best_gw = gw
                                    break
                            except:
                                pass
                    except:
                        pass
                
                if best_gw:
                    gateways[intf_primary] = best_gw
                else:
                    # Priority 3: Fallback to the first route's gateway we found for this interface
                    first_gw = next((gw for dst, gw in routes if gw), None)
                    if first_gw:
                        gateways[intf_primary] = first_gw
                        
            print(f"[{host}] Extracted gateways: {gateways}")
            
            # Navigate back to interface page
            driver.get(f"https://{host}/ng/interface")
            time.sleep(3)
        except Exception as e:
            print(f"[{host}] Failed to extract gateways: {e}")
            
    # 3. Assemble final wan_status and run pings
    for intf_config in diagnose_intfs:
        primary_intf = intf_config.split('|')[0].strip()
        intf_lower = primary_intf.lower()
        data = intf_data[intf_lower]
        key = data["key"]
        
        status_clean = data["status"]
        ip = data["ip"]
        mask = data["mask"]
        latency = ""
        
        gw_found = gateways.get(intf_lower, "")
        
        # Check if this interface was requested for pinging
        wants_ping = False
        for p_conf in ping_intfs:
            if p_conf.split('|')[0].strip().lower() == intf_lower:
                wants_ping = True
                break
                
        if ip == "0.0.0.0":
            status_clean = "DOWN (No IP)"
            
        # Only ping if requested AND if the physical status is UP
        if status_clean == "UP" and wants_ping:
            target_ip = None
            if ping_gateway:
                target_ip = gw_found
                if target_ip:
                    print(f"[{host}] Pinging {primary_intf} gateway -> {target_ip}")
                else:
                    print(f"[{host}] Gateway for {primary_intf} not found, falling back to interface IP -> {ip}")
                    target_ip = ip
            else:
                target_ip = ip
                print(f"[{host}] Pinging {primary_intf} interface IP -> {target_ip}")
            
            if target_ip:
                latency = ping_host(target_ip)
        
        wan_status[key] = {
            "status": status_clean,
            "ip": ip,
            "mask": mask,
            "gw": gw_found,
            "latency": latency,
            "ping_interface": wants_ping
        }

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
        has_failure = False
        for intf_key, intf_data in result["wan_status"].items():
            status = intf_data.get("status", "")
            ip = intf_data.get("ip", "")
            
            # 1. 0.0.0.0 (Logical down)
            if ip == "0.0.0.0":
                has_failure = True
                
            # 2. Monitored interface is DOWN with an assigned IP address
            if "DOWN" in status and ip and ip != "0.0.0.0":
                has_failure = True
                
            # 3. Ping gateway or interface was requested, but failed (timeout)
            if intf_data.get("ping_interface") and status.startswith("UP") and not intf_data.get("latency"):
                has_failure = True
                
            val = intf_data.get("latency")
            if val:
                try:
                    latencies.append(int(val))
                except:
                    pass
                    
        result["latencies"] = latencies
        result["has_failure"] = has_failure

        wan_str = ", ".join([f"{k}={v}" for k, v in result["wan_status"].items()])
        print(f"[{host}] Collected status: {wan_str}")

    except Exception as e:
        print(f"[{host}] Error during automation: {e}")
        result["error"] = str(e)
    finally:
        driver.quit()

    return result
