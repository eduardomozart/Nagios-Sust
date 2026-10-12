"""
Standard integer error codes for handlers in Nagios-Sust.
Used in the Subsystem Namespacing Contract under res.handlers.<HANDLER>.error
to enable multi-language template translation.
"""

ERR_OK = 0                     # Normal operation (no error)
ERR_IF_DOWN = 1                # Interface is DOWN with assigned IP
ERR_IF_LOGICAL_DOWN = 2        # Interface has logical down IP (0.0.0.0)
ERR_PING_TIMEOUT = 3           # Ping to gateway or target timed out
ERR_DEVICE_DOWN = 4            # Monitored device status is DOWN
ERR_DEVICE_NOT_FOUND = 5       # Device not found in discovery inventory
ERR_AUTH_FAILED = 6            # Authentication credentials rejected
ERR_CONNECTION_TIMEOUT = 7     # Network connection or SSH timeout
ERR_AUTOMATION_FAILED = 8      # Handler execution or driver error

