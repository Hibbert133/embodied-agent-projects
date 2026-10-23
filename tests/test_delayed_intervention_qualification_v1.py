"""Collector/auditor tests with tiny native physics, no MetaWorld population.

The factory/reset lifecycle is actually executed; policy and fit identities are
explicit stubs. Every fixture records actual native requested frames separately.
Mutation replays do not rerun physics. Qualification gate results are synthetic.
"""

from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
import io as textio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mujoco
import numpy as np

from scripts import qualify_delayed_intervention_v1 as collector
from scripts import audit_delayed_intervention_v1 as audit
import boundary_prefix
from src.analysis import delayed_qualification_io_v1 as contract
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit


FIXTURE_RECEIPTS = []
FIXTURE_PACKETS = []
PIPELINE_RECEIPTS = []


def packet(variant, *, finish=24, ending="success", invalid=None, failure_step=None):
    events = [];saved_events = {};journal = JsonJournal(textio.StringIO(), {
        "experiment_run_id": "DELAYED_TINY_SOFTWARE_ONLY", "manifest_id": "DELAYED_TINY_SOFTWARE_ONLY", "source_git_commit": "SOFTWARE_FIXTURE"})
    key = {"unit": 0, "task": "push-v3", "seed": 700021, "variant": variant}
    identity = {**journal.identity, **key}
    def emit(kind, payload):
        value = journal.emit(kind, {**key, **payload});events.append(deepcopy(value))
        if kind == "AGENT_EVENT": saved_events[value["sequence"]] = deepcopy(value)
        return value
    ledger = LifecycleLedger(emit, 1000000);budget = {"completed": 0, "maximum": 500}
    config = contract.read(contract.CONFIG);env = TinyEnv();frames = queries = 0
    original_simulation = TinyEnv.do_simulation;original_step = TinyEnv.step;original_query = TinyPolicy.get_action
    original_native = mujoco.mj_step
    def native(*args, **kwargs):
        nonlocal frames
        result = original_native(*args, **kwargs)
        frames += int(kwargs.get("nstep", args[2] if len(args) > 2 else 1))
        return result
    def simulate(current, ctrl, n_frames):
        return ledger.simulation_call(original_simulation, current, ctrl, n_frames)
    def reset_body(current, **kwargs):
        mujoco.mj_resetData(current.model, current.data);current.calls = 0
        for _ in range(100): current.do_simulation([0.], 5)
        return np.zeros(39), {}
    def reset(current, **kwargs):
        return ledger.reset_call(reset_body, current, **kwargs)
    def factory(task, seed):
        with ledger.scope("GOAL_GENERATION"):
            for _ in range(50): env.reset()
        return env
    def step(current, action):
        value, reward, _, _, _ = original_step(current, action)
        if current.calls == failure_step: raise RuntimeError("INJECTED_AFTER_NATIVE_STEP")
        done = current.calls >= finish
        return value, reward, done and ending == "terminated", done and ending == "truncated", {"success": done and ending == "success"}
    def query(current, observation):
        nonlocal queries
        queries += 1;return original_query(current, observation)
    four = fit((.1, -.05));eight = fit((-.08, .12), nfev=2)
    if invalid == 4: four = {"valid": False, "nfev": 3, "reason": "SOFTWARE_INVALID_FOUR"}
    if invalid == 8: eight = {"valid": False, "nfev": 4, "reason": "SOFTWARE_INVALID_EIGHT"}
    error = None
    try:
        with ExitStack() as stack:
            for owner, name, replacement in ((mujoco, "mj_step", native), (TinyEnv, "do_simulation", simulate),
                    (TinyEnv, "reset", reset), (TinyEnv, "step", step), (TinyPolicy, "get_action", query),
                    (collector, "create_task_environment", factory), (collector, "create_task_policy", lambda task: TinyPolicy())):
                stack.enter_context(patch.object(owner, name, replacement))
            stack.enter_context(patch.object(boundary_prefix, "infer_four", return_value=four))
            stack.enter_context(patch.object(boundary_prefix, "infer_operator", return_value=eight))
            try:
                row = collector.execute_one(identity, config, model(), emit, ledger, budget, saved_events)
            except collector.CollectionFailure as failure:
                error = failure;row = failure.record
    finally:
        env.close()
    value = {"events": events, "record": row, "identity": identity, "four": four, "eight": eight, "error": error,
             "ledger": ledger.snapshot(), "native_frames": frames, "actual_policy_calls": queries, "budget": budget}
    FIXTURE_RECEIPTS.append({"variant": variant, "finish": finish, "ending": ending, "invalid": invalid,
        "failure_step": failure_step, "native_frames": frames, "actual_policy_calls": queries,
        "ledger": ledger.snapshot(), "host_attempts": row["host_attempts"], "host_returned": row["host_returned"],
        "captures": row["captures"], "restores": row["restores"]})
    FIXTURE_PACKETS.append({k: deepcopy(v) for k, v in value.items() if k != "error"})
    return value


