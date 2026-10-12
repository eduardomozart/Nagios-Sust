import unittest
from unittest.mock import patch
import handlers.generic_ping as generic_ping_mod

class TestGenericPingHandler(unittest.TestCase):
    def test_handle_callable(self):
        """Confirms generic_ping module exposes callable execute_generic_ping and handle functions."""
        self.assertTrue(callable(generic_ping_mod.execute_generic_ping))
        self.assertTrue(callable(generic_ping_mod.handle))

    @patch("handlers.generic_ping.ping_with_output")
    @patch("handlers.generic_ping.socket.gethostbyname")
    def test_execute_generic_ping_success(self, mock_gethostbyname, mock_ping_with_output):
        """Verifies execute_generic_ping resolves host, records latency, and returns standardized dict."""
        mock_gethostbyname.return_value = "192.0.2.1"
        mock_ping_with_output.return_value = ("15", "Reply from 192.0.2.1: bytes=32 time=15ms TTL=64")

        options = {"capture_screenshot": False}
        res = generic_ping_mod.execute_generic_ping("test-router", "PING CRITICAL", options)

        self.assertEqual(res["host"], "test-router")
        self.assertEqual(res["latency"], 15)
        self.assertNotIn("screenshot", res)
        self.assertEqual(res["error"], 0)

    @patch("handlers.generic_ping.ping_with_output")
    @patch("handlers.generic_ping.socket.gethostbyname")
    def test_execute_generic_ping_timeout(self, mock_gethostbyname, mock_ping_with_output):
        """Verifies execute_generic_ping returns -3 and ERR_PING_TIMEOUT on failure."""
        mock_gethostbyname.return_value = "192.0.2.1"
        mock_ping_with_output.return_value = ("", "Request timed out")

        options = {"capture_screenshot": False}
        res = generic_ping_mod.execute_generic_ping("test-router", "PING CRITICAL", options)

        self.assertEqual(res["host"], "test-router")
        self.assertIsNone(res["latency"])
        self.assertEqual(res["error"], 3)

    @patch("handlers.generic_ping.ping_with_output")
    @patch("handlers.generic_ping.socket.gethostbyname")
    def test_handle_delegation(self, mock_gethostbyname, mock_ping_with_output):
        """Verifies handle delegates to execute_generic_ping."""
        mock_gethostbyname.return_value = "192.0.2.2"
        mock_ping_with_output.return_value = ("25", "Average = 25ms")

        options = {"capture_screenshot": False}
        res = generic_ping_mod.handle("test-host", "PING WARNING", options)

        self.assertEqual(res["host"], "test-host")
        self.assertEqual(res["latency"], 25)
        self.assertEqual(res["error"], 0)

    @patch("handlers.generic_ping.ping_with_output")
    @patch("handlers.generic_ping.socket.gethostbyname")
    def test_execute_generic_ping_custom_count(self, mock_gethostbyname, mock_ping_with_output):
        """Verifies execute_generic_ping respects count parameter and options['count']."""
        mock_gethostbyname.return_value = "192.0.2.1"
        mock_ping_with_output.return_value = ("10", "Reply")

        # Via direct argument
        generic_ping_mod.execute_generic_ping("test-host", "", {"capture_screenshot": False}, count=2)
        mock_ping_with_output.assert_called_with("192.0.2.1", count=2)

        # Via options["count"]
        generic_ping_mod.execute_generic_ping("test-host", "", {"capture_screenshot": False, "count": 5})
        mock_ping_with_output.assert_called_with("192.0.2.1", count=5)

    @patch("subprocess.check_output")
    def test_ping_with_output_subprocess_invocation(self, mock_subprocess):
        """Verifies ping_with_output executes platform ping with specified count."""
        mock_subprocess.return_value = "Reply from 192.0.2.1: time=12ms"
        lat, out = generic_ping_mod.ping_with_output("192.0.2.1", count=3)
        self.assertEqual(lat, "12")
        self.assertTrue(mock_subprocess.called)
        cmd_called = mock_subprocess.call_args[0][0]
        self.assertIn("3", cmd_called)

if __name__ == "__main__":
    unittest.main(buffer=True)
