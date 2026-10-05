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
- `url_template` (string): Overrides the default FortiGate interface URL. Default: `https://{host}/ng/interface`
- `diagnose_interfaces` (list): Which interfaces to extract physical status (UP/DOWN) and IP/Mask for. You can use a pipe `|` to provide fallbacks for mixed hardware (e.g. `"internal5|port5"`). Default: `["wan1", "wan2"]`
- `gather_gateway` (boolean): If `true`, the script parses `https://{host}/ng/routing/static` to export the Gateway IP to the Word template. Default: `false`
- `ping` (dictionary): Unified configuration block for ping execution overrides. You can specify a `"default"` block for global rules and interface names for specific rules. By default, ping is **disabled** for all interfaces. If enabled, it targets the local `"interface"` and uses the `"host"` execution source. 
  - `enabled` (boolean): Whether to execute ping for this interface. Default: `false`.
  - `target` (string): Set to `"gateway"` to ping the routing table gateway (implicitly enables `gather_gateway`), `"interface"` for local IP, `"ipsec_endpoint"` to auto-detect and ping an IPsec tunnel bound to this interface, or a custom IP like `"8.8.8.8"`. Default: `"interface"`.
  - `source` (string): Defines where the ping originates from. Set to `"host"` to ping locally from the machine running the script. Set to `"interface"` to run `execute ping` natively in the FortiOS CLI bound to the physical interface. Set to `"ipsec_endpoint"` to bind the FortiOS CLI ping to the logical IPsec tunnel interface. Default: `"host"`.
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
- `{{ res.screenshot }}`: The injected screenshot

### Available Template Variables (FortiGate Handler):
The `wan_status` object is a dictionary containing interface details. You can iterate over it using `{%p for intf_key, intf_data in res.wan_status.items() %}`.

Each `intf_data` contains the following properties:
- `{{ intf_data.status }}`: Link status of the interface (e.g., UP, DOWN, DOWN (No IP))
- `{{ intf_data.ip }}`: The raw IP address of the interface
- `{{ intf_data.mask }}`: The CIDR mask of the interface
- `{{ intf_data.gw }}`: The gateway IP address (if extracted or set via custom ping target)
- `{{ intf_data.ping_interface }}`: Boolean flag indicating if ping was requested for this interface in the configuration
- `{{ intf_data.ping_target_ip }}`: The actual IP address that was pinged
- `{{ intf_data.latency }}`: The ping latency in ms (empty if unreachable or not requested)

### Available Template Variables (Generic Ping Handler):
- No extra variables natively exported (only the global `res.latency` is populated)

You can even use conditional logic directly in Word to show specific text depending on the equipment type or the presence of an error. 

**Pro-Tip**: It's crucial to understand the difference between Paragraph Tags (`{%p`) and Standard Tags (`{%`):

1. **Paragraph Tags (`{%p if ... %}`)**: The `p` stands for "paragraph". When the template engine evaluates this, it **deletes the entire line/paragraph** from the document to prevent blank holes. Because of this, you must ALWAYS put `{%p` tags on their **OWN SEPARATE LINE** (by pressing Enter). If you place normal text or other tags on the same line as a `{%p` tag, they will be accidentally deleted!
   
2. **Standard Inline Tags (`{% if ... %}`)**: These tags DO NOT delete the paragraph. You should use these when you want to conditionally insert text in the middle of an existing sentence or line.

3. **MS Word Paragraph Spacing (Ghost Paragraphs)**: When Jinja removes a `{%p` tag, it merges the paragraphs above and below it. If those paragraphs have MS Word's native "Space After" formatting (usually 8pt or 12pt by default), those spaces stack up and look like a huge gap.
   **Fix**: Select the block of text in your Word template, go to the **Layout** tab -> **Spacing**, and set **After** to `0 pt`.

**Example of combining tags correctly:**

```text
{%p if res.error %}
Error: {{ res.error }}
{%p else %}
{%p for intf_key, intf_data in res.wan_status.items() %}
{%p if intf_data.ip %}
Link Status {{ intf_key }}: {{ intf_data.status }} {% if intf_data.latency %}({{ intf_data.latency }}){% endif %}
{%p endif %}
{%p endfor %}
{%p endif %}
```
