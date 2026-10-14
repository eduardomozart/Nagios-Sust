import os
import sys
import time
import subprocess
import tempfile
import platform
import shutil

try:
    import pywinctl
except ImportError:
    pywinctl = None

try:
    import mss
    import mss.tools
except ImportError:
    mss = None


def _find_window(title, timeout=3.0, poll_interval=0.25):
    """
    Polls pywinctl for a window matching the title substring.
    """
    if not pywinctl:
        return None

    deadline = time.time() + max(0.5, timeout)
    while time.time() < deadline:
        try:
            # 1. Exact or title-based match
            matched = pywinctl.getWindowsWithTitle(title)
            if matched:
                return matched[0]

            # 2. Substring scan across all active windows
            for win in pywinctl.getAllWindows():
                w_title = getattr(win, "title", "") or ""
                if title in w_title:
                    return win
        except Exception:
            pass

        time.sleep(poll_interval)

    return None


def _capture_window_box(win, output_path):
    """
    Grabs the bounding box of win using mss and saves to output_path.
    """
    if not mss:
        raise RuntimeError("mss package is not installed.")

    # Extract coordinates in logical point space
    left = int(getattr(win, "left", 0))
    top = int(getattr(win, "top", 0))
    width = int(getattr(win, "width", 0))
    height = int(getattr(win, "height", 0))

    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid window bounding box: left={left}, top={top}, width={width}, height={height}")

    box = {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with mss.mss() as sct:
        shot = sct.grab(box)
        mss.tools.to_png(shot.rgb, shot.size, output=output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Screenshot file was not generated at {output_path}")

    return output_path


def _get_linux_terminal_candidates():
    """
    Returns an ordered list of terminal candidate names:
    1. Default terminal ($TERMINAL or x-terminal-emulator)
    2. Native terminal for active desktop environment (KDE/Plasma -> konsole, GNOME/Unity -> gnome-terminal,
       XFCE -> xfce4-terminal, MATE -> mate-terminal, LXQt -> qterminal, LXDE -> lxterminal)
    3. Common installed fallbacks
    """
    candidates = []

    # 1. User-configured or system-default terminal
    user_term = os.environ.get("TERMINAL")
    if user_term and user_term not in candidates:
        candidates.append(user_term)
    if "x-terminal-emulator" not in candidates:
        candidates.append("x-terminal-emulator")

    # 2. Native terminal for detected desktop environment
    session = (
        os.environ.get("XDG_CURRENT_DESKTOP", "") + " " +
        os.environ.get("DESKTOP_SESSION", "")
    ).lower()

    if any(de in session for de in ["kde", "plasma"]):
        if "konsole" not in candidates:
            candidates.append("konsole")
    elif any(de in session for de in ["gnome", "unity"]):
        if "gnome-terminal" not in candidates:
            candidates.append("gnome-terminal")
    elif "xfce" in session:
        if "xfce4-terminal" not in candidates:
            candidates.append("xfce4-terminal")
    elif "mate" in session:
        if "mate-terminal" not in candidates:
            candidates.append("mate-terminal")
    elif "lxqt" in session:
        if "qterminal" not in candidates:
            candidates.append("qterminal")
    elif "lxde" in session:
        if "lxterminal" not in candidates:
            candidates.append("lxterminal")

    # 3. Standard fallbacks across Linux distributions
    standard_fallbacks = [
        "gnome-terminal",
        "konsole",
        "xfce4-terminal",
        "mate-terminal",
        "lxterminal",
        "qterminal",
        "xterm",
    ]
    for fallback in standard_fallbacks:
        if fallback not in candidates:
            candidates.append(fallback)

    return candidates


def _build_linux_terminal_cmd(term_bin, title, script_path):
    """
    Constructs CLI arguments for the given terminal emulator.
    """
    term_name = os.path.basename(term_bin).lower()
    if "gnome-terminal" in term_name:
        return [term_bin, f"--title={title}", "--", "sh", script_path]
    elif "konsole" in term_name:
        return [term_bin, "--title", title, "-e", "sh", script_path]
    elif "xfce4-terminal" in term_name:
        return [term_bin, f"--title={title}", "-e", f"sh {script_path}"]
    elif "mate-terminal" in term_name:
        return [term_bin, f"--title={title}", "-e", f"sh {script_path}"]
    elif "lxterminal" in term_name:
        return [term_bin, f"--title={title}", "-e", f"sh {script_path}"]
    elif "qterminal" in term_name:
        return [term_bin, "-e", f"sh {script_path}"]
    else:
        # Standard xterm / x-terminal-emulator / generic fallback
        return [term_bin, "-title", title, "-e", "sh", script_path]


def _spawn_terminal(system, title, command, raw_output):
    """
    Spawns a native OS terminal window configured to display the command prompt and output.
    Returns a handle dictionary with cleanup metadata.
    """
    handle = {
        "system": system,
        "proc": None,
        "txt_path": None,
        "script_path": None,
        "title": title,
    }

    # Write output to temporary file
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as tf:
        tf.write(raw_output or "")
        handle["txt_path"] = tf.name

    if system == "windows":
        # Escape CMD special characters (^, &, <, >, |) for batch echo to prevent accidental redirection
        safe_command = (
            str(command or "")
            .replace("^", "^^")
            .replace("&", "^&")
            .replace("<", "^<")
            .replace(">", "^>")
            .replace("|", "^|")
        )
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".bat", encoding="utf-8") as bf:
            bf.write(
                f"@echo off\r\n"
                f"title {title}\r\n"
                f"echo {safe_command}\r\n"
                f"echo.\r\n"
                f"type \"{handle['txt_path']}\"\r\n"
                f"timeout /t 5 >nul\r\n"
            )
            handle["script_path"] = bf.name

        cmd_str = f'cmd.exe /c "{handle["script_path"]}"'
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        handle["proc"] = subprocess.Popen(cmd_str, creationflags=creation_flags)

    elif system == "darwin":
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sh", encoding="utf-8") as sf:
            sf.write(
                f"#!/bin/sh\n"
                f"echo -n -e \"\\033]0;{title}\\007\"\n"
                f"echo '{command}'\n"
                f"echo\n"
                f"cat '{handle['txt_path']}'\n"
                f"sleep 5\n"
            )
            handle["script_path"] = sf.name

        os.chmod(handle["script_path"], 0o755)
        # Tell Terminal.app to execute the script in a new tab/window
        apple_script = f'tell application "Terminal" to do script "{handle["script_path"]}"'
        subprocess.run(["osascript", "-e", apple_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elif system == "linux":
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sh", encoding="utf-8") as sf:
            sf.write(
                f"#!/bin/sh\n"
                f"echo '{command}'\n"
                f"echo\n"
                f"cat '{handle['txt_path']}'\n"
                f"sleep 5\n"
            )
            handle["script_path"] = sf.name

        os.chmod(handle["script_path"], 0o755)

        term_cmd = None
        candidates = _get_linux_terminal_candidates()
        for term in candidates:
            if shutil.which(term):
                term_cmd = _build_linux_terminal_cmd(term, title, handle["script_path"])
                break

        if not term_cmd:
            raise RuntimeError(f"No supported terminal emulator found on Linux (checked {', '.join(candidates)}).")

        handle["proc"] = subprocess.Popen(term_cmd)

    return handle


def _close_terminal(handle):
    """
    Terminates the terminal window and removes temporary script files.
    """
    system = handle.get("system")
    proc = handle.get("proc")
    title = handle.get("title")

    try:
        if system == "windows" and proc and proc.pid:
            subprocess.run(f"taskkill /PID {proc.pid} /F /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "darwin" and title:
            # Tell Terminal.app to close the window
            close_script = (
                f'tell application "Terminal"\n'
                f'    set winList to (every window whose name contains "{title}")\n'
                f'    repeat with w in winList\n'
                f'        close w saving no\n'
                f'    end repeat\n'
                f'end tell'
            )
            subprocess.run(["osascript", "-e", close_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif proc:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except Exception:
                proc.kill()
    except Exception:
        pass

    # Clean up temporary files
    for key in ["txt_path", "script_path"]:
        path = handle.get(key)
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


def capture_window_screenshot(title, command, raw_output, output_path, timeout=3.0):
    """
    Spawns an OS terminal window, locates it with pywinctl, captures its bounds with mss,
    and closes the window upon completion.
    """
    if not pywinctl or not mss:
        raise RuntimeError("pywinctl and mss are required for window capture.")

    system = platform.system().lower()
    handle = _spawn_terminal(system, title, command, raw_output)

    try:
        # Give window a moment to spawn and become visible
        time.sleep(0.5)

        # Locate window by title
        win = _find_window(title, timeout=timeout)
        if not win:
            raise RuntimeError(f"Could not locate terminal window with title '{title}' within {timeout}s.")

        # Capture window bounding box
        _capture_window_box(win, output_path)
    finally:
        _close_terminal(handle)

    return output_path
