import json
from pathlib import Path
import unittest

from scripts.generate_selective_override_manifest import build_units
from scripts.run_selective_override_development import _decide
from src.probemem.models import InterventionSkill
from src.probemem.regime_memory import RegimeActionMemory
from src.probemem.selective_override import ProbeAmbiguityAssessment


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/probemem_online/selective_override_development_v1.json"
REGISTRY = ROOT / "configs/probemem_online/seed_registry_v2.json"


class ProbeMemOnlineSelectiveOverrideProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = json.loads(CONFIG.read_text(encoding="utf-8"))
        self.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))

    def test_uses_fresh_development_and_preserves_future_reserve(self) -> None:
        self.assertEqual(self.config["status"], "DEVELOPMENT_FROZEN_BEFORE_EXECUTION")
        self.assertEqual(self.config["seed_range"], [4500, 4599])
        self.assertEqual(
            self.registry["new_partitions"]["selective_override_future_reserved"],
            [4600, 4699],
        )
        self.assertTrue(self.config["prohibitions"]["reuse_gate_c_seeds"])
        units = build_units(self.config)
        self.assertEqual(len(units), 100)
        self.assertEqual([row["environment_seed"] for row in units], list(range(4500, 4600)))
        self.assertTrue(all("outcome" not in key for row in units for key in row))

    def test_ambiguity_is_measurement_stability_not_outcome_fitted_band(self) -> None:
        definition = self.config["ambiguity_definition"]
        self.assertEqual(definition["method"], "leave_one_probe_repeat_out_side_stability")
        self.assertFalse(definition["outcome_fitted_band"])
        self.assertEqual(self.config["frozen_variance_threshold"], 0.11560838098372882)

    def test_high_confidence_bypasses_api_and_conflict_falls_back(self) -> None:
        policy = self.config["primary_policy"]
        self.assertEqual(policy["high_confidence_action"], "FROZEN_VARIANCE_RULE")
        self.assertEqual(policy["memory_conflict_action"], "FALLBACK_TO_FROZEN_VARIANCE_RULE")
        self.assertIn("global_and_recent", policy["override_guard"])

    def test_scope_still_blocks_validation_heldout_and_principles(self) -> None:
        prohibitions = self.config["prohibitions"]
        self.assertTrue(prohibitions["validation"])
        self.assertTrue(prohibitions["heldout"])
        self.assertTrue(prohibitions["principle_generation"])

    def test_high_confidence_decision_makes_zero_api_calls(self) -> None:
        class FailIfCalled:
            def request_once(self, *args, **kwargs):
                raise AssertionError("high-confidence path must bypass API")

        assessment = ProbeAmbiguityAssessment(
            full_score=0.01, leave_one_out_scores=(0.01, 0.01, 0.01, 0.01),
            full_action=InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
            leave_one_out_actions=(InterventionSkill.BOUNDED_PLANAR_COMPENSATION,) * 4,
            ambiguous=False,
        )
        audit = []
        decisions, host = _decide(
            assessment=assessment, compact={}, signature=None,
            memories={
                "AMBIGUITY_GATED_MEMORY_FALLBACK": RegimeActionMemory(),
                "AMBIGUITY_GATED_MEMORY_ABSTAIN": RegimeActionMemory(),
            },
            empty_memory=RegimeActionMemory(), episode_id=21,
            policy=FailIfCalled(), api_audit=audit,
        )
        self.assertEqual(audit, [])
        self.assertTrue(all(decision.selected_skill == assessment.full_action.value for decision in decisions.values()))
        self.assertTrue(all(not row["api_called"] for row in host.values()))


if __name__ == "__main__":
    unittest.main()
