import unittest
from scripts.audit_metaworld_setup_cost import infer_counts,factory_spy


class MetaworldSetupCostTest(unittest.TestCase):
    def test_original_task_generator_has_fifty_temporary_resets_without_robot_steps(self):
        import metaworld
        result=factory_spy(metaworld)
        self.assertEqual(result["temporary_reset_calls"],50)
        self.assertEqual(result["env_step_calls"],0)
        self.assertEqual(result["tasks_generated"],50)

    def test_structural_overhead_is_separate_and_never_marked_runtime_measured(self):
        result=infer_counts(4608,288,50)
        self.assertEqual(result["registered_controlled_resets"],4608)
        self.assertEqual(result["inferred_temporary_task_factory_resets"],230400)
        self.assertEqual(result["inferred_total_reset_entry_calls"],235008)
        self.assertEqual(result["inferred_prior_temporary_task_factory_resets"],14400)
        self.assertEqual(result["inferred_prior_total_reset_entry_calls"],14688)
        self.assertFalse(result["historical_initialization_calls_runtime_measured"])

    def test_invalid_and_boolean_counts_are_rejected(self):
        for n in (-1,True,1.5):
            with self.assertRaises(ValueError):infer_counts(n,288,50)


if __name__=="__main__":unittest.main()
