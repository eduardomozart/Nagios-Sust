import unittest
from unittest.mock import patch
import handlers.procurve as procurve_mod

class TestProCurveHandler(unittest.TestCase):
    def test_procurve_vsf_system_parsing(self):
        """Validates standalone ProCurve VSF parser with mock output."""
        aoss_output = """SW-ACCESS-01# show system
 
Status and Counters - General System Information
 
  System Name        : SW-ACCESS-01
  System Contact     : admin@example.com
  System Location    : HQ-SITE
  MAC Age Time (sec) : 300
  Time Zone          : -180
  Daylight Time Rule : None
 
  Software revision  : WC.16.11.0027
  Base MAC Addr      : 445bed-e0de8b
 
VSF-Member :1
 
  ROM Version        : WC.16.01.0010
  Up Time            : 93 days
  CPU Util (%)       : 39
  MAC Addr           : 445bed-e0de80
  Serial Number      : TW0000000001
  Memory   - Total   : 333,451,776
             Free    : 210,618,404
 
 
VSF-Member :2
 
  ROM Version        : WC.16.01.0010
  Up Time            : 93 days
  CPU Util (%)       : 0
  MAC Addr           : 445bed-e09b80
  Serial Number      : TW0000000002
  Memory   - Total   : 333,451,776
             Free    : 226,953,876
"""
        info = procurve_mod.parse_aoss_system(aoss_output)
        self.assertEqual(info["os_type"], "AOS-S")
        self.assertEqual(info["hostname"], "SW-ACCESS-01")
        self.assertEqual(info["version"], "WC.16.11.0027")
        self.assertEqual(info["uptime"], "93 days")
        self.assertEqual(info["cpu_util"], 39)
        self.assertEqual(info["serial_number"], "TW0000000001")
        
        # Memory percentage: (333,451,776 - 210,618,404) / 333,451,776 * 100 = 36.837% -> 36.8%
        self.assertEqual(info["memory_usage"], 36.8)
        
        # Verify VSF members
        self.assertEqual(len(info["members"]), 2)
        m1 = info["members"][0]
        self.assertEqual(m1["member_id"], 1)
        self.assertEqual(m1["cpu_util"], 39)
        self.assertEqual(m1["memory_usage_pct"], 36.8)
        
        m2 = info["members"][1]
        self.assertEqual(m2["member_id"], 2)
        self.assertEqual(m2["cpu_util"], 0)
        # Member 2 memory: (333,451,776 - 226,953,876) / 333,451,776 * 100 = 31.938% -> 31.9%
        self.assertEqual(m2["memory_usage_pct"], 31.9)

    def test_procurve_standalone_parsing(self):
        """Validates ProCurve standalone (non-VSF) parser."""
        standalone_output = """SW-ACCESS-02# show system
 
Status and Counters - General System Information
 
  System Name        : SW-ACCESS-02
  Software revision  : YA.16.08.0003
  ROM Version        : YA.15.20
  Up Time            : 120 days
  CPU Util (%)       : 12
  Serial Number      : SG54XYZ123
  Memory   - Total   : 200,000,000
             Free    : 100,000,000
"""
        info = procurve_mod.parse_aoss_system(standalone_output)
        self.assertEqual(info["os_type"], "AOS-S")
        self.assertEqual(info["hostname"], "SW-ACCESS-02")
        self.assertEqual(info["version"], "YA.16.08.0003")
        self.assertEqual(info["uptime"], "120 days")
        self.assertEqual(info["cpu_util"], 12)
        self.assertEqual(info["memory_usage"], 50.0)
        self.assertEqual(info["serial_number"], "SG54XYZ123")

    def test_procurve_handle_execution(self):
        """Validates procurve handle function with pre-collected output."""
        output = """SW-ACCESS-01# show system
Software revision  : WC.16.11.0027
Up Time            : 93 days
CPU Util (%)       : 39
Serial Number      : TW0000000001
Memory   - Total   : 100
           Free    : 50
"""
        res = procurve_mod.handle("SW-ACCESS-01", {}, {}, pre_collected_output=output)
        self.assertIn("system_info", res)
        self.assertEqual(res["system_info"]["version"], "WC.16.11.0027")
        self.assertEqual(res["system_info"]["memory_usage"], 50.0)
        self.assertEqual(res["error"], 0)

    def test_procurve_handle_callable(self):
        """Confirms procurve module exposes a callable handle function."""
        self.assertTrue(callable(procurve_mod.handle))

    @patch("handlers.procurve.run_ssh_command", side_effect=Exception("SSH connection timed out"))
    def test_procurve_timeout_classification(self, mock_ssh):
        """Verifies that SSH timeout maps to ERR_CONNECTION_TIMEOUT."""
        from utils.error_codes import ERR_CONNECTION_TIMEOUT
        res = procurve_mod.handle("SW-ACCESS-01", {}, {"username": "admin", "password": "x"})
        self.assertEqual(res["error"], ERR_CONNECTION_TIMEOUT)

    def test_procurve_fans_parsing(self):
        """Verifies parse_aoss_fans with normal state, 1 failure (warning), and >= 2 failures (critical)."""
        normal_output = """
Fan Information
 
VSF-Member  1
 
  Num  | State       | Failures | Location
-------+-------------+----------+----------
Sys-1  | Fan OK      |   0      | Chassis
Sys-2  | Fan OK      |   0      | Chassis
Sys-3  | Fan OK      |   0      | Chassis
Sys-4  | Fan OK      |   0      | Chassis
 
0 / 4 Fans in Failure State
"""
        self.assertEqual(procurve_mod.parse_aoss_fans(normal_output), [])

        # 1 fan failure with 4 fans -> WARNING
        one_fail_output = """
Fan Information
VSF-Member  1
  Num  | State       | Failures | Location
-------+-------------+----------+----------
Sys-1  | Fan OK      |   0      | Chassis
Sys-2  | Failed      |   1      | Chassis
Sys-3  | Fan OK      |   0      | Chassis
Sys-4  | Fan OK      |   0      | Chassis
"""
        alerts_1 = procurve_mod.parse_aoss_fans(one_fail_output)
        self.assertEqual(len(alerts_1), 1)
        self.assertEqual(alerts_1[0]["severity"], "WARNING")
        self.assertEqual(alerts_1[0]["component"], "Fan Sys-2 (VSF Member 1)")

        # 2 fan failures with 4 fans -> CRITICAL
        two_fail_output = """
Fan Information
VSF-Member  1
  Num  | State       | Failures | Location
-------+-------------+----------+----------
Sys-1  | Fan OK      |   0      | Chassis
Sys-2  | Failed      |   1      | Chassis
Sys-3  | Failed      |   2      | Chassis
Sys-4  | Fan OK      |   0      | Chassis
"""
        alerts_2 = procurve_mod.parse_aoss_fans(two_fail_output)
        self.assertEqual(len(alerts_2), 2)
        self.assertEqual(alerts_2[0]["severity"], "CRITICAL")
        self.assertEqual(alerts_2[1]["severity"], "CRITICAL")

    def test_procurve_temperature_parsing(self):
        """Verifies parse_aoss_temperature with normal temp, fanless empty table, and over-temp."""
        # Normal
        normal_output = """
System Air Temperatures
  VSF-Member  1
  Temp    Current  Max   Min                        Avg    
  Sensor  Temp     Temp  Temp  Threshold  OverTemp  Temp   
  ------- -------- ----- ----- ---------- --------- -------
  Chassis 24C      25C   22C   55C        NO         23.50C
"""
        self.assertEqual(procurve_mod.parse_aoss_temperature(normal_output), [])

        # Fanless / entry switch without sensors (e.g. Aruba 2530/2930F) -> 0 alerts
        fanless_output = """
System Air Temperatures
  VSF-Member  1
  Temp    Current  Max   Min                        Avg    
  Sensor  Temp     Temp  Temp  Threshold  OverTemp  Temp   
  ------- -------- ----- ----- ---------- --------- -------
"""
        self.assertEqual(procurve_mod.parse_aoss_temperature(fanless_output), [])

        # Warning (>= 25C, < 60C)
        warn_output = """
System Air Temperatures
  Temp    Current  Max   Min                        Avg    
  Sensor  Temp     Temp  Temp  Threshold  OverTemp  Temp   
  ------- -------- ----- ----- ---------- --------- -------
  Chassis 31C      33C   27C   55C        NO         29.46C
"""
        warn_alerts = procurve_mod.parse_aoss_temperature(warn_output)
        self.assertEqual(len(warn_alerts), 1)
        self.assertEqual(warn_alerts[0]["severity"], "WARNING")

        # Critical (OverTemp YES)
        crit_output = """
System Air Temperatures
  Temp    Current  Max   Min                        Avg    
  Sensor  Temp     Temp  Temp  Threshold  OverTemp  Temp   
  ------- -------- ----- ----- ---------- --------- -------
  Chassis 62C      65C   30C   55C        YES        58.00C
"""
        crit_alerts = procurve_mod.parse_aoss_temperature(crit_output)
        self.assertEqual(len(crit_alerts), 1)
        self.assertEqual(crit_alerts[0]["severity"], "CRITICAL")

    def test_procurve_power_supply_parsing(self):
        """Verifies parse_aoss_power_supply with normal states, 1 fault (warning), and >= 2 faults (critical)."""
        normal_output = """
Power Supply Status:

 PS#    Model      Serial          State         AC/DC  + V    Wattage
 ---- --------- ------------ ----------------- -------------- ---------
   1   J9828A    IN30G4D009   Powered           AC 120V/240V      700
   2   J9828A    IN30G4D00C   Powered           AC 120V/240V      700
   3                          Not Present       -- ---------        0
   4   J9830A    IN43G4G05H   Powered           AC 120V/240V     2750

   3 /  4 supply bays delivering power.
"""
        self.assertEqual(procurve_mod.parse_aoss_power_supply(normal_output), [])

        # 1 fault with 3 populated PSUs -> WARNING
        one_fault_output = """
Power Supply Status:

 PS#    Model      Serial          State         AC/DC  + V    Wattage
 ---- --------- ------------ ----------------- -------------- ---------
   1   J9828A    IN30G4D009   Powered           AC 120V/240V      700
   2   J9828A    IN30G4D00C   Fault             AC 120V/240V      700
   3                          Not Present       -- ---------        0
   4   J9830A    IN43G4G05H   Powered           AC 120V/240V     2750
"""
        alerts_1 = procurve_mod.parse_aoss_power_supply(one_fault_output)
        self.assertEqual(len(alerts_1), 1)
        self.assertEqual(alerts_1[0]["severity"], "WARNING")
        self.assertEqual(alerts_1[0]["component"], "Power Supply 2")

        # 2 faults -> CRITICAL
        two_fault_output = """
Power Supply Status:
 PS#    Model      Serial          State         AC/DC  + V    Wattage
 ---- --------- ------------ ----------------- -------------- ---------
   1   J9828A    IN30G4D009   Permanent Failure AC 120V/240V      700
   2   J9828A    IN30G4D00C   Fault             AC 120V/240V      700
   3                          Not Present       -- ---------        0
"""
        alerts_2 = procurve_mod.parse_aoss_power_supply(two_fault_output)
        self.assertEqual(len(alerts_2), 2)
        self.assertEqual(alerts_2[0]["severity"], "CRITICAL")

    def test_procurve_handle_execution_with_granular_commands(self):
        """Verifies procurve handle parses granular CLI outputs and aggregates alerts."""
        output = """SW-ACCESS-01# show system
Software revision  : WC.16.11.0027
Up Time            : 93 days
CPU Util (%)           : 39
Serial Number      : TW0000000001
Memory   - Total   : 100
           Free    : 50
SW-ACCESS-01# show system fans
Fan Information
Sys-1  | Failed      |   1      | Chassis
Sys-2  | Failed      |   2      | Chassis
"""
        res = procurve_mod.handle("SW-ACCESS-01", {}, {}, pre_collected_output=output)
        self.assertEqual(res["error"], 0)
        self.assertEqual(len(res["alerts"]), 2)
        self.assertEqual(res["alerts"][0]["type"], "fan")
        self.assertEqual(res["alerts"][0]["severity"], "CRITICAL")


if __name__ == "__main__":
    unittest.main(buffer=True)

