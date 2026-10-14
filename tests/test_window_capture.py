import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import utils.window_capture as wc_mod

class TestWindowCapture(unittest.TestCase):
    def test_get_linux_terminal_candidates_precedence_with_user_terminal(self):
        """Verifies $TERMINAL env variable is first, followed by x-terminal-emulator and desktop native terminal."""
        with patch.dict(os.environ, {"TERMINAL": "kitty", "XDG_CURRENT_DESKTOP": "KDE", "DESKTOP_SESSION": "plasma"}, clear=True):
            candidates = wc_mod._get_linux_terminal_candidates()
            self.assertEqual(candidates[0], "kitty")
            self.assertEqual(candidates[1], "x-terminal-emulator")
            self.assertEqual(candidates[2], "konsole")
            self.assertIn("xterm", candidates)

    def test_get_linux_terminal_candidates_default_precedence_kde(self):
        """Verifies x-terminal-emulator is first, followed by konsole for KDE."""
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE", "DESKTOP_SESSION": "plasma"}, clear=True):
            candidates = wc_mod._get_linux_terminal_candidates()
            self.assertEqual(candidates[0], "x-terminal-emulator")
            self.assertEqual(candidates[1], "konsole")
            self.assertIn("xterm", candidates)

    def test_get_linux_terminal_candidates_default_precedence_gnome(self):
        """Verifies x-terminal-emulator is first, followed by gnome-terminal for GNOME."""
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "DESKTOP_SESSION": "ubuntu"}, clear=True):
            candidates = wc_mod._get_linux_terminal_candidates()
            self.assertEqual(candidates[0], "x-terminal-emulator")
            self.assertEqual(candidates[1], "gnome-terminal")
            self.assertIn("xterm", candidates)

    def test_get_linux_terminal_candidates_default_precedence_xfce(self):
        """Verifies x-terminal-emulator is first, followed by xfce4-terminal for XFCE."""
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "XFCE", "DESKTOP_SESSION": "xfce"}, clear=True):
            candidates = wc_mod._get_linux_terminal_candidates()
            self.assertEqual(candidates[0], "x-terminal-emulator")
            self.assertEqual(candidates[1], "xfce4-terminal")

    def test_get_linux_terminal_candidates_default_precedence_mate(self):
        """Verifies x-terminal-emulator is first, followed by mate-terminal for MATE."""
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "MATE", "DESKTOP_SESSION": "mate"}, clear=True):
            candidates = wc_mod._get_linux_terminal_candidates()
            self.assertEqual(candidates[0], "x-terminal-emulator")
            self.assertEqual(candidates[1], "mate-terminal")

    def test_build_linux_terminal_cmd(self):
        """Verifies command arguments for each terminal emulator."""
        self.assertEqual(
            wc_mod._build_linux_terminal_cmd("gnome-terminal", "title1", "/tmp/s.sh"),
            ["gnome-terminal", "--title=title1", "--", "sh", "/tmp/s.sh"]
        )
        self.assertEqual(
            wc_mod._build_linux_terminal_cmd("konsole", "title1", "/tmp/s.sh"),
            ["konsole", "--title", "title1", "-e", "sh", "/tmp/s.sh"]
        )
        self.assertEqual(
            wc_mod._build_linux_terminal_cmd("xfce4-terminal", "title1", "/tmp/s.sh"),
            ["xfce4-terminal", "--title=title1", "-e", "sh /tmp/s.sh"]
        )
        self.assertEqual(
            wc_mod._build_linux_terminal_cmd("xterm", "title1", "/tmp/s.sh"),
            ["xterm", "-title", "title1", "-e", "sh", "/tmp/s.sh"]
        )

    @patch("subprocess.Popen")
    @patch("shutil.which")
    def test_spawn_terminal_linux(self, mock_which, mock_popen):
        """Verifies _spawn_terminal on Linux picks the first available candidate."""
        mock_which.side_effect = lambda cmd: "/usr/bin/" + cmd if cmd == "konsole" else None
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE", "DESKTOP_SESSION": "plasma"}, clear=True):
            handle = wc_mod._spawn_terminal("linux", "TestWin", "ping -c 4 1.1.1.1", "output")
            try:
                self.assertEqual(handle["system"], "linux")
                self.assertEqual(handle["proc"], mock_proc)
                self.assertTrue(mock_popen.called)
                args = mock_popen.call_args[0][0]
                self.assertEqual(args[0], "konsole")
            finally:
                wc_mod._close_terminal(handle)

    @patch("subprocess.Popen")
    def test_spawn_terminal_windows(self, mock_popen):
        """Verifies _spawn_terminal on Windows creates a batch script and runs cmd.exe."""
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        handle = wc_mod._spawn_terminal("windows", "WinTest", "C:\\>ping -n 4 1.1.1.1", "output")
        try:
            self.assertEqual(handle["system"], "windows")
            self.assertTrue(mock_popen.called)
            cmd_str = mock_popen.call_args[0][0]
            self.assertIn("cmd.exe /c", cmd_str)
            # Verify batch script escapes CMD special characters to avoid redirection
            with open(handle["script_path"], "r", encoding="utf-8") as bf:
                bat_content = bf.read()
            self.assertIn("echo C:\\^>ping -n 4 1.1.1.1", bat_content)
        finally:
            wc_mod._close_terminal(handle)

    @patch("utils.window_capture._close_terminal")
    @patch("utils.window_capture._capture_window_box")
    @patch("utils.window_capture._find_window")
    @patch("utils.window_capture._spawn_terminal")
    def test_capture_window_screenshot_workflow(
        self, mock_spawn, mock_find, mock_capture_box, mock_close
    ):
        """Verifies the complete capture_window_screenshot orchestration."""
        mock_handle = {"system": "windows"}
        mock_spawn.return_value = mock_handle
        mock_win = MagicMock()
        mock_find.return_value = mock_win

        out_path = "/tmp/fake_shot.png"
        res = wc_mod.capture_window_screenshot("TestTitle", "ping 1.1.1.1", "output", out_path)

        self.assertEqual(res, out_path)
        mock_spawn.assert_called_once()
        mock_find.assert_called_once_with("TestTitle", timeout=3.0)
        mock_capture_box.assert_called_once_with(mock_win, out_path)
        mock_close.assert_called_once_with(mock_handle)

    @patch("utils.window_capture._close_terminal")
    @patch("utils.window_capture._find_window", return_value=None)
    @patch("utils.window_capture._spawn_terminal", return_value={"system": "linux"})
    def test_capture_window_screenshot_window_not_found(self, mock_spawn, mock_find, mock_close):
        """Verifies capture_window_screenshot cleans up and raises RuntimeError if window is not found."""
        with self.assertRaises(RuntimeError):
            wc_mod.capture_window_screenshot("Missing", "ping 1.1.1.1", "output", "/tmp/shot.png")
        self.assertTrue(mock_close.called)


if __name__ == "__main__":
    unittest.main(buffer=True)
