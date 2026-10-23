"""V2 software pipeline with the real statistics wrapper and tiny native physics.

Only synthetic seed 700031 is used; no registered MetaWorld task is created.
Private-record mutations reuse saved data and never execute more physics.
"""
from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
import gzip
import io as textio
import json
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter_ns
import tempfile
import unittest
from unittest.mock import patch

import gymnasium as gym
import mujoco
import numpy as np

from scripts import qualify_delayed_intervention_v2 as collector
from scripts import audit_delayed_intervention_v2 as audit
from src.analysis import delayed_qualification_io_v2 as io
from src.analysis.continuous_state_witness_v1 import STATISTICS_TYPE
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit
import boundary_prefix

PIPELINE_RECEIPTS = []
PIPELINE_DATA = []
SOFTWARE_LAYERS = [STATISTICS_TYPE, "tests.test_paired_probe_host_v1.TinyEnv"]


def read_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle: return [json.loads(line) for line in handle]


@contextmanager
def audit_stubs():
    with patch.object(audit.previous, "create_task_policy", return_value=TinyPolicy()), patch.object(
            audit.previous, "infer_four", return_value=fit((.1, -.05))), patch.object(
            audit.previous, "infer_operator", return_value=fit((-.08, .12), nfev=2)), patch.object(
            io, "expected_layers", return_value=SOFTWARE_LAYERS):
        yield


def pipeline():
    cell = {};frames = queries = 0;envs = [];record = {"completed": False}
    original_sim = TinyEnv.do_simulation;original_step = TinyEnv.step;original_native = mujoco.mj_step;original_query = TinyPolicy.get_action
    def native(*args, **kwargs):
        nonlocal frames
        result = original_native(*args, **kwargs);frames += int(kwargs.get("nstep", args[2] if len(args) > 2 else 1));return result
    def reset_body(env, **kwargs):
        mujoco.mj_resetData(env.model, env.data);env.calls = 0
        for _ in range(100): env.do_simulation([0.], 5)
        return np.zeros(39), {}
    def reset(env, **kwargs): return cell["ledger"].reset_call(reset_body, env, **kwargs)
    def simulate(env, ctrl, n_frames): return cell["ledger"].simulation_call(original_sim, env, ctrl, n_frames)
    def step(env, action):
        obs, reward, _, _, _ = original_step(env, action)
        return obs, reward, False, False, {"success": env.calls >= 24}
    def query(policy, observation):
        nonlocal queries
        queries += 1;return original_query(policy, observation)
    @contextmanager
    def instrument(ledger, *unused):
        cell["ledger"] = ledger
        with patch.object(TinyEnv, "reset", reset), patch.object(TinyEnv, "do_simulation", simulate), patch.object(
                TinyEnv, "step", step), patch.object(TinyPolicy, "get_action", query), patch.object(mujoco, "mj_step", native):
            yield
    def factory(task, seed):
        env = gym.wrappers.RecordEpisodeStatistics(TinyEnv());envs.append(env)
        with cell["ledger"].scope("GOAL_GENERATION"):
            for _ in range(50): env.reset()
        return env
    config = io.read(io.CONFIG);config["tasks_and_seeds"] = [{"task": "push-v3", "seed": 700031} for _ in range(3)]
    manifest = {"experiment_run_id": "V2_TINY_WRAPPED_SOFTWARE_ONLY", "manifest_id": "SOFTWARE_MANIFEST",
                "source_git_commit": "SOFTWARE_COMMIT", "config": config}
    try:
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            path = Path(tmp) / "manifest.json";io.write(path, manifest)
            stack.enter_context(patch.object(io, "load", return_value=(manifest, {"push-v3": model()})))
            stack.enter_context(patch.object(io, "clean"));stack.enter_context(patch.object(io, "git", return_value="SOFTWARE_COMMIT"))
            stack.enter_context(patch.object(collector, "create_task_environment", factory))
            stack.enter_context(patch.object(collector, "create_task_policy", return_value=TinyPolicy()))
            stack.enter_context(patch.object(LifecycleLedger, "instrument", instrument))
            stack.enter_context(patch.object(boundary_prefix, "infer_four", return_value=fit((.1, -.05))))
            stack.enter_context(patch.object(boundary_prefix, "infer_operator", return_value=fit((-.08, .12), nfev=2)))
            stack.enter_context(audit_stubs())
            with redirect_stdout(textio.StringIO()): collector.collect(path)
            source_files = {p.name: io.sha(p) for p in (path.parent / "collection").iterdir()}
            result = audit.audit(path)
            assert source_files == {p.name: io.sha(p) for p in (path.parent / "collection").iterdir()}
            folder = path.parent / "collection"
            packet = {"manifest": manifest, "records": read_lines(folder / "cases.jsonl.gz"), "events": read_lines(folder / "events.jsonl.gz"),
                "private": read_lines(folder / "state_witnesses.jsonl.gz"), "summary": io.read(folder / "summary.json"), "result": result}
            receipt = io.read(path.parent / "audit/report_receipt.json")
            assert receipt["record_audit_sha256"] == io.sha(path.parent / "audit/record_audit.json")
            assert receipt["report_sha256"] == io.sha(path.parent / "audit/report_zh.md")
            for operation in (collector.collect, audit.audit):
                try: operation(path)
                except FileExistsError: pass
                else: raise AssertionError("one-shot output was overwritten")
            record.update(completed=True, result=result, manifest=manifest)
            PIPELINE_DATA.append(packet)
            return packet
    finally:
        for env in envs: env.close()
        record.update(native_frames=frames, actual_policy_queries=queries, constructed_tiny_envs=len(envs),
            lifecycle=None if "ledger" not in cell else cell["ledger"].snapshot(), new_metaworld_steps=0, new_scientific_seeds=0, new_api_calls=0)
        PIPELINE_RECEIPTS.append(record)


