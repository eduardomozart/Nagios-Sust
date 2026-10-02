from utils.network import ping_with_output
import socket
import os
from datetime import datetime

def handle(host, alert, options):
    """
    Generic handler that resolves the host IP, pings it 4 times,
    and generates a faux cmd.exe screenshot of the ping output using headless Chrome.
    """
    result = {
        "host": host,
        "wan_status": {},
        "latencies": [],
        "screenshot_path": None
    }
    
    print(f"[{host}] Executing generic ping handler...")
    
    # Try to resolve hostname to IP, otherwise use it directly
    try:
        ip_address = socket.gethostbyname(host)
    except socket.gaierror:
        ip_address = host
        
    latency, raw_output = ping_with_output(ip_address)
    
    if latency:
        try:
            latency_val = int(latency)
            result["latencies"].append(latency_val)
            print(f"[{host}] Ping successful ({latency}ms)")
        except ValueError:
            pass
    else:
        print(f"[{host}] Ping timeout or unreachable.")
        
    if options.get("capture_screenshot", True):
        # --- Generate Native Windows Screenshot ---
        # We spawn a real cmd.exe window, use Alt+PrintScreen to grab it natively,
        # and save the clipboard to a file using Pillow.
        import subprocess
        import time
        import ctypes
        import os
        from PIL import ImageGrab
        
        # Prepare screenshot directory
        exec_timestamp = options.get("execution_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
        handler_name = "generic_ping"
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
        
        # Launch CMD window and keep it open (ping takes ~3 seconds)
        cmd_str = f'cmd.exe /c "title Nagios-Ping-{host} & ping -n 4 {ip_address} & timeout /t 2"'
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
            result["screenshot_path"] = screenshot_path
            print(f"[{host}] Native screenshot saved at {screenshot_path}")
        else:
            print(f"[{host}] Failed to grab native screenshot from clipboard. Make sure your computer is unlocked.")
            
        # Terminate the CMD window if it didn't close itself
        subprocess.run(f"taskkill /PID {proc.pid} /F /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
    return result
