try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    webdriver = None
    By = None
    WebDriverWait = None
    EC = None
from datetime import datetime
import time
import os
import re
from utils.network import ip_netmask_to_cidr, ping_host
from utils.error_codes import (
    ERR_OK,
    ERR_IF_DOWN,
    ERR_IF_LOGICAL_DOWN,
    ERR_PING_TIMEOUT,
    ERR_AUTH_FAILED,
    ERR_AUTOMATION_FAILED,
)


def parse_fortigate_faceplate_ports_html(html_content):
    """
    Parses FortiGate faceplate widget HTML (table.portgroup).
    Returns dict mapping port_id (lowercase) to its link/status/label information.
    """
    ports = {}
    if not html_content:
        return ports

    labels = re.findall(
        r'<td[^>]*class=[\'"][^\'"]*label port[^\'"]*[\'"][^>]*>\s*([^<]+?)\s*</td>',
        html_content,
        re.IGNORECASE,
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
        icon_m = re.search(r'class=[\'"]([^\'"]*ftnt-[^\'"]*)[\'"]', inner, re.IGNORECASE)
        icon = icon_m.group(1) if icon_m else ""

        status = "UP" if (link == "up" or "-up" in icon) else ("DOWN" if (link == "down" or "-down" in icon) else "UNKNOWN")
        ports[pid.lower()] = {
            "port_id": pid,
            "link": link,
            "status": status,
            "label": labels[idx].strip() if idx < len(labels) else pid,
        }
    return ports


def parse_fortigate_login_html(html_content):
    """
    Parses FortiGate WebUI login HTML to detect form presence and authentication errors.
    Returns dict:
      - has_login_form: True if username and secretkey inputs exist
      - auth_failed: True if err_msg is visible with non-empty content
      - error_message: text message if auth failed
    """
    if not html_content:
        return {"has_login_form": False, "auth_failed": False, "error_message": ""}

    has_user = bool(re.search(r'id=[\'"]username[\'"]', html_content, re.IGNORECASE))
    has_pass = bool(re.search(r'id=[\'"]secretkey[\'"]', html_content, re.IGNORECASE))

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
        "auth_failed": is_failure,
        "error_message": err_text if is_failure else "",
    }


def is_fortigate_table_ready_html(html_content):
    """
    Checks if FortiGate interfaces table (modern mutable-table-container or faceplate portgroup) is present.
    """
    if not html_content:
        return False
    return bool(
        re.search(r'table\s+class=[\'"][^\'"]*portgroup', html_content, re.IGNORECASE)
        or re.search(r'class=[\'"][^\'"]*mutable-table-container', html_content, re.IGNORECASE)
    )


def parse_fortigate_interfaces_html(html_content):
    """
    Parses FortiGate modern interface table HTML (div.mutable-table-container).
    Returns dict mapping alias/name to interface dictionary:
      {'alias': ..., 'name': ..., 'status': 'UP'/'DOWN', 'ip': ..., 'mask': ...}
    """
    interfaces = {}
    if not html_content:
        return interfaces

    matches = list(re.finditer(r'<div[^>]*\brow-id=[\'"]([^\'"]+)[\'"][^>]*>', html_content, re.IGNORECASE))
    for idx, m in enumerate(matches):
        start = m.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(html_content)
        block = html_content[start:end]

        name_cell = re.search(r'column-id=[\'"]name[\'"][^>]*>(.*?)</div>\s*</div>\s*</div>', block, re.DOTALL | re.IGNORECASE)
        if not name_cell:
            continue
        raw_name = re.sub(r'<[^>]+>', ' ', name_cell.group(1)).strip()
        raw_name = re.sub(r'\s+', ' ', raw_name)
        if not raw_name:
            continue

        alias_m = re.search(r'\(([^)]+)\)', raw_name)
        alias = alias_m.group(1).strip() if alias_m else raw_name

        icon_m = re.search(r'<f-icon[^>]*class=[\'"]([^\'"]*ftnt-[^\'"]*)[\'"]', block, re.IGNORECASE)
        icon = icon_m.group(1) if icon_m else ""
        status = "UP" if "-up" in icon else ("DOWN" if "-down" in icon else "UNKNOWN")

        ip_cell = re.search(r'column-id=[\'"]ipv4_addresses[\'"][^>]*>(.*?)</div>\s*</div>\s*</div>', block, re.DOTALL | re.IGNORECASE)
        raw_ip = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', ip_cell.group(1))).strip() if ip_cell else ""

        ip, mask = "", ""
        ip_m = re.search(r'(?:^|\b|\D)(\d{1,3}(?:\.\d{1,3}){3}(?:/(?:\d{1,3}(?:\.\d{1,3}){3}|\d{1,2}))?)', raw_ip)
        if ip_m:
            ip, mask = ip_netmask_to_cidr(ip_m.group(1))

        entry = {
            "name": raw_name,
            "alias": alias,
            "status": status,
            "ip": ip,
            "mask": mask,
        }
        interfaces[alias.lower()] = entry
        if raw_name.lower() != alias.lower():
            interfaces[raw_name.lower()] = entry

    return interfaces


