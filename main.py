import sys
import os
import argparse
import importlib
import getpass
import re

from utils.config import load_config
from utils.exit_codes import ERR_DEVICE_PROMPT_ABORTED

VERSION = "DEV_BUILD"

# Print header immediately before heavy imports
print("========================================")
print(f" Nagios-Sust {VERSION} ")
print("========================================\n")

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

def parse_args():
    if "/?" in sys.argv:
        sys.argv[sys.argv.index("/?")] = "-h"

    parser = argparse.ArgumentParser(description=f"Nagios-Sust {VERSION} - Evidence Collector")
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to YAML configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "-d", "--device", "--devices",
        action="append",
        dest="devices",
        help="Device hostname to process. Can be specified multiple times (e.g. -d SW-01 -d SW-02). Bypasses device_sources."
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"Nagios-Sust {VERSION}",
        help="Show program's version number and exit."
    )
    return parser.parse_args()

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

from sources import load_unique_hosts, get_supported_sources

def prompt_for_devices(config, source_options):
    """
    Called when 'device_sources' is not set in config and no -d devices were provided via CLI.
    Displays supported sources and allows setting device names or picking a source.
    """
    supported = get_supported_sources()
    print("Notice: 'device_sources' is not set in your configuration.")
    print("Supported device sources:")
    for src in supported:
        print(f"  - {src}")
    print()

    while True:
        try:
            user_input = input("Enter source(s) or device name(s) (comma-separated, e.g. 'SW-01, SW-02'): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(ERR_DEVICE_PROMPT_ABORTED)

        if not user_input:
            print("Error: No devices or source provided. Please try again.\n")
            continue

        # Parse tokens, trimming leading/trailing whitespace and optional quotes
        tokens = [t.strip().strip("\"'") for t in user_input.split(",") if t.strip().strip("\"'")]

        if not tokens:
            print("Error: No valid input provided. Please try again.\n")
            continue

        matched_sources = [t for t in tokens if t.lower() in supported]
        matched_devices = [t for t in tokens if t.lower() not in supported]

        # Check for invalid mixture of sources and device names
        if matched_sources and matched_devices:
            print(
                f"\n[!] Error: Cannot mix source names ({', '.join(matched_sources)}) "
                f"and device names ({', '.join(matched_devices)}) in the same input."
            )
            print("    Please enter either source name(s) OR device name(s).\n")
            continue

        # Check if all tokens are supported source names (e.g. "airwave", "nagios_pdf, airwave")
        if matched_sources:
            chosen_sources = []
            for t in tokens:
                src = t.lower()
                if src not in chosen_sources:
                    chosen_sources.append(src)
            print(f"\nUsing source(s): {', '.join(chosen_sources)}...")
            config["device_sources"] = chosen_sources
            return load_unique_hosts(config, source_options)

        # Otherwise, parse device list similar to -d
        device_names = []
        for d in tokens:
            if d not in device_names:
                device_names.append(d)

        print(f"\nUsing device list ({len(device_names)} host(s)): {', '.join(device_names)}\n")
        return [{"host": d, "sources": ["interactive"]} for d in device_names]

def main():
    args = parse_args()
    base_dir = get_base_dir()

    # Parse devices provided via CLI if any
    cli_devices = []
    if args.devices:
        for item in args.devices:
            for d in str(item).split(","):
                clean = d.strip().strip("\"'")
                if clean and clean not in cli_devices:
                    cli_devices.append(clean)

    config = load_config(args.config, base_dir=base_dir)

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

    source_options = {
        "credential_provider": get_global_credentials,
        "base_dir": base_dir,
    }

    if cli_devices:
        print(f"Device list provided via command line ({len(cli_devices)} host(s)): {', '.join(cli_devices)}")
        print("Bypassing 'device_sources' and evaluating rules directly for specified devices.\n")
        hosts = [{"host": d, "sources": ["cli"]} for d in cli_devices]
    elif config.get("device_sources"):
        hosts = load_unique_hosts(config, source_options)
    else:
        hosts = prompt_for_devices(config, source_options)

    results = []

    for host_data in hosts:
        host = host_data["host"]
        matched_rules = match_rules(host, config.get("rules", []))
        
        if not matched_rules:
            continue

        host_obj = {
            "name": host,
        }
        rules_list = []
        handlers_obj = {}

        # Build sources subsystem
        sources_list = host_data.get("sources", [])
        sources_obj = {
            "list": list(sources_list) if isinstance(sources_list, list) else [sources_list],
        }
        for src in sources_obj["list"]:
            if src in host_data and isinstance(host_data[src], dict):
                sources_obj[src] = host_data[src]

        for rule in matched_rules:
            handler_name = rule["handler"]
            rules_list.append(rule["name"])
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
                result = handler_module.handle(host, host_data, options)
                
                if isinstance(result, dict):
                    handler_entry = {
                        "error": int(result.get("error", 0)),
                    }
                    if "latency" in result and result["latency"] is not None:
                        pings = result["latency"] if isinstance(result["latency"], list) else [result["latency"]]
                        valid_pings = [int(p) for p in pings if isinstance(p, (int, float))]
                        if valid_pings:
                            negatives = [p for p in valid_pings if p < 0]
                            if negatives:
                                handler_entry["latency"] = min(negatives)
                            else:
                                handler_entry["latency"] = max(valid_pings)
                    if "if_status" in result:
                        handler_entry["if_status"] = result["if_status"]
                    if "system_info" in result and result["system_info"]:
                        handler_entry["system_info"] = result["system_info"]
                    if "screenshot" in result and result["screenshot"]:
                        handler_entry["screenshot"] = result["screenshot"]

                    handlers_obj[handler_name] = handler_entry

            except ImportError:
                print(f"Error: Handler '{handler_name}' not found in handlers/")
            except Exception as e:
                print(f"Error executing handler for {host}: {e}")

        # Assemble cumulative result for this host
        cumulative_item = {
            "host": host_obj,
            "rules": rules_list,
            "handlers": handlers_obj,
            "sources": sources_obj,
        }
        results.append(cumulative_item)

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
