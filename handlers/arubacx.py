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


def parse_aoscx_environment(output, handler_name="arubacx"):
    """
    Parses 'show environment' output from an ArubaOS-CX switch and returns
    a list of structured alerts for abnormal fans, temperature, and power supplies.
    """
    alerts = []
    if not output:
        return alerts

    current_section = None

    for line in output.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("---") or trimmed.startswith("==="):
            continue

        lower_line = trimmed.lower()
        if "sensor" in lower_line and "temperature" in lower_line:
            current_section = "temperature"
            continue
        elif "fan" in lower_line and ("speed" in lower_line or "airflow" in lower_line or "rpm" in lower_line):
            current_section = "fan"
            continue
        elif "psu" in lower_line and ("watts" in lower_line or "model" in lower_line or "status" in lower_line):
            current_section = "power_supply"
            continue

        parts = trimmed.split()
        if len(parts) < 2:
            continue

        # Ignore repeated table headers
        if parts[0].lower() in ("sensor", "fan", "psu", "module", "location"):
            continue

        if current_section == "temperature":
            status = parts[-1].strip()
            status_lower = status.lower()
            if status_lower not in ("normal", "ok", "fine", "good"):
                sev = "CRITICAL" if status_lower in ("critical", "failed", "fault", "error") else "WARNING"
                sensor_id = parts[0]
                temp_val = parts[-2] if len(parts) >= 3 else ""
                temp_str = f" ({temp_val})" if temp_val and (temp_val.replace(".", "", 1).isdigit() or "c" in temp_val.lower()) else ""
                alerts.append({
                    "handler": handler_name,
                    "severity": sev,
                    "type": "temperature",
                    "component": f"Sensor {sensor_id}",
                    "message": f"Temperature sensor {sensor_id}{temp_str}: {status}",
                    "status": status,
                })

        elif current_section == "fan":
            status = parts[-1].strip()
            status_lower = status.lower()
            if status_lower not in ("normal", "ok", "fine", "good"):
                sev = "CRITICAL" if status_lower in ("failed", "fault", "critical", "error") else "WARNING"
                fan_id = parts[0]
                alerts.append({
                    "handler": handler_name,
                    "severity": sev,
                    "type": "fan",
                    "component": f"Fan {fan_id}",
                    "message": f"Fan {fan_id}: {status}",
                    "status": status,
                })

        elif current_section == "power_supply":
            status = parts[-1].strip()
            status_lower = status.lower()
            if status_lower not in ("normal", "ok", "fine", "good", "not_present", "absent"):
                sev = "CRITICAL" if status_lower in ("fault", "failed", "critical", "error") else "WARNING"
                psu_id = parts[0]
                alerts.append({
                    "handler": handler_name,
                    "severity": sev,
                    "type": "power_supply",
                    "component": f"PSU {psu_id}",
                    "message": f"Power supply {psu_id}: {status}",
                    "status": status,
                })

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
                commands=["show system", "show environment"],
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
            "status": "Failed",
        })

    return result