def extract_fortigate_interface_details_html(html_content, interface_name):
    """
    Extracts (ip, mask, status) for interface_name from FortiGate HTML
    (evaluating modern interface table, falling back to faceplate portgroup).
    Returns (ip, mask, status).
    """
    target = interface_name.strip().lower()

    # 1. Check modern interface table
    interfaces = parse_fortigate_interfaces_html(html_content)
    if target in interfaces:
        intf = interfaces[target]
        return intf["ip"], intf["mask"], intf["status"]

    for key, intf in interfaces.items():
        if f"({target})" in key or key == target:
            return intf["ip"], intf["mask"], intf["status"]

    # 2. Check faceplate portgroup
    faceplate = parse_fortigate_faceplate_ports_html(html_content)
    if target in faceplate:
        return "", "", faceplate[target]["status"]

    for pid, pdata in faceplate.items():
        if pid == target or pid.replace("internal", "") == target or target.replace("internal", "") == pid:
            return "", "", pdata["status"]

    return "", "", "NOT FOUND"


def parse_fortigate_static_routes_html(html_content):
    """
    Parses FortiGate Static Routing Table HTML (/ng/routing/static).
    Returns list of route dicts: [{'dst': ..., 'gateway': ..., 'interface': ...}]
    """
    routes = []
    if not html_content:
        return routes

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


def resolve_fortigate_gateways(routes, diagnose_interfaces, intf_data=None):
    """
    Resolves gateway IPs for diagnose_interfaces from parsed static routes using FortiGate priority rules:
      Priority 1: Default route 0.0.0.0/0
      Priority 2: Gateway matches interface subnet
      Priority 3: First route gateway
    """
    import ipaddress

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
                    if not gw:
                        continue
                    try:
                        gw_ip = ipaddress.IPv4Address(gw)
                        if gw_ip in intf_network:
                            best_gw = gw
                            break
                    except Exception:
                        pass
            except Exception:
                pass

        if best_gw:
            gateways[intf_primary] = best_gw
        else:
            # Priority 3: First route's gateway
            first_gw = next((gw for dst, gw in r_list if gw), None)
            if first_gw:
                gateways[intf_primary] = first_gw

    return gateways


