from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path

from scripts.analyze_resonance_validation import _oracle_candidate, _select_strongest_fixed
from scripts.generate_resonance_validation_manifest import IMPLEMENTATION_PATHS, build_population_units
from src.probemem.resonance import classify_resonance
from src.probemem.resonance_policy import decide_second_attempt


ROOT = Path(__file__).resolve().parents[1]


class ResonanceValidationRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads((ROOT / "configs/probemem_acr/resonance_validation_v1.json").read_text(encoding="utf-8"))

    def test_manifest_population_excludes_heldout_and_has_independent_streams(self) -> None:
        units = build_population_units(self.config)
        self.assertEqual(len(units), 150)
        self.assertFalse({unit["environment_seed"] for unit in units} & set(range(3100, 3200)))
        for unit in units:
            streams = {unit["initial_perturbation_seed"], unit["diagnostic_probe_seed"],
                       unit["first_verification_seed"], unit["paired_second_verification_seed"]}
            self.assertEqual(len(streams), 4)

    def test_manifest_hashes_collector_analyzer_renderer_and_policy(self) -> None:
        paths = {path.as_posix() for path in IMPLEMENTATION_PATHS}
        self.assertIn("scripts/run_resonance_validation.py", paths)
        self.assertIn("scripts/analyze_resonance_validation.py", paths)
        self.assertIn("scripts/render_resonance_validation_figures.py", paths)
        self.assertIn("src/probemem/resonance_policy.py", paths)

    def test_strongest_fixed_uses_recovery_harm_steps_then_name(self) -> None:
        summary = {
            "repeat_retry": {"final_accepted_cases": 10, "harmful_second_selections": 2, "total_online_environment_steps": 1000},
            "switch_compensation": {"final_accepted_cases": 10, "harmful_second_selections": 1, "total_online_environment_steps": 1200},
        }
        self.assertEqual(_select_strongest_fixed(summary), "switch_compensation")

    def test_oracle_uses_status_progress_then_cost(self) -> None:
        pair = {
            "A": {"candidate_id": "A", "verification_status": "ACCEPTED", "observed_progress": "0.1", "verification_steps": "20"},
            "B": {"candidate_id": "B", "verification_status": "INCONCLUSIVE", "observed_progress": "1.0", "verification_steps": "1"},
        }
        self.assertEqual(_oracle_candidate(pair), ("A", False))

    def test_agent_policy_has_no_counterfactual_outcome_parameter(self) -> None:
        parameters = set(inspect.signature(decide_second_attempt).parameters)
        self.assertFalse(parameters & {"candidate_outcomes", "oracle_winner", "future_outcome"})

    def test_resonance_matrix_remains_frozen(self) -> None:
        self.assertEqual(classify_resonance("ACCEPTED", "REJECTED"), "CONTRADICTED")
        self.assertEqual(classify_resonance("INCONCLUSIVE", "ACCEPTED"), "UNRESOLVED")
        self.assertEqual(classify_resonance("REJECTED", "REJECTED"), "SUPPORTED")


if __name__ == "__main__":
    unittest.main()
