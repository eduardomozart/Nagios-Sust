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
  - `target` (string): Set to `"gateway"` to ping the routing table gateway (implicitly enables `gather_gateway`), `"interface"` for local IP, `"ipsec_remotegw"` to auto-detect and ping the remote gateway of an IPsec tunnel bound to this interface, or a custom IP like `"8.8.8.8"`. Default: `"interface"`.
  - `source` (string): Defines where the ping originates from. Set to `"host"` to ping locally from the machine running the script. Set to `"interface"` to run `execute ping` natively in the FortiOS CLI bound to the physical interface. Set to `"ipsec_endpoint"` to bind the FortiOS CLI ping to the logical IPsec tunnel interface. Default: `"host"`.
  - `tunnel_name` (string): Optional. When `target` is set to `"ipsec_remotegw"` or `source` is set to `"ipsec_endpoint"`, explicitly specifies the tunnel name (e.g. `"con1"`). If not specified, the script auto-detects the first tunnel bound to the physical interface. If the tunnel is not found, ping will abort cleanly.
  - `count` (int): Number of echo request packets to send for the interface. Default: `1`.
- `username` (string): Overrides the global credentials with a rule-specific username.
- `password` (string): Overrides the global credentials with a rule-specific password.

**Specific Options (Aruba Handlers):**
- `port` (int): SSH port for the switch connection. Default: `22`.
- `timeout` (int): SSH connection and command execution timeout in seconds. Default: `15`.
- *Note*: You can use the generic `aruba` handler to automatically probe and detect whether the connected switch is **AOS-CX** or **ProCurve**, which then delegates to the corresponding specialized handler. You can also call `arubacx` or `procurve` directly. When configured as `handler: "aruba"`, the orchestrator stores all collected evidence under `res.handlers.aruba` (e.g. `res.handlers.aruba.system_info`), matching the rule's handler name.

**Switch Hardware Troubleshooting Commands:**
Rather than executing generic environment summaries, the switch handlers execute granular hardware diagnostics to collect precise component states:
- **ArubaOS-S / ProCurve (`procurve`)**:
  - `show system`: Switch model, firmware version, serial number, uptime, CPU and memory utilization.
  - `show system fans`: Fan status and failure state across all VSF stack members.
  - `show system temperature`: Air temperatures and sensor thresholds across stack members.
    > [!NOTE]
    > Entry-level, compact, or fanless switches (such as specific models in the Aruba 2530 or low-port 2930F families) lack physical chassis temperature sensors. The CLI accepts the command because ArubaOS-S is unified, but the data table is not populated. The parser gracefully detects this and emits 0 false alerts.
  - `show system power-supply`: Power supply bay presence, model, power state, and wattage.
- **ArubaOS-CX (`arubacx`)**:
  - `show system`: Chassis model, AOS-CX firmware version, uptime, CPU and memory utilization.
  - `show environment fan`: Fan tray and fan module speed, direction, RPM, and operational status.
  - `show environment temperature`: Module sensor temperatures and severity status (`normal`, `alert`, `critical`, `emergency`).
  - `show environment power-supply`: Power supply bay presence, state, and wattage.

**Specific Options (AirWave Handler):**
- `airwave_url` (string): Aruba AirWave server URL or Hostname/IP. Default: `https://airwave`.
- `username` (string): Overrides global credentials for the AirWave connection.
- `password` (string): Overrides global credentials for the AirWave connection.
- `capture_screenshot` (boolean): Captures the Device Info viewport adjusted for horizontal scrolling. Default: `true`.

### Alert Thresholds Configuration (`alerts:`)
Nagios-Sust includes an automated threshold evaluation engine. You can customize evaluation thresholds in `config.yaml` under `alerts:`. All threshold limits use **integers only** without color names, categorizing telemetry strictly into `Normal`, `Warning`, and `Critical` severities:

```yaml
alerts:
  thresholds:
    cpu:
      warning: 75
      critical: 90
    memory:
      warning: 75
      critical: 90
    interface_utilization:
      warning: 80
      critical: 100
    packet_buffers:
      warning: 85
      critical: 95
    tx_drops:
      warning: 85
      critical: 95
    rx_errors:
      warning: 85
      critical: 95
    message_buffers:
      warning: 85
      critical: 95
    fans:
      warning: 1
      critical: 2
    temperature:
      warning: 25
      critical: 60
    power_supplies:
      warning: 1
      critical: 2
    storage:
      warning: 70
      critical: 90
    firmware_version:
      warning: 1
      critical: 2
```

#### Default Alert Thresholds (English)

| Metric Name | Warning Threshold | Critical Threshold | Notes |
|---|---|---|---|
| **CPU (%)** | `>= 75` | `>= 90` | Switch or appliance CPU utilization percentage |
| **Memory (%)** | `>= 75` | `>= 90` | Memory utilization percentage |
| **Interface Utilization (%)** | `>= 80` | `>= 100` | Interface bandwidth utilization |
| **Packet Buffers** | `>= 85` | `>= 95` | Packet buffer utilization |
| **Tx Drops** | `>= 85` | `>= 95` | Transmit packet drop rate |
| **Rx Errors** | `>= 85` | `>= 95` | Receive packet error rate |
| **Message Buffers** | `>= 85` | `>= 95` | Message buffer utilization |
| **Fans** | `>= 1` | `>= 2` | Number of failed fans |
| **Temperature (°C)** | `>= 25` | `>= 60` | Sensor temperature; OverTemp sensor flag immediately emits `CRITICAL` |
| **Power Supplies** | `>= 1` | `>= 2` | Number of failed power supplies |
| **Storage (%)** | `>= 70` | `>= 90` | Storage disk or flash utilization percentage |
| **Firmware Version** | `>= 1` | `>= 2` | Major/minor version difference behind recommended release |

