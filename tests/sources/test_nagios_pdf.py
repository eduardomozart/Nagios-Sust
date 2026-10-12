import unittest
from unittest.mock import patch
from sources import nagios_pdf
from utils.exit_codes import (
    ERR_PDF_FILE_NOT_SELECTED,
    ERR_PDF_PARSE_ERROR,
)


class TestNagiosPdfSource(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main(buffer=True)
