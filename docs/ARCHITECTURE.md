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
Handlers are specific Python scripts designed to interact with different types of equipment.
- **FortiGate (`fortigate.py`)**: Uses `selenium` to log into the FortiOS web interface. It parses the DOM for the `login_button` and dynamically queries the `portgroup` table to extract the link status of `WAN1` and `WAN2`. It saves a visual screenshot of the interface as evidence.
- *Extensibility*: To add a new equipment type (e.g., Cisco, CheckPoint), a developer simply creates a new handler file and maps it in the YAML config.

### 4. Modular Exporters (`exporters/`)
Once all handlers have finished executing, the gathered evidence and screenshots are passed to the exporters.
- **Docx Exporter (`docx_exporter.py`)**: 
  - **Design Choice**: Instead of hardcoding document styles using `python-docx`, we use `docxtpl` (Word + Jinja2 syntax). 
  - **Why?**: This allows the end-user to freely modify `template.docx` using Microsoft Word (changing fonts, adding company logos, adjusting layout) without ever touching the Python source code. The script simply injects the data into the `{{ variable }}` tags.

### 5. Build and Distribution
To simplify deployment for users without a Python environment, the application is compiled into a standalone Windows executable.
- **PyInstaller**: Used to package the code.
- **GitHub Actions (`.github/workflows/release.yml`)**: Automates the build process. When a git tag is pushed, it compiles the `.exe` and packages it alongside `config.yaml` and `template.docx` into a release `.zip` artifact.
