import os
import sys
import glob
try:
    import yaml
except ImportError:
    yaml = None
import importlib
from utils.exit_codes import (
    ERR_CONFIG_FILE_NOT_FOUND,
    ERR_PROMPTED_CONFIG_NOT_FOUND,
    ERR_NO_CONFIG_SELECTED,
    ERR_PYYAML_MISSING,
    ERR_CONFIG_PARSE_ERROR,
    ERR_CONFIG_VALIDATION_ERROR,
)

class ConfigValidationError(Exception):
    """Raised when the configuration syntax or schema is invalid."""
    pass


def deep_merge(base, override):
    """
    Recursively merges override dictionary into base dictionary.
    - Dictionaries are recursively merged.
    - Lists are concatenated.
    - Scalars in override overwrite base.
    """
    result = dict(base)
    for k, v in override.items():
        if k in result:
            if isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = deep_merge(result[k], v)
            elif isinstance(result[k], list) and isinstance(v, list):
                if k == "device_sources":
                    seen = set()
                    merged_list = []
                    for item in result[k] + v:
                        if item not in seen:
                            seen.add(item)
                            merged_list.append(item)
                    result[k] = merged_list
                else:
                    result[k] = result[k] + v
            else:
                result[k] = v
        else:
            result[k] = v
    return result


def _resolve_include_files(include_item, config_dir):
    """
    Resolves an include pattern or filename relative to config_dir.
    Supports single paths, lists, and glob patterns (e.g. 'conf.d/*.yaml').
    """
    patterns = include_item if isinstance(include_item, (list, tuple)) else [include_item]
    matched_files = []

    for pattern in patterns:
        if not isinstance(pattern, str):
            continue
        clean_pattern = pattern.strip()
        if not os.path.isabs(clean_pattern):
            clean_pattern = os.path.join(config_dir, clean_pattern)

        files = sorted(glob.glob(clean_pattern))
        if not files:
            # If literal file didn't match glob, check if it's a specific missing file
            if "*" not in pattern and "?" not in pattern:
                raise ConfigValidationError(f"Included configuration file '{pattern}' not found (resolved to '{clean_pattern}').")
        matched_files.extend(files)

    return matched_files


def resolve_includes(data, config_dir, visited_files=None):
    """
    Recursively loads and merges configs referenced by 'include:'.
    Detects and rejects circular includes.
    """
    if visited_files is None:
        visited_files = set()

    if not isinstance(data, dict) or "include" not in data:
        return data

    include_val = data.pop("include")
    included_files = _resolve_include_files(include_val, config_dir)

    merged_included = {}

    for file_path in included_files:
        canonical_path = os.path.realpath(file_path)
        if canonical_path in visited_files:
            raise ConfigValidationError(f"Circular include detected for configuration file: '{file_path}'")

        if not os.path.exists(canonical_path):
            raise ConfigValidationError(f"Included file does not exist: '{file_path}'")

        if yaml is None:
            raise ConfigValidationError("PyYAML is not installed. Please install PyYAML to load YAML configurations.")

        try:
            with open(canonical_path, "r", encoding="utf-8") as f:
                inc_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            raise ConfigValidationError(f"Error parsing included YAML file '{file_path}':\n{exc}")

        if not isinstance(inc_data, dict):
            raise ConfigValidationError(f"Included configuration file '{file_path}' must contain a YAML mapping (dictionary).")

        child_visited = set(visited_files)
        child_visited.add(canonical_path)
        resolved_child = resolve_includes(inc_data, os.path.dirname(canonical_path), child_visited)
        merged_included = deep_merge(merged_included, resolved_child)

    # Parent config overrides/merges on top of included configs
    return deep_merge(merged_included, data)


