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
