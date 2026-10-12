# Architecture & Design Choices

This document outlines the architectural decisions made for the **Nagios-Sust** project.

## Overview
The goal of this tool is to automate evidence collection for alerting hosts identified in a Nagios Service Status PDF report. Instead of a monolithic script, the system uses a modular, rule-based approach driven by a YAML configuration.

## Key Components

### 1. Configuration Engine & Validation (`utils/config.py`)
Configuration loading and validation is centralized in `utils/config.py`:
- **CLI Selection (`-c` / `--config`)**: Supports executing any specified configuration file (defaulting to `config.yaml`).
- **Modular Includes (`include:`)**: Allows breaking configuration into reusable modules (e.g. `include: ["sources.yaml", "rules.yaml"]` or globs `include: "conf.d/*.yaml"`). Recursively resolves includes with circular reference detection and deep dictionary merging.
- **Strict Schema Validation**: Validates YAML syntax and checks structure (verifying sources exist in `sources/`, handlers exist, rules have filters, exporters specify `languages`). Rejects deprecated keys like `device_source` and exporter `language`.

### 2. Orchestrator (`main.py`)
The orchestrator drives the execution flow:
- Parses CLI parameters (`-c` / `--config`) via `argparse`.
- Invokes `utils/config.load_config`.
- Delegates host aggregation across configured `device_sources` to `sources.load_unique_hosts` (or prompts for device names/sources interactively if omitted and not specified via `-d`).
- Iterates over the deduplicated host collection and matches each host against user-defined rules.
- Injects a `credential_provider` callback into matched handlers to decouple CLI/UI prompts from the automation logic.
- Enriches each handler's result dictionary with `rule_name`, `handler`, `sources` (flat list of discovered sources), and namespaced source dictionaries (`res.<SOURCE>`, e.g. `res.nagios_pdf`, `res.airwave`) before passing to exporters.

### 3. Modular Sources & Multi-Source Aggregation (`sources/`)
Device and alert discovery is decoupled into pluggable source modules:
- **Nagios PDF (`sources/nagios_pdf.py`)**: Resolves Nagios Service Status PDF reports (prompting via a native UI dialog via `utils/dialog.py` if the file is missing), parses tabular alerts via `utils/pdf_parser.py`, and applies optional host filtering.
- **AirWave (`sources/airwave.py`)**: Connects to the Aruba AirWave API via `utils/airwave.py` and `pyairwave`, enumerating devices filtered by `host_filter` (`startswith` / `regex`), device categories, and hardware models.

When multiple sources are configured (e.g. `device_sources: ["nagios_pdf", "airwave"]`), `sources.load_unique_hosts` queries each source and canonicalizes host records (case-insensitively). Overlapping devices are merged into a single unique host object housing each source's discovery attributes cleanly under its source key (e.g. `item["nagios_pdf"]`, `item["airwave"]`) and tracking source provenance in `item["sources"]` as a flat list of strings (appending each source that discovered the host).

### 4. Modular Handlers (`handlers/`)
Handlers are specific Python scripts designed to interact with different types of equipment. To add a new equipment type (e.g., Cisco, CheckPoint), a developer simply creates a new handler file and maps it in the YAML config.

- **FortiGate (`fortigate.py`)**: Uses `selenium` to log into the FortiOS web interface. It parses the DOM for the `login_button` and dynamically queries the `portgroup` table to extract the link status of `WAN1` and `WAN2`. It saves a visual screenshot of the interface as evidence and scrapes the Dashboard System Information widget into a normalized `res.system_info` structure.
- **Aruba Switches (`aruba.py`)**: Connects over SSH via `paramiko` and inspects `show system` output to automatically detect whether the device is running **AOS-CX** or **ProCurve**, then delegates execution to the corresponding handler (`arubacx.py` or `procurve.py`), which can also be invoked directly. Both extract model, firmware version, serial number, uptime, CPU utilization, and calculate memory usage percentages (including VSF stack members) into `res.system_info`.
- **AirWave (`airwave.py`)**: Automates Aruba AirWave WebUI login via `selenium`, navigates to the Device Monitoring page (`/ap_monitoring?id={device_id}`), dynamically adapts window width to capture the entire Device Info table without horizontal clipping, and parses inventory attributes (firmware, model, serial, uptime, stack state, temperature) into `res.system_info`. Resolves device IDs using `utils/airwave.py` via `pyairwave`.
- **Generic Ping (`generic_ping.py`)**: Provides a standalone ping and CMD screenshot evidence collector, and exposes `execute_generic_ping` as a reusable helper for any handler requiring network latency checks.

