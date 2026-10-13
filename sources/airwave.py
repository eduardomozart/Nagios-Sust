import sys
from utils.airwave import AirWaveClient, normalize_folders_filter
from utils.exit_codes import ERR_AIRWAVE_API_ERROR


def get_hosts(config, options=None):
    """
    Ingests network devices directly from Aruba AirWave API via pyairwave.
    Supports filtering by host_filter, device_categories, models, and recursive folders.
    """
    airwave_cfg = config.get("airwave", {})
    url = airwave_cfg.get("url") or airwave_cfg.get("host")
    if not url:
        default_url = "https://airwave"
        try:
            entered_url = input(f"Enter AirWave Server URL or IP [{default_url}]: ").strip()
            url = entered_url if entered_url else default_url
        except (EOFError, KeyboardInterrupt):
            url = default_url

    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    # Cache back to config so subsequent handlers can reuse it
    config.setdefault("airwave", {})["url"] = url

    username = airwave_cfg.get("username")
    password = airwave_cfg.get("password")
    if not username or not password:
        if options and "credential_provider" in options:
            prov_user, prov_pass = options["credential_provider"]()
            username = username or prov_user
            password = password or prov_pass
        else:
            raise ValueError("Credentials are required for AirWave device enumeration.")

    print(f"Connecting to AirWave at {url} to enumerate devices...")
    try:
        client = AirWaveClient(url, username, password)
        host_filter = airwave_cfg.get("host_filter")
        device_categories = airwave_cfg.get("device_categories")
        models = airwave_cfg.get("models")

        # Resolve folders filter from CLI options or config
        raw_folders = (
            (options.get("airwave_folders") if options else None)
            or airwave_cfg.get("folders")
            or airwave_cfg.get("folder")
            or airwave_cfg.get("airwave_folders")
        )
        folders = normalize_folders_filter(raw_folders)

        devices = client.get_devices(
            host_filter=host_filter,
            device_categories=device_categories,
            models=models,
            folders=folders if folders else None,
        )
        print(f"AirWave API returned {len(devices)} matching devices.")

        hosts = []
        for dev in devices:
            hosts.append({
                "host": dev["name"],
                "ip": dev["ip"],
                "device_id": dev["id"],
                "model": dev.get("model", ""),
                "serial": dev.get("serial_number", ""),
                "device_category": dev.get("device_category", ""),
                "folder_id": dev.get("folder_id", ""),
                "folder": dev.get("folder", ""),
                "folder_path": dev.get("folder_path", ""),
            })
        return hosts
    except Exception as e:
        print(f"Error enumerating AirWave devices: {e}")
        sys.exit(ERR_AIRWAVE_API_ERROR)
