import unittest
from unittest.mock import patch, MagicMock
import glob
from exporters import docx_exporter
from utils.exit_codes import ERR_DOCX_RENDER_ERROR
try:
    from docxtpl import DocxTemplate
    DOCXTPL_AVAILABLE = True
except ImportError:
    DOCXTPL_AVAILABLE = False


class TestDocxExporter(unittest.TestCase):
    @unittest.skipUnless(DOCXTPL_AVAILABLE, "docxtpl is not installed in the current environment")
    def test_example_templates_compilation(self):
        """Verifies that all template*.docx files compile cleanly without Jinja rendering syntax errors."""
        template_files = glob.glob("template*.docx")
        self.assertGreater(len(template_files), 0, "No template*.docx files found to test.")
        for file in template_files:
            doc = DocxTemplate(file)
            doc.render({"results": []})

    @patch("exporters.docx_exporter.os.path.exists", return_value=True)
    @patch("exporters.docx_exporter.DocxTemplate")
    @patch("exporters.docx_exporter._diagnose_template_error")
    @patch("sys.exit")
    def test_template_render_error_exits(self, mock_exit, mock_diagnose, mock_template_cls, mock_exists):
        """Verifies that an error during Word template rendering exits with ERR_DOCX_RENDER_ERROR."""
        mock_exit.side_effect = SystemExit(ERR_DOCX_RENDER_ERROR)
        mock_doc = MagicMock()
        mock_doc.render.side_effect = Exception("Jinja syntax error in docx")
        mock_template_cls.return_value = mock_doc

        config = {
            "output_file": "report.docx",
            "languages": ["en"],
        }
        with self.assertRaises(SystemExit):
            docx_exporter.export([], config)

        mock_exit.assert_called_with(ERR_DOCX_RENDER_ERROR)

    @patch("exporters.docx_exporter.os.path.exists", return_value=True)
    @patch("exporters.docx_exporter.DocxTemplate")
    def test_export_includes_sources_list_and_merged_fields(self, mock_template_cls, mock_exists):
        """Verifies that export builds context with pure 4-subsystem contract and zero legacy keys."""
        mock_doc = MagicMock()
        mock_template_cls.return_value = mock_doc

        results = [
            {
                "host": {"name": "SW-CORE-01"},
                "rules": ["Core Switches"],
                "handlers": {
                    "generic_ping": {
                        "latency": 12,
                        "error": 0,
                    },
                },
                "sources": {
                    "list": ["nagios_pdf", "airwave"],
                    "nagios_pdf": {"status": "CRITICAL", "service": "PING"},
                    "airwave": {"ip": "10.0.0.1", "device_id": "538"},
                },
            }
        ]
        config = {
            "output_file": "report.docx",
            "languages": ["en"],
        }
        docx_exporter.export(results, config)

        # Retrieve the context passed to the second render call (actual report render)
        self.assertGreaterEqual(mock_doc.render.call_count, 2)
        rendered_context = mock_doc.render.call_args[0][0]
        self.assertIn("results", rendered_context)
        item = rendered_context["results"][0]

        # Verify pure 4 domains
        self.assertEqual(item["host"]["name"], "SW-CORE-01")
        self.assertEqual(item["rules"], ["Core Switches"])
        self.assertIn("generic_ping", item["handlers"])
        self.assertNotIn("list", item["handlers"])
        self.assertEqual(item["handlers"]["generic_ping"]["latency"], 12)
        self.assertEqual(item["sources"]["list"], ["nagios_pdf", "airwave"])
        self.assertEqual(item["sources"]["nagios_pdf"], {"status": "CRITICAL", "service": "PING"})
        self.assertEqual(item["sources"]["airwave"], {"ip": "10.0.0.1", "device_id": "538"})

    @patch("exporters.docx_exporter.os.path.exists", return_value=True)
    @patch("exporters.docx_exporter.DocxTemplate")
    def test_export_sources_default_empty_list(self, mock_template_cls, mock_exists):
        """Verifies that missing sources in result defaults to an empty list."""
        mock_doc = MagicMock()
        mock_template_cls.return_value = mock_doc

        results = [{"host": {"name": "SW-ACCESS-01"}}]
        config = {
            "output_file": "report.docx",
            "languages": ["en"],
        }
        docx_exporter.export(results, config)

        rendered_context = mock_doc.render.call_args[0][0]
        item = rendered_context["results"][0]
        self.assertEqual(item["sources"]["list"], [])

    @patch("exporters.docx_exporter.Inches", side_effect=lambda x: x)
    @patch("exporters.docx_exporter.InlineImage", return_value="<InlineImageObject>")
    @patch("exporters.docx_exporter.os.path.exists")
    @patch("exporters.docx_exporter.DocxTemplate")
    def test_export_handler_screenshot_injection(self, mock_template_cls, mock_exists, mock_inline_image, mock_inches):
        """Verifies that screenshot image is attached to handlers.<HANDLER>.screenshot.image."""
        mock_doc = MagicMock()
        mock_template_cls.return_value = mock_doc
        mock_exists.side_effect = lambda path: True

        results = [
            {
                "host": {"name": "RT-01"},
                "rules": ["Check Router"],
                "handlers": {
                    "airwave": {
                        "error": 0,
                        "screenshot": {
                            "path": "/fake/screenshot.png",
                            "filename": "screenshot.png",
                            "captured": True,
                        },
                    },
                },
                "sources": {"list": []},
            }
        ]
        config = {
            "output_file": "report.docx",
            "languages": ["en"],
        }
        docx_exporter.export(results, config)

        rendered_context = mock_doc.render.call_args[0][0]
        item = rendered_context["results"][0]
        screenshot_obj = item["handlers"]["airwave"]["screenshot"]
        self.assertTrue(screenshot_obj["captured"])
        self.assertEqual(screenshot_obj["filename"], "screenshot.png")
        self.assertEqual(screenshot_obj["image"], "<InlineImageObject>")

    @patch("exporters.docx_exporter.os.path.exists", return_value=True)
    @patch("exporters.docx_exporter.DocxTemplate")
    def test_export_includes_host_alerts_and_setup_thresholds(self, mock_template_cls, mock_exists):
        """Verifies that host.alerts contains active alerts and res.alerts provides setup thresholds."""
        mock_doc = MagicMock()
        mock_template_cls.return_value = mock_doc

        alert = {
            "handler": "generic_ping",
            "severity": "CRITICAL",
            "type": "ping",
            "component": "ICMP",
            "message": "Ping timeout or unreachable (10.0.0.1)",
        }
        from utils.alert_evaluator import build_thresholds_container
        thresholds = build_thresholds_container()
        results = [
            {
                "host": {"name": "SW-CORE-01", "alerts": [alert]},
                "rules": ["Core Switches"],
                "handlers": {},
                "sources": {"list": []},
                "alerts": thresholds,
            }
        ]
        config = {
            "output_file": "report.docx",
            "languages": ["en"],
        }
        docx_exporter.export(results, config)

        rendered_context = mock_doc.render.call_args[0][0]
        item = rendered_context["results"][0]

        # Verified: alerts is directly on host for active alerts
        self.assertIn("alerts", item["host"])
        self.assertEqual(item["host"]["alerts"], [alert])
        # res.alerts provides setup thresholds container
        self.assertEqual(item["alerts"], thresholds)
        self.assertEqual(item["alerts"].cpu.warning, 75)
        self.assertEqual(item["alerts"].cpu.critical, 90)

if __name__ == "__main__":
    unittest.main(buffer=True)