**Threshold Data Architecture:**
- **Setup Thresholds (`res.alerts`)**: In MS Word report templates, iterating `res.alerts` (`{%tr for th in res.alerts %}`) accesses only the configured setup threshold definitions (`th.name`, `th.warning`, `th.critical`).
- **Active Triggered Alerts (`res.host.alerts`)**: When measured device telemetry exceeds a threshold or when a handler encounters a hardware/connectivity failure, an alert object is attached directly to `res.host.alerts` with uppercase severity (`"CRITICAL"` or `"WARNING"`).


### Device Sources & Multi-Source Enumeration
Nagios-Sust supports multiple device discovery sources under `device_sources`:
- **`nagios_pdf`**: Reads and parses Nagios Service Status PDF reports.
- **`airwave`**: Connects to the Aruba AirWave API via `airwaveapiclient` to enumerate network devices.

You can specify one or multiple sources simultaneously. When multiple sources are specified, hosts are deduplicated by name and their metadata is merged:
```yaml
device_sources:
  - "nagios_pdf"
  - "airwave"

nagios_pdf:
  report_file: "report.pdf"

airwave:
  url: "https://airwave"
  folders: ["Top > Campus A", "Campus B > Building 2"] # Optional: Filter devices by AirWave folder (recursive)
  host_filter:
    startswith: "SW" # e.g. "SW" (use regex for multiple conditions)
    regex: "^(SW|AP)" # or regex pattern
  device_categories: ["switch"] # Optional: switch, thin_ap, controller
  models: [] # Optional: filter by model
```

### AirWave Folder Filtering & Matching Scenarios
When `folders` is specified under `airwave:` in `config.yaml`, Nagios-Sust fetches AirWave's folder hierarchy (`folder_list.xml`) and includes devices in the specified folders plus all descendant subfolders recursively. Each enumerated host automatically includes `folder` (leaf folder name) and `folder_path` (hierarchy path, e.g. `Top > Campus A > Building 1`) under `res.sources.airwave`.

Nagios-Sust supports multiple intuitive folder matching scenarios:

1. **Default Behavior (Root `Top` - Omitted or Empty)**:
   Leaving `folders: []` empty or omitting `folders` altogether includes all devices across the entire AirWave instance (equivalent to querying root `Top`).
   ```yaml
   airwave:
     folders: [] # Discovers all devices across the entire AirWave instance
   ```

2. **Full Hierarchy Path Matching**:
   Target a specific branch of the hierarchy by specifying its path from the root down to the target:
   ```yaml
   airwave:
     folders:
       - "Top > Campus A > Building 1" # Targets Building 1 within Campus A
   ```

3. **Subpath & Intermediate Matching**:
   When specifying a subpath (omitting `Top >`), Nagios-Sust matches any hierarchy branch ending with the specified sequence without prepending path segments. If the same subpath exists in multiple locations, all matching branches and their children are included:
   ```yaml
   airwave:
     folders:
       - "Campus A > Building 1" # Matches both 'Top > Location A > Campus A > Building 1'
                                # and 'Top > Location B > Campus A > Building 1'
   ```

4. **Hierarchical Disambiguation**:
   If multiple campuses or locations share folder names, specify enough parent hierarchy context to target only the intended branch:
   ```yaml
   airwave:
     folders:
       - "Location A > Campus A > Building 1" # Targets Building 1 specifically inside Location A
       - "Top > Location B > Campus A > Building 1" # Full hierarchy disambiguation
   ```

5. **Bare Folder Name (Recursive)**:
   Target a folder directly by name anywhere in the tree. Note that specifying a bare name like `"Building 1"` matches any folder named `Building 1` across all campuses:
   ```yaml
   airwave:
     folders:
       - "Campus A"     # Includes Campus A, plus Building 1, Floor 1, etc.
       - "Building 1"   # Includes Building 1 from Campus A, Campus B, etc.
   ```

6. **Numeric Folder ID**:
   Target an AirWave folder directly by its internal integer ID (as a number or quoted string):
   ```yaml
   airwave:
     folders:
       - 101   # Integer folder ID
       - "102" # Quoted string folder ID
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

1. **`res.host` (Identity & Active Alerts)**:
   - `{{ res.host.name }}`: The device name (e.g. `SW-CORE-01`, `FGT-CORE-01`).
   - `{{ res.host.alerts }}`: Direct list of active alert dictionaries triggered for this host.
     - `{{ alert.handler }}`: Originating handler or evaluator (e.g. `arubacx`, `procurve`, `generic_ping`, `fortigate`).
     - `{{ alert.severity }}`: Uppercase severity level (`CRITICAL` or `WARNING`).
     - `{{ alert.type }}`: Category of the alert (`cpu`, `memory`, `fan`, `temperature`, `power_supply`, `ping`, `interface`).
     - `{{ alert.component }}`: Affected component label (e.g. `Fan 1/1/2`, `Sensor 1/1-Switch-ASIC`, `CPU`).
     - `{{ alert.message }}`: Human-readable alert explanation.

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

5. **`res.alerts` (Setup Thresholds Container)**:
   - When iterating `res.alerts` in Word templates (`{%tr for th in res.alerts %}`), it iterates strictly over the **configured setup thresholds**:
     - `{{ th.name }}`: Human-readable metric name in English (e.g. `CPU (%)`, `Memory (%)`, `Fans`, `Temperature (°C)`).
     - `{{ th.warning }}`: Warning threshold integer value.
     - `{{ th.critical }}`: Critical threshold integer value.
   - Specific thresholds can also be accessed by key: `{{ res.alerts.cpu.warning }}`, `{{ res.alerts.cpu.critical }}`.

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
