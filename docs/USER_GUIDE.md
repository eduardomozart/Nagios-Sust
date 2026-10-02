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
**Multiple Rules**: The script evaluates rules from top to bottom. If a host matches *multiple* rules, ALL matching rules will be executed in order! This means you can run a `fortigate` handler to grab WAN status AND a `generic_ping` handler for the exact same host, and both will appear as separate entries in your report.

You can match hosts either using simple `startswith` prefixes or powerful `regex` expressions.

**Advanced Regex (Negative Lookahead)**:
If you want to match all hosts starting with `FGT` *except* a specific one (e.g. `FGTDEMO01`), you can use a negative lookahead like this: `^FGT(?!DEMO01$)`.

```yaml
rules:
  - name: "Simple Ping Test"
    host_filter:
      startswith: "SW" # Matches switches or generic hosts
    handler: "generic_ping"
    options:
      capture_screenshot: false # Disables the CMD screenshot generation for this rule

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

### Handler Options
The `options` block inside a rule passes configuration to the handler script.

**Global Options (Applies to all handlers):**
- `capture_screenshot` (boolean): Set to `false` to prevent the handler from generating and saving screenshots. Defaults to `true`.

**Specific Options (FortiGate Handler):**
- `url_template` (string): Overrides the default FortiGate interface URL. Use `{host}` as a placeholder for the equipment name. Default: `https://{host}/ng/interface`
- `username` (string): Overrides the global credentials with a rule-specific username.
- `password` (string): Overrides the global credentials with a rule-specific password.

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

### Available Template Variables (All Handlers):
- `{{ res.host }}`: The equipment name
- `{{ res.rule_name }}`: The name of the rule that was matched (e.g., "Generic FortiGate Rule")
- `{{ res.latency }}`: The worst ping latency across all valid links in ms (empty if unreachable)

### Available Template Variables (FortiGate Handler):
- `{{ res.wan_status.WAN1 }}` / `{{ res.wan_status.WAN2 }}`: Link status of the primary interfaces (UP/DOWN)
- `{{ res.wan_status.WAN1_IP }}` / `{{ res.wan_status.WAN2_IP }}`: The raw IP address of the primary interfaces
- `{{ res.wan_status.WAN1_MASK }}` / `{{ res.wan_status.WAN2_MASK }}`: The CIDR mask of the primary interfaces
- `{{ res.wan_status.WAN1_LATENCY }}` / `{{ res.wan_status.WAN2_LATENCY }}`: The ping latency in ms (empty if unreachable)
- `{{ res.wan_status.WAN3 }}`: Link status of port5/internal5 (FortiGate specific, collected automatically if configured in the device's interface table)
- `{{ res.wan_status.WAN3_IP }}`: The raw IP address of port5/internal5
- `{{ res.wan_status.WAN3_MASK }}`: The CIDR mask of port5/internal5
- `{{ res.wan_status.WAN3_LATENCY }}`: The ping latency of port5/internal5 in ms
- `{{ res.screenshot }}`: The injected screenshot

### Available Template Variables (Generic Ping Handler):
- No extra variables natively exported (only the global `res.latency` is populated)

You can even use conditional logic directly in Word to show specific text depending on the equipment type or the presence of an error. 

**Pro-Tip**: It's crucial to understand the difference between Paragraph Tags (`{%p`) and Standard Tags (`{%`):

1. **Paragraph Tags (`{%p if ... %}`)**: The `p` stands for "paragraph". When the template engine evaluates this, it **deletes the entire line/paragraph** from the document to prevent blank holes. Because of this, you must ALWAYS put `{%p` tags on their **OWN SEPARATE LINE** (by pressing Enter). If you place normal text or other tags on the same line as a `{%p` tag, they will be accidentally deleted!
   
2. **Standard Inline Tags (`{% if ... %}`)**: These tags DO NOT delete the paragraph. You should use these when you want to conditionally insert text in the middle of an existing sentence or line.

**Example of combining both correctly:**

```text
{%p if res.error %}
Error: {{ res.error }}
{%p else %}
WAN1 Link Status: {{ res.wan_status.WAN1 }} {% if res.wan_status.WAN1_IP %}({{ res.wan_status.WAN1_IP }}){% endif %}
{%p endif %}
```
