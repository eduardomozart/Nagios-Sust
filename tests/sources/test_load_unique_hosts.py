import importlib
import unittest
from unittest.mock import patch
from sources import load_unique_hosts, get_supported_sources
from utils.exit_codes import (
    ERR_SOURCE_NOT_FOUND,
    ERR_SOURCE_LOAD_ERROR,
)


class TestLoadUniqueHosts(unittest.TestCase):
    def test_dynamic_source_import(self):
        """Verifies that both nagios_pdf and airwave sources can be dynamically imported."""
        for src in ["nagios_pdf", "airwave"]:
            mod = importlib.import_module(f"sources.{src}")
            self.assertTrue(hasattr(mod, "get_hosts"))

    def test_get_supported_sources(self):
        """Tests discovery of available source modules."""
        supported = get_supported_sources()
        self.assertIn("nagios_pdf", supported)
        self.assertIn("airwave", supported)

    @patch("sources.airwave.get_hosts")
    @patch("sources.nagios_pdf.get_hosts")
    def test_load_unique_hosts_multi_source(self, mock_pdf_hosts, mock_airwave_hosts):
        """Tests aggregating and deduplicating hosts across multiple sources."""
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

        # Check provenance and namespaced attributes for non-overlapping hosts
        self.assertEqual(by_host["SW-ACCESS-01"]["sources"], ["nagios_pdf"])
        self.assertEqual(by_host["SW-ACCESS-01"]["nagios_pdf"]["status"], "UP")
        self.assertEqual(by_host["AP-01"]["sources"], ["airwave"])
        self.assertEqual(by_host["AP-01"]["airwave"]["device_id"], "539")

    @patch("sys.exit")
    def test_load_unique_hosts_source_not_found_exits(self, mock_exit):
        """Verifies that an unknown source module exits with ERR_SOURCE_NOT_FOUND."""
        mock_exit.side_effect = SystemExit(ERR_SOURCE_NOT_FOUND)
        config = {"device_sources": ["non_existent_source_xyz"]}
        with self.assertRaises(SystemExit):
            load_unique_hosts(config)
        mock_exit.assert_called_with(ERR_SOURCE_NOT_FOUND)

    @patch("sources.nagios_pdf.get_hosts")
    @patch("sys.exit")
    def test_load_unique_hosts_source_load_error_exits(self, mock_exit, mock_get):
        """Verifies that an unhandled error inside a source module exits with ERR_SOURCE_LOAD_ERROR."""
        mock_exit.side_effect = SystemExit(ERR_SOURCE_LOAD_ERROR)
        mock_get.side_effect = RuntimeError("Failed to load PDF source")
        config = {"device_sources": ["nagios_pdf"]}
        with self.assertRaises(SystemExit):
            load_unique_hosts(config)
        mock_exit.assert_called_with(ERR_SOURCE_LOAD_ERROR)


if __name__ == "__main__":
    unittest.main(buffer=True)
