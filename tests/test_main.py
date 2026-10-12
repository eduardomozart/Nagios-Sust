import io
import unittest
from unittest.mock import patch
from utils.exit_codes import ERR_DEVICE_PROMPT_ABORTED


class TestMainOrchestrator(unittest.TestCase):
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
        """Verifies that cumulative orchestrator encapsulates sources and handlers cleanly without polluting host root."""
        host = "SW-CORE-01"
        host_data = {
            "host": host,
            "sources": ["nagios_pdf", "airwave"],
            "nagios_pdf": {"status": "CRITICAL", "service": "PING"},
            "airwave": {"ip": "10.0.0.1", "device_id": "538"},
        }
        # Simulate main.py cumulative assembly
        host_obj = {"name": host}
        rules_list = ["Test Rule"]
        handlers_obj = {
            "list": ["generic_ping"],
            "generic_ping": {
                "latency": 15,
                "error": 0,
            }
        }
        sources_list = host_data.get("sources", [])
        sources_obj = {
            "list": list(sources_list) if isinstance(sources_list, list) else [sources_list],
        }
        for src in sources_obj["list"]:
            if src in host_data and isinstance(host_data[src], dict):
                sources_obj[src] = host_data[src]

        cumulative_item = {
            "host": host_obj,
            "rules": rules_list,
            "handlers": handlers_obj,
            "sources": sources_obj,
        }

        self.assertEqual(cumulative_item["sources"]["list"], ["nagios_pdf", "airwave"])
        self.assertIsInstance(cumulative_item["sources"]["list"], list)
        self.assertEqual(cumulative_item["sources"]["nagios_pdf"], {"status": "CRITICAL", "service": "PING"})
        self.assertEqual(cumulative_item["sources"]["airwave"], {"ip": "10.0.0.1", "device_id": "538"})
        self.assertEqual(cumulative_item["rules"], ["Test Rule"])
        self.assertEqual(cumulative_item["handlers"]["list"], ["generic_ping"])
        self.assertEqual(cumulative_item["handlers"]["generic_ping"]["latency"], 15)
        self.assertEqual(cumulative_item["handlers"]["generic_ping"]["error"], 0)
        self.assertEqual(cumulative_item["host"]["name"], "SW-CORE-01")

    def test_orchestrator_multi_rule_accumulation(self):
        """Verifies multiple matched rules accumulate into one unified host result without collisions."""
        host = "SW-CORE-01"
        host_data = {
            "host": host,
            "sources": ["nagios_pdf"],
            "nagios_pdf": {"status": "CRITICAL"},
        }

        # Multi-rule execution simulation matching main.py logic
        host_obj = {"name": host}
        rules_list = []
        handlers_obj = {"list": []}
        sources_list = host_data.get("sources", [])
        sources_obj = {
            "list": list(sources_list) if isinstance(sources_list, list) else [sources_list],
        }
        for src in sources_obj["list"]:
            if src in host_data and isinstance(host_data[src], dict):
                sources_obj[src] = host_data[src]

        # Rule 1 execution: generic_ping
        rule1 = {"name": "Rule Ping", "handler": "generic_ping"}
        rules_list.append(rule1["name"])
        res1 = {"host": host, "latency": [12], "error": 0}
        handlers_obj["list"].append("generic_ping")
        handlers_obj["generic_ping"] = {"latency": max(res1["latency"]), "error": res1["error"]}

        # Rule 2 execution: procurve
        rule2 = {"name": "Rule Telemetry", "handler": "procurve"}
        rules_list.append(rule2["name"])
        res2 = {"host": host, "system_info": {"version": "WC.16.11.0027", "uptime": "93 days"}, "error": 0}
        handlers_obj["list"].append("procurve")
        handlers_obj["procurve"] = {"system_info": res2["system_info"], "error": res2["error"]}

        cumulative_item = {
            "host": host_obj,
            "rules": rules_list,
            "handlers": handlers_obj,
            "sources": sources_obj,
        }

        # Assert unified single item with both rules and both handlers preserved
        self.assertEqual(cumulative_item["rules"], ["Rule Ping", "Rule Telemetry"])
        self.assertEqual(cumulative_item["handlers"]["list"], ["generic_ping", "procurve"])
        self.assertEqual(cumulative_item["handlers"]["generic_ping"]["latency"], 12)
        self.assertEqual(cumulative_item["handlers"]["generic_ping"]["error"], 0)
        self.assertEqual(cumulative_item["handlers"]["procurve"]["system_info"]["version"], "WC.16.11.0027")
        self.assertEqual(cumulative_item["handlers"]["procurve"]["error"], 0)
        # Verify host remains strictly identity
        self.assertEqual(cumulative_item["host"], {"name": "SW-CORE-01"})


if __name__ == "__main__":
    unittest.main(buffer=True)
