import sys
from utils.airwave import AirWaveClient


def get_hosts(config, options=None):
    """
    Ingests network devices directly from Aruba AirWave API via pyairwave.
    """
    airwave_cfg = config.get("airwave", {})
    url = airwave_cfg.get("url") or airwave_cfg.get("host") or "https://airwave"

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

        devices = client.get_devices(
            host_filter=host_filter,
            device_categories=device_categories,
            models=models,
        )
        print(f"AirWave API returned {len(devices)} matching devices.")

        alerts = []
        for dev in devices:
            alerts.append({
                "host": dev["name"],
                "ip": dev["ip"],
                "device_id": dev["id"],
                "model": dev.get("model", ""),
                "serial": dev.get("serial_number", ""),
                "device_category": dev.get("device_category", ""),
                "folder_id": dev.get("folder_id", ""),
            })
        return alerts
    except Exception as e:
        print(f"Error enumerating AirWave devices: {e}")
        sys.exit(1)
