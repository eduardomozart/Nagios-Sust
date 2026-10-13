import re
import xml.etree.ElementTree as ET

try:
    from pyairwave.awapi import ArubaAirwave
except ImportError:
    ArubaAirwave = None


def filter_device_name(name, host_filter):
    """
    Evaluates whether a device name matches host_filter conditions.
    Supports startswith (str) and regex (str). For multiple conditions, use regex (e.g. "^(SW|AP)").
    """
    if not host_filter:
        return True

    if not name:
        return False

    # 1. startswith filter
    if "startswith" in host_filter:
        prefix = str(host_filter["startswith"])
        if not name.startswith(prefix):
            return False

    # 2. regex filter
    if "regex" in host_filter:
        pattern = str(host_filter["regex"])
        if not re.search(pattern, name):
            return False

    return True


def normalize_folders_filter(folders_input):
    """
    Normalizes folder filter input into a flat list of non-empty strings.
    Handles strings, lists of strings, and comma-separated values.
    """
    if not folders_input:
        return []
    if isinstance(folders_input, str):
        folders_input = [folders_input]
    normalized = []
    for item in folders_input:
        if isinstance(item, str):
            for part in item.split(","):
                clean = part.strip().strip("\"'")
                if clean and clean not in normalized:
                    normalized.append(clean)
        elif item:
            clean = str(item).strip().strip("\"'")
            if clean and clean not in normalized:
                normalized.append(clean)
    return normalized


def parse_folders_xml(xml_data):
    """
    Parses folder_list.xml to extract folders and build parent-child hierarchy.
    Returns a dict: {folder_id: {'id': folder_id, 'name': folder_name, 'parent_id': parent_id, 'subfolders': []}}
    """
    if not xml_data:
        return {}

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        print(f"Error parsing AirWave folder list XML: {e}")
        return {}

    folders = {}
    for folder_el in root.iter():
        tag = folder_el.tag.split("}")[-1]
        if tag != "folder":
            continue

        fid = folder_el.get("id")
        if not fid:
            for child in folder_el:
                if child.tag.split("}")[-1] == "id":
                    fid = child.text
                    break

        if not fid:
            continue

        fid = str(fid).strip()

        name = ""
        parent_id = None
        for child in folder_el:
            ctag = child.tag.split("}")[-1]
            if ctag == "name":
                name = (child.text or "").strip()
            elif ctag == "parent_id":
                p_text = (child.text or "").strip()
                parent_id = p_text if p_text and p_text != "0" else None

        folders[fid] = {
            "id": fid,
            "name": name or f"Folder {fid}",
            "parent_id": parent_id,
            "subfolders": [],
        }

    # Build subfolder hierarchy
    for fid, fdata in folders.items():
        pid = fdata.get("parent_id")
        if pid and pid in folders and pid != fid:
            if fid not in folders[pid]["subfolders"]:
                folders[pid]["subfolders"].append(fid)

    return folders


def get_folder_path(folder_id, folders_dict):
    """
    Returns the hierarchy path string (e.g. 'Top:Campus A:Building 1')
    for a given folder_id using folders_dict.
    """
    if not folder_id or not folders_dict or folder_id not in folders_dict:
        return ""

    path_names = []
    curr = folder_id
    visited = set()
    while curr and curr in folders_dict and curr not in visited:
        visited.add(curr)
        path_names.append(folders_dict[curr]["name"])
        curr = folders_dict[curr].get("parent_id")

    path_names.reverse()
    return ":".join(path_names)


def get_folder_descendant_ids(target_folders, folders_dict):
    """
    Resolves target folder names, subfolder paths with ':' (e.g. 'Campus A:Building 1'),
    or folder IDs to a set of folder IDs, including all descendant subfolders recursively (case-insensitive).
    """
    if not target_folders or not folders_dict:
        return set()

    if isinstance(target_folders, str):
        target_folders = [target_folders]

    # Precompute folder paths for all folders
    folder_paths = {fid: get_folder_path(fid, folders_dict).lower() for fid in folders_dict}

    matched_root_ids = set()
    for raw_target in target_folders:
        t = str(raw_target).strip().lower()
        if not t:
            continue

        # Check if target is a subfolder path with separator (':')
        if ":" in t:
            norm_target = re.sub(r"\s*:\s*", ":", t)
            for fid, path_str in folder_paths.items():
                if path_str == norm_target or path_str.endswith(f":{norm_target}"):
                    matched_root_ids.add(fid)
        else:
            # Match directly by folder name or folder ID
            for fid, fdata in folders_dict.items():
                name_lower = fdata.get("name", "").strip().lower()
                fid_lower = str(fid).strip().lower()
                if t == name_lower or t == fid_lower:
                    matched_root_ids.add(fid)

    # Recursively gather descendants
    all_ids = set()
    queue = list(matched_root_ids)
    while queue:
        curr_id = queue.pop(0)
        if curr_id in all_ids:
            continue
        all_ids.add(curr_id)
        if curr_id in folders_dict:
            for sub_id in folders_dict[curr_id].get("subfolders", []):
                if sub_id not in all_ids:
                    queue.append(sub_id)

    return all_ids


