"""One-axis collection/audit fixtures, never new MetaWorld scientific outcomes."""
from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
import gzip
import io as textio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gymnasium as gym
import mujoco
import numpy as np

from scripts import collect_movement_task_v1 as collector
from scripts import audit_movement_task_v1 as audit
from src.analysis import movement_task_io_v1 as io
from src.analysis import delayed_qualification_io_v2 as witness_io
from src.analysis.movement_model_source_v1 import load_bank
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit
import boundary_prefix

PIPELINE_RECEIPTS = []


class TaskFixture(TinyEnv):
    def __init__(self, mode):super().__init__();self.fixture_mode = mode
    def observation(self):
        obs = np.zeros(39);obs[:3] = [float(self.data.qpos[0])*.001,.6,.05 if self.fixture_mode == "unreachable" else .25]
        obs[4:7] = [0.,.8,.02];return obs
    def reset(self, **kwargs):
        mujoco.mj_resetData(self.model,self.data);self.calls = 0
        for _ in range(100):self.do_simulation([0.],5)
        return self.observation(),{}
    def step(self, action):
        self.calls += 1;self.do_simulation([action[0]],5)
        if self.fixture_mode == "partial" and self.calls == 20:raise RuntimeError("INJECTED_AFTER_NATIVE_WORK")
        end = {"normal":28,"early_prefix":6,"early_movement":18,"unreachable":100,"partial":28}[self.fixture_mode]
        return self.observation(),0.,False,False,{"success":self.calls >= end}


LAYERS = ["gymnasium.wrappers.common.RecordEpisodeStatistics", __name__+".TaskFixture"]


@contextmanager
def audit_stubs():
    with patch.object(audit,"create_task_policy",return_value=TinyPolicy()), patch.object(audit,"infer_four",return_value=fit((0.,0.))), patch.object(
            audit,"infer_operator",return_value=fit((0.,0.),nfev=2)), patch.object(io,"expected_layers",return_value=LAYERS):yield


def read_lines(path):
    with gzip.open(path,"rt",encoding="utf-8") as handle:return [json.loads(v) for v in handle]


def pipeline(*, partial=False):
    config = io.expected_config();specs = [("push-v3","normal"),("reach-v3","early_prefix"),
                                          ("door-open-v3","early_movement"),("push-v3","unreachable")]
    if partial:specs = [("push-v3","partial")]
    config["cases"] = [{"unit":i,"task":task,"seed":700201+i,"variant":variant,"planned_boundary":16}
                       for i,(task,_) in enumerate(specs) for variant in io.VARIANTS]
    if partial:config["cases"] = config["cases"][:1]
    config.update(executions=len(config["cases"]),paired_units=len(specs),maximum_simulation_frames=1500000)
    models = {task:{**model(),"task":task} for task in io.TASKS}
    references, receipt = load_bank(Path(__file__).resolve().parents[1])
    manifest = {"experiment_run_id":"MOVEMENT_TASK_TINY_SOFTWARE_ONLY","manifest_id":"SOFTWARE_MANIFEST",
                "source_git_commit":"SOFTWARE_COMMIT","config":config,"arx_source_receipt":receipt}
    cell = {};envs = [];frames = queries = 0;record = {"completed":False,"partial_requested":partial}
    native_original = mujoco.mj_step;simulate_original = TaskFixture.do_simulation;reset_original = TaskFixture.reset
    query_original = TinyPolicy.get_action
    def native(*args,**kwargs):
        nonlocal frames
        result = native_original(*args,**kwargs);frames += int(kwargs.get("nstep",args[2] if len(args)>2 else 1));return result
    def simulate(env,ctrl,n):return cell["ledger"].simulation_call(simulate_original,env,ctrl,n)
    def reset(env,**kwargs):return cell["ledger"].reset_call(reset_original,env,**kwargs)
    def query(policy,obs):
        nonlocal queries
        queries += 1;return query_original(policy,obs)
    @contextmanager
    def instrument(ledger,*unused):
        cell["ledger"] = ledger
        with patch.object(TaskFixture,"do_simulation",simulate),patch.object(TaskFixture,"reset",reset),patch.object(
                mujoco,"mj_step",native),patch.object(TinyPolicy,"get_action",query):yield
    def factory(task,seed):
        env = gym.wrappers.RecordEpisodeStatistics(TaskFixture(specs[seed-700201][1]));envs.append(env)
        with cell["ledger"].scope("GOAL_GENERATION"):
            for _ in range(50):env.reset()
        return env
    try:
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            path = Path(temp)/"manifest.json";io.write(path,manifest)
            stack.enter_context(patch.object(io,"load",return_value=(manifest,models,references)))
            stack.enter_context(patch.object(io,"clean"));stack.enter_context(patch.object(io,"git",return_value="SOFTWARE_COMMIT"))
            stack.enter_context(patch.object(collector,"create_task_environment",factory))
            stack.enter_context(patch.object(collector,"create_task_policy",return_value=TinyPolicy()))
            stack.enter_context(patch.object(LifecycleLedger,"instrument",instrument))
            stack.enter_context(patch.object(witness_io,"expected_layers",return_value=LAYERS))
            stack.enter_context(patch.object(boundary_prefix,"infer_four",return_value=fit((0.,0.))))
            stack.enter_context(patch.object(boundary_prefix,"infer_operator",return_value=fit((0.,0.),nfev=2)))
            stack.enter_context(audit_stubs())
            with redirect_stdout(textio.StringIO()):
                if partial:
                    try:collector.collect(path)
                    except collector.CollectionFailure:pass
                    else:raise AssertionError("native exception was hidden")
                else:collector.collect(path)
            folder = path.parent/"collection";hashes = {p.name:io.sha(p) for p in folder.iterdir()}
            if partial:
                with unittest.TestCase().assertRaises(ValueError):audit.audit(path)
                result = None
            else:result = audit.audit(path)
            assert hashes == {p.name:io.sha(p) for p in folder.iterdir()}
            packet = {"manifest":manifest,"models":models,"references":references,"records":read_lines(folder/"cases.jsonl.gz"),
                "events":read_lines(folder/"events.jsonl.gz"),"private":read_lines(folder/"state_witnesses.jsonl.gz"),
                "summary":io.read(folder/"summary.json"),"audit":result,
                "failed":io.read(folder/"failed_execution.json") if partial else None}
            with unittest.TestCase().assertRaises(FileExistsError):collector.collect(path)
            if not partial:
                with unittest.TestCase().assertRaises(FileExistsError):audit.audit(path)
            record.update(completed=True,rows=packet["summary"]["rows"],audit=result)
            return packet
    finally:
        for env in envs:env.close()
        record.update(native_frames=frames,actual_policy_queries=queries,constructed_tiny_envs=len(envs),
            lifecycle=None if "ledger" not in cell else cell["ledger"].snapshot(),
            new_metaworld_steps=0,new_scientific_seeds=0,new_api_calls=0)
        PIPELINE_RECEIPTS.append(record)