def validate_config(config, config_path="config.yaml", require_sources=True):
    """
    Validates semantic structure and types of the configuration dictionary.
    """
    if not isinstance(config, dict):
        raise ConfigValidationError(f"Configuration file '{config_path}' must contain a YAML mapping (dictionary).")

    # Reject deprecated keys
    if "device_source" in config:
        raise ConfigValidationError(
            f"'device_source' in '{config_path}' is no longer supported. "
            f"Please use 'device_sources' as a list of sources instead, e.g.:\n"
            "device_sources:\n"
            "  - 'nagios_pdf'\n"
            "  - 'airwave'"
        )

    # 1. Validate device_sources (optional; interactive prompt triggers if omitted)
    if "device_sources" in config:
        sources = config["device_sources"]
        if not isinstance(sources, list) or len(sources) == 0:
            raise ConfigValidationError(f"'device_sources' in '{config_path}' must be a non-empty list of source names.")

        for src in sources:
            if not isinstance(src, str) or not src.strip():
                raise ConfigValidationError(f"Invalid entry in 'device_sources': {src}. Each source must be a non-empty string.")
            src_name = src.strip().lower()
            try:
                importlib.import_module(f"sources.{src_name}")
            except ImportError:
                raise ConfigValidationError(
                    f"Unknown device source '{src_name}' in 'device_sources'.\n"
                    f"Make sure a corresponding module 'sources/{src_name}.py' exists."
                )

    # 2. Validate rules
    if "rules" not in config:
        raise ConfigValidationError(f"Configuration in '{config_path}' is missing required field 'rules'.")

    rules = config["rules"]
    if not isinstance(rules, list):
        raise ConfigValidationError(f"'rules' in '{config_path}' must be a list of rule definitions.")

    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ConfigValidationError(f"Rule at index {i} in '{config_path}' must be a dictionary.")

        if not rule.get("name") or not isinstance(rule.get("name"), str):
            raise ConfigValidationError(f"Rule at index {i} is missing a valid 'name' attribute.")

        host_filter = rule.get("host_filter")
        if not isinstance(host_filter, dict) or not any(k in host_filter for k in ("startswith", "regex")):
            raise ConfigValidationError(
                f"Rule '{rule.get('name')}' must specify a 'host_filter' dictionary containing 'startswith' or 'regex'."
            )
        if "startswith" in host_filter and not isinstance(host_filter["startswith"], str):
            raise ConfigValidationError(
                f"Rule '{rule.get('name')}' host_filter 'startswith' must be a string. Use 'regex' for multiple conditions."
            )
        if "regex" in host_filter and not isinstance(host_filter["regex"], str):
            raise ConfigValidationError(
                f"Rule '{rule.get('name')}' host_filter 'regex' must be a string."
            )

        handler = rule.get("handler")
        if not handler or not isinstance(handler, str):
            raise ConfigValidationError(f"Rule '{rule.get('name')}' is missing a valid 'handler' string.")

    # 3. Validate exporters
    if "exporters" in config:
        exporters = config["exporters"]
        if not isinstance(exporters, list):
            raise ConfigValidationError(f"'exporters' in '{config_path}' must be a list.")

        for i, exp in enumerate(exporters):
            if not isinstance(exp, dict):
                raise ConfigValidationError(f"Exporter at index {i} must be a dictionary.")
            if not exp.get("type") or not isinstance(exp.get("type"), str):
                raise ConfigValidationError(f"Exporter at index {i} is missing a valid 'type' string.")
            if "language" in exp:
                raise ConfigValidationError(
                    f"Exporter at index {i} in '{config_path}' uses deprecated 'language'. "
                    f"Please use 'languages' as a list instead, e.g. languages: ['en', 'pt-BR']."
                )

    # 4. Validate source-specific blocks if present
    if "nagios_pdf" in config and not isinstance(config["nagios_pdf"], dict):
        raise ConfigValidationError(f"'nagios_pdf' in '{config_path}' must be a dictionary.")

    if "airwave" in config and not isinstance(config["airwave"], dict):
        raise ConfigValidationError(f"'airwave' in '{config_path}' must be a dictionary.")

    if "credentials" in config and not isinstance(config["credentials"], dict):
        raise ConfigValidationError(f"'credentials' in '{config_path}' must be a dictionary.")


