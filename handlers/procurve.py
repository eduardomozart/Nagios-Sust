import re
from utils.ssh import run_ssh_command, classify_ssh_error
from utils.error_codes import ERR_OK

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

def parse_aoss_fans(output, handler_name="procurve"):
    """
    Parses 'show system fans' output from a ProCurve / ArubaOS-S switch.
    Supports both standalone switches and VSF stack members.
    If 1 fan fails with redundant fans available, emits WARNING; >= 2 failures emits CRITICAL.
    """
    alerts = []
    if not output:
        return alerts

    current_member = None
    total_fans = 0
    failed_fans = []

    for line in output.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue

        m_mbr = re.search(r"VSF-Member\s+(\d+)", trimmed, re.IGNORECASE)
        if m_mbr:
            current_member = m_mbr.group(1)
            continue

        if "|" in trimmed and not trimmed.startswith("---") and not trimmed.startswith("==="):
            parts = [p.strip() for p in trimmed.split("|")]
            if len(parts) >= 3:
                num = parts[0]
                state = parts[1]
                failures = parts[2]
                if num.lower() in ("num", "fan") or "state" in state.lower():
                    continue

                total_fans += 1
                state_lower = state.lower()
                failures_int = int(failures) if failures.isdigit() else 0

                is_ok = state_lower in ("fan ok", "ok", "fine", "good") and failures_int == 0
                if not is_ok:
                    failed_fans.append((num, state, failures_int, current_member))

    if failed_fans:
        sev = "CRITICAL" if len(failed_fans) >= 2 or total_fans <= 1 else "WARNING"
        for num, state, failures_int, current_member in failed_fans:
            comp = f"Fan {num} (VSF Member {current_member})" if current_member else f"Fan {num}"
            alerts.append({
                "handler": handler_name,
                "severity": sev,
                "type": "fan",
                "component": comp,
                "message": f"{comp}: {state} ({failures_int} failures)",
            })

    return alerts


def parse_aoss_temperature(output, handler_name="procurve"):
    """
    Parses 'show system temperature' output from a ProCurve / ArubaOS-S switch.
    Supports VSF stack members and gracefully handles fanless switches (e.g. 2530/2930F)
    where no sensor rows are populated.
    """
    alerts = []
    if not output:
        return alerts

    current_member = None

    for line in output.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue

        m_mbr = re.search(r"VSF-Member\s+(\d+)", trimmed, re.IGNORECASE)
        if m_mbr:
            current_member = m_mbr.group(1)
            continue

        if any(h in trimmed.lower() for h in ("temp", "sensor", "current", "system air temperatures", "threshold", "overtemp", "avg")):
            if "chassis" not in trimmed.lower() and not re.search(r"\d+C\b", trimmed, re.IGNORECASE):
                continue
        if trimmed.startswith("---") or trimmed.startswith("==="):
            continue

        parts = trimmed.split()
        if len(parts) >= 6:
            sensor = parts[0]
            current_temp_str = parts[1]
            threshold_str = parts[4]
            over_temp_str = parts[5]

            m_curr = re.search(r"(\d+(?:\.\d+)?)", current_temp_str)
            if not m_curr:
                continue

            curr_val = float(m_curr.group(1))
            m_th = re.search(r"(\d+(?:\.\d+)?)", threshold_str)
            th_val = float(m_th.group(1)) if m_th else 55.0

            comp = f"Sensor {sensor} (VSF Member {current_member})" if current_member else f"Sensor {sensor}"

            is_over = over_temp_str.upper() == "YES" or curr_val >= th_val or curr_val >= 60.0
            is_warning = not is_over and curr_val >= 25.0

            if is_over:
                alerts.append({
                    "handler": handler_name,
                    "severity": "CRITICAL",
                    "type": "temperature",
                    "component": comp,
                    "message": f"{comp}: Over-temperature ({current_temp_str}, Threshold {threshold_str})",
                })
            elif is_warning:
                alerts.append({
                    "handler": handler_name,
                    "severity": "WARNING",
                    "type": "temperature",
                    "component": comp,
                    "message": f"{comp}: High temperature ({current_temp_str})",
                })

    return alerts


def parse_aoss_power_supply(output, handler_name="procurve"):
    """
    Parses 'show system power-supply' output from a ProCurve / ArubaOS-S switch.
    Treats 'Powered' and 'Not Present' as normal. If 1 PSU fails with redundant PSUs
    available, emits WARNING; >= 2 failures emits CRITICAL.
    """
    alerts = []
    if not output:
        return alerts

    total_psus = 0
    failed_psus = []

    for line in output.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("---") or trimmed.startswith("==="):
            continue

        if any(h in trimmed.lower() for h in ("power supply status", "model", "serial", "state", "ac/dc", "wattage", "delivering power", "total power")):
            continue

        m_bay = re.match(r"^(\d+)\s+(.*)", trimmed)
        if m_bay:
            ps_num = m_bay.group(1)
            rest = m_bay.group(2)

            m_state = re.search(r"\b(Powered|Not Present|Permanent Failure|Fault|Failed|Failure|Unpowered|Off|Error)\b", rest, re.IGNORECASE)
            if m_state:
                state_str = m_state.group(1)
                state_lower = state_str.lower()
                if state_lower != "not present":
                    total_psus += 1
                if state_lower not in ("powered", "not present"):
                    failed_psus.append((ps_num, state_str))

    if failed_psus:
        sev = "CRITICAL" if len(failed_psus) >= 2 or total_psus <= 1 else "WARNING"
        for ps_num, state_str in failed_psus:
            comp = f"Power Supply {ps_num}"
            alerts.append({
                "handler": handler_name,
                "severity": sev,
                "type": "power_supply",
                "component": comp,
                "message": f"{comp}: {state_str}",
            })

    return alerts


def parse_aoss_environment(output, handler_name="procurve"):
    """
    Aggregates granular ProCurve hardware status parsers for fans, temperature, and power supplies.
    """
    alerts = []
    alerts.extend(parse_aoss_fans(output, handler_name=handler_name))
    alerts.extend(parse_aoss_temperature(output, handler_name=handler_name))
    alerts.extend(parse_aoss_power_supply(output, handler_name=handler_name))
    return alerts


def handle(host, host_data, options, pre_collected_output=None):
    """
    Dedicated handler for ProCurve / ArubaOS-S switches.
    Can be invoked directly by main.py or delegated to by handlers.aruba.
    """
    result = {
        "host": host,
        "error": ERR_OK,
        "alerts": [],
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
                commands=[
                    "show system",
                    "show system fans",
                    "show system temperature",
                    "show system power-supply",
                ],
                port=port,
                timeout=timeout
            )

        system_info = parse_aoss_system(raw_output)
        result["system_info"] = system_info
        result["alerts"] = parse_aoss_environment(raw_output, handler_name="procurve")
        print(f"[{host}] Collected ProCurve System Info: Version='{system_info.get('version')}', Uptime='{system_info.get('uptime')}', CPU={system_info.get('cpu_util')}%, Mem={system_info.get('memory_usage')}%, Alerts={len(result['alerts'])}")
    except Exception as e:
        print(f"[{host}] ProCurve execution error: {e}")
        result["error"] = classify_ssh_error(e)
        result["alerts"].append({
            "handler": "procurve",
            "severity": "CRITICAL",
            "type": "ssh",
            "component": "SSH",
            "message": f"SSH connection failed: {e}",
        })

    return result