def replay(packet):
    with audit_stubs():return audit.audit_records(packet["manifest"],packet["models"],packet["references"],
        iter(packet["records"]),iter(packet["events"]),iter(packet["private"]),packet["summary"])


class MovementTaskPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.packet = pipeline()

    def test_complete_four_method_pipeline_has_four_witnesses_and_full_costs(self):
        p = self.packet;a = p["audit"]
        self.assertEqual((a["integrity"],a["executions"],a["private_witness_records"]),("PASSED",32,128))
        self.assertEqual(a["post_movement_world_comparisons"],16)
        self.assertEqual(a["costs"]["lifecycle"]["counts"]["reset_completed"],32*51)
        self.assertEqual(a["costs"]["lifecycle"]["counts"]["simulation_frames_completed"],32*25500+5*a["costs"]["new_control_steps"])
        self.assertFalse(a["task_benefit_evaluated"])

    def test_early_successes_and_unreached_anchor_are_retained_in_task_outcomes(self):
        rows = self.packet["records"]
        self.assertTrue(all(r["success"] for r in rows))
        self.assertEqual({r["total_steps"] for r in rows if r["unit"] == 1},{6})
        self.assertTrue(all(not r["boundary_ready"] for r in rows if r["unit"] == 1))
        self.assertTrue(all(r["movement_fit_attempts"] == 0 for r in rows if r["unit"] == 2))
        self.assertTrue(all(r["reposition_steps"] == 64 for r in rows if r["unit"] == 3 and io.method(r["variant"]) != "DIRECT_C8"))

    def test_auditor_never_calls_physical_collector_or_task_actor(self):
        with patch.object(collector,"execute_one",side_effect=AssertionError("no collector")), patch(
                "src.probe.movement_task_reference_v1.run_movement_task",side_effect=AssertionError("no actor")), patch.object(
                TaskFixture,"step",side_effect=AssertionError("no physics")):
            self.assertEqual(replay(self.packet)["costs"],self.packet["audit"]["costs"])

    def test_missing_case_or_private_witness_is_rejected(self):
        for kind in ("records","private"):
            p = deepcopy(self.packet);p[kind].pop()
            with self.subTest(kind=kind),self.assertRaises(ValueError):replay(p)

    def test_command_policy_noise_or_cost_tampering_is_rejected(self):
        for kind in ("command","raw_policy","executed_action_oracle","noise_cursor_after","ledger_after"):
            p = deepcopy(self.packet)
            row = next(e for e in p["events"] if e["event"] == "STEP_COMPLETE" and e["phase"] == "TASK_AFTER_MOVEMENT")
            if kind == "ledger_after":row[kind]["counts"]["simulation_frames_completed"] += 5
            elif kind == "noise_cursor_after":row[kind] -= 1
            else:row[kind][0] += .01
            with self.subTest(kind=kind),self.assertRaises(ValueError):replay(p)

    def test_post_movement_snapshot_cannot_move_after_task_execution(self):
        p = deepcopy(self.packet);packet = next(v for v in p["private"] if v["label"] == "POST_MOVEMENT")
        packet["started_ns"] = p["summary"]["collection_closed_ns"]
        with self.assertRaises(ValueError):replay(p)

    def test_partial_native_failure_preserves_work_and_cannot_restart(self):
        packet = pipeline(partial=True);failed = packet["failed"]
        self.assertEqual(packet["summary"]["status"],"FAILED_PARTIAL")
        self.assertEqual((failed["host_attempts"],failed["host_returned"]),(20,19))
        self.assertEqual(packet["summary"]["lifecycle"]["counts"]["simulation_frames_completed"],25500+100)
        self.assertIsNotNone(failed["movement_failure"])


if __name__ == "__main__":unittest.main()
