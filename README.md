# Nagios-Sust

A modular, automated tool to collect evidence from network equipment based on Nagios Service Status PDF reports and Aruba AirWave.

## Features
- **Multi-Source Device Discovery**: Dynamically discovers target devices from multiple sources:
  - **Nagios PDF (`nagios_pdf`)**: Reads Nagios Service Status PDF exports to identify alerting hosts and services.
  - **Aruba AirWave (`airwave`)**: Queries the AirWave XML API to discover network switches, controllers, and APs with customizable category and model filters.
- **Rule-based Orchestration**: Uses a `config.yaml` file to dynamically route hosts to specific automation scripts (e.g., FortiGate, Aruba CX/ProCurve, Generic Ping).
- **Browser & CLI Automation**: Automatically logs into network appliances via Selenium or SSH, checks interface status, gathers telemetry, and captures evidence screenshots.
- **Word Template Engine**: Generates evidence reports using an easily customizable `template.docx` file. You can style the output directly in Microsoft Word.
- **Smart Credential Management**: Prompts for your password only once per execution.
- **Standalone Executable**: Distributed as an unpacked `.zip` for instant startup on Windows — no Python installation required.

## Getting Started
The easiest way to run Nagios-Sust is by using the pre-compiled Windows executable provided in the repository releases. No Python installation is required!

1. Download the latest `.zip` release artifact from the [Releases page](../../releases).
2. Extract the folder anywhere on your computer.
3. **Important Initial Setup**:
   - Rename `config.example.yaml` to `config.yaml`.
   - Rename `template_pt-BR.example.docx` to `template_pt-BR.docx` (or do the same for the English one).
4. Run the program:
   - Double-click `Nagios-Sust-x64.exe`
   - If a Nagios PDF is not found in the same folder, a native file explorer dialog will pop up asking you to select it.

## Developer Setup (Python Source)
If you wish to modify the code, develop new handlers, or run the tool directly from source:

### Prerequisites
- Python 3.12+
- Google Chrome (for Selenium WebDriver)

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/eduardomozart/Nagios-Sust.git
   cd Nagios-Sust
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Usage
1. Copy the example config and template files:
   ```bash
   cp config.example.yaml config.yaml
   cp template_pt-BR.example.docx template_pt-BR.docx
   ```
2. Place your Nagios export (`report.pdf`) in the project root, or configure device sources (`nagios_pdf`, `airwave`) in your config.

3. Run the orchestrator:
   ```bash
   python main.py
   ```

### Supported Arguments

| Argument | Short | Required | Description |
| :--- | :---: | :---: | :--- |
| `--config` | `-c` | No | Path to YAML configuration file. (Default: `config.yaml`) |
| `--device` | `-d` | No | Device hostname to process directly. Can be passed multiple times (e.g. `-d SW-01 -d SW-02`) or comma-separated (`-d SW-01,SW-02`). Bypasses `device_sources`. |
| `--version` | `-v` | No | Show program's version number and exit. |
| `--help` | `-h` | No | Show help message and exit. |

### Examples

Run with a custom configuration file:
```bash
python main.py -c custom_config.yaml
```

Run directly for specific devices (bypassing `device_sources`):
```bash
python main.py -d SW-CORE-01 -d SW-ACCESS-01
```

4. The generated report will be saved as `Evidence_Report.docx` (or with language suffixes like `Evidence_Report_pt-BR.docx` if multiple languages are configured in `exporters`).

## Documentation
- 📖 **[User Guide](docs/USER_GUIDE.md)**: Start here to learn how to configure rules, use RegEx matching, generate multi-language reports, and customize the Word template conditional blocks.
- 🏗️ **[Architecture & Design](docs/ARCHITECTURE.md)**: Deep dive into the code structure, dynamic handlers, and templating engine choices for developers.
