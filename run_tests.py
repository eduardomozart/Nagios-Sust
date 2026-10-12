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
import sys
import unittest


def main():
    if "-q" in sys.argv or "--quiet" in sys.argv:
        verbosity = 0
    elif "-v" in sys.argv or "--verbose" in sys.argv:
        verbosity = 2
    else:
        verbosity = 1

    loader = unittest.TestLoader()
    suite = loader.discover("tests", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=verbosity, buffer=True)
    result = runner.run(suite)

    if result.skipped:
        print("\nSkipped tests:")
        for test_case, reason in result.skipped:
            print(f"  - {test_case}: {reason}")

    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
