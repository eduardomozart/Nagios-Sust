# Architecture & Design Choices

This document outlines the architectural decisions made for the **Nagios-Sust** project.

## Overview
The goal of this tool is to automate evidence collection for alerting hosts identified in a Nagios Service Status PDF report. Instead of a monolithic script, the system uses a modular, rule-based approach driven by a YAML configuration.

## Key Components

### 1. Orchestrator (`main.py`)
The orchestrator drives the entire workflow:
- Reads `config.yaml`.
- Parses the Nagios PDF report (prompting via a UI dialog if the file is missing).
- Iterates over the identified hosts and matches them against user-defined rules.
- Injects a `credential_provider` callback into matched handlers to decouple CLI/UI prompts from the automation logic.

### 2. PDF Parser (`utils/pdf_parser.py`)
Relies on `pdfplumber` to extract structured tabular data from the Nagios PDF export. It dynamically finds the header row and cleans up the host strings to prevent duplicate executions for the same equipment.

### 3. Modular Handlers (`handlers/`)
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
