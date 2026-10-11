import sys
import os

VERSION = "DEV_BUILD"

# Print header immediately before heavy imports
print("========================================")
print(f" Nagios-Sust {VERSION} ")
print("========================================\n")

import yaml
import importlib
import getpass
import re

# Global credential cache
_cached_username = None
_cached_password = None

def get_global_credentials(force_prompt=False):
    global _cached_username, _cached_password
    if force_prompt:
        _cached_username = None
        _cached_password = None
    if not _cached_username:
        _cached_username = input("Enter Username: ")
    if not _cached_password:
        _cached_password = getpass.getpass(f"Enter Password for {_cached_username}: ")
    return _cached_username, _cached_password

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def load_config(config_file="config.yaml"):
    base_dir = get_base_dir()
    config_path = os.path.join(base_dir, config_file)
    
    if not os.path.exists(config_path):
        print(f"Error: Configuration file '{config_file}' not found.")
        print(f"Please rename 'config.example.yaml' to '{config_file}' and set up your rules.")
        sys.exit(1)
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        print(f"\n[!] Error parsing '{config_file}'!")
        print("    If you are using Windows paths (like C:\\Users\\...), make sure to:")
        print("    1. Use forward slashes (e.g., C:/Users/...) OR")
        print("    2. Use single quotes ('C:\\Users\\...') instead of double quotes.")
        print(f"\nDetailed YAML Error:\n{exc}")
        sys.exit(1)

def match_rules(host, rules):
    matched = []
    for rule in rules:
        host_filter = rule.get("host_filter", {})
        
        # Check startswith
        if "startswith" in host_filter:
            prefix = str(host_filter["startswith"])
            if host.startswith(prefix):
                matched.append(rule)
                continue
                
        # Check regex
        if "regex" in host_filter:
            pattern = str(host_filter["regex"])
            try:
                if re.search(pattern, host):
                    matched.append(rule)
                    continue
            except re.error as e:
                print(f"Invalid regex '{pattern}' in rule '{rule.get('name')}': {e}")
                
    return matched

def main():
    config = load_config()
    
    # Generate an execution timestamp to group all screenshots from this run
    from datetime import datetime
    execution_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Pre-load global credentials from config if specified
    global _cached_username, _cached_password
    global_creds = config.get("credentials", {})
    if global_creds.get("username"):
        _cached_username = global_creds["username"]
    if global_creds.get("password"):
        _cached_password = str(global_creds["password"]) # Cast to string in case of numeric passwords

    base_dir = get_base_dir()

    device_source = str(config.get("device_source", "nagios_pdf")).lower()
    if "--airwave" in sys.argv:
        device_source = "airwave"
    elif "--nagios" in sys.argv or "--pdf" in sys.argv:
        device_source = "nagios_pdf"

    print(f"Device Source: {device_source}")

    source_options = {
        "credential_provider": get_global_credentials,
        "base_dir": base_dir,
    }

    try:
        source_module = importlib.import_module(f"sources.{device_source}")
        alerts = source_module.get_hosts(config, source_options)
    except ImportError:
        print(f"Error: Device source '{device_source}' not found in sources/")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading devices from source '{device_source}': {e}")
        sys.exit(1)

    results = []

    for alert in alerts:
        host = alert["host"]
        matched_rules = match_rules(host, config.get("rules", []))
        
        if not matched_rules:
            # print(f"[{host}] No rules matched.")
            continue
            
        for rule in matched_rules:
            handler_name = rule["handler"]
            print(f"\nHost '{host}' matched rule '{rule['name']}'. Executing handler '{handler_name}'...")
            
            options = rule.get("options", {})
            # Inject the global state into options
            options["credential_provider"] = get_global_credentials
            options["execution_timestamp"] = execution_timestamp
            options["base_dir"] = base_dir
            if "airwave" in config and "airwave_url" not in options:
                airwave_url = config["airwave"].get("url") or config["airwave"].get("host")
                if airwave_url:
                    options["airwave_url"] = airwave_url
            
            try:
                handler_module = importlib.import_module(f"handlers.{handler_name}")
                result = handler_module.handle(host, alert, options)
                
                # Inject the rule name and handler into the result so it can be used in exporters/templates
                if isinstance(result, dict):
                    result["rule_name"] = rule["name"]
                    result["handler"] = handler_name
                    
                results.append(result)
            except ImportError:
                print(f"Error: Handler '{handler_name}' not found in handlers/")
            except Exception as e:
                print(f"Error executing handler for {host}: {e}")

    if not results:
        print("No evidence generated (no hosts matched the rules or execution failed).")
        return

    # Process Exporters
    print("\nProcessing evidence reports...")
    for exporter_config in config.get("exporters", []):
        exporter_type = exporter_config["type"]
        print(f"Running exporter: {exporter_type}")
        try:
            exporter_module = importlib.import_module(f"exporters.{exporter_type}_exporter")
            exporter_module.export(results, exporter_config)
        except ImportError:
            print(f"Error: Exporter '{exporter_type}' not found in exporters/")
        except Exception as e:
            print(f"Error executing exporter {exporter_type}: {e}")

if __name__ == "__main__":
    main()
