import unittest
from utils.ssh import classify_ssh_error
from utils.error_codes import ERR_CONNECTION_TIMEOUT, ERR_AUTOMATION_FAILED


class TestSSHUtils(unittest.TestCase):
    def test_classify_ssh_error_timeout_exception(self):
        """Verifies that timeout exceptions map to ERR_CONNECTION_TIMEOUT."""
        self.assertEqual(classify_ssh_error(Exception("Connection timed out")), ERR_CONNECTION_TIMEOUT)
        self.assertEqual(classify_ssh_error(TimeoutError("Socket read timed out")), ERR_CONNECTION_TIMEOUT)

    def test_classify_ssh_error_timeout_string(self):
        """Verifies that timeout error strings map to ERR_CONNECTION_TIMEOUT."""
        self.assertEqual(classify_ssh_error("SSH timeout after 15 seconds"), ERR_CONNECTION_TIMEOUT)
        self.assertEqual(classify_ssh_error("Operation timed out"), ERR_CONNECTION_TIMEOUT)

    def test_classify_ssh_error_other_exception(self):
        """Verifies that non-timeout exceptions map to ERR_AUTOMATION_FAILED."""
        self.assertEqual(classify_ssh_error(Exception("Unknown shell error")), ERR_AUTOMATION_FAILED)
        self.assertEqual(classify_ssh_error(Exception("Channel closed unexpectedly")), ERR_AUTOMATION_FAILED)


if __name__ == "__main__":
    unittest.main(buffer=True)
