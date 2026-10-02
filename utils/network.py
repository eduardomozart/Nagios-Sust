import subprocess
import re
import platform

def ping_host(ip_address):
    """
    Pings an IP address and returns the latency in milliseconds as a string.
    Returns "" if unreachable or timeout.
    """
    if not ip_address or ip_address == "0.0.0.0":
        return ""
        
    try:
        # Use different flags depending on the OS
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        # Ping 1 time, wait max 1000ms
        cmd = ['ping', param, '1', '-w', '1000', ip_address] if platform.system().lower() == 'windows' else ['ping', param, '1', '-W', '1', ip_address]
        
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, universal_newlines=True)
        
        # Parse latency using a math-based regex that ignores translations (time, tempo, zeit, etc.)
        match = re.search(r'[=<]\s*([0-9]+(?:\.[0-9]+)?)\s*ms', output, re.IGNORECASE)
        if match:
            # Drop decimal part if any for cleaner reports, or keep as float
            return str(int(float(match.group(1))))
                
    except Exception:
        return ""
        
    return ""

def ping_with_output(ip_address):
    """
    Pings an IP address and returns a tuple (latency_str, raw_output_str).
    """
    if not ip_address or ip_address == "0.0.0.0":
        return "", "Invalid IP address or host unreachable."
        
    try:
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        cmd = ['ping', param, '4', ip_address] if platform.system().lower() == 'windows' else ['ping', param, '4', ip_address]
        
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, universal_newlines=True)
        
        match = re.search(r'[=<]\s*([0-9]+(?:\.[0-9]+)?)\s*ms', output, re.IGNORECASE)
        latency = str(int(float(match.group(1)))) if match else ""
        
        return latency, output
                
    except subprocess.CalledProcessError as e:
        return "", e.output
    except Exception as e:
        return "", str(e)

def ip_netmask_to_cidr(ip_netmask):
    """
    Splits an IP/Netmask string and converts decimal netmask to CIDR notation.
    Returns a tuple: (IP, CIDR Mask)
    """
    if not ip_netmask or '/' not in ip_netmask:
        return ip_netmask, ""
    try:
        ip, mask = ip_netmask.split('/')
        ip = ip.strip()
        mask = mask.strip()
        if '.' in mask:
            parts = [int(p) for p in mask.split('.')]
            bin_str = ''.join([bin(p).split('b')[1].zfill(8) for p in parts])
            cidr = str(bin_str.count('1'))
            return ip, cidr
        else:
            return ip, mask
    except:
        return ip_netmask, ""
