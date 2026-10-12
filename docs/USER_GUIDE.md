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
**Multiple Rules (Cumulative Host Execution)**: The script evaluates rules from top to bottom. If a host matches *multiple* rules, ALL matching rules will execute in order and accumulate into **one unified result entry per host** in your report! For example, if a host matches both a `generic_ping` rule and an `aruba` rule, both handlers will execute for that device. The ping latency and the switch telemetry are safely namespaced under their respective handlers (`res.handlers.generic_ping.latency` and `res.handlers.aruba.system_info`), and all matched rule names are tracked in `res.rules`.

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

**Specific Options (Generic Ping Handler):**
- `count` (int): Number of echo request packets to send. Default: `4`.

**Specific Options (FortiGate Handler):**
- `url_template` (string): Overrides the default FortiGate interface URL. Default: `https://{host}/ng/interface`
- `gather_system_info` (boolean): Scrapes the System Information widget on `/ng/dashboard` to retrieve Serial Number, Firmware (e.g. `v7.4.11`), and Uptime. Default: `true`.
- `diagnose_interfaces` (list): Which interfaces to extract physical status (UP/DOWN) and IP/Mask for. You can use a pipe `|` to provide fallbacks for mixed hardware (e.g. `"internal5|port5"`). Default: `["wan1", "wan2"]`
- `gather_gateway` (boolean): If `true`, the script parses `https://{host}/ng/routing/static` to export the Gateway IP to the Word template. Default: `false`
- `ping` (dictionary): Unified configuration block for ping execution overrides. You can specify a `"default"` block for global rules and interface names for specific rules. By default, ping is **disabled** for all interfaces. If enabled, it targets the local `"interface"` and uses the `"host"` execution source. 
  - `enabled` (boolean): Whether to execute ping for this interface. Default: `false`.
  - `target` (string): Set to `"gateway"` to ping the routing table gateway (implicitly enables `gather_gateway`), `"interface"` for local IP, `"ipsec_endpoint"` to auto-detect and ping an IPsec tunnel bound to this interface, or a custom IP like `"8.8.8.8"`. Default: `"interface"`.
  - `source` (string): Defines where the ping originates from. Set to `"host"` to ping locally from the machine running the script (delegates to `execute_generic_ping` without screenshots). Set to `"interface"` to run `execute ping` natively in the FortiOS CLI bound to the physical interface. Set to `"ipsec_endpoint"` to bind the FortiOS CLI ping to the logical IPsec tunnel interface. Default: `"host"`.
  - `count` (int): Number of echo request packets to send for the interface. Default: `1`.
- `username` (string): Overrides the global credentials with a rule-specific username.
- `password` (string): Overrides the global credentials with a rule-specific password.

**Specific Options (Aruba Handlers):**
- `port` (int): SSH port for the switch connection. Default: `22`.
- `timeout` (int): SSH connection and command execution timeout in seconds. Default: `15`.
- *Note*: You can use the generic `aruba` handler to automatically probe and detect whether the connected switch is **AOS-CX** or **ProCurve**, which then delegates to the corresponding specialized handler. You can also call `arubacx` or `procurve` directly. When configured as `handler: "aruba"`, the orchestrator stores all collected evidence under `res.handlers.aruba` (e.g. `res.handlers.aruba.system_info`), matching the rule's handler name.

**Specific Options (AirWave Handler):**
- `airwave_url` (string): Aruba AirWave server URL or Hostname/IP. Default: `https://airwave`.
- `username` (string): Overrides global credentials for the AirWave connection.
- `password` (string): Overrides global credentials for the AirWave connection.
- `capture_screenshot` (boolean): Captures the Device Info viewport adjusted for horizontal scrolling. Default: `true`.

### Device Sources & Multi-Source Enumeration
Nagios-Sust supports multiple device discovery sources under `device_sources`:
- **`nagios_pdf`**: Reads and parses Nagios Service Status PDF reports.
- **`airwave`**: Connects to the Aruba AirWave API via `pyairwave` to enumerate network devices.

You can specify one or multiple sources simultaneously. When multiple sources are specified, hosts are deduplicated by name and their metadata is merged:
```yaml
device_sources:
  - "nagios_pdf"
  - "airwave"

nagios_pdf:
  report_file: "report.pdf"

airwave:
  url: "https://airwave"
  host_filter:
    startswith: "SW" # e.g. "SW" (use regex for multiple conditions)
    regex: "^(SW|AP)" # or regex pattern
  device_categories: ["switch"] # Optional: switch, thin_ap, controller
  models: [] # Optional: filter by model
```

