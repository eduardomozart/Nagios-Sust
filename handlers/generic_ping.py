from utils.network import ping_host
import socket

def handle(host, alert, options):
    """
    Generic handler that simply resolves the host IP and pings it.
    Does not take screenshots or interact with web UIs.
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
        
    latency = ping_host(ip_address)
    
    if latency:
        try:
            latency_val = int(latency)
            result["latencies"].append(latency_val)
            print(f"[{host}] Ping successful ({latency}ms)")
        except ValueError:
            pass
    else:
        print(f"[{host}] Ping timeout or unreachable.")
        
    return result
