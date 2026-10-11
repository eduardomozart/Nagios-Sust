import re
import xml.etree.ElementTree as ET

try:
    from pyairwave.awapi import ArubaAirwave
except ImportError:
    ArubaAirwave = None


def filter_device_name(name, host_filter):
    """
    Evaluates whether a device name matches host_filter conditions.
    Supports startswith (str or list of str) and regex (str or list of str).
    """
    if not host_filter:
        return True

    if not name:
        return False

    # 1. startswith filter
    if "startswith" in host_filter:
        prefix = host_filter["startswith"]
        if isinstance(prefix, (list, tuple)):
            if not any(name.startswith(str(p)) for p in prefix):
                return False
        else:
            if not name.startswith(str(prefix)):
                return False

    # 2. regex filter
    if "regex" in host_filter:
        pattern = host_filter["regex"]
        if isinstance(pattern, (list, tuple)):
            if not any(re.search(str(p), name) for p in pattern):
                return False
        else:
            if not re.search(str(pattern), name):
                return False

    return True


def parse_devices_xml(xml_data, host_filter=None, device_categories=None, models=None):
    """
    Parses ap_list.xml / ap_detail.xml to extract devices (APs/Switches/Controllers).
    Applies host_filter (startswith/regex), device_categories, and models filtering.
    Returns list of dicts: [{'id': ..., 'name': ..., 'ip': ..., 'folder_id': ..., 'model': ..., 'serial_number': ...}]
    """
    if not xml_data:
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        print(f"Error parsing AirWave AP XML: {e}")
        return []

    devices = []
    for ap_el in root.iter("ap"):
        dev_id = ap_el.get("id") or ap_el.findtext("id") or ""
        name = ap_el.findtext("name") or ""
        
        # Skip placeholder / invalid device entries
        if not name or name.strip().startswith("(id:"):
            continue

        name = name.strip()

        # Check host name filters (startswith / regex)
        if not filter_device_name(name, host_filter):
            continue

        ip = (
            ap_el.findtext("lan_ip")
            or ap_el.findtext("ip")
            or ap_el.findtext("remote_lan_ip")
            or ""
        ).strip()

        folder_id = None
        folder_el = ap_el.find("folder")
        if folder_el is not None:
            folder_id = folder_el.get("id")

        device_category = (ap_el.findtext("device_category") or "").strip()
        model = (ap_el.findtext("model") or "").strip()

        # Category and model filtering
        if device_categories or models:
            is_match = False
            if device_categories and device_category:
                for cat in device_categories:
                    if cat.strip().lower() in device_category.lower():
                        is_match = True
                        break

            if not is_match and models and model:
                for m in models:
                    if m.strip().lower() in model.lower():
                        is_match = True
                        break

            if not is_match:
                continue

        serial_number = (ap_el.findtext("serial_number") or "").strip()

        devices.append({
            "id": dev_id,
            "name": name,
            "ip": ip,
            "folder_id": folder_id,
            "device_category": device_category,
            "model": model,
            "serial_number": serial_number,
        })

    return devices


