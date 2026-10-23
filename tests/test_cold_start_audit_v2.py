import unittest
import numpy as np
from scripts.audit_cold_start_evidence_v2 import same, native_booleans


class ColdStartAuditRepairTests(unittest.TestCase):
    def test_numpy_boolean_gate_matches_native_without_changing_values(self):
        actual = {"passed": np.bool_(True), "checks": [np.bool_(True), np.bool_(False)], "error": .2}
        expected = {"passed": True, "checks": [True, False], "error": .2}
        same(actual, expected)
        self.assertIs(type(native_booleans(actual)["passed"]), bool)
        self.assertIsInstance(actual["passed"], np.bool_)
        with self.assertRaises(ValueError): same(actual, {**expected, "passed": False})
        with self.assertRaises(ValueError): same(actual, {**expected, "error": .20001})
        with self.assertRaises(TypeError): same({"unexpected": np.int64(1)}, {"unexpected": 1})


if __name__ == "__main__": unittest.main()