def _get_wan_details(driver, interface_name):
    try:
        # First attempt fast HTML-based extraction from current page source
        try:
            page_html = driver.page_source
            ip, mask, status = extract_fortigate_interface_details_html(page_html, interface_name)
            if status != "NOT FOUND":
                return ip, mask, status
        except Exception:
            pass

        # Restrict search to the Name column to avoid false positives in the 'Members' column
        xpath = f"//*[contains(text(), '({interface_name})') or normalize-space(text())='{interface_name}'][ancestor::div[@column-id='name'] or ancestor::td[contains(@class, 'name') or count(preceding-sibling::td) < 2]]"
        
        # Find the element containing the exact interface name
        elements = driver.find_elements(By.XPATH, xpath)
        
        # If not found, it might be lazy-loaded in a virtual table. Attempt to scroll down incrementally.
        scroll_attempts = 0
        while not elements and scroll_attempts < 10:
            try:
                driver.execute_script("""
                    document.querySelectorAll('.table-container, .mutable-table-container, .mutable, .vertical-scroller, .scrollers').forEach(c => {
                        c.scrollTop += 350;
                        c.dispatchEvent(new Event('scroll', {bubbles: true}));
                    });
                """)
                import time
                time.sleep(0.6) # Wait for virtual DOM to render the new rows
                elements = driver.find_elements(By.XPATH, xpath)
                scroll_attempts += 1
            except:
                break
                
        for el in elements:
            try:
                # Go up the DOM tree to find the parent table row. Strictly match ' row ' to avoid stopping at 'row-cell' or 'row-inner-cell'.
                parent = el.find_element(By.XPATH, "./ancestor::tr | ./ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' row ')]")
                
                # Extract text from individual cells and join with spaces to prevent textContent from concatenating words, which breaks Regex \b boundaries
                cells = parent.find_elements(By.XPATH, ".//*[self::td or contains(concat(' ', normalize-space(@class), ' '), ' row-cell ')]")
                row_text = " ".join([c.get_attribute("textContent").strip() for c in cells])
                
                # Extract status from the icon next to the name (e.g. ftnt-interface-rj45-up or ftnt-virtual-wan-link-down)
                status = "UNKNOWN"
                try:
                    icons = parent.find_elements(By.XPATH, ".//f-icon[contains(@class, '-up') or contains(@class, '-down')]")
                    if icons:
                        icon_class = icons[0].get_attribute("class")
                        if "-up" in icon_class: status = "UP"
                        elif "-down" in icon_class: status = "DOWN"
                except:
                    pass
                
                # If cells extraction failed (e.g., different DOM), fallback to the parent's textContent with relaxed Regex
                if not row_text:
                    row_text = parent.get_attribute("textContent")
                
                # Regex looking for an IP address (with optional subnet mask)
                match = re.search(r'(?:^|\b|\D)(\d{1,3}(?:\.\d{1,3}){3}(?:/(?:\d{1,3}(?:\.\d{1,3}){3}|\d{1,2}))?)', row_text)
                if match:
                    ip, mask = ip_netmask_to_cidr(match.group(1))
                    return ip, mask, status
                return "", "", status # Found the interface row but no IP
            except Exception as row_e:
                print(f"DEBUG: Row processing exception for {interface_name}: {row_e}")
                continue
        return "", "", "NOT FOUND"
    except:
        return "", "", "NOT FOUND"

def _ping_via_cli(driver, target_ip, host, interface_name=None):
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    import time, re
    
    try:
        print(f"[{host}] Opening CLI Console to ping {target_ip}...")
        
        # Check if terminal is already visible by looking for xterm-rows
        term = driver.find_elements(By.CSS_SELECTOR, ".xterm-rows")
        if not term:
            # Click the terminal button
            btn = driver.find_element(By.XPATH, "//nu-icon[@data-nu-icon='fa-solid__terminal']/ancestor::button")
            btn.click()
            time.sleep(5) # Wait for terminal to slide out and connect
            
        # Get baseline of how many "packet loss" strings exist
        rows = driver.find_elements(By.CSS_SELECTOR, ".xterm-rows > div")
        text = "\n".join([r.text for r in rows])
        initial_count = text.count("packet loss")
        
        # Send interface option if specified
        if interface_name:
            actions = ActionChains(driver)
            actions.send_keys(f"execute ping-options interface {interface_name}\n")
            actions.perform()
            time.sleep(1)
            rows = driver.find_elements(By.CSS_SELECTOR, ".xterm-rows > div")
            text = "\n".join([r.text for r in rows])
            if "Command fail" in text or "Return code" in text:
                print(f"[{host}] CLI interface option '{interface_name}' failed: Command fail. Resetting ping options.")
                reset_act = ActionChains(driver)
                reset_act.send_keys("execute ping-options reset\n")
                reset_act.perform()
                return ""

        # Send ping command
        actions = ActionChains(driver)
        actions.send_keys(f"execute ping {target_ip}\n")
        actions.perform()
        
        # Wait up to 15 seconds for completion
        for _ in range(15):
            time.sleep(1)
            rows = driver.find_elements(By.CSS_SELECTOR, ".xterm-rows > div")
            text = "\n".join([r.text for r in rows])
            current_count = text.count("packet loss")
            
            if current_count > initial_count:
                # Always reset ping options after test
                reset_act = ActionChains(driver)
                reset_act.send_keys("execute ping-options reset\n")
                reset_act.perform()
                # Extract latency
                matches = re.findall(r"min/avg/max.*?=\s*[\d\.]+/([\d\.]+)/[\d\.]+", text)
                if matches:
                    print(f"[{host}] CLI Ping successful: avg latency {matches[-1]}ms")
                    return str(int(float(matches[-1])))
                else:
                    print(f"[{host}] CLI Ping failed or 100% loss")
                    return ""
                    
        # Reset ping options on timeout
        reset_act = ActionChains(driver)
        reset_act.send_keys("execute ping-options reset\n")
        reset_act.perform()
        print(f"[{host}] CLI Ping timed out after 15 seconds")
        return ""
    except Exception as e:
        print(f"[{host}] CLI Ping error for {target_ip}: {e}")
        return ""

