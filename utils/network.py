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
        
        # Parse latency
        if platform.system().lower() == 'windows':
            # Match "time=15ms", "time<1ms", "tempo=15ms" or "tempo<1ms"
            match = re.search(r'(?:time|tempo)[=<]([0-9]+)ms', output, re.IGNORECASE)
            if match:
                return match.group(1)
        else:
            # Match "time=15.1 ms"
            match = re.search(r'time=([0-9\.]+) ms', output, re.IGNORECASE)
            if match:
                return match.group(1)
                
    except Exception:
        return ""
        
    return ""

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
