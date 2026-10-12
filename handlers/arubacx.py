import re
from utils.ssh import run_ssh_command, classify_ssh_error

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

from utils.error_codes import ERR_OK

def handle(host, alert, options, pre_collected_output=None):
    """
    Dedicated handler for ArubaOS-CX switches.
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

            print(f"[{host}] Connecting via SSH to AOS-CX switch...")
            raw_output = run_ssh_command(
                host=host,
                username=username,
                password=password,
                commands=["show system"],
                port=port,
                timeout=timeout
            )

        system_info = parse_aoscx_system(raw_output)
        result["system_info"] = system_info
        print(f"[{host}] Collected AOS-CX System Info: Model='{system_info.get('model')}', Version='{system_info.get('version')}', Uptime='{system_info.get('uptime')}', CPU={system_info.get('cpu_util')}%, Mem={system_info.get('memory_usage')}%")
    except Exception as e:
        print(f"[{host}] AOS-CX execution error: {e}")
        result["error"] = classify_ssh_error(e)

    return result