def _fetch_all_ipsec_tunnels_via_cli(driver, host):
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.by import By
    import time, re
    
    tunnels_map = {}
    try:
        print(f"[{host}] Opening CLI Console to extract all IPsec tunnel mappings...")
        term = driver.find_elements(By.CSS_SELECTOR, ".xterm-rows")
        if not term:
            btn = driver.find_element(By.XPATH, "//nu-icon[@data-nu-icon='fa-solid__terminal']/ancestor::button")
            btn.click()
            time.sleep(5)
            
        actions = ActionChains(driver)
        actions.send_keys('show vpn ipsec phase1-interface | grep "edit\\|interface\\|remote-gw"\n')
        actions.perform()
        
        time.sleep(3) # Wait for output to render
        rows = driver.find_elements(By.CSS_SELECTOR, ".xterm-rows > div")
        text = "\n".join([r.text for r in rows])
        
        blocks = text.split("edit ")[1:]
        for block in blocks:
            name_match = re.search(r'^"([^"]+)"', block.strip())
            intf_match = re.search(r'set interface\s+"?([^"\s\n]+)"?', block)
            gw_match = re.search(r'set remote-gw\s+([\d\.]+)', block)
            if name_match and intf_match and gw_match:
                intf_key = intf_match.group(1).lower()
                if intf_key not in tunnels_map:
                    tunnels_map[intf_key] = {
                        "name": name_match.group(1),
                        "remote-gw": gw_match.group(1)
                    }
                
        print(f"[{host}] Extracted IPsec tunnels binding via CLI: {tunnels_map}")
        return tunnels_map
    except Exception as e:
        print(f"[{host}] CLI bulk IPsec extraction exception: {e}")
        return {}

