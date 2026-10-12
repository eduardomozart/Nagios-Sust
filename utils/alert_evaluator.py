import re

DEFAULT_ALERT_THRESHOLDS = {
    "cpu": {
        "key": "cpu",
        "name": "CPU Utilization (%)",
        "warning": 75,
        "critical": 90,
    },
    "memory": {
        "key": "memory",
        "name": "Memory Usage (%)",
        "warning": 75,
        "critical": 90,
    },
    "interface_utilization": {
        "key": "interface_utilization",
        "name": "Interface Utilization (%)",
        "warning": 80,
        "critical": 100,
    },
    "packet_buffers": {
        "key": "packet_buffers",
        "name": "Packet Buffers",
        "warning": 85,
        "critical": 95,
    },
    "tx_drops": {
        "key": "tx_drops",
        "name": "Tx Drops",
        "warning": 85,
        "critical": 95,
    },
    "rx_errors": {
        "key": "rx_errors",
        "name": "Rx Errors",
        "warning": 85,
        "critical": 95,
    },
    "message_buffers": {
        "key": "message_buffers",
        "name": "Message Buffers",
        "warning": 85,
        "critical": 95,
    },
    "fans": {
        "key": "fans",
        "name": "Fans",
        "warning": 1,
        "critical": 2,
    },
    "temperature": {
        "key": "temperature",
        "name": "Temperature (°C)",
        "warning": 25,
        "critical": 60,
    },
    "power_supplies": {
        "key": "power_supplies",
        "name": "Power Supplies",
        "warning": 1,
        "critical": 2,
    },
    "storage": {
        "key": "storage",
        "name": "Storage (%)",
        "warning": 70,
        "critical": 90,
    },
    "firmware_version": {
        "key": "firmware_version",
        "name": "Firmware Version",
        "warning": 1,
        "critical": 2,
    },
}


class ThresholdItem(dict):
    """
    Individual threshold object supporting attribute and dictionary key access.
    """
    def __getattr__(self, item):
        if item in self:
            return self[item]
        raise AttributeError(f"'ThresholdItem' object has no attribute '{item}'")


class ThresholdsContainer(dict):
    """
    Container for setup thresholds that behaves as both a dictionary (with attribute access)
    and an iterable over its setup threshold objects.
    When iterated in Word templates ({%tr for th in res.alerts %}), it yields the setup thresholds only.
    """
    def __iter__(self):
        return iter(self.values())

    def __getattr__(self, item):
        if item in self:
            return self[item]
        raise AttributeError(f"'ThresholdsContainer' object has no attribute '{item}'")


def build_thresholds_container(config_alerts=None):
    """
    Builds a ThresholdsContainer populated with setup thresholds.
    Uses DEFAULT_ALERT_THRESHOLDS as default, applying any custom overrides
    configured in config.yaml under alerts.thresholds.
    """
    container = ThresholdsContainer()
    custom_thresholds = {}
    if isinstance(config_alerts, dict):
        if isinstance(config_alerts.get("thresholds"), dict):
            custom_thresholds = config_alerts["thresholds"]
        else:
            custom_thresholds = config_alerts

    for key, default_obj in DEFAULT_ALERT_THRESHOLDS.items():
        th_copy = ThresholdItem(default_obj)
        if key in custom_thresholds and isinstance(custom_thresholds[key], dict):
            custom_entry = custom_thresholds[key]
            if "warning" in custom_entry:
                th_copy["warning"] = custom_entry["warning"]
            if "critical" in custom_entry:
                th_copy["critical"] = custom_entry["critical"]
            if "name" in custom_entry:
                th_copy["name"] = custom_entry["name"]
        container[key] = th_copy

    return container


def evaluate_host_thresholds(handlers_obj, thresholds_container, host_name):
    """
    Evaluates telemetry across executed handlers against the setup thresholds.
    When a threshold is matched/exceeded, creates and returns structured alert
    dictionaries to be appended to res.host.alerts.
    """
    alerts = []
    if not isinstance(handlers_obj, dict):
        return alerts

    for handler_name, handler_data in handlers_obj.items():
        if not isinstance(handler_data, dict):
            continue

        system_info = handler_data.get("system_info", {})
        if not isinstance(system_info, dict):
            system_info = {}

        # 1. CPU Utilization (%)
        cpu_val = system_info.get("cpu_util")
        if cpu_val is not None:
            try:
                num_cpu = float(cpu_val)
                th_cpu = thresholds_container.get("cpu", {})
                crit_cpu = float(th_cpu.get("critical", 90))
                warn_cpu = float(th_cpu.get("warning", 75))
                if num_cpu >= crit_cpu:
                    alerts.append({
                        "handler": handler_name,
                        "severity": "CRITICAL",
                        "type": "cpu",
                        "component": "CPU",
                        "message": f"CPU Utilization exceeded critical threshold: {num_cpu}% (>= {crit_cpu}%)",
                    })
                elif num_cpu >= warn_cpu:
                    alerts.append({
                        "handler": handler_name,
                        "severity": "WARNING",
                        "type": "cpu",
                        "component": "CPU",
                        "message": f"CPU Utilization exceeded warning threshold: {num_cpu}% (>= {warn_cpu}%)",
                    })
            except (ValueError, TypeError):
                pass

        # 2. Memory Usage (%)
        mem_val = system_info.get("memory_usage")
        if mem_val is not None:
            try:
                num_mem = float(mem_val)
                th_mem = thresholds_container.get("memory", {})
                crit_mem = float(th_mem.get("critical", 90))
                warn_mem = float(th_mem.get("warning", 75))
                if num_mem >= crit_mem:
                    alerts.append({
                        "handler": handler_name,
                        "severity": "CRITICAL",
                        "type": "memory",
                        "component": "Memory",
                        "message": f"Memory Usage exceeded critical threshold: {num_mem}% (>= {crit_mem}%)",
                    })
                elif num_mem >= warn_mem:
                    alerts.append({
                        "handler": handler_name,
                        "severity": "WARNING",
                        "type": "memory",
                        "component": "Memory",
                        "message": f"Memory Usage exceeded warning threshold: {num_mem}% (>= {warn_mem}%)",
                    })
            except (ValueError, TypeError):
                pass

        # 3. Storage (%)
        storage_val = system_info.get("storage")
        if storage_val is not None:
            try:
                num_storage = float(storage_val)
                th_storage = thresholds_container.get("storage", {})
                crit_storage = float(th_storage.get("critical", 90))
                warn_storage = float(th_storage.get("warning", 70))
                if num_storage >= crit_storage:
                    alerts.append({
                        "handler": handler_name,
                        "severity": "CRITICAL",
                        "type": "storage",
                        "component": "Storage",
                        "message": f"Storage Usage exceeded critical threshold: {num_storage}% (>= {crit_storage}%)",
                    })
                elif num_storage >= warn_storage:
                    alerts.append({
                        "handler": handler_name,
                        "severity": "WARNING",
                        "type": "storage",
                        "component": "Storage",
                        "message": f"Storage Usage exceeded warning threshold: {num_storage}% (>= {warn_storage}%)",
                    })
            except (ValueError, TypeError):
                pass

    return alerts
