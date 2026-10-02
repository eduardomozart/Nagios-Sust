# Nagios-Sust

A modular, automated tool to collect evidence from network equipment based on Nagios Service Status PDF reports.

## Features
- **Automated Parsing**: Reads Nagios PDF exports to identify alerting hosts.
- **Rule-based Orchestration**: Uses a `config.yaml` file to dynamically route hosts to specific automation scripts (e.g., FortiGate).
- **Selenium Automation**: Automatically logs into network appliances, checks interface status, and takes evidence screenshots.
- **Word Template Engine**: Generates evidence reports using an easily customizable `template.docx` file. You can style the output directly in Microsoft Word.
- **Smart Credential Management**: Prompts for your password only once per execution.
- **Standalone Executable**: Distributed as a Windows `.exe` — no Python installation required.

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

## Using the Compiled Executable
If you downloaded the `.zip` release artifact:
1. Extract the folder.
2. Make sure `config.yaml` and `template.docx` are in the same folder as the `.exe`.
3. Double-click `Nagios-Sust-x64.exe`.

## Documentation
For a deeper dive into the code structure, dynamic handlers, and templating engine choices, see the [Architecture & Design Choices](docs/ARCHITECTURE.md) document.
