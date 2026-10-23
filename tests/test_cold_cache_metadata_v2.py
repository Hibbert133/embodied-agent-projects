import copy
import unittest
from scripts import run_cross_task_cache_validity_v2 as repair


class CacheMetadataRepairTest(unittest.TestCase):
    def test_only_static_a_is_compared_without_mutating_the_original(self):
        states = [{"id": name, "matrix_xy": [[1., 0.], [0., 1.]], "bias_xy": [i*.1, 0.]} for i, name in enumerate(("B", "A", "C"))]
        rows = [{"states_oracle": states, "stream": 7}]; before = copy.deepcopy(rows)
        value = repair.flatten_static_a(rows)
        self.assertEqual(value[0]["bias_xy"], [.1, 0.])
        value[0]["matrix_xy"][0][0] = 8
        self.assertEqual(rows, before)

    def test_missing_or_ambiguous_a_is_rejected(self):
        for states in ([], [{"id": "B"}], [{"id": "A"}, {"id": "A"}]):
            with self.assertRaises(ValueError): repair.flatten_static_a([{"states_oracle": states}])

    def test_configuration_preserves_original_bridge_validation(self):
        old = repair.v1.CONFIG, repair.v1.OWN_INPUTS, repair.v1.bridge
        original_function = repair.original_bridge.operators
        try:
            configured = repair.configure()
            self.assertIs(configured.bridge.load, repair.original_bridge.load)
            self.assertIs(repair.original_bridge.operators, original_function)
            self.assertEqual(len(configured.OWN_INPUTS), 17)
            self.assertEqual(len(set(configured.OWN_INPUTS)), 17)
        finally:
            repair.v1.CONFIG, repair.v1.OWN_INPUTS, repair.v1.bridge = old


if __name__ == "__main__":
    unittest.main()
