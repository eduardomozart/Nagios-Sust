import unittest
import handlers.aruba as aruba_mod

class TestArubaDispatcherHandler(unittest.TestCase):
    def test_detection_aoscx(self):
        """Verifies detection of AOS-CX equipment."""
        cx_output = """SW-CORE-01# show system
Product Name           : R0X24C 6405 v2 Chassis
AOS-CX Version         : FL.10.16.1020
"""
        self.assertEqual(aruba_mod.detect_equipment_type(cx_output), "arubacx")

    def test_detection_procurve(self):
        """Verifies detection of ProCurve equipment."""
        procurve_output = """SW-ACCESS-01# show system
Software revision  : WC.16.11.0027
"""
        self.assertEqual(aruba_mod.detect_equipment_type(procurve_output), "procurve")

    def test_detection_fallback(self):
        """Verifies fallback when output is unrecognizable."""
        unknown_output = "Unknown device prompt"
        self.assertEqual(aruba_mod.detect_equipment_type(unknown_output), "unknown")

    def test_dispatcher_execution_delegation(self):
        """Verifies aruba dispatcher delegates properly to arubacx or procurve handlers."""
        cx_output = """SW-CORE-01# show system
Hostname               : SW-CORE-01
Product Name           : R0X24C 6405 v2 Chassis
AOS-CX Version         : FL.10.16.1020
Up Time                : 38 weeks
CPU Util (%)           : 18
Memory Usage (%)       : 15
Chassis Serial Nbr     : SG0000000001
"""
        res_cx = aruba_mod.handle("SW-CORE-01", {}, {}, pre_collected_output=cx_output)
        self.assertEqual(res_cx["system_info"]["os_type"], "AOS-CX")
        self.assertEqual(res_cx["system_info"]["version"], "FL.10.16.1020")
        self.assertEqual(res_cx["error"], 0)

        procurve_output = """SW-ACCESS-01# show system
System Name        : SW-ACCESS-01
Software revision  : WC.16.11.0027
Up Time            : 93 days
CPU Util (%)       : 39
Serial Number      : TW0000000001
Memory   - Total   : 200
           Free    : 100
"""
        res_procurve = aruba_mod.handle("SW-ACCESS-01", {}, {}, pre_collected_output=procurve_output)
        self.assertEqual(res_procurve["system_info"]["os_type"], "AOS-S")
        self.assertEqual(res_procurve["system_info"]["version"], "WC.16.11.0027")
        self.assertEqual(res_procurve["error"], 0)

    def test_aruba_handle_callable(self):
        """Confirms aruba dispatcher module exposes a callable handle function."""
        self.assertTrue(callable(aruba_mod.handle))


if __name__ == "__main__":
    unittest.main(buffer=True)
