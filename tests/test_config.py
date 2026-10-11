import unittest
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from utils.config import (
    ConfigValidationError,
    deep_merge,
    validate_config,
    resolve_includes,
    load_config,
)


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_deep_merge_scalars_and_dicts(self):
        base = {
            "title": "Default",
            "nested": {"a": 1, "b": 2},
            "unchanged": "value",
        }
        override = {
            "title": "Overridden",
            "nested": {"b": 99, "c": 3},
            "new_key": 42,
        }
        merged = deep_merge(base, override)
        self.assertEqual(merged["title"], "Overridden")
        self.assertEqual(merged["unchanged"], "value")
        self.assertEqual(merged["new_key"], 42)
        self.assertEqual(merged["nested"], {"a": 1, "b": 99, "c": 3})

    def test_deep_merge_lists_and_device_sources_dedup(self):
        base = {
            "device_sources": ["nagios_pdf"],
            "rules": [{"name": "rule1"}],
        }
        override = {
            "device_sources": ["nagios_pdf", "airwave"],
            "rules": [{"name": "rule2"}],
        }
        merged = deep_merge(base, override)
        # device_sources must be deduplicated
        self.assertEqual(merged["device_sources"], ["nagios_pdf", "airwave"])
        # rules list should be concatenated
        self.assertEqual(len(merged["rules"]), 2)
        self.assertEqual(merged["rules"][0]["name"], "rule1")
        self.assertEqual(merged["rules"][1]["name"], "rule2")

    def test_validate_config_valid(self):
        valid = {
            "device_sources": ["nagios_pdf", "airwave"],
            "rules": [
                {
                    "name": "Switch Rule",
                    "host_filter": {"startswith": "SW"},
                    "handler": "generic_ping",
                }
            ],
            "exporters": [
                {
                    "type": "docx",
                    "languages": ["en", "pt-BR"],
                }
            ],
            "credentials": {"username": "admin", "password": "123"},
            "nagios_pdf": {"report_file": "report.pdf"},
            "airwave": {"url": "https://airwave"},
        }
        # Should not raise
        validate_config(valid, "config.yaml")

    def test_validate_config_rejects_legacy_device_source(self):
        config = {
            "device_source": "nagios_pdf",
            "device_sources": ["nagios_pdf"],
            "rules": [],
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(config)
        self.assertIn("'device_source' in 'config.yaml' is no longer supported", str(ctx.exception))

    def test_validate_config_optional_device_sources(self):
        config = {
            "rules": [
                {
                    "name": "Switch Rule",
                    "host_filter": {"startswith": "SW"},
                    "handler": "generic_ping",
                }
            ]
        }
        # Should not raise when device_sources is omitted
        validate_config(config)

    def test_validate_config_invalid_device_sources_empty(self):
        config = {"device_sources": [], "rules": []}
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(config)
        self.assertIn("must be a non-empty list", str(ctx.exception))

    def test_validate_config_unknown_device_source(self):
        config = {
            "device_sources": ["non_existent_source_xyz"],
            "rules": [],
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(config)
        self.assertIn("Unknown device source 'non_existent_source_xyz'", str(ctx.exception))

    def test_validate_config_missing_rules(self):
        config = {"device_sources": ["nagios_pdf"]}
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(config)
        self.assertIn("missing required field 'rules'", str(ctx.exception))

    def test_validate_config_malformed_rule(self):
        # Missing handler
        config = {
            "device_sources": ["nagios_pdf"],
            "rules": [
                {
                    "name": "Bad Rule",
                    "host_filter": {"startswith": "SW"},
                }
            ],
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(config)
        self.assertIn("missing a valid 'handler' string", str(ctx.exception))

        # Missing host_filter
        config["rules"][0]["handler"] = "generic_ping"
        del config["rules"][0]["host_filter"]
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(config)
        self.assertIn("must specify a 'host_filter'", str(ctx.exception))

    def test_validate_config_rejects_legacy_exporter_language(self):
        config = {
            "device_sources": ["nagios_pdf"],
            "rules": [
                {
                    "name": "Ping",
                    "host_filter": {"startswith": "SW"},
                    "handler": "generic_ping",
                }
            ],
            "exporters": [
                {
                    "type": "docx",
                    "language": ["en"],
                }
            ],
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(config)
        self.assertIn("uses deprecated 'language'", str(ctx.exception))

    @patch("utils.config.yaml")
    def test_resolve_includes_single_file(self, mock_yaml):
        sub_file = os.path.join(self.test_dir, "sub.yaml")
        with open(sub_file, "w") as f:
            f.write("credentials:\n  username: admin\n")

        mock_yaml.safe_load.return_value = {
            "credentials": {"username": "admin"},
            "rules": [{"name": "SubRule", "host_filter": {"startswith": "SW"}, "handler": "ping"}],
        }

        root_data = {
            "include": "sub.yaml",
            "device_sources": ["nagios_pdf"],
            "rules": [{"name": "RootRule", "host_filter": {"startswith": "FGT"}, "handler": "fortigate"}],
        }

        resolved = resolve_includes(root_data, self.test_dir)
        self.assertEqual(resolved["device_sources"], ["nagios_pdf"])
        self.assertEqual(resolved["credentials"]["username"], "admin")
        self.assertEqual(len(resolved["rules"]), 2)

    @patch("utils.config.yaml")
    def test_resolve_includes_circular_detection(self, mock_yaml):
        file_a = os.path.join(self.test_dir, "a.yaml")
        with open(file_a, "w") as f:
            f.write("include: b.yaml\n")

        # Mock safe_load when loading b.yaml to include a.yaml
        def fake_load(stream):
            return {"include": "a.yaml"}

        mock_yaml.safe_load.side_effect = fake_load

        root_data = {"include": "a.yaml"}
        with self.assertRaises(ConfigValidationError) as ctx:
            resolve_includes(root_data, self.test_dir)
        self.assertIn("Circular include detected", str(ctx.exception))

    def test_resolve_includes_missing_file_raises_error(self):
        root_data = {"include": "non_existent_file.yaml"}
        with self.assertRaises(ConfigValidationError) as ctx:
            resolve_includes(root_data, self.test_dir)
        self.assertIn("Included configuration file 'non_existent_file.yaml' not found", str(ctx.exception))

    def test_match_rules_single_string_and_regex_alternation(self):
        """Verifies match_rules supports startswith string and regex alternation."""
        from main import match_rules

        rules = [
            {
                "name": "PrefixRule",
                "host_filter": {"startswith": "SW-CORE"},
                "handler": "aruba",
            },
            {
                "name": "RegexAlternationRule",
                "host_filter": {"regex": r"^(SW-ACCESS|AP-\d+)"},
                "handler": "generic_ping",
            },
        ]

        # Single prefix startswith
        self.assertEqual(len(match_rules("SW-CORE-01", rules)), 1)
        self.assertEqual(match_rules("SW-CORE-01", rules)[0]["name"], "PrefixRule")

        # Regex alternation matching multiple conditions
        self.assertEqual(len(match_rules("SW-ACCESS-02", rules)), 1)
        self.assertEqual(match_rules("SW-ACCESS-02", rules)[0]["name"], "RegexAlternationRule")
        self.assertEqual(len(match_rules("AP-101", rules)), 1)
        self.assertEqual(match_rules("AP-101", rules)[0]["name"], "RegexAlternationRule")

        # Non-matching host
        self.assertEqual(len(match_rules("ROUTER-01", rules)), 0)

    def test_validate_config_rejects_list_for_startswith_or_regex(self):
        """Verifies validate_config rejects non-string startswith or regex."""
        # startswith as list should fail
        cfg_list_startswith = {
            "rules": [
                {
                    "name": "BadRule",
                    "host_filter": {"startswith": ["SW-01", "SW-02"]},
                    "handler": "aruba",
                }
            ]
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(cfg_list_startswith)
        self.assertIn("host_filter 'startswith' must be a string", str(ctx.exception))

        # regex as list should fail
        cfg_list_regex = {
            "rules": [
                {
                    "name": "BadRule",
                    "host_filter": {"regex": ["^SW", "^AP"]},
                    "handler": "aruba",
                }
            ]
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(cfg_list_regex)
        self.assertIn("host_filter 'regex' must be a string", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
