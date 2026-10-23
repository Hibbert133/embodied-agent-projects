from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from scripts import run_cold_start_evidence as run
from scripts.audit_cold_start_evidence import verify_terminal
from src.analysis.cold_start_evidence import fit_training, estimates, statistics
from src.probe.cold_start_response import ColdPrefix, TASKS, MODELS
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_acquisition_value import FakeEnv, FakeSimulator
from tests.test_cold_start_response import trained, prefix


class ColdStartEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        def emit(kind, payload):
            item = {"event": kind, "sequence": len(self.events)+1, "saved_ns": run.perf_counter_ns(), **run.normal(payload)}
            self.events.append(item); return item
        self.emit = emit; self.ledger = LifecycleLedger(emit, 1000000)
        self.factory = SimpleNamespace(_make_tasks=lambda: None)
        self.key = dict(split="QUALIFY", case_id="qual_00_0_0", task="push-v3", seed=13800, stream=0, replicate=0)
        self.operator = {"matrix_xy": [[.8, .1], [0, 1.1]], "bias_xy": [.1, -.08]}

    @contextmanager
    def fixtures(self, env):
        witness = lambda e: {"fixture": True, "time": e.data.time, "observation": e.observation.tolist()}
        with self.ledger.instrument(FakeEnv, FakeSimulator, self.factory), patch.object(run, "create_task_environment", return_value=env), patch.object(run.prior, "physics_witness", side_effect=witness):
            yield

    def test_actual_prefix_is_saved_before_eight_continuous_steps_with_one_reset(self):
        env = FakeEnv()
        with self.fixtures(env): record = run.collect(self.key, self.operator, self.emit, self.ledger)
        self.assertEqual((record["total_steps"], record["environment_resets"]), (8, 1))
        self.assertTrue(record["completed_eight"]); self.assertTrue(env.closed)
        self.assertEqual(self.events[0]["event"], "PROGRAM_SAVED")
        noise = run.noise(self.key); commands = run.program(self.key)
        for i, row in enumerate(record["trace"]):
            actual = commands[i].copy()
            actual[:2] = np.asarray(self.operator["matrix_xy"], np.float32) @ actual[:2]+np.asarray(self.operator["bias_xy"], np.float32)
            actual[:3] += noise[i]
            np.testing.assert_array_equal(row["executed_action_oracle"], np.clip(actual, -1, 1))
            self.assertLess(row["intent_saved_ns"], row["execution_started_ns"])
            if i: self.assertEqual(row["before"], record["trace"][i-1]["after"])
        self.assertEqual(self.ledger.snapshot()["by_phase"]["CONTROL"]["simulation_completed"], 8)
        self.assertEqual(self.ledger.snapshot()["counts"]["reset_completed"], 1)

    def test_early_terminal_retains_short_prefix_without_substitution(self):
        env = FakeEnv(); original = env.step
        def step(action):
            obs, reward, terminal, truncated, info = original(action)
            return obs, reward, terminal, truncated, {"success": env.calls >= 2}
        with self.fixtures(env), patch.object(env, "step", side_effect=step):
            record = run.collect(self.key, self.operator, self.emit, self.ledger)
        self.assertEqual(record["total_steps"], 2); self.assertFalse(record["completed_eight"])
        result = estimates({}, {}, run.visible_prefix(record))
        self.assertEqual(set(result), set(MODELS)); self.assertTrue(all(not r["valid"] for r in result.values()))

    def test_partial_exception_preserves_completed_physical_cost_and_closes_env(self):
        env = FakeEnv(); original = env.step
        def step(action):
            value = original(action)
            if env.calls == 3: raise RuntimeError("fixture after physical step")
            return value
        with self.fixtures(env), patch.object(env, "step", side_effect=step), self.assertRaises(RuntimeError) as caught:
            run.collect(self.key, self.operator, self.emit, self.ledger)
        partial = caught.exception.partial_record
        self.assertEqual(len(partial["trace"]), 2)
        self.assertEqual(partial["ledger_after"]["by_phase"]["CONTROL"]["simulation_completed"], 3)
        self.assertTrue(env.closed)

    def test_training_only_pipeline_handles_all_tasks_and_four_visible_estimators(self):
        _, samples = trained(); records = []
        for i, sample in enumerate(samples):
            for task in TASKS:
                p = asdict(sample.prefix); p["task"] = task; p = ColdPrefix.from_dict(p)
                records.append({"split": "TRAIN", "case_id": f"{i}_{task}", "task": task,
                                "initial": {"observation": p.initial_observation},
                                "trace": [{"command": u, "after": {"observation": o}} for u, o in zip(p.commands, p.observations)]})
        models = fit_training(records)
        for task in TASKS:
            self.assertEqual(models["same_data_arx"][task]["training_samples"], 768)
            p = asdict(prefix(run.program(self.key), [[.8, -.2], [.1, 1.2]], [.07, -.05])); p["task"] = task
            result = estimates(models, models["same_data_arx"], ColdPrefix.from_dict(p))
            self.assertEqual(set(result), set(MODELS)); self.assertTrue(result["JOINT_FULL8"]["valid"])
            self.assertEqual(result["SAME_DATA_ARX8"], result["OLD_ARX8"])
        records[0]["split"] = "QUALIFY"
        with self.assertRaises(ValueError): fit_training(records)

    def test_registration_and_independent_prefix_noise_keep_reserved_seeds(self):
        c = json.loads(run.CONFIG.read_text(encoding="utf-8")); run.validate(c)
        train = run.population(c, "TRAIN"); qual = run.population(c, "QUALIFY")
        self.assertEqual({r["seed"] for r in train}, set(range(14000, 14384)))
        self.assertEqual({r["seed"] for r in qual}, set(range(13800, 13848)))
        self.assertEqual(len(qual), 96); self.assertEqual(len(run.operators(c)), 16)
        self.assertFalse(np.array_equal(run.noise(self.key), run.noise({**self.key, "replicate": 1})))
        np.testing.assert_array_equal(run.program(self.key), run.program({**self.key, "replicate": 1}))
        for change in ({"api_calls": 1}, {"qualification_seed_start": 13448}):
            with self.assertRaises(ValueError): run.validate({**c, **change})

    def test_invalid_estimates_retain_all_denominators_and_failed_gate(self):
        rows = []
        for s in range(16):
            for t in TASKS:
                for f in range(2):
                    rows.append(dict(stream=s, task=t, replicate=f, operator_oracle={"matrix_xy": np.eye(2).tolist(), "bias_xy": [0., 0.]},
                                     estimates={k: dict(valid=True, matrix_xy=np.eye(2).tolist(), bias_xy=[0., 0.]) for k in MODELS}))
        rows[0]["estimates"]["JOINT_FULL8"] = {"valid": False}
        result = statistics(rows, {})
        self.assertEqual(result["models"]["JOINT_FULL8"]["cases"], 96)
        self.assertEqual(result["models"]["JOINT_FULL8"]["valid"], 95)
        self.assertAlmostEqual(result["models"]["JOINT_FULL8"]["mean_score"], 10.5/96)
        self.assertFalse(result["qualification"]["passed"])
        with self.assertRaises(ValueError): statistics(rows[:-1], {})

    def test_terminal_audit_rejects_budget_cost_scope_and_status_tampering(self):
        identity = dict(experiment_run_id="unit", manifest_id="unit", source_git_commit="unit")
        lifecycle = dict(counts=dict(reset_completed=480, simulation_frames_completed=259200),
                         by_phase=dict(CONTROL=dict(simulation_completed=3840), CONTROLLED_RESET=dict(reset_completed=480)))
        status = {**identity, "status": "COMPLETED_COMPONENT_FAILED", "training_episodes": 384, "qualification_episodes": 96,
                  "controlled_steps": 3840, "controlled_resets": 480, "api_calls": 0, "task_policy_executions": 0,
                  "memory_writes": 0, "lifecycle": lifecycle}
        summary = {**status, "models_sha256": "unit", "statistics": dict(qualification=dict(passed=False),
                   task_performance_established=False, probability_qualification=False, algorithm_novelty_established=False)}
        verify_terminal(summary, status, identity, lifecycle, 3840, "unit")
        for field, value in (("status", "COMPLETED_COMPONENT_PASSED"), ("api_calls", 1), ("controlled_steps", 3841)):
            altered = {**status, field: value}
            with self.assertRaises(ValueError): verify_terminal({**summary, field: value}, altered, identity, lifecycle, 3840, "unit")
        changed = deepcopy(summary); changed["statistics"]["probability_qualification"] = True
        with self.assertRaises(ValueError): verify_terminal(changed, status, identity, lifecycle, 3840, "unit")


if __name__ == "__main__": unittest.main()
