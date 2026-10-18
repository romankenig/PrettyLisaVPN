"""Check that failure during rollback cannot omit or disguise restoration."""

import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "runtime_rollback", Path(__file__).resolve().parents[1] / "runtime_rollback.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecoveryTests(unittest.TestCase):
    def test_successful_cycle_runs_both_stages(self):
        calls = []
        MODULE.recovery_cycle(lambda: calls.append("rollback"), lambda: calls.append("restore"))
        self.assertEqual(calls, ["rollback", "restore"])

    def test_failed_rollback_still_restores_and_reports_failure(self):
        calls = []

        def rollback():
            calls.append("rollback")
            raise RuntimeError("partial rollback")

        with self.assertRaisesRegex(RuntimeError, "partial rollback"):
            MODULE.recovery_cycle(rollback, lambda: calls.append("restore"))
        self.assertEqual(calls, ["rollback", "restore"])

    def test_restoration_failure_is_never_success(self):
        calls = []

        def restore():
            calls.append("restore")
            raise RuntimeError("restore failed")

        with self.assertRaisesRegex(RuntimeError, "restore failed"):
            MODULE.recovery_cycle(lambda: calls.append("rollback"), restore)
        self.assertEqual(calls, ["rollback", "restore"])


if __name__ == "__main__":
    unittest.main()
