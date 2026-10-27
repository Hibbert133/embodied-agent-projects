"""Pure-key regression checks: no environment, model inference or API."""
import unittest
from src.analysis import learned_acquisition_native_audit_v1 as old
from src.analysis import learned_acquisition_native_audit_v2 as repaired


class RepairTests(unittest.TestCase):
    def test_original_set_serialization_failure_is_reproduced_without_physics(self):
        with self.assertRaises(ValueError):old.same(set(old.a.PROGRAMS),set(old.a.PROGRAMS))

    def test_repaired_membership_accepts_order_only_and_rejects_missing_extra(self):
        good={p:None for p in reversed(old.a.PROGRAMS)};repaired.check_program_membership(good)
        for bad in (dict(list(good.items())[:-1]),dict(good,UNKNOWN=None),list(good)):
            with self.subTest(value=bad),self.assertRaises(ValueError):repaired.check_program_membership(bad)
