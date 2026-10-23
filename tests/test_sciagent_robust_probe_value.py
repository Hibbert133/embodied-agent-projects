import time
import unittest

from src.probemem_sciagent.capability_contract import build_capability_contract
import sys

from src.probemem_sciagent.hard_deadline_transport import execute_subprocess_with_hard_deadline
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.robust_probe_value import (
    MAXIMUM_CURRENT_PROBABILITY_GAP,
    attach_robust_probe_value_contract,
    validate_robust_probe_value_certificate,
)


class SciAgentRobustProbeValueTest(unittest.TestCase):
    def setUp(self):
        self.capability = build_capability_contract(
            snapshot=ScientificMemorySnapshot(1, (), (), (), ()),
            current_evidence_id="current",
        ).to_payload()
        self.contract = attach_robust_probe_value_contract(
            {"capability_contract": self.capability}
        )["probe_value_contract"]

    def test_hard_deadline_returns_completed_child_result(self):
        self.assertEqual(
            execute_subprocess_with_hard_deadline(
                [sys.executable, "-c", "print('ok')"],
                input_text="", deadline_seconds=2.0,
            ).strip(), "ok",
        )

    def test_hard_deadline_terminates_slow_child(self):
        started = time.perf_counter()
        with self.assertRaisesRegex(TimeoutError, "hard deadline"):
            execute_subprocess_with_hard_deadline(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                input_text="", deadline_seconds=0.1,
            )
        self.assertLess(time.perf_counter() - started, 1.5)

    def test_robust_rule_admits_ambiguous_discriminative_high_value_probe(self):
        result = self._validate(self._certificate())
        self.assertTrue(result.admitted)
        self.assertTrue(result.outcome_discriminative)
        self.assertAlmostEqual(result.current_probability_gap, MAXIMUM_CURRENT_PROBABILITY_GAP)

    def test_clear_current_preference_blocks_probe(self):
        value = self._certificate()
        value["current_selected_probability_token"] = "P_14"
        value["current_alternative_probability_token"] = "P_08"
        result = self._validate(value)
        self.assertFalse(result.admitted)
        self.assertIn("CURRENT_ACTION_NOT_AMBIGUOUS", result.rejection_reasons)

    def test_outcomes_that_keep_same_skill_block_probe(self):
        value = self._certificate()
        value["outcome_branches"][1].update({
            "selected_probability_token": "P_16",
            "alternative_probability_token": "P_04",
        })
        result = self._validate(value)
        self.assertFalse(result.admitted)
        self.assertIn("OUTCOMES_NOT_DECISION_DISCRIMINATIVE", result.rejection_reasons)

    def test_quantization_lower_bound_can_block_nominal_gain(self):
        value = self._certificate()
        for branch in value["outcome_branches"]:
            if branch["selected_probability_token"] == "P_16":
                branch["selected_probability_token"] = "P_13"
            if branch["alternative_probability_token"] == "P_16":
                branch["alternative_probability_token"] = "P_13"
        result = self._validate(value)
        self.assertFalse(result.admitted)
        self.assertIn("ROBUST_VALUE_NOT_ABOVE_NORMALIZED_COST", result.rejection_reasons)

    def _validate(self, raw):
        return validate_robust_probe_value_certificate(
            raw, decision={
                "decision_mode": "RUN_MICRO_PROBE",
                "selected_probe_type": "COMPENSATION_RESPONSE_PROBE",
                "selected_skill": "BOUNDED_PLANAR_COMPENSATION",
            },
            capability_contract=self.capability,
            probe_value_contract=self.contract,
        )

    @staticmethod
    def _certificate():
        return {
            "selected_probe_token": "PROBE_0",
            "current_selected_probability_token": "P_11",
            "current_alternative_probability_token": "P_09",
            "outcome_branches": [
                {"outcome_token": "OUTCOME_COMP_ALIGNED", "branch_probability_token": "P_10",
                 "selected_probability_token": "P_16", "alternative_probability_token": "P_04"},
                {"outcome_token": "OUTCOME_COMP_NOT_ALIGNED", "branch_probability_token": "P_10",
                 "selected_probability_token": "P_04", "alternative_probability_token": "P_16"},
            ],
        }


if __name__ == "__main__":
    unittest.main()
