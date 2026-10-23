from contextlib import contextmanager
import copy
from time import perf_counter_ns
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from collections import deque
import numpy as np
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout import strong_reference_execution_v1 as host
from tests.test_operator_identification import model
from tests.test_passive_supported_reference_v1 import prior
from scripts.audit_strong_chronological_reference_v1 import verify_new
from scripts.audit_acquisition_value_v3 import JournalAudit
from src.probe.chronological_cache_reference import VerifiedPoint


def run_fixture(*, use_cache=False, bad_reset=False):
    events = []
    def emit(kind, payload):
        value = {"event": kind, "sequence": len(events)+1, "saved_ns": perf_counter_ns(), **copy.deepcopy(payload)}
        events.append(value)
        return value
    ledger = LifecycleLedger(emit, 2000000)
    class Env:
        def __init__(self):
            self.unwrapped = self
            self.model = SimpleNamespace(opt=SimpleNamespace(timestep=.0025))
            self.data = SimpleNamespace(time=0.)
            self.frame_skip = 5
            self.bad_reset = bad_reset
        def do_simulation(self, ctrl, n_frames): self.data.time += .0025*n_frames
        def reset(self, **kwargs):
            self.calls, self.position, self.velocity = 0, np.zeros(39), np.zeros(3)
            self.data.time = 0.
            for _ in range(100): self.do_simulation([0.]*4, 5)
            return self.position.copy(), {}
        def step(self, action):
            if self.bad_reset and self.calls == 8:
                self.bad_reset = False
                self.reset()
            self.do_simulation(action, 5)
            self.calls += 1
            self.velocity = .5*self.velocity+.006*np.array(action[:3])
            self.position[:3] += self.velocity
            return self.position.copy(), 0., False, False, {"success": self.calls == 26}
        def close(self): pass
    factory = SimpleNamespace(_make_tasks=lambda: None)
    def make_tasks():
        env = Env()
        for _ in range(50): env.reset()
        return env
    factory._make_tasks = make_tasks
    key = {"experiment_run_id": "test", "manifest_id": "test", "source_git_commit": "test", "phase": "SMOKE", "stream": 0,
           "episode": 1 if use_cache else 0, "seed": 18000, "task": "push-v3", "method": "PASSIVE8_KEEP"}
    fault = {"matrix_xy": np.eye(2).tolist(), "bias_xy": [.12, -.08], "deadzone_xy": [0., 0.]}
    state = {"cache": prior().point if use_cache else None, "cusum": 0.}
    policy = SimpleNamespace(get_action=lambda observation: np.array([.2, .1, 0., 0.]))
    witness = lambda env: {"state_spec": 0, "integration": [env.data.time], "body_pos": [], "site_pos": [], "task_fields": {}, "complete_hidden_state_qualification": False}
    with ledger.instrument(Env, Env, factory), patch.object(host, "create_task_environment", side_effect=lambda task, seed: factory._make_tasks()), patch.object(host, "create_task_policy", return_value=policy), patch.object(host.prior, "physics_witness", side_effect=witness):
        record = host.execute(key, fault, state, model("LINEAR_ARX"), None, (), emit, ledger)
    return record, state, events, ledger.snapshot()


class StrongReferencePhysicalHostTest(unittest.TestCase):
    def test_independent_physical_audit_reconstructs_private_noise_and_rejects_tampering(self):
        record, _, events, _ = run_fixture(use_cache=True)
        journal = JournalAudit({})
        business = deque()
        for event in events:
            item = journal.accept(event)
            if item is not None: business.append(item)
        def audit(part):
            state = {"cache": VerifiedPoint.from_dict(part["state_before"]["cache"]), "cusum": 0.}
            fault = {"matrix_xy": np.eye(2).tolist(), "bias_xy": [.12, -.08], "deadzone_xy": [0., 0.]}
            policy = SimpleNamespace(get_action=lambda observation: np.array([.2, .1, 0., 0.]))
            with patch("scripts.audit_strong_chronological_reference_v1.create_task_policy", return_value=policy):
                verify_new(part, model("LINEAR_ARX"), None, fault, state, (), copy.deepcopy(business), .0125)
        audit(record)
        for kind in ("noise", "cache", "time"):
            changed = copy.deepcopy(record)
            if kind == "noise": changed["trace"][8]["noise_after_hash"] = "rewound"
            elif kind == "cache": changed["state_after"]["cache"]["source_episode"] = 1
            else: changed["trace"][8]["simulation_time_before_oracle"] += .1
            with self.subTest(kind=kind), self.assertRaises(ValueError): audit(changed)

    def test_actual_callback_host_preserves_frames_noise_and_single_controlled_reset(self):
        record, state, events, ledger = run_fixture()
        self.assertEqual(record["outcome"]["total_steps"], 26)
        self.assertEqual(record["outcome"]["noise_rows_consumed"], 26)
        self.assertEqual(record["outcome"]["environment_resets"], 1)
        self.assertEqual(ledger["by_phase"]["GOAL_GENERATION"]["reset_completed"], 50)
        self.assertEqual(ledger["by_phase"]["CONTROLLED_RESET"]["reset_completed"], 1)
        self.assertEqual(ledger["by_phase"]["CONTROL"]["simulation_frames_completed"], 26*5)
        self.assertEqual(ledger["counts"]["simulation_frames_completed"], 51*500+26*5)
        self.assertEqual(record["decisions"][-1]["action"], "REJECT_UPDATE_KEEP")
        self.assertIsNone(state["cache"])
        for row in record["trace"]:
            self.assertLess(row["intent_saved_ns"], row["execution_started_ns"])
            self.assertAlmostEqual(row["simulation_time_after_oracle"]-row["simulation_time_before_oracle"], .0125)
            self.assertEqual(row["command"], np.array([.2, .1, 0., 0.], np.float32).astype(float).tolist())
        self.assertGreater(record["cache_event"]["saved_ns"], record["trace"][-1]["completed_ns"])

    def test_actual_cache_source_is_not_renewed_after_a_rejected_update(self):
        record, state, _, _ = run_fixture(use_cache=True)
        self.assertEqual(state["cache"].source_episode, 0)
        self.assertEqual(record["state_after"], record["state_before"])
        self.assertEqual(record["decisions"][-1]["action"], "REJECT_UPDATE_KEEP")

    def test_reset_inside_physical_execution_is_rejected_and_preserved(self):
        with self.assertRaises(host.prior.BranchFailure) as error: run_fixture(bad_reset=True)
        self.assertEqual(error.exception.record["completed_steps"], 9)
        self.assertIn("no-reset clock", error.exception.record["error"])
        self.assertEqual(error.exception.record["ledger_after"]["by_phase"]["CONTROL"]["reset_completed"], 1)


if __name__ == "__main__": unittest.main()