> [!NOTE]
> If `device_sources` is omitted from your configuration and no `-d` flags are passed on the CLI, the program will display the list of supported device sources and prompt you in the terminal to enter device names (comma-separated, similar to `-d`) or select a source name.

### CLI Config Option (`-c` / `--config`)
You can specify a custom configuration file path when running the script:
```bash
python main.py -c /path/to/custom_config.yaml
```

### CLI Device Specification (`-d` / `--device`)
Instead of enumerating devices from `device_sources`, you can directly pass one or multiple target devices via the command line:
```bash
python main.py -d SW-CORE-01 -d SW-ACCESS-01
```
Or with comma-separated values:
```bash
python main.py -d SW-CORE-01,SW-ACCESS-01
```
When `-d` / `--device` is specified, `device_sources` is bypassed and the orchestrator directly evaluates your rules and handlers on the specified device list.

### Modular Configuration (`include:`)
Configurations can include other configuration files using `include:` with single files, lists of files, or glob patterns:
```yaml
include:
  - "conf.d/*.yaml"
  - "credentials.secret.yaml"
```
Included files are deep-merged, with parent settings taking precedence and list items concatenated (and `device_sources` automatically deduplicated). Circular includes are safely detected and rejected.

### Multi-Language Exports
You can generate reports in multiple languages simultaneously! The script will look for `template_<language>.docx` files.
```yaml
exporters:
  - type: "docx"
    languages: ["pt-BR", "en"] # Will generate one report per language
    output_file: "Evidence_Report.docx"
```

