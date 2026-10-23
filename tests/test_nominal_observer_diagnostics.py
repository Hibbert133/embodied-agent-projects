import copy
import unittest
from scripts.analyze_nominal_observer_diagnostics import case_diagnostic,report


class NominalObserverDiagnosticsTest(unittest.TestCase):
    def test_task_success_does_not_hide_precision_failure(self):
        record={"episode_index":1,"seed":10000,"task":"push-v3","program":"POLICY_ONLY",
            "outcome":{"success":True,"maximum_block_error":.5,"total_steps":20,"snapshots":[],
                "blocks":[{"nominal_mean_error_inf":.05,"end_step":5,"phase":"POLICY"},
                          {"nominal_mean_error_inf":.5,"end_step":9,"phase":"POLICY"}]}}
        original=copy.deepcopy(record);result=case_diagnostic(record,.1)
        self.assertTrue(result["precision_exceeded"])
        self.assertTrue(result["nominal_task_success"])
        self.assertEqual(result["first_exceeded_block"]["end_step"],9)
        self.assertEqual(record,original)

    def test_missing_measurements_are_not_zero_error_or_silent_omission(self):
        record={"episode_index":1,"seed":10000,"task":"reach-v3","program":"POLICY_ONLY",
            "outcome":{"success":False,"maximum_block_error":None,"total_steps":1,"snapshots":[],"blocks":[]}}
        result=case_diagnostic(record,.1)
        self.assertTrue(result["precision_exceeded"])
        text=report({"experiment_run_id":"synthetic","precision_exceeded_cases":1,"cases":[result]})
        self.assertIn("无测量",text)


if __name__=="__main__":unittest.main()
