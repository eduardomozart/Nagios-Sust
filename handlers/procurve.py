import re
from utils.ssh import run_ssh_command, classify_ssh_error

def parse_aoss_system(output):
    """
    Parses 'show system' output from an ArubaOS-S / ProCurve switch.
    Supports both standalone switches and VSF stacks.
    Converts memory usage to percentage based on Total and Free bytes.
    """
    sys_name = re.search(r'System Name\s*:\s*(.+)', output)
    sw_rev = re.search(r'Software revision\s*:\s*(.+)', output)
    
    hostname = sys_name.group(1).strip() if sys_name else ""
    version = sw_rev.group(1).strip() if sw_rev else ""

    # Check for VSF stack members
    vsf_blocks = re.split(r'VSF-Member\s*:\s*(\d+)', output)
    members = []

    if len(vsf_blocks) > 1:
        # vsf_blocks: [general_text, member1_id, member1_text, member2_id, member2_text, ...]
        for i in range(1, len(vsf_blocks), 2):
            m_id = int(vsf_blocks[i])
            m_text = vsf_blocks[i + 1]

            uptime = re.search(r'Up Time\s*:\s*(.+)', m_text)
            cpu = re.search(r'CPU Util \(%\)\s*:\s*(\d+)', m_text)
            serial = re.search(r'Serial Number\s*:\s*(.+)', m_text)
            rom = re.search(r'ROM Version\s*:\s*(.+)', m_text)

            mem_tot = re.search(r'Memory\s*-\s*Total\s*:\s*([\d,]+)', m_text)
            mem_free = re.search(r'Free\s*:\s*([\d,]+)', m_text)

            mem_pct = None
            tot_val = None
            free_val = None
            if mem_tot and mem_free:
                tot_val = int(mem_tot.group(1).replace(',', ''))
                free_val = int(mem_free.group(1).replace(',', ''))
                if tot_val > 0:
                    used = tot_val - free_val
                    mem_pct = round((used / tot_val) * 100, 1)

            cpu_val = int(cpu.group(1).strip()) if cpu and cpu.group(1).strip().isdigit() else (cpu.group(1).strip() if cpu else "")

            members.append({
                "member_id": m_id,
                "uptime": uptime.group(1).strip() if uptime else "",
                "cpu_util": cpu_val,
                "serial_number": serial.group(1).strip() if serial else "",
                "rom_version": rom.group(1).strip() if rom else "",
                "memory_total": tot_val,
                "memory_free": free_val,
                "memory_usage_pct": mem_pct
            })
    else:
        # Standalone switch
        uptime = re.search(r'Up Time\s*:\s*(.+)', output)
        cpu = re.search(r'CPU Util \(%\)\s*:\s*(\d+)', output)
        serial = re.search(r'Serial Number\s*:\s*(.+)', output)
        rom = re.search(r'ROM Version\s*:\s*(.+)', output)

        mem_tot = re.search(r'Memory\s*-\s*Total\s*:\s*([\d,]+)', output)
        mem_free = re.search(r'Free\s*:\s*([\d,]+)', output)

        mem_pct = None
        tot_val = None
        free_val = None
        if mem_tot and mem_free:
            tot_val = int(mem_tot.group(1).replace(',', ''))
            free_val = int(mem_free.group(1).replace(',', ''))
            if tot_val > 0:
                used = tot_val - free_val
                mem_pct = round((used / tot_val) * 100, 1)

        cpu_val = int(cpu.group(1).strip()) if cpu and cpu.group(1).strip().isdigit() else (cpu.group(1).strip() if cpu else "")

        members.append({
            "member_id": 1,
            "uptime": uptime.group(1).strip() if uptime else "",
            "cpu_util": cpu_val,
            "serial_number": serial.group(1).strip() if serial else "",
            "rom_version": rom.group(1).strip() if rom else "",
            "memory_total": tot_val,
            "memory_free": free_val,
            "memory_usage_pct": mem_pct
        })

    primary = members[0] if members else {}

    return {
        "hostname": hostname,
        "os_type": "AOS-S",
        "model": "ProCurve Switch",
        "serial_number": primary.get("serial_number", ""),
        "version": version,
        "raw_version": version,
        "uptime": primary.get("uptime", ""),
        "cpu_util": primary.get("cpu_util", ""),
        "memory_usage": primary.get("memory_usage_pct", ""),
        "memory_total": primary.get("memory_total"),
        "memory_free": primary.get("memory_free"),
        "members": members
    }

from utils.error_codes import ERR_OK

def handle(host, alert, options, pre_collected_output=None):
    """
    Dedicated handler for ProCurve / ArubaOS-S switches.
    Can be invoked directly by main.py or delegated to by handlers.aruba.
    """
    result = {
        "host": host,
        "error": ERR_OK,
    }

    try:
        if pre_collected_output:
            raw_output = pre_collected_output
        else:
            username = options.get("username")
            password = options.get("password")

            if not username or not password:
                if "credential_provider" in options:
                    prov_user, prov_pass = options["credential_provider"]()
                    username = username or prov_user
                    password = password or prov_pass
                else:
                    raise ValueError("Credentials are required but not provided in options.")

            port = options.get("port", 22)
            timeout = options.get("timeout", 15)

            print(f"[{host}] Connecting via SSH to ProCurve switch...")
            raw_output = run_ssh_command(
                host=host,
                username=username,
                password=password,
                commands=["show system"],
                port=port,
                timeout=timeout
            )

        system_info = parse_aoss_system(raw_output)
        result["system_info"] = system_info
        print(f"[{host}] Collected ProCurve System Info: Version='{system_info.get('version')}', Uptime='{system_info.get('uptime')}', CPU={system_info.get('cpu_util')}%, Mem={system_info.get('memory_usage')}%")
    except Exception as e:
        print(f"[{host}] ProCurve execution error: {e}")
        result["error"] = classify_ssh_error(e)

    return result