def prompt_for_config_file(base_dir=None):
    """
    Prompts the user to specify or browse for a configuration file
    when default 'config.yaml' is missing and none was given via CLI.
    """
    if base_dir is None:
        base_dir = os.getcwd()

    print("Configuration file 'config.yaml' not found.")
    selected = None
    try:
        user_input = input("Please enter the path to a configuration file (or press Enter to browse): ").strip().strip("\"'")
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(ERR_NO_CONFIG_SELECTED)

    if user_input:
        selected = user_input
    else:
        try:
            from utils.dialog import open_file_dialog
            selected = open_file_dialog(
                title="Select Configuration YAML File",
                file_filter="YAML files (*.yaml;*.yml)\0*.yaml;*.yml\0All files (*.*)\0*.*\0\0"
            )
        except Exception:
            selected = None

    if not selected:
        print("Error: No configuration file selected.")
        sys.exit(ERR_NO_CONFIG_SELECTED)

    if not os.path.isabs(selected):
        if os.path.exists(selected):
            chosen_path = os.path.abspath(selected)
        else:
            chosen_path = os.path.join(base_dir, selected)
    else:
        chosen_path = selected

    if not os.path.exists(chosen_path):
        print(f"Error: Configuration file '{selected}' not found.")
        sys.exit(ERR_PROMPTED_CONFIG_NOT_FOUND)

    return chosen_path


def resolve_config_path(cli_config=None, base_dir=None):
    """
    Resolves the configuration file path to use:
    1. If cli_config is provided (-c / --config):
       Verifies existence. If not found, prints an error message and exits with code ERR_CONFIG_FILE_NOT_FOUND.
    2. If cli_config is None:
       Checks for default 'config.yaml' in current directory or base_dir.
       If found, returns it.
       If not found, prompts the user which config file to use.
    """
    if base_dir is None:
        base_dir = os.getcwd()

    # 1. Specified via CLI (-c / --config)
    if cli_config is not None:
        if not os.path.isabs(cli_config):
            if os.path.exists(cli_config):
                config_path = os.path.abspath(cli_config)
            else:
                config_path = os.path.join(base_dir, cli_config)
        else:
            config_path = cli_config

        if not os.path.exists(config_path):
            print(f"Error: Configuration file '{cli_config}' not found.")
            sys.exit(ERR_CONFIG_FILE_NOT_FOUND)
        return config_path

    # 2. None specified on CLI: check default config.yaml
    default_name = "config.yaml"
    if os.path.exists(default_name):
        return os.path.abspath(default_name)
    default_path = os.path.join(base_dir, default_name)
    if os.path.exists(default_path):
        return default_path

    # 3. Default does not exist: ask which config file to use
    return prompt_for_config_file(base_dir=base_dir)


def load_config(config_file=None, base_dir=None, require_sources=True):
    """
    Resolves, loads, parses, resolves includes, and validates a configuration file.
    """
    if base_dir is None:
        base_dir = os.getcwd()

    config_path = resolve_config_path(config_file, base_dir=base_dir)

    if yaml is None:
        print("[!] Error: PyYAML is not installed. Please install PyYAML to load YAML configurations.")
        sys.exit(ERR_PYYAML_MISSING)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        print(f"\n[!] Error parsing YAML configuration '{config_file}'!")
        print("    If you are using Windows paths (like C:\\Users\\...), make sure to:")
        print("    1. Use forward slashes (e.g., C:/Users/...) OR")
        print("    2. Use single quotes ('C:\\Users\\...') instead of double quotes.")
        print(f"\nDetailed YAML Error:\n{exc}")
        sys.exit(ERR_CONFIG_PARSE_ERROR)

    config_dir = os.path.dirname(os.path.realpath(config_path))
    visited = {os.path.realpath(config_path)}

    try:
        merged_config = resolve_includes(raw_data, config_dir, visited)
        validate_config(merged_config, config_file, require_sources=require_sources)
    except ConfigValidationError as err:
        print(f"\n[!] Configuration Validation Error in '{config_file}':")
        print(f"    {err}\n")
        sys.exit(ERR_CONFIG_VALIDATION_ERROR)

    return merged_config
