from utils.error_codes import ERR_OK, ERR_PING_TIMEOUT
import socket
import subprocess
import re
import platform
import os
from datetime import datetime

def ping_with_output(ip_address, count=4, timeout_ms=1000):
    """
    Pings an IP address and returns a tuple (latency_str, raw_output_str).
    """
    if not ip_address or ip_address == "0.0.0.0":
        return "", "Invalid IP address or host unreachable."
        
    try:
        count_str = str(max(1, int(count)))
        if platform.system().lower() == 'windows':
            cmd = ['ping', '-n', count_str, '-w', str(timeout_ms), ip_address]
        else:
            timeout_sec = str(max(1, int(timeout_ms // 1000)))
            cmd = ['ping', '-c', count_str, '-W', timeout_sec, ip_address]
        
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, universal_newlines=True)
        match = re.search(r'[=<]\s*([0-9]+(?:\.[0-9]+)?)\s*ms', output, re.IGNORECASE)
        latency = str(int(float(match.group(1)))) if match else ""
        return latency, output
                
    except subprocess.CalledProcessError as e:
        return "", getattr(e, "output", str(e))
    except Exception as e:
        return "", str(e)

def execute_generic_ping(host, alert="", options=None, handler_name="generic_ping", count=None):
    """
    Generic execution logic that resolves the host IP, pings it with configurable count,
    records latency, and generates a native screenshot if enabled.
    """
    if options is None:
        options = {}

    ping_count = count if count is not None else options.get("count", 4)
    try:
        ping_count = max(1, int(ping_count))
    except (ValueError, TypeError):
        ping_count = 4

    result = {
        "host": host,
        "latency": None,
        "error": ERR_PING_TIMEOUT,
    }
    
    print(f"[{host}] Executing ping for {handler_name} (count={ping_count})...")
    
    # Try to resolve hostname to IP, otherwise use it directly
    try:
        ip_address = socket.gethostbyname(host)
    except socket.gaierror:
        ip_address = host
        
    latency, raw_output = ping_with_output(ip_address, count=ping_count)
    
    if latency:
        try:
            latency_val = int(latency)
            result["latency"] = latency_val
            result["error"] = ERR_OK
            print(f"[{host}] Ping successful ({latency}ms)")
        except ValueError:
            pass
    else:
        print(f"[{host}] Ping timeout or unreachable.")
        
    if options.get("capture_screenshot", True):
        # --- Generate Native Windows Screenshot ---
        try:
            import subprocess
            import time
            import ctypes
            import os
            from PIL import ImageGrab
            
            # Prepare screenshot directory
            exec_timestamp = options.get("execution_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
            base_dir = options.get("base_dir", os.getcwd())
            screenshots_dir = os.path.join(base_dir, "screenshots", exec_timestamp, handler_name)
            os.makedirs(screenshots_dir, exist_ok=True)
            
            capture_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_filename = f"screenshot_{host}_{capture_timestamp}.png"
            screenshot_path = os.path.join(screenshots_dir, screenshot_filename)
            
            print(f"[{host}] Launching native CMD window for screenshot...")
            
            # Clear clipboard before taking new screenshot
            ctypes.windll.user32.OpenClipboard(0)
            ctypes.windll.user32.EmptyClipboard()
            ctypes.windll.user32.CloseClipboard()
            
            # Launch CMD window and keep it open
            cmd_str = f'cmd.exe /c "title Nagios-Ping-{host} & ping -n {ping_count} {ip_address} & timeout /t 2"'
            proc = subprocess.Popen(cmd_str, creationflags=subprocess.CREATE_NEW_CONSOLE)
            
            # Wait for the ping to run and finish visually in the window
            time.sleep(4.5)
            
            # Synthesize Alt + PrintScreen to capture the active window (the CMD we just spawned)
            VK_MENU = 0x12
            VK_SNAPSHOT = 0x2C
            KEYEVENTF_KEYUP = 0x0002
            
            ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_SNAPSHOT, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_SNAPSHOT, 0, KEYEVENTF_KEYUP, 0)
            ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            
            # Give Windows a moment to populate the clipboard
            time.sleep(1)
            
            # Grab image from clipboard
            img = ImageGrab.grabclipboard()
            if img is not None:
                img.save(screenshot_path)
                result["screenshot"] = {
                    "image": None,
                    "path": screenshot_path,
                    "filename": screenshot_filename,
                    "captured": True,
                }
                print(f"[{host}] Native screenshot saved at {screenshot_path}")
            else:
                print(f"[{host}] Failed to grab native screenshot from clipboard. Make sure your computer is unlocked.")
                
            # Terminate the CMD window if it didn't close itself
            subprocess.run(f"taskkill /PID {proc.pid} /F /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[{host}] Native screenshot generation skipped or not supported on this platform: {e}")
            
    return result

def handle(host, alert, options):
    """
    Generic handler that resolves the host IP, pings it 4 times,
    and generates a CMD screenshot of the ping output.
    """
    return execute_generic_ping(host, alert, options, handler_name="generic_ping")

