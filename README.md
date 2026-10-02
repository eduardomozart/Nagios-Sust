# Nagios-Sust

A modular, automated tool to collect evidence from network equipment based on Nagios Service Status PDF reports.

## Features
- **Automated Parsing**: Reads Nagios PDF exports to identify alerting hosts.
- **Rule-based Orchestration**: Uses a `config.yaml` file to dynamically route hosts to specific automation scripts (e.g., FortiGate).
- **Selenium Automation**: Automatically logs into network appliances, checks interface status, and takes evidence screenshots.
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
2. Place your Nagios export (`report.pdf`) in the project root, or select it via the UI prompt.
3. Run the orchestrator:
   ```bash
   python main.py
   ```
4. The generated report will be saved as `Evidence_Report.docx` (or the equivalent language suffix specified in your config).

## Documentation
- 📖 **[User Guide](docs/USER_GUIDE.md)**: Start here to learn how to configure rules, use RegEx matching, generate multi-language reports, and customize the Word template conditional blocks.
- 🏗️ **[Architecture & Design](docs/ARCHITECTURE.md)**: Deep dive into the code structure, dynamic handlers, and templating engine choices for developers.
