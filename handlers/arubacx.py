import re
from utils.ssh import run_ssh_command, classify_ssh_error
from utils.error_codes import ERR_OK

def parse_aoscx_system(output):
    """
    Parses 'show system' output from an ArubaOS-CX switch.
    """
    data = {}
    for line in output.splitlines():
        if ":" in line:
            parts = line.split(":", 1)
            data[parts[0].strip()] = parts[1].strip()
            
    hostname = data.get("Hostname", "")
    model = data.get("Product Name", "")
    version = data.get("AOS-CX Version", "")
    uptime = data.get("Up Time", "")
    cpu_raw = data.get("CPU Util (%)", "")
    mem_raw = data.get("Memory Usage (%)", "")
    serial = data.get("Chassis Serial Nbr", "")
    
    cpu_val = int(cpu_raw) if cpu_raw.isdigit() else cpu_raw
    mem_val = int(mem_raw) if mem_raw.isdigit() else mem_raw

    return {
        "hostname": hostname,
        "os_type": "AOS-CX",
        "model": model,
        "serial_number": serial,
        "version": version,
        "raw_version": version,
        "uptime": uptime,
        "cpu_util": cpu_val,
        "memory_usage": mem_val,
        "members": []
    }


def parse_aoscx_fans(output, handler_name="arubacx"):
    """
    Parses 'show environment fan' output from an ArubaOS-CX switch.
    Inspects both fan tray information and individual fan modules.
    If 1 fan fails with redundant fans available, emits WARNING; >= 2 failures emits CRITICAL.
    """
    alerts = []
    if not output:
        return alerts

    current_section = None
    total_fans = 0
    failed_fans = []

    for line in output.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("---") or trimmed.startswith("==="):
            continue

        lower = trimmed.lower()
        if "fan tray information" in lower:
            current_section = "tray"
            continue
        elif "fan information" in lower:
            current_section = "fan"
            continue

        parts = trimmed.split()
        if len(parts) < 2 or parts[0].lower() in ("mbr/tray", "mbr/tray/fan", "fan", "serial"):
            continue

        if current_section == "tray":
            tray_id = parts[0]
            for token in parts:
                tok_lower = token.lower()
                if tok_lower in ("ready", "ok"):
                    total_fans += 1
                    break
                elif tok_lower in ("fault", "failed", "critical", "error"):
                    total_fans += 1
                    failed_fans.append((f"Fan Tray {tray_id}", token))
                    break

        elif current_section == "fan":
            fan_id = parts[0]
            status_token = parts[-2] if len(parts) >= 3 and parts[-1].isdigit() else parts[-1]
            status_lower = status_token.lower()
            if status_lower in ("ok", "normal", "slow", "medium", "fast", "max"):
                total_fans += 1
            elif status_lower in ("fault", "failed", "critical", "error"):
                total_fans += 1
                failed_fans.append((f"Fan {fan_id}", status_token))

    if failed_fans:
        sev = "CRITICAL" if len(failed_fans) >= 2 or total_fans <= 1 else "WARNING"
        for comp, token in failed_fans:
            alerts.append({
                "handler": handler_name,
                "severity": sev,
                "type": "fan",
                "component": comp,
                "message": f"{comp}: {token}",
            })

    return alerts


def parse_aoscx_temperature(output, handler_name="arubacx"):
    """
    Parses 'show environment temperature' output from an ArubaOS-CX switch.
    """
    alerts = []
    if not output:
        return alerts

    for line in output.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("---") or trimmed.startswith("==="):
            continue

        if any(h in trimmed.lower() for h in ("temperature information", "module type", "current", "temperature", "status", "mbr/slot-sensor")):
            continue

        parts = trimmed.split()
        if len(parts) >= 3:
            sensor = parts[0]
            status_token = parts[-1]
            status_lower = status_token.lower()

            # Find temperature value (token preceding C or status)
            temp_str = ""
            for i, p in enumerate(parts):
                if p.upper() == "C" and i > 0:
                    temp_str = f"{parts[i-1]} C"
                    break

            if status_lower in ("emergency", "critical", "fault", "failed"):
                alerts.append({
                    "handler": handler_name,
                    "severity": "CRITICAL",
                    "type": "temperature",
                    "component": f"Sensor {sensor}",
                    "message": f"Temperature Sensor {sensor} ({temp_str}): {status_token}",
                })
            elif status_lower in ("warning", "alert"):
                alerts.append({
                    "handler": handler_name,
                    "severity": "WARNING",
                    "type": "temperature",
                    "component": f"Sensor {sensor}",
                    "message": f"Temperature Sensor {sensor} ({temp_str}): {status_token}",
                })

    return alerts


def parse_aoscx_power_supply(output, handler_name="arubacx"):
    """
    Parses 'show environment power-supply' output from an ArubaOS-CX switch.
    If 1 PSU fails with redundant PSUs available, emits WARNING; >= 2 failures emits CRITICAL.
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


def parse_aoscx_environment(output, handler_name="arubacx"):
    """
    Aggregates granular ArubaOS-CX hardware status parsers for fans, temperature, and power supplies.
    """
    alerts = []
    alerts.extend(parse_aoscx_fans(output, handler_name=handler_name))
    alerts.extend(parse_aoscx_temperature(output, handler_name=handler_name))
    alerts.extend(parse_aoscx_power_supply(output, handler_name=handler_name))
    return alerts


def handle(host, host_data, options, pre_collected_output=None):
    """
    Dedicated handler for ArubaOS-CX switches.
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

            print(f"[{host}] Connecting via SSH to AOS-CX switch...")
            raw_output = run_ssh_command(
                host=host,
                username=username,
                password=password,
                commands=[
                    "show system",
                    "show environment fan",
                    "show environment temperature",
                    "show environment power-supply",
                ],
                port=port,
                timeout=timeout
            )

        system_info = parse_aoscx_system(raw_output)
        result["system_info"] = system_info
        result["alerts"] = parse_aoscx_environment(raw_output, handler_name="arubacx")
        print(f"[{host}] Collected AOS-CX System Info: Model='{system_info.get('model')}', Version='{system_info.get('version')}', Uptime='{system_info.get('uptime')}', CPU={system_info.get('cpu_util')}%, Mem={system_info.get('memory_usage')}%, Alerts={len(result['alerts'])}")
    except Exception as e:
        print(f"[{host}] AOS-CX execution error: {e}")
        result["error"] = classify_ssh_error(e)
        result["alerts"].append({
            "handler": "arubacx",
            "severity": "CRITICAL",
            "type": "ssh",
            "component": "SSH",
            "message": f"SSH connection failed: {e}",
        })

    return result
