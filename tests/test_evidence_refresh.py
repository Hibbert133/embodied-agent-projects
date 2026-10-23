from dataclasses import replace
import json
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.autoresearch import RecoveryPolicyConfig
from src.probemem.evidence_refresh import (METHODS, Measurement, CachedEvidence, decide,
                                           plan_from_samples, accepted_update)
from scripts.run_evidence_refresh import CONFIG, units, summarize
from scripts import run_evidence_refresh as runner

ROOT = Path(__file__).resolve().parents[1]


def sample(x=.145, y=0):
    return Measurement((x * .01, y * .01), (.01, .01), 0.)


class RefreshPolicyTest(unittest.TestCase):
    def setUp(self):
        self.recovery = RecoveryPolicyConfig.from_mapping(json.loads(
            (ROOT / "configs/autoresearch/default_recovery_config.json").read_text()))
        self.plan = plan_from_samples([sample()], self.recovery, "prior")

    def cache(self, owner="DECISION_STABILITY"):
        return CachedEvidence(owner, 0, 0, 1, self.plan, sample())

    def decision(self, method="DECISION_STABILITY", values=None, cache=True, episode=1, budget=564):
        values = values or [sample()] * 4
        calls = []

        def read():
            calls.append(len(calls))
            return values[len(calls) - 1]

        d = decide(method, read, cache=self.cache(method) if cache else None,
                   recovery=self.recovery, stream=0, episode=episode,
                   decision_sequence=10, remaining_budget=budget)
        self.assertEqual(len(calls), d.repetitions)
        return d

    def test_bootstrap_and_fixed_prefixes(self):
        self.assertEqual(self.decision(cache=False).repetitions, 4)
        for method, count in (("FIXED_16", 1), ("FIXED_32", 2), ("FIXED_64", 4), ("UNCORRECTED", 0)):
            self.assertEqual(self.decision(method, cache=False).repetitions, count)

    def test_agreement_stops_before_any_future_suffix_read(self):
        d = self.decision(values=[sample()])  # would IndexError if a suffix were read
        self.assertEqual(d.repetitions, 1)
        self.assertEqual(d.reason, "CURRENT_ACTION_MATCHES_CACHE")

    def test_changed_action_requires_stability_and_can_stop_at_two(self):
        d = self.decision(values=[sample(0, -.198), sample(0, -.198)])
        self.assertEqual(d.repetitions, 2)
        self.assertEqual(d.reason, "LEAVE_ONE_OUT_ACTION_STABLE")
        self.assertNotEqual(d.plan.execution_signature(), self.plan.execution_signature())

    def test_budget_reserves_full_task_execution(self):
        with self.assertRaisesRegex(ValueError, "budget"):
            self.decision("FIXED_32", cache=False, budget=531)
        self.assertEqual(self.decision("FIXED_32", cache=False, budget=532).repetitions, 2)

    def test_cache_chronology_and_ownership_fail_closed(self):
        for cache in (replace(self.cache(), owner="STALE"), replace(self.cache(), stream=1),
                      replace(self.cache(), episode=2), replace(self.cache(), available_sequence=10)):
            with self.assertRaisesRegex(ValueError, "cache"):
                decide("DECISION_STABILITY", lambda: sample(), cache=cache, recovery=self.recovery,
                       stream=0, episode=1, decision_sequence=10)

    def test_exact_schema_rejects_nested_oracle_and_nonfinite_input(self):
        valid = {"estimated_drift_per_step": [.00145, 0], "axis_response_gain": [.01, .01], "residual": 0}
        for bad in (dict(valid, oracle={"fault_axis": "x"}),
                    dict(valid, residual=float("nan")), dict(valid, axis_response_gain=[0, .01]),
                    dict(valid, residual=True)):
            with self.assertRaises(ValueError):
                Measurement.from_mapping(bad)

    def test_periodic_and_threshold_baselines(self):
        self.assertEqual(self.decision("PERIODIC_4", episode=4).repetitions, 4)
        self.assertEqual(self.decision("PERIODIC_4", episode=5).repetitions, 0)
        self.assertEqual(self.decision("STALE").repetitions, 0)
        d = self.decision("CHANGE_THRESHOLD", values=[sample(.16)])
        self.assertEqual(d.plan, self.plan)
        self.assertEqual(d.repetitions, 1)
        self.assertEqual(self.decision("CHANGE_THRESHOLD", values=[sample(-.18)] * 4).repetitions, 4)

    def test_only_accepted_actual_current_measurements_update_cache(self):
        d = self.decision()
        old = self.cache()
        for status in ("REJECTED", "INCONCLUSIVE"):
            self.assertIs(accepted_update(d, old, stream=0, episode=1, outcome_sequence=11, status=status), old)
        updated = accepted_update(d, old, stream=0, episode=1, outcome_sequence=11, status="ACCEPTED")
        self.assertEqual(updated.episode, 1)
        self.assertEqual(updated.available_sequence, 11)
        stale = self.decision("STALE")
        self.assertIs(accepted_update(stale, old, stream=0, episode=1, outcome_sequence=11, status="ACCEPTED"), old)

    def test_complete_execution_signature_includes_quantized_parameters(self):
        # Same discrete skill is insufficient: these require different correction magnitudes.
        different = plan_from_samples([sample(.198)], self.recovery, "different")
        self.assertEqual(self.plan.skill_id, different.skill_id)
        self.assertNotEqual(self.plan.execution_signature(), different.execution_signature())


