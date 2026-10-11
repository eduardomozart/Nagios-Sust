import os
import sys
import glob
try:
    import yaml
except ImportError:
    yaml = None
import importlib

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


def load_config(config_file="config.yaml", base_dir=None, require_sources=True):
    """
    Loads, parses, resolves includes, and validates a configuration file.
    """
    if base_dir is None:
        base_dir = os.getcwd()

    if not os.path.isabs(config_file):
        if os.path.exists(config_file):
            config_path = os.path.abspath(config_file)
        else:
            config_path = os.path.join(base_dir, config_file)
    else:
        config_path = config_file

    if not os.path.exists(config_path):
        print(f"Error: Configuration file '{config_file}' not found.")
        print(f"Resolved path: '{config_path}'")
        print("Please verify the file path or provide a valid file with -c / --config.")
        sys.exit(1)

    if yaml is None:
        print("[!] Error: PyYAML is not installed. Please install PyYAML to load YAML configurations.")
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        print(f"\n[!] Error parsing YAML configuration '{config_file}'!")
        print("    If you are using Windows paths (like C:\\Users\\...), make sure to:")
        print("    1. Use forward slashes (e.g., C:/Users/...) OR")
        print("    2. Use single quotes ('C:\\Users\\...') instead of double quotes.")
        print(f"\nDetailed YAML Error:\n{exc}")
        sys.exit(1)

    config_dir = os.path.dirname(os.path.realpath(config_path))
    visited = {os.path.realpath(config_path)}

    try:
        merged_config = resolve_includes(raw_data, config_dir, visited)
        validate_config(merged_config, config_file, require_sources=require_sources)
    except ConfigValidationError as err:
        print(f"\n[!] Configuration Validation Error in '{config_file}':")
        print(f"    {err}\n")
        sys.exit(1)

    return merged_config