def parse_airwave_device_info_html(html_content, device_name=""):
    """
    Parses AirWave Device Info table HTML (fragment_div_AP__Monitoring__InfoTable / infoTableWrapper)
    into a standardized system_info dictionary.
    """
    system_info = {
        "hostname": device_name,
        "os_type": "AirWave",
        "model": "",
        "device_model": "",
        "serial_number": "",
        "version": "",
        "raw_version": "",
        "uptime": "",
        "cpu_util": "",
        "memory_usage": "",
        "mac_address": "",
        "ip": "",
        "status": "",
        "switch_role": "",
        "switch_state": "",
        "stack_topology": "",
        "stack_status": "",
        "temperature": "",
        "clients": "",
        "usage": "",
        "configuration": "",
        "members": [],
    }

    if not html_content:
        return system_info

    # Clean script tags and comments
    cleaned_html = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", html_content, flags=re.IGNORECASE)

    # 1. Look for row items: <td ... class="fieldName">Field:</td><td ...>Value</td> or <span>Field:</span> Value
    # Pairings with <td>
    pairs = re.findall(
        r'<td[^>]*?(?:class=[\'"][^\'"]*fieldName[^\'"]*[\'"][^>]*)?>\s*(?:<span[^>]*class=[\'"]fieldName[\'"][^>]*>)?([^<:]+):?\s*(?:</span>)?\s*</td>\s*<td[^>]*>(.*?)</td>',
        cleaned_html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    extracted_fields = {}
    for k_raw, v_raw in pairs:
        key = re.sub(r"<[^>]+>", "", k_raw).strip().lower()
        val = re.sub(r"<[^>]+>", "", v_raw).strip()
        val = re.sub(r"\s+", " ", val).strip()
        if key and val and key not in extracted_fields:
            extracted_fields[key] = val

    # Also capture <span>Field:</span> Value patterns inside <td>
    span_pairs = re.findall(
        r'<span[^>]*class=[\'"]fieldName[\'"][^>]*>([^<:]+):?\s*</span>\s*([^<\n\r]+)',
        cleaned_html,
        flags=re.IGNORECASE,
    )
    for k_raw, v_raw in span_pairs:
        key = k_raw.strip().lower()
        val = v_raw.strip()
        if key and val and key not in extracted_fields:
            extracted_fields[key] = val

    # Also handle <td colspan="1" nowrap="1">Firmware:</td><td>...</td>
    fw_match = re.search(r'Firmware:\s*</td>\s*<td[^>]*>(.*?)</td>', cleaned_html, flags=re.DOTALL | re.IGNORECASE)
    if fw_match and "firmware" not in extracted_fields:
        fw_val = re.sub(r"<[^>]+>", "", fw_match.group(1)).strip()
        extracted_fields["firmware"] = re.sub(r"\s+", " ", fw_val)

    # Map extracted values to standard system_info fields
    if "status" in extracted_fields:
        system_info["status"] = extracted_fields["status"]

    if "firmware" in extracted_fields:
        raw_fw = extracted_fields["firmware"]
        system_info["raw_version"] = raw_fw
        # Extract main version e.g. FL.10.13.1050 from 'FL.10.13.1050 (ROM: FL.01.14.0002)'
        v_match = re.search(r'([A-Za-z0-9_\-\.]+)', raw_fw)
        system_info["version"] = v_match.group(1) if v_match else raw_fw

    if "model" in extracted_fields:
        system_info["model"] = extracted_fields["model"]

    if "type" in extracted_fields:
        if not system_info["model"]:
            system_info["model"] = extracted_fields["type"]
        system_info["device_type"] = extracted_fields["type"]

    if "device model" in extracted_fields:
        system_info["device_model"] = extracted_fields["device model"]

    if "serial" in extracted_fields:
        system_info["serial_number"] = extracted_fields["serial"]
    elif "serial number" in extracted_fields:
        system_info["serial_number"] = extracted_fields["serial number"]

    if "uptime" in extracted_fields:
        system_info["uptime"] = extracted_fields["uptime"]

    if "lan mac address" in extracted_fields:
        system_info["mac_address"] = extracted_fields["lan mac address"]
    elif "mac address" in extracted_fields:
        system_info["mac_address"] = extracted_fields["mac address"]

    if "ip address" in extracted_fields:
        # Extract plain IP address
        ip_m = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})', extracted_fields["ip address"])
        system_info["ip"] = ip_m.group(1) if ip_m else extracted_fields["ip address"]

    if "switch role" in extracted_fields:
        system_info["switch_role"] = extracted_fields["switch role"]

    if "switch state" in extracted_fields:
        system_info["switch_state"] = extracted_fields["switch state"]

    if "stack topology" in extracted_fields:
        system_info["stack_topology"] = extracted_fields["stack topology"]

    if "stack operational status" in extracted_fields:
        system_info["stack_status"] = extracted_fields["stack operational status"]

    if "temperature" in extracted_fields:
        system_info["temperature"] = extracted_fields["temperature"]

    if "clients" in extracted_fields:
        system_info["clients"] = extracted_fields["clients"]

    if "usage" in extracted_fields:
        system_info["usage"] = extracted_fields["usage"]

    if "configuration" in extracted_fields:
        system_info["configuration"] = extracted_fields["configuration"]

    # Refine OS Type based on firmware or model
    fw_str = system_info.get("version", "")
    dev_model = system_info.get("model", "")
    if any(fw_str.startswith(p) for p in ["FL.", "GL.", "ML.", "PL.", "TL.", "LL.", "NL."]) or "AOS-CX" in dev_model:
        system_info["os_type"] = "AOS-CX"
    elif any(fw_str.startswith(p) for p in ["WC.", "WB.", "KB.", "YA.", "YB.", "RA."]) or "ProCurve" in dev_model:
        system_info["os_type"] = "AOS-S"

    return system_info


class AirWaveClient:
    """
    Wrapper around pyairwave to enumerate devices and folders from Aruba AirWave API.
    """

    def __init__(self, host, username, password):
        if ArubaAirwave is None:
            raise ImportError(
                "The 'pyairwave' library is required for AirWave API operations.\n"
                "Please install it using:\n"
                "pip install git+https://github.com/eduardomozart/pyairwave.git"
            )

        # Normalize host string
        clean_host = re.sub(r"^https?://", "", str(host)).rstrip("/")

        self.host = clean_host
        self.username = username
        self.password = password
        self.aw_info = {
            "ip": self.host,
            "username": self.username,
            "password": self.password,
        }
        self._aw = None
        self._cached_devices = None

    def _get_aw(self):
        if self._aw is None:
            self._aw = ArubaAirwave(self.aw_info, ssl_verify=False)
        return self._aw

    def get_devices(self, host_filter=None, device_categories=None, models=None, force_refresh=False):
        """
        Fetches all devices from /ap_list.xml and filters them based on host_filter,
        device_categories, and models.
        """
        if self._cached_devices is None or force_refresh:
            aw = self._get_aw()
            xml_data = aw.command(apiPath="/ap_list.xml")
            # Parse without host filters initially to store full cache
            self._cached_devices = parse_devices_xml(xml_data)

        # Apply filters to cached list
        filtered = []
        for dev in self._cached_devices:
            if not filter_device_name(dev["name"], host_filter):
                continue

            if device_categories or models:
                is_match = False
                dev_cat = dev.get("device_category", "")
                dev_mod = dev.get("model", "")
                if device_categories and dev_cat:
                    for c in device_categories:
                        if c.strip().lower() in dev_cat.lower():
                            is_match = True
                            break
                if not is_match and models and dev_mod:
                    for m in models:
                        if m.strip().lower() in dev_mod.lower():
                            is_match = True
                            break
                if not is_match:
                    continue

            filtered.append(dev)

        return filtered

    def get_device_by_host(self, host):
        """
        Resolves a host name or IP address to its AirWave device dictionary.
        """
        if not host:
            return None

        devices = self.get_devices()
        host_lower = host.strip().lower()

        # 1. Exact match by name
        for dev in devices:
            if dev["name"].lower() == host_lower:
                return dev

        # 2. Match by IP address
        for dev in devices:
            if dev.get("ip") and dev["ip"] == host.strip():
                return dev

        # 3. Match without domain suffix if host contains dots
        short_host = host_lower.split(".")[0]
        for dev in devices:
            dev_short = dev["name"].lower().split(".")[0]
            if dev_short == short_host:
                return dev

        return None
