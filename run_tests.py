#!/usr/bin/env python3
"""
Nagios-Sust Test Runner.
Executes test discovery with stdout/stderr buffering enabled, suppressing
output from passing tests and only surfacing failures and tracebacks.

Usage:
    python3 run_tests.py          # Run all unit tests quietly with buffering
    python3 run_tests.py -q       # Minimal output (only errors/failures)
    python3 run_tests.py -v       # Run with test method names displayed
"""
import os
import sys
import unittest

# Ensure local .venv site-packages is available if present
venv_site_packages = os.path.join(
    os.path.dirname(__file__),
    ".venv",
    "lib",
    f"python{sys.version_info.major}.{sys.version_info.minor}",
    "site-packages",
)
if os.path.isdir(venv_site_packages) and venv_site_packages not in sys.path:
    sys.path.insert(0, venv_site_packages)


def main():
    if "-q" in sys.argv or "--quiet" in sys.argv:
        verbosity = 0
    elif "-v" in sys.argv or "--verbose" in sys.argv:
        verbosity = 2
    else:
        verbosity = 1

    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py", top_level_dir=".")
    runner = unittest.TextTestRunner(verbosity=verbosity, buffer=True)
    result = runner.run(suite)

    if result.skipped:
        print("\nSkipped tests:")
        for test_case, reason in result.skipped:
            print(f"  - {test_case}: {reason}")

    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
