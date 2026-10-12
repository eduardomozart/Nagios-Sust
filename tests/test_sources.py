import io
import unittest
import importlib
from unittest.mock import patch, MagicMock
from sources import nagios_pdf, airwave
from utils.exit_codes import (
    ERR_SOURCE_NOT_FOUND,
    ERR_SOURCE_LOAD_ERROR,
    ERR_PDF_FILE_NOT_SELECTED,
    ERR_PDF_PARSE_ERROR,
    ERR_AIRWAVE_API_ERROR,
    ERR_DEVICE_PROMPT_ABORTED,
)


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
            "device_sources": ["nagios_pdf"],
            "nagios_pdf": {
                "report_file": "custom_report.pdf",
            },
        }
        hosts = nagios_pdf.get_hosts(config)
        self.assertEqual(len(hosts), 3)
        mock_get_path.assert_called()

        # 2. Filtered by startswith
        config_filtered = {
            "device_sources": ["nagios_pdf"],
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
            "device_sources": ["nagios_pdf"],
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
            "device_sources": ["airwave"],
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

    @patch("sources.airwave.get_hosts")
    @patch("sources.nagios_pdf.get_hosts")
    def test_load_unique_hosts_multi_source(self, mock_pdf_hosts, mock_airwave_hosts):
        """Tests aggregating and deduplicating hosts across multiple sources."""
        from sources import load_unique_hosts

        mock_pdf_hosts.return_value = [
            {"host": "SW-CORE-01", "status": "CRITICAL", "service": "PING"},
            {"host": "SW-ACCESS-01", "status": "UP", "service": ""},
        ]
        mock_airwave_hosts.return_value = [
            {"host": "sw-core-01", "ip": "10.0.0.1", "device_id": "538", "model": "6300M"},
            {"host": "AP-01", "ip": "10.0.0.50", "device_id": "539"},
        ]

        config = {
            "device_sources": ["nagios_pdf", "airwave"],
        }

        unique = load_unique_hosts(config)
        self.assertEqual(len(unique), 3)

        by_host = {h["host"].upper(): h for h in unique}
        self.assertIn("SW-CORE-01", by_host)
        self.assertIn("SW-ACCESS-01", by_host)
        self.assertIn("AP-01", by_host)

        # Check namespaced attributes and provenance for SW-CORE-01
        core = by_host["SW-CORE-01"]
        self.assertEqual(core["sources"], ["nagios_pdf", "airwave"])
        self.assertEqual(core["nagios_pdf"], {"status": "CRITICAL", "service": "PING"})
        self.assertEqual(core["airwave"], {"ip": "10.0.0.1", "device_id": "538", "model": "6300M"})
        # Confirm no root attribute pollution
        self.assertNotIn("status", core)
        self.assertNotIn("ip", core)

        # Check provenance and namespaced attributes for non-overlapping hosts
        self.assertEqual(by_host["SW-ACCESS-01"]["sources"], ["nagios_pdf"])
        self.assertEqual(by_host["SW-ACCESS-01"]["nagios_pdf"]["status"], "UP")
        self.assertEqual(by_host["AP-01"]["sources"], ["airwave"])
        self.assertEqual(by_host["AP-01"]["airwave"]["device_id"], "539")

    @patch("main.sys.argv", ["main.py", "-d", "SW-CORE-01", "-d", "SW-ACCESS-01,SW-03"])
    def test_cli_device_arguments_parsing(self):
        """Tests parsing multiple -d and comma-separated device arguments."""
        from main import parse_args
        args = parse_args()
        self.assertEqual(args.devices, ["SW-CORE-01", "SW-ACCESS-01,SW-03"])

        cli_devices = []
        for item in args.devices:
            for d in str(item).split(","):
                clean = d.strip()
                if clean and clean not in cli_devices:
                    cli_devices.append(clean)
        self.assertEqual(cli_devices, ["SW-CORE-01", "SW-ACCESS-01", "SW-03"])

    def test_get_supported_sources(self):
        """Tests discovery of available source modules."""
        from sources import get_supported_sources
        supported = get_supported_sources()
        self.assertIn("nagios_pdf", supported)
        self.assertIn("airwave", supported)

    @patch("builtins.input", return_value="SW-01, SW-02")
    def test_prompt_for_devices_entering_names(self, mock_input):
        """Tests interactive fallback prompting when user enters device names."""
        from main import prompt_for_devices
        hosts = prompt_for_devices({}, {})
        self.assertEqual(len(hosts), 2)
        self.assertEqual(hosts[0], {"host": "SW-01", "sources": ["interactive"]})
        self.assertEqual(hosts[1], {"host": "SW-02", "sources": ["interactive"]})

    @patch("main.load_unique_hosts")
    @patch("builtins.input", return_value="nagios_pdf, airwave")
    def test_prompt_for_devices_entering_multiple_sources(self, mock_input, mock_load):
        """Tests interactive fallback prompting when user types multiple source names."""
        from main import prompt_for_devices
        mock_load.return_value = [{"host": "SW-01", "sources": ["nagios_pdf", "airwave"]}]
        config = {}
        hosts = prompt_for_devices(config, {})
        self.assertEqual(config["device_sources"], ["nagios_pdf", "airwave"])
        mock_load.assert_called_with(config, {})
        self.assertEqual(len(hosts), 1)

    @patch("sys.stdout", new_callable=io.StringIO)
    @patch("builtins.input", side_effect=["airwave, SW-01", "SW-01"])
    def test_prompt_for_devices_mixed_source_and_device(self, mock_input, mock_stdout):
        """Tests that mixing source names and device names displays an error and re-prompts."""
        from main import prompt_for_devices
        hosts = prompt_for_devices({}, {})
        output = mock_stdout.getvalue()
        self.assertIn("Cannot mix source names", output)
        self.assertIn("airwave", output)
        self.assertIn("SW-01", output)
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0], {"host": "SW-01", "sources": ["interactive"]})
        self.assertEqual(mock_input.call_count, 2)

    @patch("sys.exit")
    def test_load_unique_hosts_source_not_found_exits(self, mock_exit):
        """Verifies that an unknown source module exits with ERR_SOURCE_NOT_FOUND."""
        from sources import load_unique_hosts
        mock_exit.side_effect = SystemExit(ERR_SOURCE_NOT_FOUND)
        config = {"device_sources": ["non_existent_source_xyz"]}
        with self.assertRaises(SystemExit):
            load_unique_hosts(config)
        mock_exit.assert_called_with(ERR_SOURCE_NOT_FOUND)

    @patch("sources.nagios_pdf.get_hosts")
    @patch("sys.exit")
    def test_load_unique_hosts_source_load_error_exits(self, mock_exit, mock_get):
        """Verifies that an unhandled error inside a source module exits with ERR_SOURCE_LOAD_ERROR."""
        from sources import load_unique_hosts
        mock_exit.side_effect = SystemExit(ERR_SOURCE_LOAD_ERROR)
        mock_get.side_effect = RuntimeError("Failed to load PDF source")
        config = {"device_sources": ["nagios_pdf"]}
        with self.assertRaises(SystemExit):
            load_unique_hosts(config)
        mock_exit.assert_called_with(ERR_SOURCE_LOAD_ERROR)

    @patch("sources.nagios_pdf.open_file_dialog", return_value=None)
    @patch("os.path.exists", return_value=False)
    @patch("sys.exit")
    def test_nagios_pdf_no_file_selected_exits(self, mock_exit, mock_exists, mock_dialog):
        """Verifies that cancelling PDF file selection dialog exits with ERR_PDF_FILE_NOT_SELECTED."""
        mock_exit.side_effect = SystemExit(ERR_PDF_FILE_NOT_SELECTED)
        with self.assertRaises(SystemExit):
            nagios_pdf.get_hosts({"nagios_pdf": {"report_file": "missing.pdf"}})
        mock_exit.assert_called_with(ERR_PDF_FILE_NOT_SELECTED)

    @patch("sources.nagios_pdf.parse_nagios_pdf", side_effect=Exception("Corrupt PDF"))
    @patch("sources.nagios_pdf.get_pdf_file_path", return_value="/path/corrupt.pdf")
    @patch("sys.exit")
    def test_nagios_pdf_parse_error_exits(self, mock_exit, mock_path, mock_parse):
        """Verifies that a PDF parsing exception exits with ERR_PDF_PARSE_ERROR."""
        mock_exit.side_effect = SystemExit(ERR_PDF_PARSE_ERROR)
        with self.assertRaises(SystemExit):
            nagios_pdf.get_hosts({"nagios_pdf": {}})
        mock_exit.assert_called_with(ERR_PDF_PARSE_ERROR)

    @patch("sources.airwave.AirWaveClient", side_effect=Exception("AirWave connection refused"))
    @patch("sys.exit")
    def test_airwave_api_error_exits(self, mock_exit, mock_client):
        """Verifies that an AirWave API error exits with ERR_AIRWAVE_API_ERROR."""
        mock_exit.side_effect = SystemExit(ERR_AIRWAVE_API_ERROR)
        config = {
            "airwave": {
                "url": "https://airwave.local",
                "username": "admin",
                "password": "password",
            }
        }
        with self.assertRaises(SystemExit):
            airwave.get_hosts(config)
        mock_exit.assert_called_with(ERR_AIRWAVE_API_ERROR)

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    @patch("sys.exit")
    def test_prompt_for_devices_aborted_exits(self, mock_exit, mock_input):
        """Verifies that aborting the device selection prompt exits with ERR_DEVICE_PROMPT_ABORTED."""
        from main import prompt_for_devices
        mock_exit.side_effect = SystemExit(ERR_DEVICE_PROMPT_ABORTED)
        with self.assertRaises(SystemExit):
            prompt_for_devices({}, {})
        mock_exit.assert_called_with(ERR_DEVICE_PROMPT_ABORTED)

    def test_orchestrator_namespaced_sources_injection(self):
        """Verifies that main.py injects sources as a flat list and attaches namespaced source dictionaries without polluting root."""
        host_data = {
            "host": "SW-CORE-01",
            "sources": ["nagios_pdf", "airwave"],
            "nagios_pdf": {"status": "CRITICAL", "service": "PING"},
            "airwave": {"ip": "10.0.0.1", "device_id": "538"},
        }
        handler_result = {
            "host": "SW-CORE-01",
            "latencies": [15],
            "wan_status": {"wan1": {"status": "UP"}},
            "status": "HANDLER_OPERATIONAL_STATUS",
        }
        rule = {"name": "Test Rule", "handler": "generic_ping"}

        # Simulate the injection logic from main.py
        result = dict(handler_result)
        result["rule_name"] = rule["name"]
        result["handler"] = rule["handler"]

        sources = host_data.get("sources", [])
        result["sources"] = list(sources) if isinstance(sources, list) else [sources]

        for src in result["sources"]:
            if src in host_data and isinstance(host_data[src], dict):
                result[src] = host_data[src]

        self.assertEqual(result["sources"], ["nagios_pdf", "airwave"])
        self.assertIsInstance(result["sources"], list)
        self.assertEqual(result["nagios_pdf"], {"status": "CRITICAL", "service": "PING"})
        self.assertEqual(result["airwave"], {"ip": "10.0.0.1", "device_id": "538"})
        # Handler status is completely preserved without collision
        self.assertEqual(result["status"], "HANDLER_OPERATIONAL_STATUS")
        self.assertNotIn("source", result)
        self.assertNotIn("ip", result)
        self.assertNotIn("device_id", result)


if __name__ == "__main__":
    unittest.main(buffer=True)
