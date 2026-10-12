import unittest
from unittest.mock import patch
import handlers.arubacx as arubacx_mod

class TestArubaCXHandler(unittest.TestCase):
    def test_aoscx_system_parsing(self):
        """Validates standalone ArubaOS-CX parser with mock output."""
        cx_output = """SW-CORE-01# show system
Hostname               : SW-CORE-01
System Description     : FL.10.16.1020
System Contact         : admin@example.com
System Location        : DataCenter
 
Vendor                 : HPE ANW
Product Name           : R0X24C 6405 v2 Chassis
Chassis Serial Nbr     : SG0000000001
Base MAC Address       : d4e053-b2e600
AOS-CX Version         : FL.10.16.1020
 
Time Zone              : America/Sao_Paulo
 
Up Time                : 38 weeks, 22 hours, 53 minutes
CPU Util (%)           : 18
CPU Util (% avg 1 min) : 19
CPU Util (% avg 5 min) : 22
Memory Usage (%)       : 15
"""
        info = arubacx_mod.parse_aoscx_system(cx_output)
        self.assertEqual(info["os_type"], "AOS-CX")
        self.assertEqual(info["hostname"], "SW-CORE-01")
        self.assertEqual(info["model"], "R0X24C 6405 v2 Chassis")
        self.assertEqual(info["version"], "FL.10.16.1020")
        self.assertEqual(info["uptime"], "38 weeks, 22 hours, 53 minutes")
        self.assertEqual(info["cpu_util"], 18)
        self.assertEqual(info["memory_usage"], 15)
        self.assertEqual(info["serial_number"], "SG0000000001")

    def test_aoscx_handle_execution(self):
        """Validates arubacx handle function with pre-collected output."""
        cx_output = """SW-CORE-01# show system
Hostname               : SW-CORE-01
Product Name           : R0X24C 6405 v2 Chassis
AOS-CX Version         : FL.10.16.1020
Up Time                : 10 days
CPU Util (%)           : 12
Memory Usage (%)       : 20
Chassis Serial Nbr     : SG0000000001
"""
        res = arubacx_mod.handle("SW-CORE-01", {}, {}, pre_collected_output=cx_output)
        self.assertIn("system_info", res)
        self.assertEqual(res["system_info"]["version"], "FL.10.16.1020")
        self.assertEqual(res["system_info"]["os_type"], "AOS-CX")
        self.assertEqual(res["error"], 0)

    def test_aoscx_handle_callable(self):
        """Confirms arubacx module exposes a callable handle function."""
        self.assertTrue(callable(arubacx_mod.handle))

    @patch("handlers.arubacx.run_ssh_command", side_effect=Exception("Connection timed out"))
    def test_aoscx_timeout_classification(self, mock_ssh):
        """Verifies that SSH timeout maps to ERR_CONNECTION_TIMEOUT."""
        from utils.error_codes import ERR_CONNECTION_TIMEOUT
        res = arubacx_mod.handle("SW-CORE-01", {}, {"username": "admin", "password": "x"})
        self.assertEqual(res["error"], ERR_CONNECTION_TIMEOUT)

    def test_aoscx_environment_parsing_normal(self):
        """Verifies parse_aoscx_environment returns empty list when all sensors and fans are normal."""
        output = """
-------------------------------------------------------------------------------
Sensor Temperature Information
-------------------------------------------------------------------------------
Sensor  Location              Temperature   Status
-------------------------------------------------------------------------------
1/1     chassis               32.5C         normal
1/2     management-module     41.0C         normal

-------------------------------------------------------------------------------
Fan Information
-------------------------------------------------------------------------------
Fan       Speed(rpm)   Airflow          Status
-------------------------------------------------------------------------------
1/1/1     4500         front-to-back    normal
1/1/2     4550         front-to-back    ok

-------------------------------------------------------------------------------
PSU Information
-------------------------------------------------------------------------------
PSU     Watts   Status
-------------------------------------------------------------------------------
1/1     500W    normal
1/2     500W    ok
"""
        alerts = arubacx_mod.parse_aoscx_environment(output)
        self.assertEqual(alerts, [])

    def test_aoscx_environment_parsing_faults(self):
        """Verifies parse_aoscx_environment emits structured alerts for fan, temp, and PSU failures."""
        output = """
Sensor Temperature Information
Sensor  Location              Temperature   Status
1/1     chassis               85.0C         critical
1/2     line-card             65.0C         alert

Fan Information
Fan       Speed(rpm)   Airflow          Status
1/1/1     0            front-to-back    failed

PSU Information
PSU     Watts   Status
1/1     0W      fault
"""
        alerts = arubacx_mod.parse_aoscx_environment(output, handler_name="arubacx")
        self.assertEqual(len(alerts), 4)

        # Temp 1/1 critical
        a_temp1 = alerts[0]
        self.assertEqual(a_temp1["handler"], "arubacx")
        self.assertEqual(a_temp1["severity"], "CRITICAL")
        self.assertEqual(a_temp1["type"], "temperature")
        self.assertEqual(a_temp1["component"], "Sensor 1/1")
        self.assertEqual(a_temp1["status"], "critical")

        # Temp 1/2 warning (alert)
        a_temp2 = alerts[1]
        self.assertEqual(a_temp2["severity"], "WARNING")
        self.assertEqual(a_temp2["type"], "temperature")

        # Fan 1/1/1 failed
        a_fan = alerts[2]
        self.assertEqual(a_fan["handler"], "arubacx")
        self.assertEqual(a_fan["severity"], "CRITICAL")
        self.assertEqual(a_fan["type"], "fan")
        self.assertEqual(a_fan["component"], "Fan 1/1/1")
        self.assertEqual(a_fan["status"], "failed")

        # PSU 1/1 fault
        a_psu = alerts[3]
        self.assertEqual(a_psu["handler"], "arubacx")
        self.assertEqual(a_psu["severity"], "CRITICAL")
        self.assertEqual(a_psu["type"], "power_supply")
        self.assertEqual(a_psu["component"], "PSU 1/1")
        self.assertEqual(a_psu["status"], "fault")

    def test_aoscx_handle_execution_with_environment(self):
        """Verifies arubacx handle parses environment and populates alerts list."""
        output = """SW-CORE-01# show system
Hostname               : SW-CORE-01
Product Name           : R0X24C 6405 v2 Chassis
AOS-CX Version         : FL.10.16.1020
Up Time                : 10 days
CPU Util (%)           : 12
Memory Usage (%)       : 20
Chassis Serial Nbr     : SG0000000001
SW-CORE-01# show environment
Fan Information
Fan       Speed(rpm)   Airflow          Status
1/1/1     0            front-to-back    failed
"""
        res = arubacx_mod.handle("SW-CORE-01", {}, {}, pre_collected_output=output)
        self.assertEqual(res["error"], 0)
        self.assertEqual(len(res["alerts"]), 1)
        self.assertEqual(res["alerts"][0]["type"], "fan")
        self.assertEqual(res["alerts"][0]["status"], "failed")

if __name__ == "__main__":
    unittest.main(buffer=True)
