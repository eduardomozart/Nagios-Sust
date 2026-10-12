import unittest
import handlers.arubacx as arubacx_mod

class TestArubaCXHandler(unittest.TestCase):
    def test_aoscx_system_parsing(self):
        """Validates standalone ArubaOS-CX parser with anonymized output."""
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

    def test_aoscx_handle_callable(self):
        """Confirms arubacx module exposes a callable handle function."""
        self.assertTrue(callable(arubacx_mod.handle))

if __name__ == "__main__":
    unittest.main(buffer=True)
