from pathlib import Path
import unittest

from scripts.analyze_selective_override_development import analyze


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "outputs/probemem_online/selective_override_runs/probemem_online_selective_override_20260804T064750Z_1107f99883b4"


class SelectiveOverrideAnalysisTest(unittest.TestCase):
    def test_registered_run_is_incomplete_for_ambiguity_population(self) -> None:
        result = analyze(RUN)
        self.assertEqual(result["run_status"], "INCOMPLETE_POPULATION")
        self.assertEqual(result["operational_cases"], 40)
        self.assertEqual(result["ambiguous_cases"], 3)
        self.assertFalse(result["promotion_gate"]["evaluated"])
        self.assertFalse(result["promotion_gate"]["passed"])

    def test_cost_reduction_is_descriptive_and_primary_ties_frozen(self) -> None:
        result = analyze(RUN)
        self.assertAlmostEqual(result["api"]["call_reduction"], 0.925)
        self.assertEqual(result["primary_vs_frozen_changes"], {
            "changed": 2, "helpful": 0, "harmful": 0, "tie": 2,
        })
        methods = result["methods"]
        self.assertEqual(methods["AMBIGUITY_GATED_MEMORY_FALLBACK"]["accepted"], 34)
        self.assertEqual(methods["FROZEN_VARIANCE_RULE"]["accepted"], 34)


if __name__ == "__main__":
    unittest.main()