### 4. Modular Exporters (`exporters/`)
Once all handlers have finished executing, the gathered evidence and screenshots are passed to the exporters.
- **Docx Exporter (`docx_exporter.py`)**: Injects collected evidence and screenshots into the Word template and saves the final report.

### 5. Build and Distribution
To simplify deployment for users without a Python environment, the application is compiled into a standalone Windows executable.
- **PyInstaller**: Used to package the code.
- **GitHub Actions (`.github/workflows/release.yml`)**: Automates the build process. When a git tag is pushed, it compiles the `.exe` and packages it alongside `config.yaml` and `template.docx` into a release `.zip` artifact.

## Key Design Choices

### Standardized `res.system_info` Schema
Device metadata is strictly housed inside `res.system_info` (`hostname`, `os_type`, `model`, `serial_number`, `version`, `uptime`, `cpu_util`, `memory_usage`), preventing root-level field pollution and enabling generic, hardware-agnostic Jinja2 tags in Word templates.
- **Hardware-Agnostic Reporting**: Templates can render standard system inventory tables (firmware, serial number, uptime, CPU/memory utilization) without needing vendor-specific conditional tags.
- **Namespace Cleanliness**: Root-level dictionary keys are reserved for handler-specific operational evidence (e.g., WAN link statuses, IPsec tunnel states, CLI ping captures), eliminating key collisions across different handler implementations.

### Decoupled Document Templating (`docxtpl`)
Instead of hardcoding document styles using `python-docx`, the reporting engine uses `docxtpl` (Word + Jinja2 syntax). This allows end-users to freely modify `template.docx` using Microsoft Word (changing fonts, adding company logos, adjusting layout) without ever touching the Python source code. The script simply injects the data into the `{{ variable }}` tags.

## Application Exit Codes

Nagios-Sust defines unified, distinct numeric exit codes in `utils/exit_codes.py` for each fatal termination condition. These exit codes allow CI/CD runners, external wrapper scripts, and CLI operators to differentiate between configuration mistakes, source/connectivity failures, and template rendering errors:

| Exit Code | Constant | Category | Description |
|---|---|---|---|
| `0` | `EXIT_SUCCESS` | Success | Application completed successfully. |
| `10` | `ERR_CONFIG_FILE_NOT_FOUND` | Configuration | Explicitly specified configuration file (`-c` / `--config`) was not found. |
| `11` | `ERR_PROMPTED_CONFIG_NOT_FOUND` | Configuration | Configuration file path provided during interactive prompt does not exist. |
| `12` | `ERR_NO_CONFIG_SELECTED` | Configuration | No configuration file was selected or interactive config selection prompt was aborted. |
| `13` | `ERR_PYYAML_MISSING` | Configuration | PyYAML package is not installed in the Python runtime environment. |
| `14` | `ERR_CONFIG_PARSE_ERROR` | Configuration | YAML syntax or parsing error encountered while parsing configuration files. |
| `15` | `ERR_CONFIG_VALIDATION_ERROR` | Configuration | Configuration schema validation failed (e.g., missing required fields, invalid keys, circular includes). |
| `20` | `ERR_SOURCE_NOT_FOUND` | Device Sources | Specified device source name was not found in `sources/`. |
| `21` | `ERR_SOURCE_LOAD_ERROR` | Device Sources | Fatal error encountered while querying or loading devices from a source module. |
| `22` | `ERR_PDF_FILE_NOT_SELECTED` | Device Sources | Nagios PDF file dialog was cancelled or no file was selected. |
| `23` | `ERR_PDF_PARSE_ERROR` | Device Sources | Fatal error encountered while parsing the Nagios Service Status PDF file. |
| `24` | `ERR_AIRWAVE_API_ERROR` | Device Sources | Fatal connection or query error communicating with the Aruba AirWave API. |
| `25` | `ERR_DEVICE_PROMPT_ABORTED` | Orchestrator | Interactive device or source selection prompt was aborted without input. |
| `30` | `ERR_DOCX_RENDER_ERROR` | Exporters | Fatal template error encountered while rendering Word template (`docxtpl`). |
