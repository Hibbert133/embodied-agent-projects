import unittest

from scripts.analyze_phase_conditioned_evidence_need import _as_bool, evaluate_promotion


class PhaseConditionedEvidenceNeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = {
            "minimum_probe_need_roc_auc": 0.75,
            "minimum_diagnostic_accuracy_relative_to_always_probe": 1.0,
            "maximum_probe_request_rate": 0.6,
        }

    def test_online_agent_is_allowed_only_when_all_gates_pass(self) -> None:
        result = evaluate_promotion(
            auc=0.8, gated_accuracy=1.0, always_accuracy=1.0,
            probe_request_rate=0.5, promotion=self.gate,
        )
        self.assertTrue(result["online_agent_allowed"])

    def test_high_probe_rate_blocks_online_agent(self) -> None:
        result = evaluate_promotion(
            auc=0.8, gated_accuracy=1.0, always_accuracy=1.0,
            probe_request_rate=0.7, promotion=self.gate,
        )
        self.assertFalse(result["online_agent_allowed"])
        self.assertFalse(result["criteria"]["probe_request_rate"])

    def test_csv_boolean_is_not_interpreted_by_string_truthiness(self) -> None:
        self.assertFalse(_as_bool("False"))
        self.assertTrue(_as_bool("True"))


if __name__ == "__main__":
    unittest.main()
