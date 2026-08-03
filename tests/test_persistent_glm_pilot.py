from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.run_persistent_glm_pilot import PERSISTENT_SYSTEM_PROMPT, select_cases
from src.reasoning.evidence import validate_no_oracle_evidence


ROOT = Path(__file__).resolve().parents[1]


class PersistentGlmPilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads((ROOT / "configs/probemem_acr/persistent_glm_pilot_v1.json").read_text(encoding="utf-8"))

    def test_selection_is_ten_cases_balanced_only_by_evaluator(self) -> None:
        cases = select_cases(self.config)
        self.assertEqual(len(cases), 10)
        counts = {name: sum(row["selection_stratum_evaluator_only"] == name for row in cases) for name in ("fault_01", "fault_05")}
        self.assertEqual(counts, {"fault_01": 5, "fault_05": 5})
        for row in cases:
            validate_no_oracle_evidence(row["agent_visible_evidence"])
            self.assertNotIn("selection_stratum_evaluator_only", row["agent_visible_evidence"])

    def test_protocol_has_exact_ten_call_cap_and_no_execution(self) -> None:
        self.assertEqual(self.config["maximum_cases"], 10)
        self.assertEqual(self.config["maximum_api_calls"], 10)
        self.assertEqual(self.config["schema_repair_attempts_per_case"], 0)
        self.assertTrue(self.config["prohibitions"]["execute_model_action"])
        self.assertTrue(self.config["prohibitions"]["send_evaluator_outcome"])

    def test_prompt_forbids_truth_threshold_and_continuous_action(self) -> None:
        lowered = PERSISTENT_SYSTEM_PROMPT.lower()
        self.assertIn("condition identity", lowered)
        self.assertIn("threshold", lowered)
        self.assertIn("continuous robot actions", lowered)


if __name__ == "__main__":
    unittest.main()