def parse_devices_xml(xml_data, host_filter=None, device_categories=None, models=None):
    """
    Parses ap_list.xml / ap_detail.xml to extract devices (APs/Switches/Controllers).
    Applies host_filter (startswith/regex), device_categories, and models filtering.
    Returns list of dicts: [{'id': ..., 'name': ..., 'ip': ..., 'folder_id': ..., 'folder': ..., 'model': ..., 'serial_number': ...}]
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
        folder_name = ""
        folder_el = ap_el.find("folder")
        if folder_el is not None:
            folder_id = folder_el.get("id")
            folder_name = (folder_el.text or "").strip()

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
            "folder": folder_name,
            "folder_path": folder_name,
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


def parse_airwave_login_html(html_content):
    """
    Parses AirWave WebUI login page HTML to inspect session and authentication status.
    Returns dict:
      - is_logged_in: True if login dialog is absent or hidden (session active)
      - has_login_dialog: True if login username input field is visible
      - login_failed: True if failure message is visible and populated
      - error_message: text of login failure error
    """
    if not html_content:
        return {"is_logged_in": True, "has_login_dialog": False, "login_failed": False, "error_message": ""}

    user_match = re.search(r'<input[^>]*id=[\'"]login-username-id[\'"][^>]*>', html_content, re.IGNORECASE)
    has_user_input = bool(user_match)
    user_hidden = False
    if user_match:
        tag_str = user_match.group(0)
        if "display: none" in tag_str or "display:none" in tag_str or 'type="hidden"' in tag_str:
            user_hidden = True

    has_dialog = has_user_input and not user_hidden

    err_match = re.search(r'<div[^>]*id=[\'"]login-failed[\'"][^>]*>(.*?)</div>', html_content, re.DOTALL | re.IGNORECASE)
    err_text = ""
    err_visible = False
    if err_match:
        tag_full = err_match.group(0)
        open_tag = tag_full[:tag_full.find(">") + 1]
        is_hidden = "display: none" in open_tag or "display:none" in open_tag
        raw_text = re.sub(r'<[^>]+>', '', err_match.group(1)).strip()
        if raw_text and not is_hidden:
            err_text = raw_text
            err_visible = True

    return {
        "is_logged_in": not has_dialog and not err_visible,
        "has_login_dialog": has_dialog,
        "login_failed": err_visible,
        "error_message": err_text,
    }


class AirWaveClient:
    """
    Wrapper around pyairwave to enumerate devices and folders from Aruba AirWave API.
    """
    _aw = None
    _cached_devices = None
    _cached_folders = None

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
        self._cached_folders = None

    def _get_aw(self):
        if self._aw is None:
            self._aw = ArubaAirwave(self.aw_info, ssl_verify=False)
        return self._aw

    def get_folders(self, force_refresh=False):
        """
        Fetches and parses folder_list.xml from AirWave API.
        Returns dict of folders: {id: {'id': id, 'name': name, 'parent_id': parent_id, 'subfolders': [...]}}
        """
        if getattr(self, "_cached_folders", None) is None or force_refresh:
            try:
                aw = self._get_aw()
                xml_data = None
                if hasattr(aw, "get_folder_list"):
                    try:
                        xml_data = aw.get_folder_list()
                    except Exception:
                        xml_data = None
                if not xml_data:
                    xml_data = aw.command(apiPath="/folder_list.xml")
                self._cached_folders = parse_folders_xml(xml_data)
            except Exception as e:
                print(f"Warning: Could not fetch AirWave folder list: {e}")
                self._cached_folders = {}
        return self._cached_folders

    def get_devices(self, host_filter=None, device_categories=None, models=None, folders=None, force_refresh=False):
        """
        Fetches all devices from /ap_list.xml and filters them based on host_filter,
        device_categories, models, and recursive folders.
        """
        if self._cached_devices is None or force_refresh:
            aw = self._get_aw()
            xml_data = aw.command(apiPath="/ap_list.xml")
            # Parse without host filters initially to store full cache
            self._cached_devices = parse_devices_xml(xml_data)

            # Resolve folder names and breadcrumb paths using folder_list
            folders_dict = self.get_folders(force_refresh=force_refresh)
            if folders_dict:
                for dev in self._cached_devices:
                    fid = dev.get("folder_id")
                    if fid and fid in folders_dict:
                        dev["folder"] = folders_dict[fid]["name"]
                        dev["folder_path"] = get_folder_path(fid, folders_dict)

        folders_dict = self.get_folders()

        # Resolve allowed folder IDs if folders filter is specified
        allowed_folder_ids = None
        normalized_folders = normalize_folders_filter(folders)
        if normalized_folders:
            if folders_dict:
                allowed_folder_ids = get_folder_descendant_ids(normalized_folders, folders_dict)
                if not allowed_folder_ids:
                    print(f"Warning: None of the specified AirWave folders were found: {normalized_folders}")
                    return []
            else:
                allowed_folder_ids = None

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

            # Check folder filter
            if normalized_folders:
                if allowed_folder_ids is not None:
                    dev_fid = str(dev.get("folder_id") or "").strip()
                    if dev_fid not in allowed_folder_ids:
                        continue
                else:
                    # Fallback when folders_dict is empty: match by folder name
                    dev_folder = (dev.get("folder") or "").lower()
                    if not any(f.lower() in dev_folder for f in normalized_folders):
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
