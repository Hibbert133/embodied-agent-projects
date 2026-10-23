import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
from types import SimpleNamespace

import numpy as np

from src.probemem.evidence_persistence import CONDITIONS, METHODS, summarize_crossed
from scripts.run_evidence_persistence import validate_config, manifest_digest
from scripts import run_evidence_persistence as runner


def fixture(seeds=(8000, 8001)):
    return [{"seed": k, "source_context_oracle": s, "target_context_oracle": t,
             "method": m, "success": m == "PROBE_COMPENSATION" and s == t}
            for k in seeds for s in CONDITIONS for t in CONDITIONS for m in METHODS]


class EvidencePersistenceTest(unittest.TestCase):
    def test_crossed_design_keeps_diagonal_in_independent_estimator(self):
        result = summarize_crossed(fixture(), [8000, 8001], samples=100)
        self.assertEqual(result["task_clusters"], 2)
        self.assertEqual(result["logical_rows"], 64)
        self.assertEqual(result["means"]["interaction"], .75)
        self.assertEqual(result["means"]["PROBE_COMPENSATION_independent"], .25)
        self.assertEqual(result["interaction_cluster_bootstrap_95"], [.75, .75])

    def test_context_independent_policy_has_zero_interaction(self):
        rows = fixture()
        for row in rows:
            row["success"] = row["target_context_oracle"] == "fault_01"
        result = summarize_crossed(rows, [8000, 8001], samples=100)
        self.assertEqual(result["means"]["interaction"], 0)

    def test_cluster_bootstrap_does_not_treat_context_rows_as_independent(self):
        rows = fixture()
        for row in rows:
            if row["seed"] == 8001:
                row["success"] = False
        result = summarize_crossed(rows, [8000, 8001], samples=2000)
        self.assertEqual(result["means"]["interaction"], .375)
        self.assertEqual(result["interaction_cluster_bootstrap_95"], [0, .75])

    def test_negative_control_source_dependence_fails_closed(self):
        rows = fixture()
        rows[1]["success"] = True
        with self.assertRaisesRegex(ValueError, "negative control"):
            summarize_crossed(rows, [8000, 8001])

    def test_incomplete_duplicate_unknown_and_nonboolean_rejected(self):
        rows = fixture()
        variants = [rows[:-1], rows + [copy.deepcopy(rows[0])]]
        unknown = copy.deepcopy(rows)
        unknown[0]["seed"] = 8999
        variants.append(unknown)
        invalid = copy.deepcopy(rows)
        invalid[0]["success"] = "False"
        variants.append(invalid)
        for case in variants:
            with self.assertRaises(ValueError):
                summarize_crossed(case, [8000, 8001])

    def test_frozen_config_refuses_population_budget_or_scope_change(self):
        path = Path(__file__).resolve().parents[1] / "configs/evidence_persistence/development_v1.json"
        config = json.loads(path.read_text())
        validate_config(config)
        for key, value in (("seed_start", 8016), ("num_seeds", 17), ("case_max_steps", 565),
                           ("api_calls", 1), ("memory_writes", 1), ("all_states_included", False)):
            modified = dict(config, **{key: value})
            with self.assertRaises(ValueError):
                validate_config(modified)

    def test_manifest_hash_binds_settings_but_excludes_its_own_id(self):
        manifest = {"config": {"seed_start": 8000}, "source_git_commit": "x"}
        original = manifest_digest(manifest)
        manifest["manifest_id"] = original
        self.assertEqual(original, manifest_digest(manifest))
        manifest["config"]["seed_start"] = 8001
        self.assertNotEqual(original, manifest_digest(manifest))

    def test_runner_journals_before_outcomes_and_deduplicates_only_control(self):
        config = json.loads(runner.CONFIG.read_text())
        manifest = {"config": config, "source_git_commit": "test", "experiment_run_id": "synthetic",
                    "input_sha256": {}}
        manifest["manifest_id"] = manifest_digest(manifest)
        environment = SimpleNamespace(reset=lambda **kw: (np.zeros(39), {}), close=lambda: None)
        probe = {"probe_environment_steps": 64,
                 "repetitions": [{"transitions": [{"start_gripper_position": [0, 0, 0]}]}]}
        plan = SimpleNamespace(requires_fresh_verification=True, to_dict=lambda: {"test_plan": True})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest))

            def execute(**kwargs):
                decisions = [json.loads(line) for line in (path.parent / "decisions.jsonl").read_text().splitlines()]
                current = [r for r in decisions if r["seed"] == kwargs["seed"]]
                self.assertEqual(len(current), 5)  # all four source plans and control exist first
                return {"success": True, "steps": 1, "initial_state_hash": kwargs["expected_initial_hash"]}

            with patch.object(runner, "check_clean"), patch.object(runner, "git", return_value="test"), \
                 patch.object(runner, "create_push_environment", return_value=environment), \
                 patch.object(runner, "_build_probe_context", return_value=probe), \
                 patch.object(runner, "_plan", return_value=plan), \
                 patch.object(runner, "_execute", side_effect=execute) as physical, \
                 patch("builtins.print"):
                runner.run(path)
                self.assertEqual(physical.call_count, 320)
                with self.assertRaises(FileExistsError):
                    runner.run(path)
            rows = [json.loads(line) for line in (path.parent / "outcomes.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 512)
            self.assertEqual(sum(r["reused"] for r in rows), 192)
            self.assertTrue(all(r["decision_sequence"] < r["sequence"] for r in rows))
            status = json.loads((path.parent / "status.json").read_text())
            self.assertEqual(status["status"], "COMPLETED_FEASIBILITY_FAILED")
            self.assertEqual(status["complete_seeds"], list(range(8000, 8016)))


if __name__ == "__main__":
    unittest.main()
