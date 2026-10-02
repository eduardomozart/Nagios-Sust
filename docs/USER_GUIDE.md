# Nagios-Sust User Guide

Welcome to the Nagios Sustenance Automation tool! This guide will help you understand how to use, configure, and get the most out of the application.

## 1. How It Works
The program reads a Nagios PDF report (like `report.pdf`) and looks for all network equipment (hosts) that are in an alerting or warning state.
For each host found, it checks `config.yaml` to see if there is a matching rule. If a rule matches, it launches a "handler" (a specialized script) that logs into that specific equipment (using Google Chrome in the background), checks the status of its interfaces (like WAN1 and WAN2), and takes a screenshot.
Finally, all this evidence is injected into an MS Word template (`template.docx`).

## 2. Setting Up Your `config.yaml`
The `config.yaml` file (packaged as `config.example.yaml` by default - rename it to start using) is the brain of the automation. 

### Global Credentials
You can define global credentials so you don't have to type them every time. 
If you leave the password empty `""`, the script is smart enough to prompt you securely in the terminal during execution.

```yaml
credentials:
  username: "admin"
  password: "" # The script will ask for the password securely on the terminal
```

### Writing Rules
Rules define what equipment the script should automate.
**Order Matters**: The script evaluates rules from top to bottom. The first rule that matches the host will be used.
You can match hosts either using simple `startswith` prefixes or powerful `regex` expressions.

```yaml
rules:
  - name: "FortiGate Custom Regex"
    host_filter:
      regex: "^(FGTDEMO|SWDEMO)" # Matches FGTDEMO-01, SWDEMO-CORE, etc.
    handler: "fortigate"
    options: {}

  - name: "Generic FortiGate Rule"
    host_filter:
      startswith: "FGT" # Simple prefix match
    handler: "fortigate"
    options:
      url_template: "https://{host}/ng/interface"
```

### Multi-Language Exports
You can generate reports in multiple languages simultaneously! The script will look for `template_<language>.docx` files.
```yaml
exporters:
  - type: "docx"
    language: ["pt-BR", "en"] # Will generate one report per language
    output_file: "Evidence_Report.docx"
```

## 3. Dealing with File Paths in YAML
When defining paths (like the location of your Nagios report) in Windows, backslashes (`\`) can cause issues if placed inside double quotes. 

**Wrong:**
`nagios_report: "C:\Users\eduardo\Downloads\report.pdf"`

**Correct (Use single quotes):**
`nagios_report: 'C:\Users\eduardo\Downloads\report.pdf'`

**Correct (Use forward slashes):**
`nagios_report: "C:/Users/eduardo/Downloads/report.pdf"`

## 4. Customizing the Word Template
You don't need to know Python to change the layout of the final report!
Simply open `template_pt-BR.example.docx` or `template_en.example.docx` in Microsoft Word, rename it to remove the `.example` part, and modify it as you please. You can change fonts, colors, add company logos, or change the table layout. 

### Available Template Variables:
- `{{ res.host }}`: The equipment name
- `{{ res.rule_name }}`: The name of the rule that was matched (e.g., "Generic FortiGate Rule")
- `{{ res.wan_status.WAN1 }}` / `{{ res.wan_status.WAN2 }}`: Link status of the primary interfaces
- `{{ res.wan_status.WAN3 }}`: Link status of port5/internal5 (FortiGate specific, collected automatically if configured in the device's interface table)
- `{{ res.screenshot }}`: The injected screenshot

You can even use conditional logic directly in Word to show specific text depending on the equipment type or the presence of an error. 

**Pro-Tip**: To avoid syntax errors (`Encountered unknown tag 'endif'`) and prevent empty blank lines in your final document, you should place every `{%p` tag on its **OWN SEPARATE LINE** (by pressing Enter). 
The `p` in `{%p` stands for "paragraph". When the template engine reads a `{%p` tag, it will automatically **delete the entire paragraph/line** containing that tag from the final document, so it won't leave any holes or blank spaces!

```text
{%p if res.error %}
Error: {{ res.error }}
{%p else %}
WAN1 Link Status: {{ res.wan_status.WAN1 }}
{%p endif %}
```
