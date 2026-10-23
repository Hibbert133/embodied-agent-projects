import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_probemem_verifier_demo import analyze


COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


class ProbeMemVerifierAnalysisTest(unittest.TestCase):
    def test_gate_and_call_reduction_use_shared_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            cases = ((21, COMP, "ACCEPTED"), (22, RETRY, "REJECTED"))
            for method in ("FROZEN_DETERMINISTIC", "ALWAYS_ON_VERIFIER", "BUDGETED_VERIFIER", "EVALUATOR_ONLY_ORACLE"):
                for episode, skill, status in cases:
                    rows.append({
                        "episode_id": episode, "method": method, "final_skill": skill,
                        "default_skill": skill, "verification_status": status,
                        "final_object_goal_distance": 0.2, "environment_steps": 100,
                        "verifier_called": method == "ALWAYS_ON_VERIFIER" or (method == "BUDGETED_VERIFIER" and episode == 21),
                        "override_applied": False, "override_reason": "VERIFIER_BYPASSED",
                        "verifier_latency_ms": 1.0, "memory_coverage": 0.8,
                        "memory_conflict": False, "recent_contradiction": False,
                        "evaluator_only": method == "EVALUATOR_ONLY_ORACLE",
                    })
            self._csv(root / "decisions.csv", rows)
            self._csv(root / "candidate_outcomes.csv", [
                {"episode_id": 21, "candidate_skill": COMP, "verification_status": "ACCEPTED"},
                {"episode_id": 21, "candidate_skill": RETRY, "verification_status": "REJECTED"},
                {"episode_id": 22, "candidate_skill": COMP, "verification_status": "ACCEPTED"},
                {"episode_id": 22, "candidate_skill": RETRY, "verification_status": "REJECTED"},
            ])
            (root / "operational_memory_records.json").write_text("[]", encoding="utf-8")
            (root / "run_status.json").write_text(json.dumps({
                "status": "COMPLETED", "initial_units": 2, "operational_cases": 2,
                "experiment_run_id": "run", "manifest_id": "manifest", "source_git_commit": "commit",
            }), encoding="utf-8")
            result = analyze(root)
            self.assertEqual(result["verifier_budget"]["budgeted_call_rate"], 0.5)
            self.assertEqual(result["verifier_budget"]["call_reduction_vs_always_on"], 0.5)
            self.assertTrue(result["demo_gate"]["route_b"])
            self.assertTrue(result["demo_gate"]["passed"])

    @staticmethod
    def _csv(path: Path, rows: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