def _extract_if_status(driver, host, options):
    if_status = {}
    
    diagnose_intfs = options.get("diagnose_interfaces", ["wan1", "wan2"])
    gather_gateway = options.get("gather_gateway", False)
    
    ping_config = options.get("ping", {})
    if not isinstance(ping_config, dict):
        ping_config = {}
        
    ping_defaults = ping_config.get("default", {})
    if not isinstance(ping_defaults, dict):
        ping_defaults = {}
        
    default_ping_enabled = ping_defaults.get("enabled", False)
    default_ping_target = ping_defaults.get("target", "interface")
    default_ping_source = ping_defaults.get("source", "host")

    # Decide if we need to fetch static routes or ipsec bindings
    fetch_routes = gather_gateway or str(default_ping_target).lower() == "gateway"
    fetch_ipsec = str(default_ping_target).lower() == "ipsec_endpoint" or str(default_ping_source).lower() == "ipsec_endpoint"
    
    # Check if any specific interface configuration requests a gateway or ipsec ping
    for k, v in ping_config.items():
        if k != "default" and isinstance(v, dict):
            target = str(v.get("target", "")).lower()
            source = str(v.get("source", "")).lower()
            if target == "gateway":
                fetch_routes = True
            if target == "ipsec_endpoint" or source == "ipsec_endpoint":
                fetch_ipsec = True

    # 1. We are already on /ng/interface. Extract IP, mask, and link status.
    intf_data = {}
    for intf_config in diagnose_intfs:
        # Support aliases like 'internal5|port5'
        aliases = [a.strip() for a in intf_config.split('|')]
        primary_intf = aliases[0]
        intf_lower = primary_intf.lower()
        key = primary_intf.upper()
        
        found = False
        for alias in aliases:
            ip, mask, status_clean = _get_wan_details(driver, alias)
            if status_clean != "NOT FOUND":
                intf_data[intf_lower] = {
                    "key": key,
                    "status": status_clean,
                    "ip": ip,
                    "mask": mask,
                    "aliases": aliases,
                    "used_alias": alias
                }
                found = True
                break
                
        if not found:
            intf_data[intf_lower] = {
                "key": key,
                "status": "NOT FOUND",
                "ip": "",
                "mask": "",
                "aliases": aliases,
                "used_alias": primary_intf
            }

    # 2. If gather_gateway or ping_target requested it, go to static routing and find gateways.
    gateways = {}
    if fetch_routes:
        print(f"[{host}] Routing table scrape requested. Fetching static routes to find gateways...")
        try:
            driver.get(f"https://{host}/ng/routing/static")
            time.sleep(3) # Wait for table load
            
            routes = parse_fortigate_static_routes_html(driver.page_source)
            gateways = resolve_fortigate_gateways(routes, diagnose_intfs, intf_data)
            print(f"[{host}] Extracted gateways: {gateways}")
            
            # Navigate back to interface page
            driver.get(f"https://{host}/ng/interface")
            time.sleep(3)
        except Exception as e:
            print(f"[{host}] Failed to extract gateways: {e}")
            
    # 2.5 If IPsec endpoints are requested, bulk extract all tunnel mappings via CLI
    ipsec_tunnels = {}
    if fetch_ipsec:
        ipsec_tunnels = _fetch_all_ipsec_tunnels_via_cli(driver, host)
        # Navigate back to interface page if needed, but we probably didn't leave it since we just opened CLI
        # However, to ensure consistency, let's make sure we are on interface page without any CLI overlay
        driver.get(f"https://{host}/ng/interface")
        time.sleep(3)

    # 3. Assemble final wan_status and run pings
    for intf_config in diagnose_intfs:
        aliases = [a.strip() for a in intf_config.split('|')]
        primary_intf = aliases[0]
        intf_lower = primary_intf.lower()
        data = intf_data[intf_lower]
        key = data["used_alias"].upper()
        
        status_clean = data["status"]
        ip = data["ip"]
        mask = data["mask"]
        latency = ""
        
        gw_found = gateways.get(intf_lower, "")
        
        # Apply global ping defaults
        wants_ping = default_ping_enabled
        intf_ping_target = default_ping_target
        intf_ping_source = default_ping_source
        
        # Check for interface-specific overrides
        for k, v in ping_config.items():
            if k == "default":
                continue
                
            # k could be an alias like 'internal5|port5'
            k_primary = k.split('|')[0].strip().lower()
            if k_primary == intf_lower:
                if isinstance(v, dict):
                    if "enabled" in v: wants_ping = v["enabled"]
                    if "target" in v: intf_ping_target = v["target"]
                    if "source" in v: intf_ping_source = v["source"]
                elif isinstance(v, bool):
                    wants_ping = v
                break
                
        if ip == "0.0.0.0":
            status_clean = "DOWN (No IP)"
            
        # Validation: prevent source='host' from pinging invalid targets
        if wants_ping and str(intf_ping_source).lower() == "host":
            tgt = str(intf_ping_target).lower()
            if tgt not in ["interface", "gateway"]:
                print(f"[{host}] ERROR: source='host' only supports 'interface' or 'gateway' targets. Cannot use '{intf_ping_target}'. Ping disabled for {primary_intf}.")
                wants_ping = False
            
        # Only ping if requested AND if the physical status is UP
        target_ip = None
        if status_clean == "UP" and wants_ping:
            if str(intf_ping_target).lower() == "gateway":
                target_ip = gw_found
                if target_ip:
                    print(f"[{host}] Pinging {primary_intf} gateway -> {target_ip}")
                else:
                    print(f"[{host}] Gateway for {primary_intf} not found, falling back to interface IP -> {ip}")
                    target_ip = ip
            elif str(intf_ping_target).lower() == "ipsec_endpoint":
                tunnel_data = None
                for alias in aliases:
                    if alias.lower() in ipsec_tunnels:
                        tunnel_data = ipsec_tunnels[alias.lower()]
                        break
                        
                if tunnel_data:
                    tunnel_name = tunnel_data["name"]
                    target_ip = tunnel_data["remote-gw"]
                    print(f"[{host}] IPsec tunnel '{tunnel_name}' for {primary_intf} detected. Pinging endpoint -> {target_ip}")
                else:
                    print(f"[{host}] IPsec tunnel for {primary_intf} not found. Skipping ping (fail and continue).")
                    target_ip = None
            elif str(intf_ping_target).lower() == "interface":
                target_ip = ip
                print(f"[{host}] Pinging {primary_intf} interface IP -> {target_ip}")
            else:
                target_ip = str(intf_ping_target)
                gw_found = target_ip # Update gw_found so the template prints it correctly if requested
                print(f"[{host}] Pinging custom target -> {target_ip} for {primary_intf}")
            
            if target_ip:
                source_val = str(intf_ping_source).lower()
                if source_val == "host":
                    latency = ping_host(target_ip)
                else:
                    ping_intf_name = data["used_alias"]
                    if source_val == "ipsec_endpoint":
                        tunnel_data = None
                        for alias in aliases:
                            if alias.lower() in ipsec_tunnels:
                                tunnel_data = ipsec_tunnels[alias.lower()]
                                break
                        if tunnel_data:
                            ping_intf_name = tunnel_data["name"]
                            print(f"[{host}] Sourcing ping from IPsec tunnel '{ping_intf_name}'")
                        else:
                            print(f"[{host}] IPsec tunnel for {primary_intf} not found to source ping. Skipping ping (fail and continue).")
                            target_ip = None
                    if target_ip:
                        latency = _ping_via_cli(driver, target_ip, host, interface_name=ping_intf_name)
        
        if_status[key] = {
            "status": status_clean,
            "ip": ip,
            "mask": mask,
            "gw": gw_found,
            "latency": latency,
            "ping_interface": wants_ping,
            "ping_target_ip": target_ip if target_ip else ""
        }

    return if_status

