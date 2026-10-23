"""Tampering tests for the independent chronological prefix audit."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from scripts import run_evidence_refresh as runner
from scripts.analyze_evidence_refresh import read_rows, verify_and_replay
from src.autoresearch import RecoveryPolicyConfig
from src.probe.directional import PROBE_DIRECTIONS, ProbeResult

ROOT = Path(__file__).resolve().parents[1]


class EvidenceRefreshAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = json.loads((ROOT / "configs/evidence_refresh/development_v1.json").read_text())
        config["bootstrap_samples"] = 10
        cls.manifest = {"config": config, "units": runner.units(config), "input_sha256": {},
                        "source_git_commit": "test", "experiment_run_id": "synthetic"}
        cls.manifest["manifest_id"] = runner.manifest_digest(cls.manifest)
        cls.recovery = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / config["recovery_config"]).read_text()))
        env = SimpleNamespace(reset=lambda **kw: (np.zeros(39), {}), close=lambda: None)

        def probes(*args, seed, **kwargs):
            result = []
            for direction, vector in PROBE_DIRECTIONS:
                displacement = (.0058 + .008 * float(vector[0]), .008 * float(vector[1]), 0.)
                result.append(ProbeResult(seed, direction, tuple(float(x) for x in .2 * vector), 4, (0., 0., 0.),
                                          displacement, displacement, .2, 0.))
            return result

        def execute(**kwargs):
            return {"success": True, "steps": 10, "verification_status": "ACCEPTED",
                    "initial_state_hash": kwargs["expected_initial_hash"]}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(cls.manifest))
            with patch.object(runner, "check_clean"), patch.object(runner, "git", return_value="test"), \
                 patch.object(runner, "create_push_environment", return_value=env), \
                 patch.object(runner, "run_symmetric_probes", side_effect=probes), \
                 patch.object(runner, "_execute", side_effect=execute), patch("builtins.print"):
                runner.run(path)
            cls.records = [read_rows(path.parent / name) for name in
                           ("evaluator_probes.jsonl", "decisions.jsonl", "outcomes.jsonl", "cache_writes.jsonl")]

    def audit(self, records=None):
        return verify_and_replay(self.manifest, *(records or self.records), self.recovery)

    def test_replays_all_prefixes_and_physical_cost(self):
        result = self.audit()
        self.assertEqual(result["replayed_decisions"], 768)
        self.assertEqual(result["physical_task_rollouts"], 192)
        self.assertEqual(result["physical_task_steps"], 1920)
        self.assertEqual(result["physical_probe_steps"], 6144)

    def test_rejects_uncharged_suffix(self):
        rows = copy.deepcopy(self.records)
        rows[1][0]["consumed_measurements"] = []
        with self.assertRaisesRegex(ValueError, "uncharged suffix"):
            self.audit(rows)

    def test_rejects_cross_method_cache(self):
        rows = copy.deepcopy(self.records)
        target = next(r for r in rows[1] if r["cache_before"])
        target["cache_before"]["owner"] = "FIXED_64"
        with self.assertRaisesRegex(ValueError, "prior selected accepted"):
            self.audit(rows)

    def test_rejects_current_outcome_before_all_decisions(self):
        rows = copy.deepcopy(self.records)
        rows[1][7]["sequence"], rows[2][0]["sequence"] = rows[2][0]["sequence"], rows[1][7]["sequence"]
        with self.assertRaisesRegex(ValueError, "precede"):
            self.audit(rows)

    def test_rejects_unreproducible_probe_inference(self):
        rows = copy.deepcopy(self.records)
        rows[0][0]["repetitions"][0]["inference"]["residual"] += 1
        with self.assertRaisesRegex(ValueError, "inference"):
            self.audit(rows)

    def test_rejects_forged_shared_outcome(self):
        rows = copy.deepcopy(self.records)
        target = next(r for r in rows[2] if r["reused_branch"])
        target["steps"] += 1
        with self.assertRaisesRegex(ValueError, "shared branch"):
            self.audit(rows)

    def test_rejects_cost_and_missing_cache_write(self):
        rows = copy.deepcopy(self.records)
        rows[2][0]["probe_steps"] = 0
        with self.assertRaisesRegex(ValueError, "budget"):
            self.audit(rows)
        rows = copy.deepcopy(self.records)
        rows[3].pop()
        with self.assertRaisesRegex(ValueError, "cache write log"):
            self.audit(rows)


if __name__ == "__main__":
    unittest.main()
