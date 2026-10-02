# Nagios-Sust User Guide

Welcome to the Nagios Sustenance Automation tool! This guide will help you understand how to use, configure, and get the most out of the application.

## 1. How It Works
The program reads a Nagios PDF report (like `report.pdf`) and looks for all network equipment (hosts) that are in an alerting or warning state.
For each host found, it checks `config.yaml` to see if there is a matching rule. If a rule matches, it launches a "handler" (a specialized script) that logs into that specific equipment (using Google Chrome in the background), checks the status of its interfaces (like WAN1 and WAN2), and takes a screenshot.
Finally, all this evidence is injected into an MS Word template (`template.docx`).

## 2. Setting Up Your `config.yaml`
The `config.yaml` file is the brain of the automation. 

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
For example, if your PDF has a host named `FGTDEMO-FW-01`, and you have a specific rule for `FGTDEMO` and a generic rule for `FGT`, make sure to place the specific rule (`FGTDEMO`) *above* the generic one (`FGT`) in the YAML file!

```yaml
rules:
  - name: "Specific FGTDEMO Rule"
    host_filter:
      startswith: "FGTDEMO"
    handler: "fortigate"
    options:
      url_template: "https://{host}/ng/interface"
      # You can override the global credentials here:
      # username: "other_admin"

  - name: "Generic FortiGate Rule"
    host_filter:
      startswith: "FGT"
    handler: "fortigate"
    options:
      url_template: "https://{host}/ng/interface"
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
Simply open `template.docx` in Microsoft Word and modify it as you please. You can change fonts, colors, add company logos, or change the table layout. 

Just make sure you leave the `{{ variable }}` tags intact so the script knows where to inject the screenshots and the collected data.
