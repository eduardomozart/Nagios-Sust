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
from utils.pdf_parser import parse_nagios_pdf
from utils.dialog import open_file_dialog

# Global credential cache
_cached_username = None
_cached_password = None

def get_global_credentials():
    global _cached_username, _cached_password
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
        input("Press Enter to exit...")
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

def match_rule(host, rules):
    for rule in rules:
        host_filter = rule.get("host_filter", {})
        if "startswith" in host_filter:
            prefix = str(host_filter["startswith"])
            if host.startswith(prefix):
                return rule
    return None

def get_pdf_file_path(default_path):
    if os.path.exists(default_path):
        return default_path
        
    print(f"Warning: PDF file '{os.path.basename(default_path)}' not found.")
    print("Please select the PDF file from the file explorer dialog...")
    
    file_path = open_file_dialog(
        title="Select Nagios Report PDF",
        file_filter="PDF files (*.pdf)\0*.pdf\0All files (*.*)\0*.*\0\0"
    )
    
    if not file_path:
        print("No file selected. Exiting.")
        sys.exit(1)
        
    return file_path

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
        
    pdf_file_name = config.get("nagios_report", "report.pdf")
    
    base_dir = get_base_dir()
    # os.path.join safely ignores base_dir if pdf_file_name is already an absolute path
    pdf_default_path = os.path.join(base_dir, pdf_file_name)
    
    print(f"Checking for report file: {pdf_file_name}...")
    pdf_path = get_pdf_file_path(pdf_default_path)
    
    print(f"Reading PDF: {pdf_path}")
    try:
        alerts = parse_nagios_pdf(pdf_path)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)

    print(f"Found {len(alerts)} unique hosts in the PDF.")
    results = []

    for alert in alerts:
        host = alert["host"]
        rule = match_rule(host, config.get("rules", []))
        
        if rule:
            handler_name = rule["handler"]
            print(f"\nHost '{host}' matched rule '{rule['name']}'. Executing handler '{handler_name}'...")
            
            options = rule.get("options", {})
            # Inject the global state into options
            options["credential_provider"] = get_global_credentials
            options["execution_timestamp"] = execution_timestamp
            
            try:
                handler_module = importlib.import_module(f"handlers.{handler_name}")
                result = handler_module.handle(host, alert, options)
                
                # Inject the rule name into the result so it can be used in exporters/templates
                if isinstance(result, dict):
                    result["rule_name"] = rule["name"]
                    
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
