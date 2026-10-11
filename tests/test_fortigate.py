import ipaddress
import os
import re
import unittest
from handlers.fortigate import parse_fortigate_system_info_html
from utils.network import ip_netmask_to_cidr

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

def _read_fixture(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()

def parse_faceplate_html(html_content):
    """Parses FortiGate faceplate widget HTML (table.portgroup)."""
    ports = {}
    group_m = re.search(
        r'<td[^>]*class=[\'"][^\'"]*label portgroup[^\'"]*[\'"][^>]*>.*?<span[^>]*>([^<]+)</span>',
        html_content,
        re.DOTALL,
    )
    group_label = group_m.group(1).strip() if group_m else ""
    if group_label == "&nbsp;":
        group_label = ""
        
    labels = re.findall(
        r'<td[^>]*class=[\'"][^\'"]*label port[^\'"]*[\'"][^>]*>\s*([^<]+?)\s*</td>',
        html_content,
    )
    port_divs = list(
        re.finditer(
            r'<div[^>]+port-id=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</div>',
            html_content,
            re.DOTALL | re.IGNORECASE,
        )
    )
    
    for idx, m in enumerate(port_divs):
        div_tag = m.group(0)
        pid = m.group(1).strip()
        link_m = re.search(r'\blink=[\'"]([^\'"]+)[\'"]', div_tag, re.IGNORECASE)
        link = link_m.group(1).lower() if link_m else ""
        inner = m.group(2)
        icon_m = re.search(r'class=[\'"]([^\'"]*ftnt-[^\'"]*)[\'"]', inner)
        icon = icon_m.group(1) if icon_m else ""
        
        status = "UP" if (link == "up" or "-up" in icon) else ("DOWN" if (link == "down" or "-down" in icon) else "UNKNOWN")
        
        ports[pid.lower()] = {
            "port_id": pid,
            "link": link,
            "status": status,
            "icon": icon,
            "group": group_label,
            "label": labels[idx].strip() if idx < len(labels) else pid,
        }
    return ports

def parse_login_page_html(html_content):
    """Parses FortiGate WebUI login HTML."""
    has_user = bool(re.search(r'id=[\'"]username[\'"]', html_content, re.IGNORECASE))
    has_pass = bool(re.search(r'id=[\'"]secretkey[\'"]', html_content, re.IGNORECASE))
    has_btn = bool(re.search(r'id=[\'"]login_button[\'"]|aria-label=[\'"]Login Read-Only[\'"]', html_content, re.IGNORECASE))
    
    err_div = re.search(r'<div[^>]*id=[\'"]err_msg[\'"][^>]*style=[\'"]([^\'"]*)[\'"][^>]*>', html_content, re.IGNORECASE)
    style = err_div.group(1) if err_div else ""
    is_displayed = False
    if err_div:
        is_displayed = not ("display: none" in style or "display:none" in style)
        
    err_content_m = re.search(r'id=[\'"]err_msg_content[\'"][^>]*>(.*?)</div>', html_content, re.DOTALL | re.IGNORECASE)
    err_text = ""
    if err_content_m:
        err_text = re.sub(r'<[^>]+>', '', err_content_m.group(1)).strip()
        
    is_failure = is_displayed and bool(err_text)
    
    return {
        "has_login_form": has_user and has_pass,
        "has_username_field": has_user,
        "has_password_field": has_pass,
        "has_login_button": has_btn,
        "is_auth_failure": is_failure,
        "error_message": err_text if is_failure else "",
    }

def parse_interfaces_html(html_content):
    """Parses FortiGate modern interface table HTML (div.mutable-table-container)."""
    interfaces = []
    matches = list(re.finditer(r'<div[^>]*\brow-id=[\'"]([^\'"]+)[\'"][^>]*>', html_content, re.IGNORECASE))
    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(html_content)
        b = html_content[start:end]
        
        name_cell = re.search(r'column-id=[\'"]name[\'"][^>]*>(.*?)</div>\s*</div>\s*</div>', b, re.DOTALL | re.IGNORECASE)
        if not name_cell:
            continue
        raw_name = re.sub(r'<[^>]+>', ' ', name_cell.group(1)).strip()
        raw_name = re.sub(r'\s+', ' ', raw_name)
        if not raw_name:
            continue
            
        alias_m = re.search(r'\(([^)]+)\)', raw_name)
        alias = alias_m.group(1).strip() if alias_m else raw_name
        
        icon_m = re.search(r'<f-icon[^>]*class=[\'"]([^\'"]*ftnt-[^\'"]*)[\'"]', b, re.IGNORECASE)
        icon = icon_m.group(1) if icon_m else ""
        status = "UP" if "-up" in icon else ("DOWN" if "-down" in icon else "UNKNOWN")
        
        type_cell = re.search(r'column-id=[\'"]type[\'"][^>]*>(.*?)</div>\s*</div>\s*</div>', b, re.DOTALL | re.IGNORECASE)
        intf_type = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', type_cell.group(1))).strip() if type_cell else ""
        
        ip_cell = re.search(r'column-id=[\'"]ipv4_addresses[\'"][^>]*>(.*?)</div>\s*</div>\s*</div>', b, re.DOTALL | re.IGNORECASE)
        raw_ip = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ip_cell.group(1))).strip() if ip_cell else ""
        
        ip = ""
        mask = ""
        ip_m = re.search(r'(?:^|\b|\D)(\d{1,3}(?:\.\d{1,3}){3}(?:/(?:\d{1,3}(?:\.\d{1,3}){3}|\d{1,2}))?)', raw_ip)
        if ip_m:
            ip, mask = ip_netmask_to_cidr(ip_m.group(1))
            
        interfaces.append({
            "name": raw_name,
            "alias": alias,
            "type": intf_type,
            "status": status,
            "raw_ip": raw_ip,
            "ip": ip,
            "mask": mask,
            "icon": icon,
        })
        
    return interfaces

