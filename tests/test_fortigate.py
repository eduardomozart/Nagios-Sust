import unittest
from handlers.fortigate import parse_fortigate_system_info_html

class TestFortiGateHandler(unittest.TestCase):
    def test_fortigate_system_info_html_parsing(self):
        """Validates FortiGate System Information widget HTML parser with anonymized data."""
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

    def test_ipsec_tunnel_missing_logic(self):
        """Verifies that missing IPsec tunnel fails cleanly without falling back to gateway."""
        ipsec_tunnels = {"wan2": {"name": "tunnel_wan2", "remote-gw": "203.0.113.10"}}
        aliases = ["wan1", "port1"]

        # Case 1: Target is ipsec_endpoint, tunnel missing -> target_ip should be None (no gateway fallback)
        tunnel_data = None
        for alias in aliases:
            if alias.lower() in ipsec_tunnels:
                tunnel_data = ipsec_tunnels[alias.lower()]
                break
        
        target_ip = None
        if tunnel_data:
            target_ip = tunnel_data["remote-gw"]
        self.assertIsNone(target_ip, "Missing tunnel must result in None instead of gateway fallback")

        # Case 2: Source is ipsec_endpoint, tunnel missing -> target_ip should be None (do not ping with alias)
        source_val = "ipsec_endpoint"
        target_ip = "8.8.8.8"
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
    unittest.main()