_extract_wan_status = _extract_if_status

def parse_fortigate_system_info_html(html_content):
    """
    Parses FortiOS System Information widget HTML into a standardized dictionary.
    Extracts Serial Number, Firmware (e.g. v7.4.11), Uptime, Hostname, etc.
    """
    system_info = {
        "hostname": "",
        "os_type": "FortiOS",
        "model": "FortiGate",
        "serial_number": "",
        "version": "",
        "raw_version": "",
        "uptime": "",
        "cpu_util": "",
        "memory_usage": "",
        "mode": "",
        "system_time": "",
        "wan_ip": "",
        "members": []
    }
    
    tr_matches = re.findall(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>', html_content, re.DOTALL | re.IGNORECASE)
    for k_html, v_html in tr_matches:
        k = re.sub(r'<[^>]+>', '', k_html).strip().lower()
        v = re.sub(r'<[^>]+>', '', v_html).strip()
        v = re.sub(r'\s+', ' ', v).strip()
        
        if "hostname" in k:
            system_info["hostname"] = v
        elif "serial number" in k:
            system_info["serial_number"] = v
        elif "firmware" in k:
            system_info["raw_version"] = v
            m = re.search(r'(v\d+(?:\.\d+)+)', v)
            system_info["version"] = m.group(1) if m else v
        elif "uptime" in k:
            system_info["uptime"] = v
        elif "mode" in k:
            system_info["mode"] = v
        elif "system time" in k:
            system_info["system_time"] = v
        elif "wan ip" in k:
            system_info["wan_ip"] = v

    return system_info

def _extract_system_info(driver, host, options):
    """
    Navigates to FortiOS Dashboard if necessary and scrapes the System Information widget.
    Falls back to CLI 'get system status' if widget DOM is not available.
    """
    dashboard_url = options.get("dashboard_url", "https://{host}/ng/dashboard").format(host=host)
    print(f"[{host}] Fetching System Information from dashboard...")
    try:
        # Navigate to dashboard if not already there
        if "/ng/dashboard" not in driver.current_url:
            driver.get(dashboard_url)
            time.sleep(3)

        # Wait for system information widget
        widget_elements = driver.find_elements(By.CSS_SELECTOR, "fos-dashboard-system-information-widget")
        if not widget_elements:
            for _ in range(5):
                time.sleep(1)
                widget_elements = driver.find_elements(By.CSS_SELECTOR, "fos-dashboard-system-information-widget")
                if widget_elements:
                    break

        if widget_elements:
            widget_html = widget_elements[0].get_attribute("outerHTML")
            return parse_fortigate_system_info_html(widget_html)
            
        # Fallback: look for key-value table directly
        tables = driver.find_elements(By.CSS_SELECTOR, "table.nu-table-key-value")
        for tbl in tables:
            tbl_html = tbl.get_attribute("outerHTML")
            if "serial number" in tbl_html.lower() or "firmware" in tbl_html.lower():
                return parse_fortigate_system_info_html(tbl_html)
                
    except Exception as e:
        print(f"[{host}] Web UI System Information extraction error: {e}")

    # Fallback to CLI
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        print(f"[{host}] Attempting CLI fallback for System Information...")
        term = driver.find_elements(By.CSS_SELECTOR, ".xterm-rows")
        if not term:
            btn = driver.find_elements(By.XPATH, "//nu-icon[@data-nu-icon='fa-solid__terminal']/ancestor::button")
            if btn:
                btn[0].click()
                time.sleep(4)
        actions = ActionChains(driver)
        actions.send_keys("get system status\n")
        actions.perform()
        time.sleep(3)
        rows = driver.find_elements(By.CSS_SELECTOR, ".xterm-rows > div")
        cli_text = "\n".join([r.text for r in rows])
        
        serial_m = re.search(r'Serial-Number:\s*([^\s\n]+)', cli_text)
        ver_m = re.search(r'Version:\s*(.+)', cli_text)
        
        system_info = {
            "hostname": "",
            "os_type": "FortiOS",
            "model": "FortiGate",
            "serial_number": serial_m.group(1).strip() if serial_m else "",
            "version": "",
            "raw_version": ver_m.group(1).strip() if ver_m else "",
            "uptime": "",
            "cpu_util": "",
            "memory_usage": "",
            "mode": "",
            "system_time": "",
            "wan_ip": "",
            "members": []
        }
        if system_info["raw_version"]:
            m = re.search(r'(v\d+(?:\.\d+)+)', system_info["raw_version"])
            if m:
                system_info["version"] = m.group(1)
        return system_info
    except Exception as e:
        print(f"[{host}] CLI fallback for System Information failed: {e}")

    return {
        "hostname": "",
        "os_type": "FortiOS",
        "model": "FortiGate",
        "serial_number": "",
        "version": "",
        "raw_version": "",
        "uptime": "",
        "cpu_util": "",
        "memory_usage": "",
        "mode": "",
        "system_time": "",
        "wan_ip": "",
        "members": []
    }

def handle(host, alert_info, options):
    url = options.get("url_template", "https://{host}/ng/interface").format(host=host)
    
    username = options.get("username")
    password = options.get("password")

    # If credentials are not provided via config, request them via the provider injected by main.py
    if not username or not password:
        if "credential_provider" in options:
            prov_user, prov_pass = options["credential_provider"]()
            username = username or prov_user
            password = password or prov_pass
        else:
            raise ValueError("Credentials are required but not provided in options.")

    print(f"[{host}] Starting evidence collection at {url}")

    driver_options = webdriver.ChromeOptions()
    driver_options.add_argument('--ignore-certificate-errors')
    # Suppress console errors from Chrome to keep the terminal clean
    # driver_options.add_argument('--log-level=3')
    # driver_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    # driver_options.add_argument('--headless') # Uncomment to run headless without opening a window
    
    # Using Chrome. Ensure you have a compatible chromedriver installed and in PATH.
    driver = webdriver.Chrome(options=driver_options)

    result = {
        "host": host,
        "url": url,
        "error": ERR_OK,
    }

    try:
        driver.get(url)
        
        # 1. Perform Login
        print(f"[{host}] Waiting for login screen...")
        user_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "username")) 
        )
        user_field.clear()
        user_field.send_keys(username)
        
        pass_field = driver.find_element(By.ID, "secretkey")
        pass_field.clear()
        pass_field.send_keys(password)

        # Click the Login button based on the provided HTML
        try:
            login_btn = driver.find_element(By.ID, "login_button")
        except:
            login_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Login Read-Only']")
            
        login_btn.click()

        # 2. Wait for the interfaces table, FortiManager prompt, or Authentication failure
        print(f"[{host}] Login submitted. Waiting for authentication result...")
        
        start_time = time.time()
        fmg_handled = False
        login_success = False
        
        while time.time() - start_time < 30:
            # Check for authentication failure
            try:
                login_state = parse_fortigate_login_html(driver.page_source)
                if login_state.get("auth_failed"):
                    raise Exception("Authentication Failed. Skipping device.")
            except Exception as e:
                if str(e) == "Authentication Failed. Skipping device.":
                    raise
                pass

            # If the interfaces table has appeared, we are done waiting
            if is_fortigate_table_ready_html(driver.page_source) or driver.find_elements(By.CSS_SELECTOR, "table.portgroup") or driver.find_elements(By.CSS_SELECTOR, "div.mutable-table-container"):
                login_success = True
                break
                
            # If the FortiManager centrally managed prompt appears, click "Login Read-Only"
            if not fmg_handled:
                fmg_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Login Read-Only')]")
                if fmg_buttons:
                    print(f"[{host}] FortiManager interception detected. Clicking 'Login Read-Only'...")
                    try:
                        fmg_buttons[0].click()
                        fmg_handled = True
                    except Exception as e:
                        print(f"[{host}] Failed to click FortiManager prompt: {e}")
                        
            time.sleep(1)
        else:
            raise Exception("Timeout waiting for interfaces table to load after login.")
            
        if login_success:
            print(f"[{host}] Login successful. Proceeding to collect interfaces...")

        
        # Short pause to ensure rendering of icons/states
        time.sleep(3)
        
        # 3. Take Screenshot (if enabled)
        if options.get("capture_screenshot", True):
            exec_timestamp = options.get("execution_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
            # Use the current filename without extension (e.g. 'fortigate')
            handler_name = os.path.splitext(os.path.basename(__file__))[0]
            
            # Create nested screenshots directory: screenshots/<timestamp>/<handler_name>
            base_dir = options.get("base_dir", os.getcwd())
            screenshots_dir = os.path.join(base_dir, "screenshots", exec_timestamp, handler_name)
            os.makedirs(screenshots_dir, exist_ok=True)
            
            capture_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_filename = f"screenshot_{host}_{capture_timestamp}.png"
            screenshot_path = os.path.join(screenshots_dir, screenshot_filename)
            
            driver.save_screenshot(screenshot_path)
            result["screenshot"] = {
                "image": None,
                "path": screenshot_path,
                "filename": screenshot_filename,
                "captured": True,
            }
            print(f"[{host}] Screenshot saved at {screenshot_path}")

        # 4. Extract Interface status and run latency checks
        result["if_status"] = _extract_if_status(driver, host, options)
        
        # 5. Extract System Information (if enabled)
        if options.get("gather_system_info", True):
            sys_info = _extract_system_info(driver, host, options)
            if sys_info:
                result["system_info"] = sys_info
                print(f"[{host}] System info: S/N={sys_info.get('serial_number')}, Version={sys_info.get('version')}, Uptime={sys_info.get('uptime')}")
        
        # Populate latency array and determine error code
        latencies = []
        error_code = ERR_OK
        for intf_key, intf_data in result["if_status"].items():
            status = intf_data.get("status", "")
            ip = intf_data.get("ip", "")
            
            # 1. 0.0.0.0 (Logical down)
            if ip == "0.0.0.0" and error_code == ERR_OK:
                error_code = ERR_IF_LOGICAL_DOWN
                
            # 2. Monitored interface is DOWN with an assigned IP address
            if "DOWN" in status and ip and ip != "0.0.0.0" and error_code == ERR_OK:
                error_code = ERR_IF_DOWN
                
            # 3. Ping gateway or interface was requested, but failed (timeout)
            if intf_data.get("ping_interface") and status.startswith("UP") and not intf_data.get("latency") and error_code == ERR_OK:
                error_code = ERR_PING_TIMEOUT
                
            val = intf_data.get("latency")
            if val:
                try:
                    latencies.append(int(val))
                except:
                    pass
                    
        if latencies:
            result["latency"] = latencies
        result["error"] = error_code

        if_str = ", ".join([f"{k}={v}" for k, v in result["if_status"].items()])
        print(f"[{host}] Collected status: {if_str}")

    except Exception as e:
        print(f"[{host}] Error during automation: {e}")
        err_str = str(e).lower()
        if "login" in err_str or "auth" in err_str:
            result["error"] = ERR_AUTH_FAILED
        else:
            result["error"] = ERR_AUTOMATION_FAILED
    finally:
        driver.quit()

    return result