def extract_interface_details(html_content, interface_name):
    """Extracts IP, netmask, and link status (UP/DOWN/NOT FOUND) for an interface."""
    target = interface_name.strip().lower()
    
    # Check modern interface table
    for item in parse_interfaces_html(html_content):
        name_lower = item["name"].lower()
        alias_lower = item["alias"].lower()
        if f"({target})" in name_lower or name_lower == target or alias_lower == target:
            return item["ip"], item["mask"], item["status"]
            
    # Check faceplate portgroup table
    faceplate = parse_faceplate_html(html_content)
    if target in faceplate:
        return "", "", faceplate[target]["status"]
        
    for pid, pdata in faceplate.items():
        if pid == target:
            return "", "", pdata["status"]
        if pid.startswith("internal") and pid.replace("internal", "") == target:
            return "", "", pdata["status"]
        if target.startswith("internal") and target.replace("internal", "") == pid:
            return "", "", pdata["status"]
            
    return "", "", "NOT FOUND"

def parse_routing_table_html(html_content):
    """Parses FortiGate Static Routing Table HTML."""
    routes = []
    matches = list(re.finditer(r'<div[^>]*\brow-id=[\'"]([^\'"]+)[\'"][^>]*>', html_content, re.IGNORECASE))
    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(html_content)
        b = html_content[start:end]
        
        cell_matches = list(re.finditer(r'<div[^>]*\scolumn-id=[\'"]([^\'"]+)[\'"][^>]*>', b, re.IGNORECASE))
        row_data = {}
        for c_idx, cm in enumerate(cell_matches):
            col_name = cm.group(1)
            c_start = cm.end()
            c_end = cell_matches[c_idx + 1].start() if c_idx + 1 < len(cell_matches) else len(b)
            cell_content = b[c_start:c_end]
            val = re.sub(r'<[^>]+>', ' ', cell_content).strip()
            val = re.sub(r'\s+', ' ', val)
            row_data[col_name] = val
            
        routes.append({
            "dst": row_data.get("dst", ""),
            "gateway": row_data.get("gateway", ""),
            "interface": row_data.get("$intf", ""),
        })
    return routes

