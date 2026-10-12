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
        """Verifies that export builds context with sources list and merged discovery attributes, and no singular source."""
        mock_doc = MagicMock()
        mock_template_cls.return_value = mock_doc

        results = [
            {
                "host": "SW-CORE-01",
                "rule_name": "Core Switches",
                "handler": "generic_ping",
                "sources": ["nagios_pdf", "airwave"],
                "nagios_pdf": {"status": "CRITICAL", "service": "PING"},
                "airwave": {"ip": "10.0.0.1", "device_id": "538"},
                "latencies": [12],
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

        # Verify sources is a flat list
        self.assertEqual(item["sources"], ["nagios_pdf", "airwave"])
        # Verify singular 'source' is deliberately not present
        self.assertNotIn("source", item)
        # Verify namespaced source dictionaries (res.<SOURCE>)
        self.assertEqual(item["nagios_pdf"], {"status": "CRITICAL", "service": "PING"})
        self.assertEqual(item["airwave"], {"ip": "10.0.0.1", "device_id": "538"})
        # Verify root namespace is clean with zero attribute pollution
        self.assertNotIn("status", item)
        self.assertNotIn("service", item)

    @patch("exporters.docx_exporter.os.path.exists", return_value=True)
    @patch("exporters.docx_exporter.DocxTemplate")
    def test_export_sources_default_empty_list(self, mock_template_cls, mock_exists):
        """Verifies that missing sources in result defaults to an empty list."""
        mock_doc = MagicMock()
        mock_template_cls.return_value = mock_doc

        results = [{"host": "SW-ACCESS-01"}]
        config = {
            "output_file": "report.docx",
            "languages": ["en"],
        }
        docx_exporter.export(results, config)

        rendered_context = mock_doc.render.call_args[0][0]
        item = rendered_context["results"][0]
        self.assertEqual(item["sources"], [])
        self.assertNotIn("source", item)


if __name__ == "__main__":
    unittest.main(buffer=True)
