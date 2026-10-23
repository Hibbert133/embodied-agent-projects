import unittest
from scripts.report_response_acquisition_utility import compact, reason, actual_pair, totals
from tests import test_response_acquisition_utility_audit as fixture


class ResponseAcquisitionUtilityReportTest(unittest.TestCase):
    def pair(self):
        a, b = fixture.ResponseAcquisitionUtilityAuditTest().pair()
        for record in (a, b):
            record.update(experiment_run_id="test", manifest_id="manifest", source_git_commit="source")
        return a, b

    def test_independent_prefix_eligibility_does_not_read_branch_result(self):
        a, b = map(compact, self.pair())
        a["branch"] = {"success": True, "stopped": True, "steps": 500, "probes": 16}
        self.assertEqual(reason(a, b), "MATCHED")
        a["prefix"][0]["rng_after"] = "changed"
        self.assertEqual(reason(a, b), "DIFFERENT_PHYSICAL_PREFIX")

    def test_trace_tampering_fails_even_if_saved_outcome_is_plausible(self):
        a, _ = self.pair()
        a["outcome"]["success"] = True
        with self.assertRaises(ValueError): compact(a)
        a, _ = self.pair(); a["trace"][2]["host_calls"] = 9
        with self.assertRaises(ValueError): compact(a)
        a, _ = self.pair(); a["outcome"]["total_steps"] = 500
        with self.assertRaises(ValueError): compact(a)

    def test_independent_stopped_case_retains_cost_and_denominator(self):
        a, b = self.pair(); a["decisions"][-1]["controller"] = None; a["outcome"]["stopped"] = True
        a, b = compact(a), compact(b)
        row = actual_pair(a, b)
        self.assertEqual((row["target_stopped"], row["target_total_steps"]), (True, 6))
        self.assertEqual((totals([row])["cases"], totals([row])["target_stops"]), (1, 1))
        self.assertIsNone(totals([])["mean_target_total_steps"])

    def test_different_cache_and_shared_success_are_not_qualified(self):
        a, b = map(compact, self.pair()); a["cache_before"]["bias_xy"][1] = 1e-15
        self.assertEqual(reason(a, b), "UNEQUAL_OLD_CACHE")
        with self.assertRaises(ValueError): actual_pair(a, b)
        a, b = map(compact, self.pair())
        for r in (a, b): r["prefix"][-1]["after"]["success"] = True
        self.assertEqual(reason(a, b), "ENDED_BY_SHARED_PREFIX")


if __name__ == "__main__":
    unittest.main()