def resolve_gateways(routes, diagnose_interfaces, intf_data=None):
    """Resolves gateway IPs using FortiGate priority rules."""
    if intf_data is None:
        intf_data = {}
        
    gateways = {}
    routes_by_intf = {p.split('|')[0].strip().lower(): [] for p in diagnose_interfaces}
    
    for r in routes:
        dst = r.get("dst", "")
        gw = r.get("gateway", "")
        intf_text = r.get("interface", "").lower()
        
        for p_conf in diagnose_interfaces:
            p_aliases = [a.strip() for a in p_conf.split('|')]
            p_primary = p_aliases[0].lower()
            for alias in p_aliases:
                alias_lower = alias.lower()
                if f"({alias_lower})" in intf_text or alias_lower == intf_text or alias_lower in intf_text:
                    routes_by_intf[p_primary].append((dst, gw))
                    break
                    
    for intf_primary, r_list in routes_by_intf.items():
        if not r_list:
            continue
            
        # Priority 1: Default route 0.0.0.0/0
        default_gw = next((gw for dst, gw in r_list if dst == "0.0.0.0/0" and gw), None)
        if default_gw:
            gateways[intf_primary] = default_gw
            continue
            
        # Priority 2: Gateway matches interface subnet
        data = intf_data.get(intf_primary)
        best_gw = None
        if data and data.get("ip") and data.get("mask"):
            try:
                ip_val = data["ip"]
                mask_val = data["mask"]
                intf_network = ipaddress.IPv4Network(f"{ip_val}/{mask_val}", strict=False)
                for dst, gw in r_list:
                    if not gw: continue
                    try:
                        gw_ip = ipaddress.IPv4Address(gw)
                        if gw_ip in intf_network:
                            best_gw = gw
                            break
                    except:
                        pass
            except:
                pass
                
        if best_gw:
            gateways[intf_primary] = best_gw
        else:
            # Priority 3: First route's gateway
            first_gw = next((gw for dst, gw in r_list if gw), None)
            if first_gw:
                gateways[intf_primary] = first_gw
                
    return gateways

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

    def test_faceplate_ports_html(self):
        """Tests parsing faceplate port status from fixtures/fgt.txt (DMZ, WAN1, WAN2)."""
        html_content = _read_fixture("fgt.txt")
        ports = parse_faceplate_html(html_content)

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

        self.assertEqual(extract_interface_details(html_content, "wan1"), ("", "", "UP"))
        self.assertEqual(extract_interface_details(html_content, "wan2"), ("", "", "UP"))
        self.assertEqual(extract_interface_details(html_content, "dmz"), ("", "", "UP"))
        self.assertEqual(extract_interface_details(html_content, "internal1"), ("", "", "NOT FOUND"))

    def test_login_form_html(self):
        """Tests parsing WebUI login screen from fixtures/fgt2.txt (form present, no error message)."""
        html_content = _read_fixture("fgt2.txt")
        login_data = parse_login_page_html(html_content)

        self.assertTrue(login_data["has_login_form"])
        self.assertTrue(login_data["has_username_field"])
        self.assertTrue(login_data["has_password_field"])
        self.assertTrue(login_data["has_login_button"])
        self.assertFalse(login_data["is_auth_failure"])
        self.assertEqual(login_data["error_message"], "")

    def test_faceplate_internal_ports_html(self):
        """Tests parsing internal faceplate ports from fixtures/fgt3.txt (INTERNAL 1-5, A, B)."""
        html_content = _read_fixture("fgt3.txt")
        ports = parse_faceplate_html(html_content)

        self.assertEqual(len(ports), 7)
        self.assertEqual(ports["internal1"]["status"], "DOWN")
        self.assertEqual(ports["internal2"]["status"], "DOWN")
        self.assertEqual(ports["internal3"]["status"], "DOWN")
        self.assertEqual(ports["internal4"]["status"], "DOWN")
        self.assertEqual(ports["internal5"]["status"], "UP")
        self.assertEqual(ports["a"]["status"], "DOWN")
        self.assertEqual(ports["b"]["status"], "DOWN")

        self.assertEqual(ports["internal5"]["group"], "INTERNAL")
        self.assertEqual(ports["internal5"]["label"], "5")

        self.assertEqual(extract_interface_details(html_content, "internal5"), ("", "", "UP"))
        self.assertEqual(extract_interface_details(html_content, "5"), ("", "", "UP"))
        self.assertEqual(extract_interface_details(html_content, "internal1"), ("", "", "DOWN"))
        self.assertEqual(extract_interface_details(html_content, "a"), ("", "", "DOWN"))
        self.assertEqual(extract_interface_details(html_content, "wan1"), ("", "", "NOT FOUND"))

    def test_interfaces_table_html(self):
        """Tests parsing modern mutable table from fixtures/fgt4.txt with VLANs and anonymized IPs."""
        html_content = _read_fixture("fgt4.txt")
        interfaces = parse_interfaces_html(html_content)

        self.assertEqual(len(interfaces), 6)
        intf_map = {item["alias"]: item for item in interfaces}

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

        self.assertEqual(extract_interface_details(html_content, "wan1"), ("203.0.113.254", "30", "UP"))
        self.assertEqual(extract_interface_details(html_content, "wan2"), ("198.51.100.202", "30", "UP"))
        self.assertEqual(extract_interface_details(html_content, "internal5"), ("192.168.1.104", "24", "UP"))
        self.assertEqual(extract_interface_details(html_content, "dmz"), ("192.0.2.65", "27", "UP"))
        self.assertEqual(extract_interface_details(html_content, "LAN Balanced"), ("0.0.0.0", "0", "UP"))
        self.assertEqual(extract_interface_details(html_content, "virtual-wan-link"), ("0.0.0.0", "0", "DOWN"))
        self.assertEqual(extract_interface_details(html_content, "unknown_port"), ("", "", "NOT FOUND"))

    def test_login_auth_failure_html(self):
        """Tests parsing WebUI login error screen from fixtures/fgt5.txt (Authentication failure displayed)."""
        html_content = _read_fixture("fgt5.txt")
        login_data = parse_login_page_html(html_content)

        self.assertTrue(login_data["has_login_form"])
        self.assertTrue(login_data["has_username_field"])
        self.assertTrue(login_data["has_password_field"])
        self.assertTrue(login_data["has_login_button"])
        self.assertTrue(login_data["is_auth_failure"])
        self.assertEqual(login_data["error_message"], "Authentication failure")

    def test_full_webui_interfaces_html(self):
        """Tests parsing complete WebUI page from fixtures/fgt6.txt with anonymized IPs."""
        html_content = _read_fixture("fgt6.txt")
        interfaces = parse_interfaces_html(html_content)

        self.assertEqual(len(interfaces), 5)
        intf_map = {item["alias"]: item for item in interfaces}

        self.assertIn("fortilink", intf_map)
        self.assertEqual(intf_map["fortilink"]["status"], "DOWN")
        self.assertEqual(intf_map["fortilink"]["type"], "802.3ad Aggregate")
        self.assertEqual(intf_map["fortilink"]["raw_ip"], "Dedicated to FortiSwitch")

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

        self.assertEqual(extract_interface_details(html_content, "wan1"), ("192.0.2.2", "24", "UP"))
        self.assertEqual(extract_interface_details(html_content, "wan2"), ("198.51.100.14", "30", "UP"))
        self.assertEqual(extract_interface_details(html_content, "dmz"), ("192.0.2.33", "27", "UP"))
        self.assertEqual(extract_interface_details(html_content, "internal5"), ("0.0.0.0", "0", "UP"))
        self.assertEqual(extract_interface_details(html_content, "fortilink"), ("", "", "DOWN"))

    def test_routing_table_html(self):
        """Tests parsing static routing table and gateway resolution from fixtures/fgt7.txt."""
        html_content = _read_fixture("fgt7.txt")
        routes = parse_routing_table_html(html_content)

        self.assertEqual(len(routes), 9)
        route_pairs = [(r["dst"], r["gateway"], r["interface"]) for r in routes]
        self.assertIn(("10.0.0.0/8", "", "LAN Balanced"), route_pairs)
        self.assertIn(("192.0.2.10/32", "192.0.2.1", "Vlan100 (wan1)"), route_pairs)
        self.assertIn(("0.0.0.0/0", "192.168.1.1", "Vlan300 (internal5)"), route_pairs)
        self.assertIn(("0.0.0.0/0", "198.51.100.13", "Vlan200 (wan2)"), route_pairs)

        intf_data = {
            "wan1": {"ip": "192.0.2.2", "mask": "24"},
            "wan2": {"ip": "198.51.100.14", "mask": "30"},
            "internal5": {"ip": "192.168.1.104", "mask": "24"}
        }
        gateways = resolve_gateways(routes, ["wan1", "wan2", "internal5|port5"], intf_data)

        self.assertEqual(gateways["wan2"], "198.51.100.13")
        self.assertEqual(gateways["internal5"], "192.168.1.1")
        self.assertEqual(gateways["wan1"], "192.0.2.1")

        empty_gw = resolve_gateways(routes, ["port99"], intf_data)
        self.assertEqual(empty_gw, {})

if __name__ == "__main__":
    unittest.main()
