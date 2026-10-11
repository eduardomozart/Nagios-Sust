import unittest
import handlers.procurve as procurve_mod

class TestProCurveHandler(unittest.TestCase):
    def test_procurve_vsf_system_parsing(self):
        """Validates standalone ProCurve VSF parser with anonymized output."""
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

    def test_procurve_handle_callable(self):
        """Confirms procurve module exposes a callable handle function."""
        self.assertTrue(callable(procurve_mod.handle))

if __name__ == "__main__":
    unittest.main()
