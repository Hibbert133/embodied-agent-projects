import json
from pathlib import Path
import csv
import tempfile
import unittest

from src.probemem.additional_experiments import (
    ExperimentMemoryRecord,
    MethodChronologicalMemory,
    deterministic_verifier,
    select_from_retrieval,
    transfer_label,
    verifier_intervention_outcome,
)
from scripts.generate_probemem_additional_manifest import build_units
from scripts.analyze_probemem_additional_ablation import analyze


ROOT = Path(__file__).resolve().parents[1]
COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"
SCALES = (1.0, 0.3, 1.0, 1.0, 0.02, 0.02, 1.5)


def record(owner: str, episode: int, skill: str, status: str, *, offset: float = 0.0):
    return ExperimentMemoryRecord(
        f"{owner}-{episode}", owner, episode, episode + 1,
        (offset,) * 7, skill, status, episode * 10,
    )


class AdditionalExperimentContractsTest(unittest.TestCase):
    def test_config_freezes_sequential_population_and_prohibitions(self) -> None:
        config = json.loads((ROOT / "configs/probemem_additional/ablation_development_v1.json").read_text())
        self.assertEqual(config["seed_range"], [7200, 7399])
        self.assertEqual(config["future_reserved_seed_range"], [7400, 7499])
        self.assertEqual(config["target_operational_cases"], 60)
        self.assertFalse(config["population_descriptive_targets"]["affects_stopping_or_seed_selection"])
        self.assertTrue(all(config["prohibitions"].values()))
        self.assertEqual(config["budget"]["total_online_case_max_steps"], 1064)
        units = build_units(config)
        self.assertEqual([row["environment_seed"] for row in units], list(range(7200, 7400)))
        self.assertEqual(units[0]["condition_id_oracle"], "fault_01")
        self.assertEqual(units[5]["condition_id_oracle"], "fault_01")
        self.assertTrue(all("outcome" not in key for row in units for key in row))

    def test_manifest_and_runner_ignore_only_untracked_output_artifacts(self) -> None:
        generator = (ROOT / "scripts/generate_probemem_additional_manifest.py").read_text(encoding="utf-8")
        runner = (ROOT / "scripts/run_probemem_additional_ablation.py").read_text(encoding="utf-8")
        self.assertIn('"diff", "--name-only"', generator)
        self.assertIn('"diff", "--cached", "--name-only"', generator)
        self.assertIn('"diff", "--name-only"', runner)
        self.assertNotIn('_git("status", "--porcelain")', generator)
        self.assertNotIn('_git("status", "--porcelain")', runner)

    def test_memory_is_owner_isolated_accepted_only_and_prior_only(self) -> None:
        memory = MethodChronologicalMemory("MEMORY_ONLY", scales=SCALES)
        memory.append(record("MEMORY_ONLY", 1, COMP, "ACCEPTED"))
        memory.append(record("MEMORY_ONLY", 2, RETRY, "REJECTED", offset=0.1))
        items = memory.retrieve((0.0,) * 7, current_episode_id=3, decision_sequence=100, limit=3)
        self.assertEqual([item.record_id for item in items], ["MEMORY_ONLY-1"])
        with self.assertRaisesRegex(ValueError, "cross-method"):
            memory.append(record("FULL_PROBEMEM", 3, COMP, "ACCEPTED"))

    def test_current_or_not_yet_completed_record_is_unavailable(self) -> None:
        memory = MethodChronologicalMemory("PROBE_MEMORY", scales=SCALES)
        memory.append(record("PROBE_MEMORY", 2, COMP, "ACCEPTED"))
        self.assertEqual(memory.retrieve((0.0,) * 7, current_episode_id=2, decision_sequence=99, limit=3), ())
        self.assertEqual(memory.retrieve((0.0,) * 7, current_episode_id=3, decision_sequence=20, limit=3), ())

    def test_retrieval_vote_falls_back_on_empty_or_tie(self) -> None:
        self.assertEqual(select_from_retrieval((), fallback_skill=RETRY), (RETRY, False))
        memory = MethodChronologicalMemory("M", scales=SCALES)
        memory.append(record("M", 1, COMP, "ACCEPTED"))
        memory.append(record("M", 2, RETRY, "ACCEPTED"))
        items = memory.retrieve((0.0,) * 7, current_episode_id=3, decision_sequence=99, limit=3)
        self.assertEqual(select_from_retrieval(items, fallback_skill=RETRY), (RETRY, False))

    def test_verifier_uses_only_owner_supplied_prior_records(self) -> None:
        records = [record("FULL", index, RETRY, "ACCEPTED") for index in range(1, 5)]
        result = deterministic_verifier(
            proposal_skill=COMP, prior_records=records, current_episode_id=6,
            invoked=True, probability_margin_minimum=0.15,
            coverage_minimum=3, confidence_minimum=0.70,
        )
        self.assertEqual(result.selected_skill, RETRY)
        self.assertEqual(result.reason, "OVERRIDE")

    def test_transfer_and_verifier_outcome_taxonomies(self) -> None:
        self.assertEqual(transfer_label(
            no_memory_skill=COMP, memory_skill=RETRY,
            no_memory_status="REJECTED", memory_status="ACCEPTED", retrieval_count=1,
        ), "USEFUL_TRANSFER")
        self.assertEqual(verifier_intervention_outcome(
            proposal_skill=COMP, selected_skill=RETRY,
            proposal_status="REJECTED", selected_status="ACCEPTED",
        ), "CORRECT_REJECTION")
        self.assertEqual(verifier_intervention_outcome(
            proposal_skill=COMP, selected_skill=RETRY,
            proposal_status="ACCEPTED", selected_status="REJECTED",
        ), "FALSE_REJECTION")

    def test_analysis_uses_common_recovery_denominator_and_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            population = [
                {"operational": True, "condition_id_oracle": "fault_01", "mechanism_oracle": "stable_bias"},
                {"operational": True, "condition_id_oracle": "fault_05", "mechanism_oracle": "stochastic_noise"},
            ]
            methods = ("BASELINE", "MEMORY_ONLY", "EVIDENCE_ACQUISITION_ENABLED", "PROBE_MEMORY", "FULL_PROBEMEM")
            decisions = []
            for episode in (1, 2):
                for method in methods:
                    full = method == "FULL_PROBEMEM"
                    decisions.append({
                        "episode_id": episode, "seed": 7200 + episode, "method": method,
                        "condition_id_oracle": "fault_01" if episode == 1 else "fault_05",
                        "mechanism_oracle": "stable_bias" if episode == 1 else "stochastic_noise",
                        "mechanism_prediction": "stable_bias" if episode == 1 else "stochastic_noise",
                        "evidence_steps": 64 if method in {"EVIDENCE_ACQUISITION_ENABLED", "PROBE_MEMORY", "FULL_PROBEMEM"} else 0,
                        "retrieval_count": 0, "proposal_skill": COMP, "selected_skill": COMP,
                        "verifier_eligible": full, "valid_proposal": full,
                        "verifier_invoked": full and episode == 2,
                        "proposal_probability": 0.8 if full and episode == 2 else "",
                        "alternative_probability": 0.2 if full and episode == 2 else "",
                        "proposal_action_signature_id": f"sig-{episode}",
                        "selected_action_signature_id": f"sig-{episode}",
                        "verification_status": "ACCEPTED" if episode == 1 else "REJECTED",
                        "total_online_steps": 600,
                    })
            outcomes = [
                {"episode_id": episode, "action_signature_id": f"sig-{episode}", "realization": 0,
                 "verification_status": "ACCEPTED" if episode == 1 else "REJECTED"}
                for episode in (1, 2)
            ]
            self._csv(root / "population.csv", population)
            self._csv(root / "decisions.csv", decisions)
            self._csv(root / "candidate_outcomes.csv", outcomes)
            (root / "memory_retrieval_audit.csv").write_text("", encoding="utf-8")
            (root / "run_status.json").write_text(json.dumps({
                "status": "COMPLETED", "experiment_run_id": "run", "manifest_id": "manifest",
                "source_git_commit": "commit", "population_by_condition": {"fault_01": 1, "fault_05": 1},
                "population_by_mechanism": {"stable_bias": 1, "stochastic_noise": 1},
                "descriptive_population_imbalance": True,
            }), encoding="utf-8")
            result = analyze(root)
            self.assertEqual(result["common_initial_failure_denominator"], 2)
            self.assertEqual(result["verifier"]["proposal_coverage"], 1.0)
            self.assertEqual(result["verifier"]["invocation_coverage"], 0.5)
            self.assertEqual(result["research_findings"]["RQ3"]["conclusion"], "Not supported")
            self.assertEqual(result["failure_taxonomy_counts"]["DIAGNOSIS_CORRECT_RECOVERY_FAILED"], 1)
            self.assertEqual(
                [case["selection_basis"] for case in result["selected_cases"]],
                ["FIRST_SEQUENTIAL_OPERATIONAL_fault_01", "FIRST_SEQUENTIAL_OPERATIONAL_fault_05"],
            )
            report = (root / "additional_experiments_report.md").read_text(encoding="utf-8")
            self.assertIn("### RQ3", report)
            self.assertIn("Question:", report)
            self.assertIn("Observed evidence:", report)
            self.assertNotIn("See the registered tables", report)
            self.assertIn("configuration-level marginal effects", report)

    @staticmethod
    def _csv(path: Path, rows: list[dict]) -> None:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
