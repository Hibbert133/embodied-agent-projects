from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.generate_persistent_regime_manifest import build_units
from src.probemem.models import InterventionSkill
from src.probemem.persistent_regime import FROZEN_CONSISTENCY_THRESHOLD, select_from_persistent_probe


ROOT = Path(__file__).resolve().parents[1]


class PersistentRegimeProtocolTests(unittest.TestCase):
    def test_manifest_crosses_fifty_seeds_with_two_conditions(self) -> None:
        config = json.loads((ROOT / "configs/probemem_acr/persistent_regime_development_v1.json").read_text())
        units = build_units(config)
        self.assertEqual(len(units), 100)
        self.assertEqual({unit["condition_id_oracle"] for unit in units}, {"fault_01", "fault_05"})
        self.assertFalse({unit["environment_seed"] for unit in units} & set(range(3100, 3200)))

    def test_frozen_historical_threshold_selects_registered_skills(self) -> None:
        self.assertEqual(FROZEN_CONSISTENCY_THRESHOLD, 0.11560838098372882)
        stable, _ = select_from_persistent_probe({"consistency": {"estimated_bias_std_norm": 0.1}})
        noisy, _ = select_from_persistent_probe({"consistency": {"estimated_bias_std_norm": 0.2}})
        self.assertEqual(stable, InterventionSkill.BOUNDED_PLANAR_COMPENSATION)
        self.assertEqual(noisy, InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY)

    def test_probe_rule_rejects_oracle_fields(self) -> None:
        with self.assertRaises(ValueError):
            select_from_persistent_probe({"condition_id": "fault_01", "consistency": {"estimated_bias_std_norm": 0.1}})

    def test_protocol_forbids_glm_and_heldout(self) -> None:
        config = json.loads((ROOT / "configs/probemem_acr/persistent_regime_development_v1.json").read_text())
        self.assertTrue(config["prohibitions"]["call_llm"])
        self.assertTrue(config["prohibitions"]["run_heldout"])


if __name__ == "__main__":
    unittest.main()
