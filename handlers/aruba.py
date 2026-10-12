from utils.ssh import run_ssh_command, classify_ssh_error
from utils.error_codes import ERR_AUTOMATION_FAILED
import handlers.arubacx as arubacx_handler
import handlers.procurve as procurve_handler

def detect_equipment_type(output):
    """
    Detects whether an Aruba network device is AOS-CX, ProCurve, etc.
    Extensible for ClearPass, Aruba Mobility Controllers, Instant APs in the future.
    """
    if "AOS-CX" in output or "AOS-CX Version" in output:
        return "arubacx"
    elif "Software revision" in output or "Status and Counters" in output or "VSF-Member" in output or "ProCurve" in output:
        return "procurve"
    # Future expansion:
    # elif "ClearPass" in output:
    #     return "clearpass"
    # elif "ArubaOS (MODEL" in output or "Mobility Controller" in output:
    #     return "controller"
    return "unknown"

def handle(host, host_data, options, pre_collected_output=None):
    """
    Generic Aruba dispatcher handler.
    Connects via SSH, runs initial identification ('show system'), detects the
    device type (AOS-CX vs ProCurve / AOS-S), and delegates execution to the
    corresponding specialized handler.
    """
    if pre_collected_output is not None:
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

        print(f"[{host}] Connecting via SSH to probe Aruba equipment type...")
        try:
            raw_output = run_ssh_command(
                host=host,
                username=username,
                password=password,
                commands=["show system"],
                port=port,
                timeout=timeout
            )
        except Exception as e:
            print(f"[{host}] Aruba dispatcher execution error: {e}")
            return {
                "host": host,
                "error": classify_ssh_error(e),
                "alerts": [{
                    "handler": "aruba",
                    "severity": "CRITICAL",
                    "type": "ssh",
                    "component": "SSH",
                    "message": f"SSH connection failed: {e}",
                }],
            }

    try:
        detected_type = detect_equipment_type(raw_output)
        print(f"[{host}] Detected Aruba device family: '{detected_type}'")

        if detected_type == "arubacx":
            if pre_collected_output is None:
                try:
                    diag_output = run_ssh_command(
                        host=host,
                        username=username,
                        password=password,
                        commands=[
                            "show environment fan",
                            "show environment temperature",
                            "show environment power-supply",
                        ],
                        port=port,
                        timeout=timeout
                    )
                    raw_output = f"{raw_output}\n{diag_output}"
                except Exception as diag_err:
                    print(f"[{host}] ArubaOS-CX diagnostic command collection warning: {diag_err}")
            return arubacx_handler.handle(host, host_data, options, pre_collected_output=raw_output)
        elif detected_type == "procurve":
            if pre_collected_output is None:
                try:
                    diag_output = run_ssh_command(
                        host=host,
                        username=username,
                        password=password,
                        commands=[
                            "show system fans",
                            "show system temperature",
                            "show system power-supply",
                        ],
                        port=port,
                        timeout=timeout
                    )
                    raw_output = f"{raw_output}\n{diag_output}"
                except Exception as diag_err:
                    print(f"[{host}] ProCurve diagnostic command collection warning: {diag_err}")
            return procurve_handler.handle(host, host_data, options, pre_collected_output=raw_output)
        else:
            print(f"[{host}] Unrecognized Aruba device type. Aborting execution.")
            return {
                "host": host,
                "error": ERR_AUTOMATION_FAILED,
                "alerts": [{
                    "handler": "aruba",
                    "severity": "CRITICAL",
                    "type": "device",
                    "component": "Identification",
                    "message": "Unrecognized Aruba device type",
                }],
            }

    except Exception as e:
        print(f"[{host}] Aruba dispatcher execution error: {e}")
        return {
            "host": host,
            "error": classify_ssh_error(e),
            "alerts": [{
                "handler": "aruba",
                "severity": "CRITICAL",
                "type": "execution",
                "component": "Dispatcher",
                "message": f"Aruba dispatcher execution error: {e}",
            }],
        }
