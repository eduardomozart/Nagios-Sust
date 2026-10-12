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

    def test_aoscx_fans_normal(self):
        """Verifies parse_aoscx_fans returns empty list when all fans are normal/ok."""
        output = """Fan tray information
------------------------------------------------------------------------------
Mbr/Tray  Description                             Status  Serial Number  Fans
------------------------------------------------------------------------------
1/1       JL369A 8400 Fan tray                    ready   SGXXXXXXXXXX   6
1/2       JL369A 8400 Fan tray                    ready   SGXXXXXXXXXX   6
Fan information
------------------------------------------------------------------------
Mbr/Tray/Fan  Serial Number  Speed   Direction      Status        RPM
------------------------------------------------------------------------
1/1/1         SGXXXXXXXXXX   slow    front-to-back  ok            6000
1/1/2         SGXXXXXXXXXX   normal  front-to-back  ok            8000
"""
        alerts = arubacx_mod.parse_aoscx_fans(output)
        self.assertEqual(alerts, [])

    def test_aoscx_fans_redundancy_warning_and_critical(self):
        """Verifies 1 fan fault emits WARNING when redundant, >= 2 emits CRITICAL."""
        # Single fan fault with redundant fans (total > 1) -> WARNING
        single_fault = """Fan information
------------------------------------------------------------------------
Mbr/Tray/Fan  Serial Number  Speed   Direction      Status        RPM
------------------------------------------------------------------------
1/1/1         SGXXXXXXXXXX   slow    front-to-back  ok            6000
1/1/2         SGXXXXXXXXXX   max     front-to-back  fault         16500
"""
        alerts = arubacx_mod.parse_aoscx_fans(single_fault, handler_name="arubacx")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "WARNING")
        self.assertEqual(alerts[0]["component"], "Fan 1/1/2")

        # Two fan faults -> CRITICAL
        double_fault = """Fan information
------------------------------------------------------------------------
Mbr/Tray/Fan  Serial Number  Speed   Direction      Status        RPM
------------------------------------------------------------------------
1/1/1         SGXXXXXXXXXX   max     front-to-back  fault         16500
1/1/2         SGXXXXXXXXXX   max     front-to-back  fault         16500
"""
        alerts = arubacx_mod.parse_aoscx_fans(double_fault, handler_name="arubacx")
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["severity"], "CRITICAL")
        self.assertEqual(alerts[1]["severity"], "CRITICAL")

        # Single fan fault on non-redundant system (total = 1) -> CRITICAL
        single_nonredundant = """Fan information
------------------------------------------------------------------------
Mbr/Tray/Fan  Serial Number  Speed   Direction      Status        RPM
------------------------------------------------------------------------
1/1/1         SGXXXXXXXXXX   max     front-to-back  fault         16500
"""
        alerts = arubacx_mod.parse_aoscx_fans(single_nonredundant, handler_name="arubacx")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "CRITICAL")

    def test_aoscx_temperature_parsing(self):
        """Verifies parse_aoscx_temperature evaluates normal, warning, and critical/emergency sensors."""
        output = """Temperature information
------------------------------------------------------------------------------
                                                     Current
Mbr/Slot-Sensor                 Module Type        temperature  Status
------------------------------------------------------------------------------
1/1-PCIE-Switch                 line-card-module     95.82 C    normal
1/1-Processor                   line-card-module     0.00 C     fault
1/1-Switch-ASIC                 line-card-module     116.36 C   emergency
1/1-Switch-ASIC-Internal        line-card-module     108.25 C   critical
1/2-PCIE-Switch                 line-card-module     95.82 C    alert
"""
        alerts = arubacx_mod.parse_aoscx_temperature(output, handler_name="arubacx")
        self.assertEqual(len(alerts), 4)

        # Fault, emergency, critical -> CRITICAL
        self.assertEqual(alerts[0]["component"], "Sensor 1/1-Processor")
        self.assertEqual(alerts[0]["severity"], "CRITICAL")
        self.assertEqual(alerts[1]["component"], "Sensor 1/1-Switch-ASIC")
        self.assertEqual(alerts[1]["severity"], "CRITICAL")
        self.assertEqual(alerts[2]["component"], "Sensor 1/1-Switch-ASIC-Internal")
        self.assertEqual(alerts[2]["severity"], "CRITICAL")

        # Alert -> WARNING
        self.assertEqual(alerts[3]["component"], "Sensor 1/2-PCIE-Switch")
        self.assertEqual(alerts[3]["severity"], "WARNING")

    def test_aoscx_power_supply_redundancy(self):
        """Verifies parse_aoscx_power_supply redundancy logic (1 failure WARNING, >= 2 CRITICAL)."""
        # 1 failure with 3 total present PSUs -> WARNING
        output_single_fail = """Power Supply Status:

 PS#    Model      Serial          State         AC/DC  + V    Wattage
 ---- --------- ------------ ----------------- -------------- ---------
   1                          Not Present       -- ---------        0
   2   J9829A    IN30G4D00C   Permanent Failure  AC 120V/240V     1100
   3   J9829A    IN30G4D00D   Powered           -- ---------       1100
   4   J9829A    IN43G4G05H   Powered           AC 120V/240V      1100

   2 /  4 supply bays delivering power.
"""
        alerts = arubacx_mod.parse_aoscx_power_supply(output_single_fail, handler_name="arubacx")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["severity"], "WARNING")
        self.assertEqual(alerts[0]["component"], "Power Supply 2")

        # 2 failures -> CRITICAL
        output_double_fail = """Power Supply Status:

 PS#    Model      Serial          State         AC/DC  + V    Wattage
 ---- --------- ------------ ----------------- -------------- ---------
   1   J9829A    IN30G4D00A   Fault             AC 120V/240V     1100
   2   J9829A    IN30G4D00C   Permanent Failure  AC 120V/240V     1100
   3   J9829A    IN30G4D00D   Powered           -- ---------       1100
"""
        alerts = arubacx_mod.parse_aoscx_power_supply(output_double_fail, handler_name="arubacx")
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["severity"], "CRITICAL")
        self.assertEqual(alerts[1]["severity"], "CRITICAL")

    def test_aoscx_handle_execution_with_environment(self):
        """Verifies arubacx handle parses granular environment outputs and populates alerts list."""
        output = """SW-CORE-01# show system
Hostname               : SW-CORE-01
Product Name           : R0X24C 6405 v2 Chassis
AOS-CX Version         : FL.10.16.1020
Up Time                : 10 days
CPU Util (%)           : 12
Memory Usage (%)       : 20
Chassis Serial Nbr     : SG0000000001
SW-CORE-01# show environment fan
Fan information
------------------------------------------------------------------------
Mbr/Tray/Fan  Serial Number  Speed   Direction      Status        RPM
------------------------------------------------------------------------
1/1/1         SGXXXXXXXXXX   slow    front-to-back  ok            6000
1/1/2         SGXXXXXXXXXX   fast    front-to-back  fault         14000
SW-CORE-01# show environment temperature
Temperature information
------------------------------------------------------------------------------
Mbr/Slot-Sensor                 Module Type        temperature  Status
------------------------------------------------------------------------------
1/1-PCIE-Switch                 line-card-module     95.82 C    normal
SW-CORE-01# show environment power-supply
Power Supply Status:
 PS#    Model      Serial          State         AC/DC  + V    Wattage
 ---- --------- ------------ ----------------- -------------- ---------
   1   J9829A    IN30G4D00C   Powered           AC 120V/240V     1100
"""
        res = arubacx_mod.handle("SW-CORE-01", {}, {}, pre_collected_output=output)
        self.assertEqual(res["error"], 0)
        self.assertEqual(len(res["alerts"]), 1)
        self.assertEqual(res["alerts"][0]["type"], "fan")
        self.assertEqual(res["alerts"][0]["severity"], "WARNING")
        self.assertEqual(res["alerts"][0]["component"], "Fan 1/1/2")

if __name__ == "__main__":
    unittest.main(buffer=True)
