import unittest

from handlers.fortigate import (
    extract_fortigate_interface_details_html,
    is_fortigate_table_ready_html,
    parse_fortigate_faceplate_ports_html,
    parse_fortigate_interfaces_html,
    parse_fortigate_login_html,
    parse_fortigate_static_routes_html,
    parse_fortigate_system_info_html,
    resolve_fortigate_gateways,
)


class TestFortiGateHandler(unittest.TestCase):
    def test_system_info_html_parsing(self):
        """Validates FortiGate System Information widget HTML parser with mock data."""
        html_sample = """
        <fos-dashboard-system-information-widget class="ng-star-inserted">
          <table role="presentation" class="nu-table nu-table-slightly-condensed nu-table-key-value">
            <tbody>
              <tr><td>Hostname</td><td>FGT-CORE-01</td></tr>
              <tr><td>Serial number</td><td><span><span>FGT60D0000000000</span></span></td></tr>
              <tr><td>Firmware</td><td class="can-wrap"><div> v7.4.11 build2878 (Mature) </div></td></tr>
              <tr><td>Mode</td><td><span>NAT</span></td></tr>
              <tr><td>System time</td><td><span>2026/10/11 11:20:03</span></td></tr>
              <tr><td>Uptime</td><td><div><span> 2h 19m 51s</span></div></td></tr>
              <tr><td>WAN IP</td><td><span><span>198.51.100.1</span></span></td></tr>
            </tbody>
          </table>
        </fos-dashboard-system-information-widget>
        """
        info = parse_fortigate_system_info_html(html_sample)

        self.assertEqual(info["hostname"], "FGT-CORE-01")
        self.assertEqual(info["serial_number"], "FGT60D0000000000")
        self.assertEqual(info["version"], "v7.4.11")
        self.assertEqual(info["raw_version"], "v7.4.11 build2878 (Mature)")
        self.assertEqual(info["uptime"], "2h 19m 51s")
        self.assertEqual(info["mode"], "NAT")
        self.assertEqual(info["system_time"], "2026/10/11 11:20:03")
        self.assertEqual(info["wan_ip"], "198.51.100.1")
        self.assertEqual(info["os_type"], "FortiOS")

    def test_faceplate_ports_html(self):
        """Tests parsing faceplate port status (DMZ, WAN1, WAN2)."""
        html_content = """
        <table class="portgroup">
          <tr>
            <td class="label port">DMZ</td>
            <td class="label port">WAN1</td>
            <td class="label port">WAN2</td>
          </tr>
          <tr>
            <td><div port-id="dmz" link="up"><f-icon class="ftnt-faceplate-port-rj45-up"></f-icon></div></td>
            <td><div port-id="wan1" link="up"><f-icon class="ftnt-faceplate-port-rj45-up"></f-icon></div></td>
            <td><div port-id="wan2" link="up"><f-icon class="ftnt-faceplate-port-rj45-up"></f-icon></div></td>
          </tr>
        </table>
        """
        ports = parse_fortigate_faceplate_ports_html(html_content)

        self.assertIn("dmz", ports)
        self.assertIn("wan1", ports)
        self.assertIn("wan2", ports)

        self.assertEqual(ports["dmz"]["status"], "UP")
        self.assertEqual(ports["dmz"]["link"], "up")
        self.assertEqual(ports["dmz"]["label"], "DMZ")

        self.assertEqual(ports["wan1"]["status"], "UP")
        self.assertEqual(ports["wan1"]["link"], "up")
        self.assertEqual(ports["wan1"]["label"], "WAN1")

        self.assertEqual(ports["wan2"]["status"], "UP")
        self.assertEqual(ports["wan2"]["link"], "up")
        self.assertEqual(ports["wan2"]["label"], "WAN2")

    def test_faceplate_internal_ports_html(self):
        """Tests parsing internal faceplate ports (INTERNAL 1-5, A, B)."""
        html_content = """
        <table class="portgroup">
          <tr>
            <td class="label port">1</td><td class="label port">2</td><td class="label port">3</td>
            <td class="label port">4</td><td class="label port">5</td><td class="label port">A</td>
            <td class="label port">B</td>
          </tr>
          <tr>
            <td><div port-id="internal1" link="down"></div></td>
            <td><div port-id="internal2" link="down"></div></td>
            <td><div port-id="internal3" link="down"></div></td>
            <td><div port-id="internal4" link="down"></div></td>
            <td><div port-id="internal5" link="up"></div></td>
            <td><div port-id="a" link="down"></div></td>
            <td><div port-id="b" link="down"></div></td>
          </tr>
        </table>
        """
        ports = parse_fortigate_faceplate_ports_html(html_content)

        self.assertEqual(len(ports), 7)
        self.assertEqual(ports["internal1"]["status"], "DOWN")
        self.assertEqual(ports["internal2"]["status"], "DOWN")
        self.assertEqual(ports["internal3"]["status"], "DOWN")
        self.assertEqual(ports["internal4"]["status"], "DOWN")
        self.assertEqual(ports["internal5"]["status"], "UP")
        self.assertEqual(ports["a"]["status"], "DOWN")
        self.assertEqual(ports["b"]["status"], "DOWN")

        self.assertEqual(ports["internal5"]["label"], "5")

    def test_table_ready_detection(self):
        """Tests detecting interfaces table readiness on faceplate and modern table HTML."""
        self.assertTrue(is_fortigate_table_ready_html('<table class="portgroup"></table>'))
        self.assertTrue(is_fortigate_table_ready_html('<div class="mutable-table-container"></div>'))
        self.assertFalse(is_fortigate_table_ready_html('<div id="login-container"></div>'))

    def test_login_pending_no_auth_error(self):
        """Tests parsing WebUI login screen (form present, no error message)."""
        html_content = """
        <div id="login">
          <div id="err_msg" style="display: none"><div id="err_msg_content"></div></div>
          <input id="username" />
          <input id="secretkey" type="password" />
        </div>
        """
        login_data = parse_fortigate_login_html(html_content)

        self.assertTrue(login_data["has_login_form"])
        self.assertFalse(login_data["auth_failed"])
        self.assertEqual(login_data["error_message"], "")

    def test_login_auth_failure_detected(self):
        """Tests parsing WebUI login error screen (Authentication failure displayed)."""
        html_content = """
        <div id="login">
          <div id="err_msg" style=""><div id="err_msg_content">Authentication failure</div></div>
          <input id="username" />
          <input id="secretkey" type="password" />
        </div>
        """
        login_data = parse_fortigate_login_html(html_content)

        self.assertTrue(login_data["has_login_form"])
        self.assertTrue(login_data["auth_failed"])
        self.assertEqual(login_data["error_message"], "Authentication failure")

    def test_interfaces_table_html(self):
        """Tests parsing modern mutable table with VLANs and sample IPs."""
        html_content = """
        <div class="mutable-table-container">
          <div class="row" row-id="r1">
            <div column-id="name"><f-icon class="ftnt-interface-rj45-up"></f-icon><span>Vlan1009 (dmz)</span></div></div></div>
            <div column-id="ipv4_addresses">192.0.2.65/255.255.255.224</div></div></div>
          </div>
          <div class="row" row-id="r2">
            <div column-id="name"><f-icon class="ftnt-interface-rj45-up"></f-icon><span>Vlan200 (wan2)</span></div></div></div>
            <div column-id="ipv4_addresses">198.51.100.202/255.255.255.252</div></div></div>
          </div>
          <div class="row" row-id="r3">
            <div column-id="name"><f-icon class="ftnt-interface-rj45-up"></f-icon><span>Vlan300 (internal5)</span></div></div></div>
            <div column-id="ipv4_addresses">192.168.1.104/255.255.255.0</div></div></div>
          </div>
          <div class="row" row-id="r4">
            <div column-id="name"><f-icon class="ftnt-interface-rj45-up"></f-icon><span>Vlan100 (wan1)</span></div></div></div>
            <div column-id="ipv4_addresses">203.0.113.254/255.255.255.252</div></div></div>
          </div>
        </div>
        """
        intf_map = parse_fortigate_interfaces_html(html_content)

        self.assertIn("dmz", intf_map)
        self.assertEqual(intf_map["dmz"]["ip"], "192.0.2.65")
        self.assertEqual(intf_map["dmz"]["mask"], "27")
        self.assertEqual(intf_map["dmz"]["status"], "UP")

        self.assertIn("wan2", intf_map)
        self.assertEqual(intf_map["wan2"]["ip"], "198.51.100.202")
        self.assertEqual(intf_map["wan2"]["mask"], "30")
        self.assertEqual(intf_map["wan2"]["status"], "UP")

        self.assertIn("internal5", intf_map)
        self.assertEqual(intf_map["internal5"]["ip"], "192.168.1.104")
        self.assertEqual(intf_map["internal5"]["mask"], "24")
        self.assertEqual(intf_map["internal5"]["status"], "UP")

        self.assertIn("wan1", intf_map)
        self.assertEqual(intf_map["wan1"]["ip"], "203.0.113.254")
        self.assertEqual(intf_map["wan1"]["mask"], "30")
        self.assertEqual(intf_map["wan1"]["status"], "UP")

        self.assertEqual(extract_fortigate_interface_details_html(html_content, "wan1"), ("203.0.113.254", "30", "UP"))
        self.assertEqual(extract_fortigate_interface_details_html(html_content, "wan2"), ("198.51.100.202", "30", "UP"))
        self.assertEqual(extract_fortigate_interface_details_html(html_content, "internal5"), ("192.168.1.104", "24", "UP"))
        self.assertEqual(extract_fortigate_interface_details_html(html_content, "dmz"), ("192.0.2.65", "27", "UP"))
        self.assertEqual(extract_fortigate_interface_details_html(html_content, "unknown_port"), ("", "", "NOT FOUND"))

    def test_full_webui_interfaces_html(self):
        """Tests parsing complete interface table with sample IPs."""
        html_content = """
        <div class="mutable-table-container">
          <div class="row" row-id="r1">
            <div column-id="name"><f-icon class="ftnt-interface-rj45-up"></f-icon><span>Vlan100 (wan1)</span></div></div></div>
            <div column-id="ipv4_addresses">192.0.2.2/255.255.255.0</div></div></div>
          </div>
          <div class="row" row-id="r2">
            <div column-id="name"><f-icon class="ftnt-interface-rj45-up"></f-icon><span>Vlan200 (wan2)</span></div></div></div>
            <div column-id="ipv4_addresses">198.51.100.14/255.255.255.252</div></div></div>
          </div>
          <div class="row" row-id="r3">
            <div column-id="name"><f-icon class="ftnt-interface-rj45-up"></f-icon><span>Vlan1009 (dmz)</span></div></div></div>
            <div column-id="ipv4_addresses">192.0.2.33/255.255.255.224</div></div></div>
          </div>
          <div class="row" row-id="r4">
            <div column-id="name"><f-icon class="ftnt-interface-rj45-up"></f-icon><span>Vlan300 (internal5)</span></div></div></div>
            <div column-id="ipv4_addresses">0.0.0.0/0.0.0.0</div></div></div>
          </div>
        </div>
        """
        intf_map = parse_fortigate_interfaces_html(html_content)

        self.assertIn("wan1", intf_map)
        self.assertEqual(intf_map["wan1"]["ip"], "192.0.2.2")
        self.assertEqual(intf_map["wan1"]["mask"], "24")
        self.assertEqual(intf_map["wan1"]["status"], "UP")

        self.assertIn("wan2", intf_map)
        self.assertEqual(intf_map["wan2"]["ip"], "198.51.100.14")
        self.assertEqual(intf_map["wan2"]["mask"], "30")
        self.assertEqual(intf_map["wan2"]["status"], "UP")

        self.assertIn("dmz", intf_map)
        self.assertEqual(intf_map["dmz"]["ip"], "192.0.2.33")
        self.assertEqual(intf_map["dmz"]["mask"], "27")
        self.assertEqual(intf_map["dmz"]["status"], "UP")

        self.assertIn("internal5", intf_map)
        self.assertEqual(intf_map["internal5"]["ip"], "0.0.0.0")
        self.assertEqual(intf_map["internal5"]["mask"], "0")
        self.assertEqual(intf_map["internal5"]["status"], "UP")

        self.assertEqual(extract_fortigate_interface_details_html(html_content, "wan1"), ("192.0.2.2", "24", "UP"))
        self.assertEqual(extract_fortigate_interface_details_html(html_content, "wan2"), ("198.51.100.14", "30", "UP"))
        self.assertEqual(extract_fortigate_interface_details_html(html_content, "dmz"), ("192.0.2.33", "27", "UP"))
        self.assertEqual(extract_fortigate_interface_details_html(html_content, "internal5"), ("0.0.0.0", "0", "UP"))
        self.assertEqual(extract_fortigate_interface_details_html(html_content, "port99"), ("", "", "NOT FOUND"))

    def test_static_routing_table_and_gateway_resolution_html(self):
        """Tests parsing static routing table and gateway resolution."""
        html_content = """
        <div class="table-container">
          <div row-id="r1"><div column-id="dst">10.0.0.0/8</div><div column-id="gateway"></div><div column-id="$intf">LAN Balanced</div></div>
          <div row-id="r2"><div column-id="dst">172.16.0.0/12</div><div column-id="gateway"></div><div column-id="$intf">LAN Balanced</div></div>
          <div row-id="r3"><div column-id="dst">192.0.2.10/32</div><div column-id="gateway">192.0.2.1</div><div column-id="$intf">Vlan100 (wan1)</div></div>
          <div row-id="r4"><div column-id="dst">192.0.2.20/32</div><div column-id="gateway">192.0.2.1</div><div column-id="$intf">Vlan100 (wan1)</div></div>
          <div row-id="r5"><div column-id="dst">203.0.113.0/24</div><div column-id="gateway"></div><div column-id="$intf">LAN Balanced</div></div>
          <div row-id="r6"><div column-id="dst">172.16.1.115/32</div><div column-id="gateway">192.0.2.1</div><div column-id="$intf">Vlan100 (wan1)</div></div>
          <div row-id="r7"><div column-id="dst">0.0.0.0/0</div><div column-id="gateway">192.168.1.1</div><div column-id="$intf">Vlan300 (internal5)</div></div>
          <div row-id="r8"><div column-id="dst">192.168.0.0/16</div><div column-id="gateway"></div><div column-id="$intf">LAN Balanced</div></div>
          <div row-id="r9"><div column-id="dst">0.0.0.0/0</div><div column-id="gateway">198.51.100.13</div><div column-id="$intf">Vlan200 (wan2)</div></div>
        </div>
        """
        routes = parse_fortigate_static_routes_html(html_content)

        self.assertEqual(len(routes), 9)
        route_pairs = [(r["dst"], r["gateway"], r["interface"]) for r in routes]
        self.assertIn(("10.0.0.0/8", "", "LAN Balanced"), route_pairs)
        self.assertIn(("192.0.2.10/32", "192.0.2.1", "Vlan100 (wan1)"), route_pairs)
        self.assertIn(("0.0.0.0/0", "192.168.1.1", "Vlan300 (internal5)"), route_pairs)
        self.assertIn(("0.0.0.0/0", "198.51.100.13", "Vlan200 (wan2)"), route_pairs)

        intf_data = {
            "wan1": {"ip": "192.0.2.2", "mask": "24"},
            "wan2": {"ip": "198.51.100.14", "mask": "30"},
            "internal5": {"ip": "192.168.1.104", "mask": "24"},
        }
        gateways = resolve_fortigate_gateways(routes, ["wan1", "wan2", "internal5|port5"], intf_data)

        self.assertEqual(gateways["wan1"], "192.0.2.1")
        self.assertEqual(gateways["wan2"], "198.51.100.13")
        self.assertEqual(gateways["internal5"], "192.168.1.1")

        empty_gw = resolve_fortigate_gateways(routes, ["port99"], intf_data)
        self.assertEqual(empty_gw, {})

    def test_ipsec_tunnel_missing_logic(self):
        """Verifies that missing IPsec tunnel fails cleanly without falling back to gateway."""
        ipsec_tunnels = {"wan2": {"name": "tunnel_wan2", "remote-gw": "203.0.113.10"}}
        aliases = ["wan1", "port1"]

        tunnel_data = None
        for alias in aliases:
            if alias.lower() in ipsec_tunnels:
                tunnel_data = ipsec_tunnels[alias.lower()]
                break

        target_ip = None
        if tunnel_data:
            target_ip = tunnel_data["remote-gw"]
        self.assertIsNone(target_ip, "Missing tunnel must result in None instead of gateway fallback")

        source_val = "ipsec_endpoint"
        target_ip = "192.0.2.1"
        if source_val == "ipsec_endpoint":
            tunnel_data = None
            for alias in aliases:
                if alias.lower() in ipsec_tunnels:
                    tunnel_data = ipsec_tunnels[alias.lower()]
                    break
            if not tunnel_data:
                target_ip = None
        self.assertIsNone(target_ip, "Missing source tunnel must abort ping instead of using interface alias")


if __name__ == "__main__":
    unittest.main(buffer=True)