class RefreshDesignTest(unittest.TestCase):
    def test_independent_task_seeds_and_balanced_streams(self):
        c = json.loads(CONFIG.read_text())
        design = units(c)
        self.assertEqual([u["seed"] for u in design], list(range(8200, 8296)))
        for stream in range(8):
            contexts = [u["context_id_oracle"] for u in design if u["stream"] == stream]
            self.assertEqual(len(set(contexts)), 1 if stream < 4 else 4)
        self.assertEqual(c["maximum_physical_steps"], 96 * (64 + 8 * 500))

    def test_cheap_equal_success_baseline_blocks_promotion(self):
        c = json.loads(CONFIG.read_text())
        c["bootstrap_samples"] = 100
        rows = [{**u, "method": m, "success": True, "steps": 100,
                 "probe_steps": 64 if m == "FIXED_64" else 16 if m == "FIXED_16" else 32}
                for u in units(c) for m in METHODS]
        result = summarize(rows, c)
        self.assertTrue(result["performance_gates"]["success_tolerance"])
        self.assertTrue(result["performance_gates"]["probe_saving"])
        self.assertFalse(result["performance_gate_passed"])
        self.assertIn("FIXED_16", result["dominating_baselines"])
        with self.assertRaisesRegex(ValueError, "incomplete"):
            summarize(rows[:-1], c)

    def test_complete_mocked_stream_has_causal_decisions_and_isolated_cache(self):
        config = json.loads(CONFIG.read_text())
        config["bootstrap_samples"] = 100
        manifest = {"config": config, "units": units(config), "input_sha256": {},
                    "source_git_commit": "test", "experiment_run_id": "synthetic"}
        manifest["manifest_id"] = runner.manifest_digest(manifest)
        env = SimpleNamespace(reset=lambda **kw: (np.zeros(39), {}), close=lambda: None)
        transition = SimpleNamespace(steps=4, start_gripper_position=(0, 0, 0), to_dict=lambda: {})
        estimate = SimpleNamespace(to_dict=lambda: {"estimated_drift_per_step": (.00145, 0.),
                                    "axis_response_gain": (.01, .01), "residual": 0.})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest))

            def execute(**kwargs):
                records = [json.loads(x) for x in (path.parent / "decisions.jsonl").read_text().splitlines()]
                self.assertEqual(len([r for r in records if r["seed"] == kwargs["seed"]]), 8)
                return {"success": True, "steps": 10, "verification_status": "ACCEPTED",
                        "initial_state_hash": kwargs["expected_initial_hash"]}

            with patch.object(runner, "check_clean"), patch.object(runner, "git", return_value="test"), \
                 patch.object(runner, "create_push_environment", return_value=env), \
                 patch.object(runner, "run_symmetric_probes", return_value=[transition] * 4), \
                 patch.object(runner, "estimate_planar_bias", return_value=estimate), \
                 patch.object(runner, "_execute", side_effect=execute) as physical, patch("builtins.print"):
                runner.run(path)
                self.assertEqual(physical.call_count, 192)  # one shared correction and control per episode
                with self.assertRaises(FileExistsError):
                    runner.run(path)
            decisions = [json.loads(x) for x in (path.parent / "decisions.jsonl").read_text().splitlines()]
            self.assertEqual(len(decisions), 768)
            for row in decisions:
                cache = row["cache_before"]
                if row["episode"] == 0:
                    self.assertIsNone(cache)
                if cache:
                    self.assertEqual(cache["owner"], row["decision"]["method"])
                    self.assertEqual(cache["stream"], row["stream"])
                    self.assertLess(cache["episode"], row["episode"])
                self.assertEqual(len(row["consumed_measurements"]), row["decision"]["repetitions"])
            status = json.loads((path.parent / "status.json").read_text())
            self.assertEqual(status["complete_episodes"], 96)
            self.assertEqual(status["status"], "COMPLETED_FEASIBILITY_FAILED")


if __name__ == "__main__":
    unittest.main()