def replay(value):
    with patch.object(audit, "create_task_policy", return_value=TinyPolicy()), patch.object(
            audit, "infer_four", return_value=value["four"]), patch.object(audit, "infer_operator", return_value=value["eight"]):
        return audit.audit_case(value["events"], value["record"], value["identity"],
                                contract.read(contract.CONFIG)["fault_oracle"], model())


class DelayedQualificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packets = {v: packet(v) for v in contract.VARIANTS}
        cls.invalid = [packet("CONTINUE_CURRENT", invalid=n) for n in (4, 8)]
        cls.early = [packet("CONTINUE_CURRENT", finish=n) for n in (2, 6, 12, 16)]
        cls.endings = [packet("CONTINUE_CURRENT", finish=24, ending=e) for e in ("terminated", "truncated")]
        cls.deadline = packet("CONTINUE_CURRENT", finish=501)
        cls.failed = packet("CONTINUE_CURRENT", failure_step=17)

    def test_five_complete_paths_replay_actual_saved_commands(self):
        for name, value in self.packets.items():
            with self.subTest(variant=name):
                checked = replay(value);row = value["record"]
                self.assertEqual(checked["ledger"], value["ledger"])
                self.assertEqual(checked["recomputed_policy_queries"], value["actual_policy_calls"])
                self.assertEqual(value["native_frames"], 25500 + row["total_steps"] * 5)
                self.assertEqual(value["ledger"]["counts"]["reset_completed"], 51)
                self.assertEqual(row["total_steps"], 16 if name == "STOP" else 24)
                self.assertEqual(row["deadline_loss"], 500 if name == "STOP" else 24)
                self.assertEqual(checked["recomputed_parameter_fits"], 2)
        left = self.packets["CONTINUE_CURRENT"]["record"];right = self.packets["DIRECT_CURRENT"]["record"]
        self.assertTrue(audit.physical_rows_equal(left["physical_rows"], right["physical_rows"], 24))
        self.assertEqual(left["end_witness"], right["end_witness"])
        commands = [tuple(self.packets[v]["record"]["physical_rows"][16]["command"]) for v in contract.VARIANTS[:3]]
        self.assertEqual(len(set(commands)), 3)

    def test_invalid_fits_and_early_endings_keep_unavailable_cases(self):
        for value in self.invalid + self.early:
            with self.subTest(steps=value["record"]["total_steps"]):
                replay(value)
                self.assertFalse(value["record"]["boundary_ready"])
                self.assertIsNone(value["record"]["intervention"])
                self.assertEqual(value["record"]["deadline_loss"], value["record"]["total_steps"] if value["record"]["success"] else 500)

    def test_termination_truncation_and_full_deadline_are_retained(self):
        for value in self.endings + [self.deadline]:
            replay(value);self.assertFalse(value["record"]["success"])
            self.assertEqual(value["record"]["deadline_loss"], 500)
        self.assertEqual(self.deadline["record"]["total_steps"], 500)

    def test_partial_native_failure_keeps_attempt_and_unknown_outcome(self):
        value = self.failed;row = value["record"]
        self.assertIsInstance(value["error"], collector.CollectionFailure)
        self.assertFalse(row["completed"]);self.assertFalse(row["computation_counters_complete"])
        self.assertEqual((row["host_attempts"], row["host_returned"], value["budget"]["completed"]), (17, 16, 16))
        self.assertEqual(value["native_frames"], 25500 + 17 * 5)
        self.assertEqual(value["ledger"]["counts"]["simulation_frames_completed"], value["native_frames"])
        self.assertTrue(any(e["event"] == "DELAYED_INTERVENTION_ABORTED" for e in value["events"]))
        with self.assertRaises(ValueError): replay(value)

    def test_tampered_command_choice_evidence_and_private_noise_rejected(self):
        for kind in ("choice", "command", "raw", "fit_prefix", "fit_result", "noise", "hidden_field", "policy_before"):
            value = deepcopy(self.packets["SWITCH_SAVED"])
            events = value["events"]
            choice = next(e for e in events if e["event"] == "DELAYED_AGENT_EVENT" and e["agent_event"] == "CHOICE")["public_payload"]
            command = next(e for e in events if e["event"] == "DELAYED_AGENT_EVENT" and e["agent_event"] == "COMMAND")["public_payload"]
            if kind == "choice": choice["action_id"] = "CONTINUE_CURRENT"
            elif kind == "command": command["command"][0] += .01
            elif kind == "raw": command["raw_policy"][0] += .01
            elif kind == "policy_before": command["before"]["observation"][0] += .01
            elif kind == "fit_prefix": next(e for e in events if e.get("agent_event") == "FIT_INTENT")["public_payload"]["prefix"]["commands"][0][0] += .01
            elif kind == "fit_result": next(e for e in events if e.get("agent_event") == "FIT_RESULT")["public_payload"]["fit"]["bias_xy"][0] += .01
            elif kind == "noise": next(e for e in events if e["event"] == "STEP_COMPLETE")["executed_action_oracle"][0] += .01
            elif kind == "hidden_field": choice["boundary_observation"]["seed"] = 1
            with self.subTest(mutation=kind), self.assertRaises(ValueError): replay(value)

    def test_order_clocks_costs_references_and_extra_events_rejected(self):
        for kind in ("global_gap", "clock", "local_bool", "stale_public_clock", "execution_before_save", "source_reference", "frames", "extra_event", "deleted_result", "record_cost", "record_capture"):
            value = deepcopy(self.packets["CONTINUE_CURRENT"]);events = value["events"]
            if kind == "global_gap": events[10]["sequence"] += 1
            elif kind == "clock": events[10]["saved_ns"] = 0
            elif kind == "local_bool": next(e for e in events if e.get("agent_event") == "PREFIX_PROGRAM")["public_payload"]["sequence"] = False
            elif kind == "stale_public_clock": next(e for e in events if e.get("agent_event") == "STEP_RESULT")["public_payload"]["saved_ns"] = next(e for e in events if e.get("agent_event") == "COMMAND")["public_payload"]["saved_ns"]
            elif kind == "execution_before_save": next(e for e in events if e["event"] == "STEP_COMPLETE")["execution_started_ns"] = 0
            elif kind == "source_reference": next(e for e in events if e["event"] == "DELAYED_INTERVENTION_START")["saved_provenance"]["source_global_sequence"] += 1
            elif kind == "frames": next(e for e in events if e["event"] == "STEP_COMPLETE")["ledger_after"]["counts"]["simulation_frames_completed"] += 5
            elif kind == "extra_event": events.append(deepcopy(events[-1]))
            elif kind == "deleted_result": events.pop(next(i for i, e in enumerate(events) if e.get("agent_event") == "STEP_RESULT"))
            elif kind == "record_cost": value["record"]["optimizer_nfev"] += 1
            elif kind == "record_capture": value["record"]["captures"] = 1
            with self.subTest(mutation=kind), self.assertRaises(ValueError): replay(value)

    def test_population_gate_is_separate_from_data_integrity(self):
        config = contract.read(contract.CONFIG);rows = []
        for unit, spec in enumerate(config["tasks_and_seeds"]):
            for variant in config["variants"]:
                # Population-only synthetic table, explicitly not a valid identity journal.
                row = deepcopy(self.packets[variant]["record"]);row.update(unit=unit, **spec);rows.append(row)
        result = audit.compare_population(rows, config)
        self.assertEqual(result["qualification"], "QUALIFIED")
        self.assertEqual(len(result["failures"]), 3)
        self.assertTrue(all(r["historical_steps_amortized_per_unit"] == 1280 for r in result["methods"]))
        bad = deepcopy(rows);bad[0]["boundary_ready"] = False
        self.assertEqual(audit.compare_population(bad, config)["qualification"], "NOT_QUALIFIED")
        bad = deepcopy(rows);bad[4]["end_witness"]["native_sha256"] = "a" * 64
        self.assertEqual(audit.compare_population(bad, config)["qualification"], "NOT_QUALIFIED")
        with self.assertRaises(ValueError): audit.compare_population(rows[:-1], config)
        with self.assertRaises(ValueError): audit.compare_population(rows[::-1], config)

    def test_config_rejects_bool_aliases_population_budget_and_unknown_fields(self):
        config = contract.read(contract.CONFIG);contract.validate(config)
        changes = [("boundary_step", True), ("maximum_environment_steps", 7501), ("new_api_calls", False),
                   ("reserved_seeds", [21404, 21599]), ("unexpected", 1)]
        for key, value in changes:
            bad = deepcopy(config);bad[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError): contract.validate(bad)
        bad = deepcopy(config);bad["fault_oracle"]["matrix_xy"][0][0] = True
        with self.assertRaises(ValueError): contract.validate(bad)

    def test_incomplete_or_dirty_sources_cannot_prepare(self):
        with patch.object(contract, "git", return_value="dirty"), self.assertRaises(ValueError): contract.clean()
        with patch.object(contract, "git", return_value=""), self.assertRaises(ValueError): contract.clean()
        with patch.object(contract, "clean", side_effect=ValueError("uncommitted")), patch.object(contract, "sources") as sources:
            with self.assertRaises(ValueError): collector.prepare()
            sources.assert_not_called()

    def test_full_collector_files_and_independent_population_audit(self):
        ledger_cell = {};frames = queries = 0;envs = []
        original_simulation = TinyEnv.do_simulation;original_step = TinyEnv.step;original_native = mujoco.mj_step
        original_query = TinyPolicy.get_action
        def native(*args, **kwargs):
            nonlocal frames
            result = original_native(*args, **kwargs)
            frames += int(kwargs.get("nstep", args[2] if len(args) > 2 else 1));return result
        def reset_body(env, **kwargs):
            mujoco.mj_resetData(env.model, env.data);env.calls = 0
            for _ in range(100): env.do_simulation([0.], 5)
            return np.zeros(39), {}
        def reset(env, **kwargs): return ledger_cell["value"].reset_call(reset_body, env, **kwargs)
        def simulate(env, ctrl, n_frames): return ledger_cell["value"].simulation_call(original_simulation, env, ctrl, n_frames)
        def step(env, action):
            obs, reward, _, _, _ = original_step(env, action)
            return obs, reward, False, False, {"success": env.calls >= 24}
        def query(policy, observation):
            nonlocal queries
            queries += 1;return original_query(policy, observation)
        @contextmanager
        def instrument(ledger, *unused):
            ledger_cell["value"] = ledger
            with patch.object(TinyEnv, "reset", reset), patch.object(TinyEnv, "do_simulation", simulate), patch.object(
                    TinyEnv, "step", step), patch.object(TinyPolicy, "get_action", query), patch.object(mujoco, "mj_step", native):
                yield
        def factory(task, seed):
            env = TinyEnv();envs.append(env)
            with ledger_cell["value"].scope("GOAL_GENERATION"):
                for _ in range(50): env.reset()
            return env
        config = contract.read(contract.CONFIG)
        # All three software units use one synthetic task/seed. This never
        # allocates any of the scientific 21400--21402 seeds or MetaWorld tasks.
        config["tasks_and_seeds"] = [{"task": "push-v3", "seed": 700021} for _ in range(3)]
        manifest = {"experiment_run_id": "TINY_PIPELINE_ONLY", "manifest_id": "SOFTWARE_MANIFEST",
                    "source_git_commit": "SOFTWARE_FIXTURE", "config": config}
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            path = Path(tmp) / "manifest.json";contract.write(path, manifest)
            stack.enter_context(patch.object(contract, "load", return_value=(manifest, {"push-v3": model()})))
            stack.enter_context(patch.object(contract, "clean"));stack.enter_context(patch.object(contract, "git", return_value="SOFTWARE_FIXTURE"))
            stack.enter_context(patch.object(collector, "create_task_environment", factory))
            stack.enter_context(patch.object(collector, "create_task_policy", return_value=TinyPolicy()))
            stack.enter_context(patch.object(LifecycleLedger, "instrument", instrument))
            for target in (boundary_prefix, audit):
                stack.enter_context(patch.object(target, "infer_four", return_value=fit((.1, -.05))))
                stack.enter_context(patch.object(target, "infer_operator", return_value=fit((-.08, .12), nfev=2)))
            stack.enter_context(patch.object(audit, "create_task_policy", return_value=TinyPolicy()))
            with redirect_stdout(textio.StringIO()): collector.collect(path)
            original_hashes = {p.name: contract.sha(p) for p in (path.parent / "collection").iterdir()}
            result = audit.audit(path)
            self.assertEqual(result["integrity"], "PASSED");self.assertEqual(result["qualification"], "QUALIFIED")
            self.assertEqual(result["executions"], 15)
            self.assertEqual(result["costs"]["new_control_steps"], 336)
            self.assertEqual(result["costs"]["lifecycle"]["counts"]["simulation_frames_completed"], frames)
            self.assertEqual(result["costs"]["policy_queries"], queries)
            report_receipt = contract.read(path.parent / "audit/report_receipt.json")
            self.assertEqual(report_receipt["record_audit_sha256"], contract.sha(path.parent / "audit/record_audit.json"))
            self.assertEqual(report_receipt["report_sha256"], contract.sha(path.parent / "audit/report_zh.md"))
            self.assertEqual(report_receipt["execution_rows"], 15)
            self.assertEqual(len(result["execution_rows"]), 15)
            self.assertEqual(original_hashes, {p.name: contract.sha(p) for p in (path.parent / "collection").iterdir()})
            with self.assertRaises(FileExistsError): collector.collect(path)
            with self.assertRaises(FileExistsError): audit.audit(path)
            PIPELINE_RECEIPTS.append({"status": "PASSED", "native_frames": frames, "actual_policy_calls": queries,
                "audit": result, "collection_summary": contract.read(path.parent / "collection/summary.json"),
                "allocation_scope": "THREE_SYNTHETIC_PUSH_UNITS_SEED700021_NO_METAWORLD"})
        for env in envs: env.close()

    def test_factory_exception_preserves_closed_partial_collection(self):
        config = contract.read(contract.CONFIG)
        manifest = {"experiment_run_id": "TINY_FAILED_FACTORY", "manifest_id": "SOFTWARE_MANIFEST",
                    "source_git_commit": "SOFTWARE_FIXTURE", "config": config}
        with tempfile.TemporaryDirectory() as tmp, patch.object(contract, "clean"), patch.object(contract, "load", return_value=(
                manifest, {case["task"]: model() for case in config["tasks_and_seeds"]})), patch.object(
                contract, "git", return_value="SOFTWARE_FIXTURE"), patch.object(collector, "create_task_environment",
                side_effect=RuntimeError("SOFTWARE_FACTORY_FAILURE_BEFORE_CREATION")):
            path = Path(tmp) / "manifest.json";contract.write(path, manifest)
            with self.assertRaises(collector.CollectionFailure): collector.collect(path)
            folder = path.parent / "collection"
            summary = contract.read(folder / "summary.json");completion = contract.read(folder / "completion.json")
            self.assertEqual(summary["status"], "FAILED_PARTIAL");self.assertEqual(summary["completed_executions"], 0)
            self.assertEqual(summary["controlled_steps"], 0);self.assertEqual(summary["lifecycle"]["counts"], {})
            self.assertFalse(contract.read(folder / "failed_execution.json")["completed"])
            for name, expected in completion["artifact_sha256"].items(): self.assertEqual(contract.sha(folder / name), expected)
            with self.assertRaises(FileExistsError): collector.collect(path)
            with self.assertRaisesRegex(ValueError, "partial collection"): audit.audit(path)
            self.assertEqual(contract.read(path.parent / "audit/record_audit.json")["integrity"], "FAILED")


if __name__ == "__main__":
    unittest.main()
