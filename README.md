# Nagios-Sust

A modular, automated tool to collect evidence from network equipment based on Nagios Service Status PDF reports.

## Features
- **Automated Parsing**: Reads Nagios PDF exports to identify alerting hosts.
- **Rule-based Orchestration**: Uses a `config.yaml` file to dynamically route hosts to specific automation scripts (e.g., FortiGate).
- **Selenium Automation**: Automatically logs into network appliances, checks interface status, and takes evidence screenshots.
- **Word Template Engine**: Generates evidence reports using an easily customizable `template.docx` file. You can style the output directly in Microsoft Word.
- **Smart Credential Management**: Prompts for your password only once per execution.
- **Standalone Executable**: Distributed as an unpacked `.zip` for instant startup on Windows — no Python installation required.

## Getting Started (Python Source)

### Prerequisites
- Python 3.12+
- Google Chrome (for Selenium WebDriver)

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/Nagios-Sust.git
   cd Nagios-Sust
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Usage
1. Place your Nagios export (`report.pdf`) in the project root. If the file is missing, a file explorer dialog will pop up asking you to select it.
2. Adjust your rules and settings in `config.yaml`.
3. Run the orchestrator:
   ```bash
   python main.py
   ```
4. The generated report will be saved as `Evidence_Report.docx` (or whatever name is specified in your config).

## Using the Compiled Release
If you downloaded the `.zip` release artifact from GitHub Actions:
1. Extract the folder.
2. Open the extracted folder (which contains the DLLs, `config.yaml`, and `template.docx`).
3. Double-click `Nagios-Sust-x64.exe`.

## Documentation
- 📖 **[User Guide](docs/USER_GUIDE.md)**: Start here to learn how to configure rules, handle Windows file paths, and customize the Word template.
- 🏗️ **[Architecture & Design](docs/ARCHITECTURE.md)**: Deep dive into the code structure, dynamic handlers, and templating engine choices for developers.
