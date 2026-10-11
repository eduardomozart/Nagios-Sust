import unittest
import importlib
from unittest.mock import patch, MagicMock
from sources import nagios_pdf, airwave


class TestSources(unittest.TestCase):
    def test_dynamic_source_import(self):
        """Verifies that both nagios_pdf and airwave sources can be dynamically imported."""
        for src in ["nagios_pdf", "airwave"]:
            mod = importlib.import_module(f"sources.{src}")
            self.assertTrue(hasattr(mod, "get_hosts"))

    @patch("sources.nagios_pdf.parse_nagios_pdf")
    @patch("sources.nagios_pdf.get_pdf_file_path")
    def test_nagios_pdf_source(self, mock_get_path, mock_parse_pdf):
        """Tests nagios_pdf.get_hosts with configuration and host filtering."""
        mock_get_path.return_value = "/path/to/report.pdf"
        mock_parse_pdf.return_value = [
            {"host": "SW-CORE-01", "service": "", "status": "CRITICAL"},
            {"host": "SW-ACCESS-01", "service": "", "status": "WARNING"},
            {"host": "FGT-FIREWALL-01", "service": "", "status": "CRITICAL"},
        ]

        # 1. Unfiltered
        config = {
            "device_source": "nagios_pdf",
            "nagios_pdf": {
                "report_file": "custom_report.pdf",
            },
        }
        hosts = nagios_pdf.get_hosts(config)
        self.assertEqual(len(hosts), 3)
        mock_get_path.assert_called()

        # 2. Filtered by startswith
        config_filtered = {
            "nagios_pdf": {
                "report_file": "custom_report.pdf",
                "host_filter": {"startswith": "SW"},
            },
        }
        hosts_sw = nagios_pdf.get_hosts(config_filtered)
        self.assertEqual(len(hosts_sw), 2)
        self.assertTrue(all(h["host"].startswith("SW") for h in hosts_sw))

        # 3. Filtered by regex
        config_regex = {
            "nagios_pdf": {
                "report_file": "custom_report.pdf",
                "host_filter": {"regex": "CORE"},
            },
        }
        hosts_core = nagios_pdf.get_hosts(config_regex)
        self.assertEqual(len(hosts_core), 1)
        self.assertEqual(hosts_core[0]["host"], "SW-CORE-01")

    @patch("sources.airwave.AirWaveClient")
    def test_airwave_source(self, mock_client_cls):
        """Tests airwave.get_hosts with mocked AirWaveClient."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_devices.return_value = [
            {
                "id": "538",
                "name": "SW-CORE-01",
                "ip": "192.0.2.11",
                "model": "Aruba 6300M",
                "serial_number": "SG0000000003",
                "device_category": "switch",
                "folder_id": "1",
            },
            {
                "id": "539",
                "name": "AP01",
                "ip": "192.0.2.50",
                "model": "AP-535",
                "serial_number": "SG0000000004",
                "device_category": "thin_ap",
                "folder_id": "2",
            },
        ]

        config = {
            "device_source": "airwave",
            "airwave": {
                "url": "https://airwave.local",
                "username": "admin",
                "password": "secretpassword",
                "host_filter": {"startswith": "SW"},
            },
        }

        hosts = airwave.get_hosts(config)
        self.assertEqual(len(hosts), 2)
        self.assertEqual(hosts[0]["host"], "SW-CORE-01")
        self.assertEqual(hosts[0]["device_id"], "538")
        self.assertEqual(hosts[1]["host"], "AP01")
        mock_client.get_devices.assert_called_with(
            host_filter={"startswith": "SW"},
            device_categories=None,
            models=None,
        )


if __name__ == "__main__":
    unittest.main()
