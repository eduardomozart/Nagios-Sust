from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os

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
        user_field.send_keys(username)
        
        pass_field = driver.find_element(By.ID, "secretkey")
        pass_field.send_keys(password)

        # Click the Login button based on the provided HTML
        # We try the standard ID first, then fallback to the aria-label mentioned earlier just in case
        try:
            login_btn = driver.find_element(By.ID, "login_button")
        except:
            login_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Login Read-Only']")
            
        login_btn.click()

        # 2. Wait for the interfaces table (portgroup) to load
        print(f"[{host}] Login successful. Waiting for interfaces table...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.portgroup"))
        )
        
        # Short pause to ensure rendering of icons/states
        time.sleep(3)
        
        # 3. Take Screenshot
        screenshot_path = os.path.abspath(f"screenshot_{host}.png")
        driver.save_screenshot(screenshot_path)
        result["screenshot_path"] = screenshot_path
        print(f"[{host}] Screenshot saved at {screenshot_path}")

        # 4. Extract WAN1 and WAN2 status based on the provided HTML
        try:
            wan1_element = driver.find_element(By.CSS_SELECTOR, "div[port-id='wan1']")
            wan1_status = wan1_element.get_attribute("link")
            result["wan_status"]["WAN1"] = wan1_status.upper() if wan1_status else "UNKNOWN"
        except Exception:
            result["wan_status"]["WAN1"] = "NOT FOUND"
            
        try:
            wan2_element = driver.find_element(By.CSS_SELECTOR, "div[port-id='wan2']")
            wan2_status = wan2_element.get_attribute("link")
            result["wan_status"]["WAN2"] = wan2_status.upper() if wan2_status else "UNKNOWN"
        except Exception:
            result["wan_status"]["WAN2"] = "NOT FOUND"

        print(f"[{host}] Collected status: WAN1={result['wan_status']['WAN1']}, WAN2={result['wan_status']['WAN2']}")

    except Exception as e:
        print(f"[{host}] Error during automation: {e}")
        result["error"] = str(e)
    finally:
        driver.quit()

    return result
