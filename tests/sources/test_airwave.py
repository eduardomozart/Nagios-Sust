import unittest
from unittest.mock import patch, MagicMock
from sources import airwave
from utils.exit_codes import ERR_AIRWAVE_API_ERROR


class TestAirwaveSource(unittest.TestCase):
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
            folders=None,
        )

    @patch("sources.airwave.AirWaveClient")
    def test_airwave_source_with_folders_filter(self, mock_client_cls):
        """Tests that folders configuration in airwave config is normalized and passed to get_devices."""
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
                "folder_id": "10",
                "folder": "Building 1",
                "folder_path": "Top > Campus A > Building 1",
            }
        ]

        config = {
            "device_sources": ["airwave"],
            "airwave": {
                "url": "https://airwave.local",
                "username": "admin",
                "password": "secretpassword",
                "folders": ["Campus A", "Campus B"],
            },
        }

        hosts = airwave.get_hosts(config)
        self.assertEqual(len(hosts), 1)
        self.assertEqual(hosts[0]["host"], "SW-CORE-01")
        self.assertEqual(hosts[0]["folder_id"], "10")
        self.assertEqual(hosts[0]["folder"], "Building 1")
        self.assertEqual(hosts[0]["folder_path"], "Top > Campus A > Building 1")
        mock_client.get_devices.assert_called_with(
            host_filter=None,
            device_categories=None,
            models=None,
            folders=["Campus A", "Campus B"],
        )

    @patch("sources.airwave.AirWaveClient")
    def test_airwave_source_with_subfolder_path_filter(self, mock_client_cls):
        """Tests that subfolder paths (e.g. 'Campus A > Building 1') in config are normalized and passed."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_devices.return_value = []

        config = {
            "airwave": {
                "url": "https://airwave.local",
                "username": "admin",
                "password": "secretpassword",
                "folders": ["Campus A > Building 1", "Top > Campus B > Building 2"],
            },
        }

        airwave.get_hosts(config)
        mock_client.get_devices.assert_called_with(
            host_filter=None,
            device_categories=None,
            models=None,
            folders=["Campus A > Building 1", "Top > Campus B > Building 2"],
        )

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


if __name__ == "__main__":
    unittest.main(buffer=True)
