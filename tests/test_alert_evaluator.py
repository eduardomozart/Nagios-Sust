import unittest
from utils.alert_evaluator import (
    DEFAULT_ALERT_THRESHOLDS,
    ThresholdsContainer,
    build_thresholds_container,
    evaluate_host_thresholds,
)


class TestAlertEvaluator(unittest.TestCase):
    def test_default_alert_thresholds_integers_only(self):
        """Verifies that all warning and critical thresholds in DEFAULT_ALERT_THRESHOLDS are integers."""
        for key, entry in DEFAULT_ALERT_THRESHOLDS.items():
            self.assertIn("key", entry)
            self.assertIn("name", entry)
            self.assertIn("warning", entry)
            self.assertIn("critical", entry)
            self.assertIsInstance(
                entry["warning"], int,
                f"Threshold 'warning' for '{key}' is not an int: {entry['warning']}"
            )
            self.assertIsInstance(
                entry["critical"], int,
                f"Threshold 'critical' for '{key}' is not an int: {entry['critical']}"
            )

    def test_thresholds_container_iteration_and_attributes(self):
        """Verifies ThresholdsContainer yields setup thresholds when iterated and supports attribute access."""
        container = build_thresholds_container()
        self.assertIsInstance(container, ThresholdsContainer)

        # Attribute access
        self.assertEqual(container.cpu.warning, 75)
        self.assertEqual(container.cpu.critical, 90)
        self.assertEqual(container.cpu.name, "CPU Utilization (%)")
        self.assertEqual(container.fans.warning, 1)
        self.assertEqual(container.fans.critical, 2)
        self.assertEqual(container.power_supplies.warning, 1)
        self.assertEqual(container.power_supplies.critical, 2)
        self.assertEqual(container.firmware_version.warning, 1)
        self.assertEqual(container.firmware_version.critical, 2)
        self.assertEqual(container.temperature.warning, 25)
        self.assertEqual(container.temperature.critical, 60)

        # Iteration yields threshold objects only
        items = list(container)
        self.assertEqual(len(items), len(DEFAULT_ALERT_THRESHOLDS))
        for item in items:
            self.assertIn("name", item)
            self.assertIn("warning", item)
            self.assertIn("critical", item)

    def test_thresholds_container_custom_overrides(self):
        """Verifies that custom thresholds in config override default values."""
        config_alerts = {
            "thresholds": {
                "cpu": {"warning": 60, "critical": 80},
                "temperature": {"warning": 30, "critical": 65},
            }
        }
        container = build_thresholds_container(config_alerts)
        self.assertEqual(container.cpu.warning, 60)
        self.assertEqual(container.cpu.critical, 80)
        self.assertEqual(container.temperature.warning, 30)
        self.assertEqual(container.temperature.critical, 65)
        # Unspecified metrics keep defaults
        self.assertEqual(container.memory.warning, 75)
        self.assertEqual(container.memory.critical, 90)

    def test_evaluate_host_thresholds_normal_telemetry(self):
        """Verifies evaluate_host_thresholds returns empty list when telemetry is within normal limits."""
        container = build_thresholds_container()
        handlers_obj = {
            "procurve": {
                "system_info": {
                    "cpu_util": 35,
                    "memory_usage": 40.0,
                    "storage": 50,
                }
            }
        }
        alerts = evaluate_host_thresholds(handlers_obj, container, "SW-CORE-01")
        self.assertEqual(alerts, [])

    def test_evaluate_host_thresholds_warning_and_critical(self):
        """Verifies evaluate_host_thresholds emits WARNING and CRITICAL alerts when thresholds are matched."""
        container = build_thresholds_container()
        handlers_obj = {
            "procurve": {
                "system_info": {
                    "cpu_util": 80,       # >= 75 (Warning), < 90
                    "memory_usage": 92.5, # >= 90 (Critical)
                    "storage": 95,        # >= 90 (Critical)
                }
            }
        }
        alerts = evaluate_host_thresholds(handlers_obj, container, "SW-CORE-01")
        self.assertEqual(len(alerts), 3)

        cpu_alert = next(a for a in alerts if a["type"] == "cpu")
        self.assertEqual(cpu_alert["severity"], "WARNING")
        self.assertEqual(cpu_alert["handler"], "procurve")
        self.assertIn("80", cpu_alert["message"])

        mem_alert = next(a for a in alerts if a["type"] == "memory")
        self.assertEqual(mem_alert["severity"], "CRITICAL")
        self.assertEqual(mem_alert["handler"], "procurve")
        self.assertIn("92.5", mem_alert["message"])

        storage_alert = next(a for a in alerts if a["type"] == "storage")
        self.assertEqual(storage_alert["severity"], "CRITICAL")


if __name__ == "__main__":
    unittest.main(buffer=True)