def replay(packet):
    with audit_stubs():
        return audit.audit_records(packet["manifest"], {"push-v3": model()}, packet["records"], packet["events"], packet["private"], packet["summary"])


class DelayedQualificationV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.packet = pipeline()

    def test_complete_wrapped_pipeline_preserves_full_and_projected_verdicts(self):
        p = self.packet;r = p["result"]
        self.assertEqual((r["integrity"], r["qualification"]), ("PASSED", "QUALIFIED"))
        self.assertEqual((r["executions"], r["costs"]["private_witness_records"]), (15, 45))
        self.assertEqual(r["costs"]["new_control_steps"], 336)
        self.assertEqual(r["costs"]["lifecycle"]["counts"]["simulation_frames_completed"], 384180)
        self.assertEqual(PIPELINE_RECEIPTS[-1]["native_frames"], 384180)
        self.assertEqual(r["costs"]["policy_queries"], PIPELINE_RECEIPTS[-1]["actual_policy_queries"])
        self.assertTrue(all(not x["matched_prefixes"] and not x["direct_loop_equal"] for x in r["legacy_full_fingerprint_checks"]))
        self.assertTrue(all(x["initial"]["only_registered_timing_components_differ"] and x["boundary"]["only_registered_timing_components_differ"] for x in r["witness_pair_diagnostics"]))
        self.assertEqual(len(r["failures"]), 3)

    def test_private_record_must_be_saved_in_its_actual_source_interval(self):
        for kind in ("late", "early", "anchor", "sequence", "label", "extra"):
            p = deepcopy(self.packet);value = p["private"][0]
            if kind == "late": value["saved_ns"] = p["summary"]["collection_closed_ns"] + 1
            elif kind == "early": value["started_ns"] = value["source_anchor_saved_ns"] - 1
            elif kind == "anchor": value["source_anchor_sequence"] += 1
            elif kind == "sequence": value["sequence"] = False
            elif kind == "label": value["label"] = "FINAL"
            else: value["unknown"] = True
            p["records"][0]["state_witnesses"][0] = deepcopy(value)
            with self.subTest(kind=kind), self.assertRaises(ValueError): replay(p)

    def test_graph_projection_components_and_source_hash_cannot_be_substituted(self):
        for kind in ("graph", "projection", "component", "source", "native", "layer", "edit"):
            p = deepcopy(self.packet);value = p["private"][1]
            if kind == "graph": value["witness"]["raw_graph"][2].append("0" * 64)
            elif kind == "projection": value["witness"]["comparison_python_sha256"] = "0" * 64
            elif kind == "component": value["witness"]["components"][0]["raw_sha256"] = "0" * 64
            elif kind == "source": value["source_witness"]["python_semantic_sha256"] = "0" * 64
            elif kind == "native": value["witness"]["native_sha256"] = "0" * 64
            elif kind == "layer": value["witness"]["layer_types"][-1] = "unknown.Env"
            elif kind == "edit": value["witness"]["projection_edits"][0]["field"] = "episode_lengths"
            p["records"][0]["state_witnesses"][1] = deepcopy(value)
            with self.subTest(kind=kind), self.assertRaises(ValueError): replay(p)

    def test_private_stream_costs_denominators_and_public_leakage_are_checked(self):
        for kind in ("missing", "copied", "cost", "steps", "leak", "case_missing"):
            p = deepcopy(self.packet)
            if kind == "missing": p["private"].pop()
            elif kind == "copied": p["records"][0]["state_witnesses"][0] = deepcopy(p["private"][3])
            elif kind == "cost": p["private"][0]["ledger_after"]["counts"]["simulation_frames_completed"] += 5
            elif kind == "steps": p["summary"]["controlled_steps"] += 1
            elif kind == "case_missing": p["records"].pop()
            else: next(e for e in p["events"] if e.get("agent_event") == "PREFIX_PROGRAM")["public_payload"]["state_graph"] = p["private"][0]["witness"]
            with self.subTest(kind=kind), self.assertRaises(ValueError): replay(p)

    def test_registered_config_and_incomplete_freeze_fail_closed(self):
        config = io.read(io.CONFIG);io.validate(config)
        for field, value in (("witnesses_per_execution", True), ("reserved_seeds", [21604, 21799]), ("maximum_environment_steps", 7501), ("new_api_calls", 1)):
            bad = deepcopy(config);bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): io.validate(bad)
        with patch.object(io, "git", return_value=""), self.assertRaises(ValueError): io.clean()
        with patch.object(io, "clean", side_effect=ValueError("uncommitted")), patch.object(io, "sources") as sources:
            with self.assertRaises(ValueError): collector.prepare()
            sources.assert_not_called()

    def test_returned_case_copy_must_match_flushed_private_stream(self):
        p = self.packet;first = p["private"][0]
        # The stored packet itself must exactly agree with the independently
        # written private stream. No new environment is needed for this check.
        changed = deepcopy(p);changed["records"][0]["state_witnesses"][0]["witness"]["comparison_python_sha256"] = "f" * 64
        with self.assertRaises(ValueError): replay(changed)
        self.assertEqual(first["label"], "INITIAL")

    def test_observer_rejects_changed_private_acknowledgement(self):
        first = self.packet["private"][0]
        session = SimpleNamespace(task="push-v3", env=None, policy=None, ctx={"calls": 0},
            ledger=SimpleNamespace(snapshot=lambda: deepcopy(first["ledger_before"])), witness=lambda: deepcopy(first["source_witness"]))
        position = lambda: {"sequence": first["source_anchor_sequence"], "saved_ns": first["source_anchor_saved_ns"]}
        def bad_ack(kind, payload):
            payload["witness"]["comparison_python_sha256"] = "f" * 64
            return {**payload, "sequence": 0, "saved_ns": perf_counter_ns()}
        with patch.object(collector, "capture_witness", return_value=deepcopy(first["witness"])), audit_stubs():
            with self.assertRaisesRegex(ValueError, "acknowledgement changed"):
                collector.observe_state(session, "INITIAL", first["source_witness"], position, bad_ack)

    def test_observer_rejects_unaccounted_physical_ledger_change(self):
        first = self.packet["private"][0];ledger = deepcopy(first["ledger_before"])
        session = SimpleNamespace(task="push-v3", env=None, policy=None, ctx={"calls": 0},
            ledger=SimpleNamespace(snapshot=lambda: deepcopy(ledger)), witness=lambda: deepcopy(first["source_witness"]))
        def bad_capture(*args):
            ledger["counts"]["simulation_frames_completed"] += 5
            return deepcopy(first["witness"])
        with patch.object(collector, "capture_witness", bad_capture), audit_stubs():
            with self.assertRaisesRegex(ValueError, "physical ledger"):
                collector.observe_state(session, "INITIAL", first["source_witness"],
                    lambda: {"sequence": first["source_anchor_sequence"], "saved_ns": first["source_anchor_saved_ns"]},
                    lambda *args: self.fail("changed-state witness must not be saved"))


if __name__ == "__main__": unittest.main()
