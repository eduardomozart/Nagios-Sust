"""
utils/exit_codes.py - Unified exit codes for Nagios-Sust.
Defines distinct numeric exit codes for every error condition that terminates execution.
"""

# Successful execution
EXIT_SUCCESS = 0

# Configuration Errors (10-19)
ERR_CONFIG_FILE_NOT_FOUND = 10       # Explicitly specified configuration file (-c / --config) not found
ERR_PROMPTED_CONFIG_NOT_FOUND = 11   # Configuration file entered in interactive prompt not found
ERR_NO_CONFIG_SELECTED = 12          # No configuration file selected or user aborted selection prompt
ERR_PYYAML_MISSING = 13              # PyYAML library is not installed
ERR_CONFIG_PARSE_ERROR = 14          # YAML syntax / parsing error in configuration file
ERR_CONFIG_VALIDATION_ERROR = 15     # Configuration validation error (invalid schema, circular includes, etc.)

# Device Source & Discovery Errors (20-29)
ERR_SOURCE_NOT_FOUND = 20            # Device source module not found in sources/
ERR_SOURCE_LOAD_ERROR = 21           # Fatal error while loading/ingesting hosts from a device source
ERR_PDF_FILE_NOT_SELECTED = 22       # Nagios PDF report file dialog was cancelled or no file was selected
ERR_PDF_PARSE_ERROR = 23             # Fatal error parsing Nagios PDF report file
ERR_AIRWAVE_API_ERROR = 24           # Fatal error connecting to or querying Aruba AirWave API
ERR_DEVICE_PROMPT_ABORTED = 25       # User aborted interactive device/source selection prompt

# Exporter & Report Generation Errors (30-39)
ERR_DOCX_RENDER_ERROR = 30           # Fatal error rendering Word template with DocxTemplate
