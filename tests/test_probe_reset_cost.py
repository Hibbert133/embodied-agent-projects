import unittest
from scripts.audit_probe_reset_cost import accounting


class ResetCostTest(unittest.TestCase):
    def test_four_directional_starts_per_repetition_and_uniform_sensitivity(self):
        rows = [{"method":"FIXED_16","probe_steps":16,"steps":100,"success":True},
                {"method":"DECISION_STABILITY","probe_steps":32,"steps":110,"success":False}]
        result = accounting(rows)
        self.assertEqual(result["methods"]["FIXED_16"]["charged_direction_resets"],4)
        cost = result["candidate_minus_fixed16_cost"]
        self.assertEqual(cost["intercept_task_plus_probe_steps"],26)
        self.assertEqual(cost["slope_per_reset_step_equivalent"],4)
        self.assertTrue(cost["dominated_for_every_nonnegative_uniform_reset_cost"])

    def test_cannot_claim_uniform_dominance_if_reset_slope_is_negative(self):
        rows = [{"method":"FIXED_16","probe_steps":16,"steps":100,"success":True},
                {"method":"DECISION_STABILITY","probe_steps":0,"steps":130,"success":False}]
        self.assertFalse(accounting(rows)["candidate_minus_fixed16_cost"]["dominated_for_every_nonnegative_uniform_reset_cost"])

    def test_unregistered_probe_cost_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"unregistered"):
            accounting([{"method":"FIXED_16","probe_steps":15,"steps":100,"success":True}])


if __name__ == "__main__":
    unittest.main()