## 3. Dealing with File Paths in YAML
When defining paths (like the location of your Nagios report) in Windows, backslashes (`\`) can cause issues if placed inside double quotes. 

**Wrong:**
```yaml
nagios_pdf:
  report_file: "C:\Users\Administrator\Downloads\report.pdf"
```

**Correct (Use single quotes):**
```yaml
nagios_pdf:
  report_file: 'C:\Users\Administrator\Downloads\report.pdf'
```

**Correct (Use forward slashes):**
```yaml
nagios_pdf:
  report_file: "C:/Users/Administrator/Downloads/report.pdf"
```

## 4. Customizing the Word Template
You don't need to know Python to change the layout of the final report!
Simply open `template_pt-BR.example.docx` or `template_en.example.docx` in Microsoft Word, rename it to remove the `.example` part, and modify it as you please. You can change fonts, colors, add company logos, or change the table layout.

### Cumulative Subsystem Namespacing Contract
Nagios-Sust structures all collected evidence into 4 distinct architectural domains per host: `host`, `rules`, `handlers`, and `sources`. When a device matches multiple rules, results accumulate into **one unified result entry per host** without overwriting or polluting namespaces:

```json
{
  "host": {
    "name": "SW-CORE-01"
  },
  "rules": [
    "Core Switches Ping",
    "Core Switches Telemetry"
  ],
  "handlers": {
    "generic_ping": {
      "error": 0,
      "latency": 15,
      "screenshot": {
        "image": "<InlineImage>",
        "path": "/path/to/screenshots/20261011_120000/generic_ping/screenshot_SW-CORE-01.png",
        "filename": "screenshot_SW-CORE-01.png",
        "captured": true
      }
    },
    "aruba": {
      "error": 0,
      "system_info": {
        "hostname": "SW-CORE-01",
        "os_type": "AOS-CX",
        "model": "R0X24C 6405 v2 Chassis",
        "serial_number": "SG0000000001",
        "version": "FL.10.16.1020",
        "uptime": "38 weeks, 22 hours, 53 minutes",
        "cpu_util": 18,
        "memory_usage": 15.0,
        "members": []
      }
    }
  },
  "sources": {
    "list": ["nagios_pdf", "airwave"],
    "nagios_pdf": {
      "status": "CRITICAL",
      "service": "PING"
    },
    "airwave": {
      "device_id": "538",
      "ip": "10.0.0.1",
      "model": "Aruba 6300M"
    }
  }
}
```

### The 4 Subsystem Domains

1. **`res.host` (Identity)**:
   - `{{ res.host.name }}`: The device name (e.g. `SW-CORE-01`, `FGT-CORE-01`).

2. **`res.rules` (Rule Metadata)**:
   - `{{ res.rules }}`: Direct list of all matched rule names executed for this host.
   - Display as text: `{{ res.rules | join(', ') }}`
   - Iterate over rules: `{%p for rule in res.rules %}`

3. **`res.handlers` (Execution Evidence)**:
   - Pure dictionary mapping executed handler names to their evidence dictionaries (e.g. `res.handlers.generic_ping`, `res.handlers.aruba`, `res.handlers.fortigate`).
   - Dynamically iterate over handlers: `{%p for handler_name, handler_data in res.handlers.items() %}`
   - **`res.handlers.<HANDLER>`**: Isolated evidence namespace for each executed handler, matching the rule's `handler` name (e.g. `res.handlers.aruba` when using `handler: "aruba"`):
     - `{{ res.handlers.<HANDLER>.error }}`: Standard integer error code (`0` for success, non-zero for faults).
     - `{{ res.handlers.<HANDLER>.latency }}`: Ping latency integer in ms (`>= 0` on success, `None` on timeout; only present on handlers that ping the device itself like `generic_ping`).
     - `{{ res.handlers.<HANDLER>.system_info }}`: Hardware and OS telemetry dictionary (only present when scraped or parsed by the handler):
       - `{{ res.handlers.<HANDLER>.system_info.hostname }}`: Detected hostname
       - `{{ res.handlers.<HANDLER>.system_info.os_type }}`: Operating system (`FortiOS`, `AOS-CX`, or `AOS-S`)
       - `{{ res.handlers.<HANDLER>.system_info.model }}`: Hardware or chassis model
       - `{{ res.handlers.<HANDLER>.system_info.serial_number }}`: Chassis/device serial number
       - `{{ res.handlers.<HANDLER>.system_info.version }}`: Firmware/software version
       - `{{ res.handlers.<HANDLER>.system_info.uptime }}`: Uptime string
       - `{{ res.handlers.<HANDLER>.system_info.cpu_util }}`: CPU utilization percentage
       - `{{ res.handlers.<HANDLER>.system_info.memory_usage }}`: Memory utilization percentage
       - `{{ res.handlers.<HANDLER>.system_info.members }}`: List of VSF stack members (for stacked switches)
     - `{{ res.handlers.<HANDLER>.if_status }}`: Interface status dictionary (populated by `fortigate` handler):
       - Iterated using: `{%p for intf_name, intf_data in res.handlers.fortigate.if_status.items() %}`
       - `{{ intf_data.status }}`: Link status (e.g. `UP`, `DOWN`)
       - `{{ intf_data.ip }}`: Interface IP address
       - `{{ intf_data.mask }}`: CIDR subnet mask
       - `{{ intf_data.gw }}`: Gateway IP address
       - `{{ intf_data.latency }}`: Interface ping latency in ms (`>= 0` on success, `None` on failure/timeout; key is only present if `ping_interface` is enabled).
       - `{{ intf_data.ping_count }}`: Number of ping packets sent for this interface (key is only present if `ping_interface` is enabled).
     - `{{ res.handlers.<HANDLER>.screenshot }}`: Visual screenshot metadata (only present if captured):
       - `{{ res.handlers.<HANDLER>.screenshot.image }}`: Word-injected image object (`docxtpl.InlineImage`)
       - `{{ res.handlers.<HANDLER>.screenshot.path }}`: Absolute file path to the saved screenshot
       - `{{ res.handlers.<HANDLER>.screenshot.filename }}`: Base filename of the screenshot
       - `{{ res.handlers.<HANDLER>.screenshot.captured }}`: Boolean flag indicating if file was successfully saved

4. **`res.sources` (Discovery Attributes)**:
   - `{{ res.sources.list }}`: List of sources that discovered the device (e.g. `["nagios_pdf", "airwave"]`).
   - Display as text: `{{ res.sources.list | join(', ') }}`
   - **`res.sources.<SOURCE>`**: Sub-dictionary housing discovery attributes without polluting root:
     - **`{{ res.sources.nagios_pdf }}`**: Alert details from Nagios PDF (e.g. `{{ res.sources.nagios_pdf.status }}`, `{{ res.sources.nagios_pdf.service }}`).
     - **`{{ res.sources.airwave }}`**: Inventory attributes from AirWave API (e.g. `{{ res.sources.airwave.device_id }}`, `{{ res.sources.airwave.ip }}`, `{{ res.sources.airwave.model }}`).

### Standard Integer Error Codes
Handlers return standardized numeric error codes (`utils/error_codes.py`) to decouple execution results from presentation languages:

| Error Code | Constant | Meaning |
|---|---|---|
| `0` | `ERR_OK` | Operational / Success |
| `1` | `ERR_IF_DOWN` | Monitored interface physically down |
| `2` | `ERR_IF_LOGICAL_DOWN` | Monitored interface logically down (unassigned IP `0.0.0.0`) |
| `3` | `ERR_PING_TIMEOUT` | Ping gateway or interface timed out |
| `4` | `ERR_DEVICE_DOWN` | Device reported down in discovery/monitoring |
| `5` | `ERR_DEVICE_NOT_FOUND` | Device not found in inventory enumeration |
| `6` | `ERR_AUTH_FAILED` | Authentication or login failed |
| `7` | `ERR_CONNECTION_TIMEOUT` | Connection timed out |
| `8` | `ERR_AUTOMATION_FAILED` | Handler script or browser automation encountered an unhandled error |

### Multi-Language Error Translation Examples

Because error codes are numbers, templates translate errors into the report's native language using standard Jinja conditions.

#### English Template (`template_en.docx`):
```text
{%p if res.handlers.fortigate.error == 0 %}
Status: Operational
{%p elif res.handlers.fortigate.error == 1 %}
Status: Error - Interface physically down
{%p elif res.handlers.fortigate.error == 2 %}
Status: Error - Interface logically down (IP 0.0.0.0)
{%p elif res.handlers.fortigate.error == 3 %}
Status: Error - Ping timeout to gateway
{%p elif res.handlers.fortigate.error == 6 %}
Status: Error - Authentication failed
{%p else %}
Status: Error - Automation failure (Code {{ res.handlers.fortigate.error }})
{%p endif %}
```

#### Portuguese Template (`template_pt-BR.docx`):
```text
{%p if res.handlers.fortigate.error == 0 %}
Status: Operacional
{%p elif res.handlers.fortigate.error == 1 %}
Status: Falha - Interface fisicamente inativa
{%p elif res.handlers.fortigate.error == 2 %}
Status: Falha - Interface logicamente inativa (IP 0.0.0.0)
{%p elif res.handlers.fortigate.error == 3 %}
Status: Falha - Tempo limite de ping para o gateway
{%p elif res.handlers.fortigate.error == 6 %}
Status: Falha - Falha de autenticação
{%p else %}
Status: Falha - Erro de automação (Código {{ res.handlers.fortigate.error }})
{%p endif %}
```

### Rendering Handler Screenshots in Word
When `capture_screenshot` is enabled and successful, inject the screenshot using `image`:

```text
{%p if res.handlers.fortigate.screenshot and res.handlers.fortigate.screenshot.captured %}
{{ res.handlers.fortigate.screenshot.image }}
{%p endif %}
```

### Iterating Over Executed Handlers
You can also dynamically iterate through all handlers executed for a host:

```text
{%p for h_name, h_data in res.handlers.items() %}
Handler: {{ h_name }} | Error: {{ h_data.error }}
{%p if h_data.latency %}
Latency: {{ h_data.latency }} ms
{%p endif %}
{%p if h_data.system_info %}
Model: {{ h_data.system_info.model }} | S/N: {{ h_data.system_info.serial_number }}
{%p endif %}
{%p endfor %}
```

### Formatting Tips: Paragraph (`{%p`) vs Inline (`{%`) Tags
1. **Paragraph Tags (`{%p if ... %}`)**: The `p` stands for "paragraph". When evaluated, it **deletes the entire line/paragraph** from the document to avoid blank space. ALWAYS place `{%p` tags on their **OWN SEPARATE LINE** (by pressing Enter). Never place regular text or standard tags on the same line as a `{%p` tag!
2. **Standard Inline Tags (`{% if ... %}`)**: These tags DO NOT delete paragraphs. Use them when conditionally inserting text inside an existing sentence or table cell.
3. **MS Word Paragraph Spacing**: When Jinja removes a `{%p` tag, MS Word's native paragraph spacing ("Space After") can accumulate. Select the text block in Word, go to the **Layout** tab -> **Spacing**, and set **After** to `0 pt`.
