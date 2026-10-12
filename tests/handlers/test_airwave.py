import unittest
from unittest.mock import patch, MagicMock
from utils.airwave import (
    AirWaveClient,
    filter_device_name,
    parse_airwave_device_info_html,
    parse_airwave_login_html,
    parse_devices_xml,
)
from utils.error_codes import ERR_OK, ERR_DEVICE_NOT_FOUND, ERR_DEVICE_DOWN
import handlers.airwave as airwave_handler


class TestAirWaveIntegration(unittest.TestCase):
    def test_filter_device_name_startswith(self):
        """Validates prefix matching for device names (single string)."""
        self.assertTrue(filter_device_name("SW-CORE-01", {"startswith": "SW"}))
        self.assertFalse(filter_device_name("AP-01", {"startswith": "SW"}))

    def test_filter_device_name_regex(self):
        """Validates regex matching for device names (single string and alternation)."""
        # Standard regex
        self.assertTrue(filter_device_name("SW-CORE-01", {"regex": "^SW.*01$"}))
        self.assertFalse(filter_device_name("SW-CORE-02", {"regex": "^SW.*01$"}))

        # Multiple conditions via regex alternation
        self.assertTrue(filter_device_name("SW-CORE-01", {"regex": "^(SW-CORE|AP-LAB)"}))
        self.assertTrue(filter_device_name("AP-LAB-05", {"regex": "^(SW-CORE|AP-LAB)"}))
        self.assertFalse(filter_device_name("SW-ACCESS-01", {"regex": "^(SW-CORE|AP-LAB)"}))

        # Negative lookahead
        self.assertTrue(filter_device_name("SW-CORE-01", {"regex": "^SW(?!DEMO)"}))
        self.assertFalse(filter_device_name("SWDEMO-01", {"regex": "^SW(?!DEMO)"}))

    def test_parse_devices_xml(self):
        """Validates parsing of ap_list.xml and applying category, model, and host_filter."""
        sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <amp:amp_ap_list xmlns:amp="http://www.airwave.com">
          <ap id="538">
            <name>SW-CORE-01</name>
            <lan_ip>192.0.2.11</lan_ip>
            <device_category>switch</device_category>
            <model>Aruba 6300M</model>
            <serial_number>SG0000000003</serial_number>
            <folder id="12">Campus</folder>
          </ap>
          <ap id="539">
            <name>SWACCESS01</name>
            <ip>192.0.2.12</ip>
            <device_category>switch</device_category>
            <model>Aruba 2930F</model>
            <serial_number>CN12345678</serial_number>
            <folder id="12">Campus</folder>
          </ap>
          <ap id="540">
            <name>AP-LOBBY-01</name>
            <remote_lan_ip>192.0.2.50</remote_lan_ip>
            <device_category>thin_ap</device_category>
            <model>AP-535</model>
            <serial_number>AP98765432</serial_number>
          </ap>
          <ap id="541">
            <name>(id:541)</name>
            <lan_ip>192.0.2.99</lan_ip>
          </ap>
        </amp:amp_ap_list>
        """

        # 1. Parse all valid devices
        devices = parse_devices_xml(sample_xml)
        self.assertEqual(len(devices), 3)  # (id:541) should be ignored
        self.assertEqual(devices[0]["id"], "538")
        self.assertEqual(devices[0]["name"], "SW-CORE-01")
        self.assertEqual(devices[0]["ip"], "192.0.2.11")
        self.assertEqual(devices[0]["model"], "Aruba 6300M")
        self.assertEqual(devices[0]["serial_number"], "SG0000000003")
        self.assertEqual(devices[0]["folder_id"], "12")

        # 2. Filter with startswith
        sw_devices = parse_devices_xml(sample_xml, host_filter={"startswith": "SW-CORE"})
        self.assertEqual(len(sw_devices), 1)
        self.assertEqual(sw_devices[0]["name"], "SW-CORE-01")

        # 3. Filter with device_category
        ap_devices = parse_devices_xml(sample_xml, device_categories=["thin_ap"])
        self.assertEqual(len(ap_devices), 1)
        self.assertEqual(ap_devices[0]["name"], "AP-LOBBY-01")

        # 4. Filter with model
        model_devices = parse_devices_xml(sample_xml, models=["2930F"])
        self.assertEqual(len(model_devices), 1)
        self.assertEqual(model_devices[0]["name"], "SWACCESS01")

    def test_parse_airwave_device_info_html(self):
        """Validates scraping of the AirWave Device Info table using user-provided HTML."""
        sample_html = """
        <div id="fragment_div_AP__Monitoring__InfoTable" handler_class="Mercury%3A%3AHandler%3A%3AAP%3A%3AMonitoring" request_args="id=538">
        <div class="infoTableWrapper">
        <table cellspacing="0" cellpadding="0" border="0" class="data responsive">
        <tbody><tr class="table_title"><td colspan="100%">
        <div class="title_heading">Device Info</div></td>
        </tr>
        <tr><td colspan="100%"><span class="fieldName">Status:</span> Up
        </td></tr>
        <tr>
        <td class="fieldName">Configuration:</td>
        <td colspan="100%">
        <a href="/device_config?id=538">
        Mismatched</a>
        (The settings on the device do not match the desired configuration policy.)
        </td>
        </tr>
        <tr>
        <td colspan="1" nowrap="1">Firmware:</td><td>FL.10.13.1050 (ROM: FL.01.14.0002)
        </td>
        </tr>
        <tr>
        <td nowrap="nowrap" class="fieldName">Switch Active Controller:</td><td nowrap="nowrap"><a href="/ap_monitoring?id=274">MC-01</a></td>
        <td nowrap="nowrap" class="fieldName">Switch Standby Controller:</td><td nowrap="nowrap"><a href="/ap_monitoring?id=406">MC-02</a></td>
        </tr>
        <tr>
        <td nowrap="nowrap" class="fieldName">Upstream Device:</td><td nowrap="nowrap"><a href="/ap_monitoring?id=579">SW-CORE-02</a></td>
        <td nowrap="nowrap" class="fieldName">Upstream Port:</td><td nowrap="nowrap"><a href="/interface_monitoring?id=579&amp;interface_id=2705">lag201</a></td>
        </tr>
        <tr>
        <td nowrap="nowrap" class="fieldName">Type:</td><td nowrap="nowrap">Aruba 6300 Switch</td>
        <td nowrap="nowrap" class="fieldName">Model:</td><td nowrap="nowrap">6300M 48-port HPE Smart Rate 1/2.5/5GbE Class 6 PoE and 4-port SFP56 Switch</td>
        <td nowrap="nowrap" class="fieldName">Last Contacted:</td><td nowrap="nowrap">10/11/2026 2:30 PM -03</td>
        <td nowrap="nowrap" class="fieldName">Uptime:</td><td nowrap="nowrap">2 days 18 hrs 16 mins</td>
        </tr>
        <tr>
        <td nowrap="nowrap" class="fieldName">Switch Role:</td><td nowrap="nowrap">Conductor</td>
        <td nowrap="nowrap" class="fieldName">Switch State:</td><td nowrap="nowrap">Ready</td>
        </tr>
        <tr>
        <td nowrap="nowrap" class="fieldName">Stack Topology:</td><td nowrap="nowrap">Ring</td>
        <td nowrap="nowrap" class="fieldName">Stack Operational Status:</td><td nowrap="nowrap">No Split</td>
        <td nowrap="nowrap" class="fieldName">Stack Split Policy:</td><td nowrap="nowrap">None</td>
        </tr>
        <tr>
        <td nowrap="nowrap" class="fieldName">LAN MAC Address:</td><td nowrap="nowrap">A4:0E:75:D2:8E:C0</td>
        <td nowrap="nowrap" class="fieldName">Serial:</td><td nowrap="nowrap">SG0000000003</td>
        <td nowrap="nowrap" class="fieldName">Device Model:</td><td nowrap="nowrap">JL659A</td>
        </tr>
        <tr>
        <td nowrap="nowrap" class="fieldName">IP Address:</td><td nowrap="nowrap">
        <span id="span_ip_popup"><a target="_blank" href="http://192.0.2.11/">192.0.2.11</a></span>
        </td>
        <td nowrap="nowrap" class="fieldName">Clients:</td><td nowrap="nowrap">15</td>
        <td nowrap="nowrap" class="fieldName">Usage:</td><td nowrap="nowrap">136.76 Mbps</td>
        </tr>
        <tr>
        <td nowrap="nowrap" class="fieldName">Temperature:</td><td nowrap="nowrap">24°C</td>
        </tr>
        </tbody></table>
        </div>
        </div>
        """

        info = parse_airwave_device_info_html(sample_html, device_name="SW-CORE-01")

        self.assertEqual(info["hostname"], "SW-CORE-01")
        self.assertEqual(info["status"], "Up")
        self.assertEqual(info["version"], "FL.10.13.1050")
        self.assertEqual(info["raw_version"], "FL.10.13.1050 (ROM: FL.01.14.0002)")
        self.assertEqual(info["model"], "6300M 48-port HPE Smart Rate 1/2.5/5GbE Class 6 PoE and 4-port SFP56 Switch")
        self.assertEqual(info["device_model"], "JL659A")
        self.assertEqual(info["serial_number"], "SG0000000003")
        self.assertEqual(info["uptime"], "2 days 18 hrs 16 mins")
        self.assertEqual(info["switch_role"], "Conductor")
        self.assertEqual(info["switch_state"], "Ready")
        self.assertEqual(info["stack_topology"], "Ring")
        self.assertEqual(info["mac_address"], "A4:0E:75:D2:8E:C0")
        self.assertEqual(info["ip"], "192.0.2.11")
        self.assertEqual(info["temperature"], "24°C")
        self.assertEqual(info["clients"], "15")
        self.assertEqual(info["usage"], "136.76 Mbps")
        self.assertEqual(info["os_type"], "AOS-CX")

    def test_device_lookup_logic(self):
        """Verifies device lookup by hostname, IP address, and short hostname."""
        mock_devices = [
            {"id": "538", "name": "SW-CORE-01.corp.net", "ip": "192.0.2.11"},
            {"id": "539", "name": "SWACCESS01", "ip": "192.0.2.12"},
        ]

        class MockAirWaveClient(AirWaveClient):
            def __init__(self):
                self._cached_devices = mock_devices

        client = MockAirWaveClient()

        # Match exact name
        dev1 = client.get_device_by_host("SWACCESS01")
        self.assertIsNotNone(dev1)
        self.assertEqual(dev1["id"], "539")

        # Match short name
        dev2 = client.get_device_by_host("SW-CORE-01")
        self.assertIsNotNone(dev2)
        self.assertEqual(dev2["id"], "538")

        # Match IP address
        dev3 = client.get_device_by_host("192.0.2.11")
        self.assertIsNotNone(dev3)
        self.assertEqual(dev3["id"], "538")

        # Not found
        dev4 = client.get_device_by_host("NONEXISTENT")
        self.assertIsNone(dev4)

    def test_parse_airwave_login_active_session_html(self):
        """Tests parsing AirWave WebUI HTML when user session is active (no login dialog)."""
        active_html = '<div id="header"><span class="user">admin</span></div>'
        state = parse_airwave_login_html(active_html)

        self.assertTrue(state["is_logged_in"])
        self.assertFalse(state["has_login_dialog"])
        self.assertFalse(state["login_failed"])
        self.assertEqual(state["error_message"], "")

    def test_parse_airwave_login_dialog_html(self):
        """Tests parsing AirWave WebUI HTML when login dialog is presented."""
        login_html = """
        <div id="login-container">
          <input id="login-username-id" />
          <input id="login-password-id" type="password" />
          <button id="login-button">Log In</button>
        </div>
        """
        state = parse_airwave_login_html(login_html)

        self.assertFalse(state["is_logged_in"])
        self.assertTrue(state["has_login_dialog"])
        self.assertFalse(state["login_failed"])
        self.assertEqual(state["error_message"], "")

    def test_parse_airwave_login_failure_error_html(self):
        """Tests parsing AirWave WebUI HTML when authentication failure is reported."""
        failed_html = """
        <div id="login-container">
          <input id="login-username-id" />
          <div id="login-failed">Invalid username or password</div>
        </div>
        """
        state = parse_airwave_login_html(failed_html)

        self.assertFalse(state["is_logged_in"])
        self.assertTrue(state["login_failed"])
        self.assertEqual(state["error_message"], "Invalid username or password")

    @patch("handlers.airwave.get_cached_airwave_client")
    def test_airwave_handle_device_not_found(self, mock_get_client):
        """Verifies that AirWave handler returns ERR_DEVICE_NOT_FOUND without dummy keys when device is absent."""
        mock_client = MagicMock()
        mock_client.get_device_by_host.return_value = None
        mock_get_client.return_value = mock_client

        options = {
            "airwave_server": "https://airwave.example.com",
            "username": "admin",
            "password": "secretpassword",
        }
        res = airwave_handler.handle("NONEXISTENT", {}, options)

        self.assertEqual(res["host"], "NONEXISTENT")
        self.assertEqual(res["error"], ERR_DEVICE_NOT_FOUND)

    @patch("handlers.airwave.parse_airwave_device_info_html")
    @patch("handlers.airwave.By")
    @patch("handlers.airwave.EC")
    @patch("handlers.airwave.WebDriverWait")
    @patch("handlers.airwave._login_airwave_webui")
    @patch("handlers.airwave.webdriver")
    @patch("handlers.airwave.get_cached_airwave_client")
    def test_airwave_handle_success_system_info(self, mock_get_client, mock_webdriver, mock_login, mock_wait, mock_ec, mock_by, mock_parse_info):
        """Verifies that AirWave handler captures system_info and sets error=ERR_OK without dummy keys."""
        mock_client = MagicMock()
        mock_client.get_device_by_host.return_value = {"id": "538", "name": "SW-CORE-01"}
        mock_get_client.return_value = mock_client

        mock_driver = MagicMock()
        mock_webdriver.Chrome.return_value = mock_driver

        mock_driver.find_elements.return_value = [MagicMock()]
        mock_parse_info.return_value = {
            "model": "Aruba 6300M",
            "serial_number": "SG0000000003",
            "version": "FL.10.16.1020",
            "uptime": "38 weeks",
            "status": "Up",
        }

        options = {
            "airwave_server": "https://airwave.example.com",
            "username": "admin",
            "password": "secretpassword",
            "capture_screenshot": False,
        }
        res = airwave_handler.handle("SW-CORE-01", {}, options)

        self.assertEqual(res["host"], "SW-CORE-01")
        self.assertEqual(res["error"], ERR_OK)
        self.assertIn("system_info", res)
        self.assertEqual(res["system_info"]["model"], "Aruba 6300M")
        self.assertEqual(res["system_info"]["serial_number"], "SG0000000003")


if __name__ == "__main__":
    unittest.main(buffer=True)
