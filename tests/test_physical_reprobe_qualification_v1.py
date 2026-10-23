"""Frozen collection/audit software pipeline using one-axis native fixtures only."""
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

from scripts import qualify_physical_reprobe_v1 as collector
from scripts import audit_physical_reprobe_v1 as audit
from src.analysis import physical_reprobe_io_v1 as io
from src.analysis import delayed_qualification_io_v2 as witness_io
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit
import boundary_prefix

PIPELINE_RECEIPTS = []


class QualificationEnv(TinyEnv):
    def __init__(self, mode):
        super().__init__();self.fixture_mode=mode

    def observation(self):
        obs=np.zeros(39);obs[:3]=[float(self.data.qpos[0])*.001,.6,.25]
        obs[4:7]=[0.,.8,.02]
        if self.fixture_mode=="unreachable":obs[2]=.05
        return obs

    def reset(self, **kwargs):
        mujoco.mj_resetData(self.model,self.data);self.calls=0
        for _ in range(100):self.do_simulation([0.],5)
        return self.observation(),{}

    def step(self, action):
        self.calls+=1;self.do_simulation([action[0]],5)
        if self.fixture_mode=="partial" and self.calls==20:raise RuntimeError("INJECTED_AFTER_NATIVE_STEP")
        return self.observation(),0.,False,False,{"success":self.fixture_mode=="early" and self.calls>=24}


LAYERS=["gymnasium.wrappers.common.RecordEpisodeStatistics", __name__+".QualificationEnv"]


@contextmanager
def audit_stubs():
    with patch.object(audit,"create_task_policy",return_value=TinyPolicy()), patch.object(
            audit,"infer_four",return_value=fit((0.,0.))), patch.object(
            audit,"infer_operator",return_value=fit((0.,0.),nfev=2)), patch.object(io,"expected_layers",return_value=LAYERS):
        yield


def read_lines(path):
    with gzip.open(path,"rt",encoding="utf-8") as f:return [json.loads(line) for line in f]


def pipeline(*, partial=False):
    config=io.expected_config()
    specs=[("push-v3",16,"normal"),("reach-v3",32,"early"),("door-open-v3",64,"unreachable"),
           ("reach-v3",16,"normal"),("door-open-v3",16,"normal")]
    if partial:specs=[("push-v3",16,"partial")]
    config["cases"]=[{"unit":i,"task":task,"seed":700111+i,"variant":"PHYSICAL_REPROBE","planned_boundary":boundary}
                     for i,(task,boundary,_) in enumerate(specs)]
    config["executions"]=len(specs);config["maximum_simulation_frames"]=200000
    models={task:{**model(),"task":task} for task in io.TASKS}
    manifest={"experiment_run_id":"PHYSICAL_REPROBE_TINY_SOFTWARE_ONLY","manifest_id":"SOFTWARE_MANIFEST",
              "source_git_commit":"SOFTWARE_COMMIT","config":config}
    cell={};envs=[];frames=queries=0;record={"completed":False,"partial_requested":partial}
    native_original=mujoco.mj_step;simulate_original=QualificationEnv.do_simulation;reset_original=QualificationEnv.reset
    query_original=TinyPolicy.get_action
    def native(*args,**kwargs):
        nonlocal frames
        value=native_original(*args,**kwargs);frames+=int(kwargs.get("nstep",args[2] if len(args)>2 else 1));return value
    def simulate(env,ctrl,n):return cell["ledger"].simulation_call(simulate_original,env,ctrl,n)
    def reset(env,**kwargs):return cell["ledger"].reset_call(reset_original,env,**kwargs)
    def query(policy,obs):
        nonlocal queries
        queries+=1;return query_original(policy,obs)
    @contextmanager
    def instrument(ledger,*unused):
        cell["ledger"]=ledger
        with patch.object(QualificationEnv,"do_simulation",simulate),patch.object(QualificationEnv,"reset",reset),patch.object(
                mujoco,"mj_step",native),patch.object(TinyPolicy,"get_action",query):yield
    def factory(task,seed):
        mode=specs[seed-700111][2];env=gym.wrappers.RecordEpisodeStatistics(QualificationEnv(mode));envs.append(env)
        with cell["ledger"].scope("GOAL_GENERATION"):
            for _ in range(50):env.reset()
        return env
    try:
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            path=Path(temp)/"manifest.json";io.write(path,manifest)
            stack.enter_context(patch.object(io,"load",return_value=(manifest,models)))
            stack.enter_context(patch.object(io,"clean"));stack.enter_context(patch.object(io,"git",return_value="SOFTWARE_COMMIT"))
            stack.enter_context(patch.object(collector,"create_task_environment",factory))
            stack.enter_context(patch.object(collector,"create_task_policy",return_value=TinyPolicy()))
            stack.enter_context(patch.object(LifecycleLedger,"instrument",instrument))
            stack.enter_context(patch.object(witness_io,"expected_layers",return_value=LAYERS))
            stack.enter_context(patch.object(boundary_prefix,"infer_four",return_value=fit((0.,0.))))
            stack.enter_context(patch.object(boundary_prefix,"infer_operator",return_value=fit((0.,0.),nfev=2)))
            stack.enter_context(audit_stubs())
            if partial:
                with redirect_stdout(textio.StringIO()):
                    try:collector.collect(path)
                    except collector.CollectionFailure:pass
                    else:raise AssertionError("partial native failure was hidden")
            else:
                with redirect_stdout(textio.StringIO()):collector.collect(path)
            folder=path.parent/"collection";hashes={p.name:io.sha(p) for p in folder.iterdir()}
            if partial:
                with unittest.TestCase().assertRaises(ValueError):audit.audit(path)
                result=None
            else:result=audit.audit(path)
            assert hashes=={p.name:io.sha(p) for p in folder.iterdir()}
            packet={"manifest":manifest,"models":models,"records":read_lines(folder/"cases.jsonl.gz"),
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
    with audit_stubs():return audit.audit_records(packet["manifest"],packet["models"],packet["records"],packet["events"],packet["private"],packet["summary"])


class ReprobeQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.packet=pipeline()

    def test_complete_multi_case_pipeline_uses_cumulative_ledger(self):
        p=self.packet;self.assertEqual((p["audit"]["integrity"],p["audit"]["qualification"]),("PASSED","QUALIFIED"))
        self.assertEqual(p["audit"]["private_witness_records"],15)
        self.assertEqual(p["audit"]["costs"]["lifecycle"]["by_phase"]["CONTROLLED_RESET"]["reset_completed"],5)
        self.assertEqual([r["complete_window"] for r in p["records"]],[True,False,False,True,True])
        self.assertFalse(p["audit"]["measurement_model_qualified"])

    def test_early_success_and_unreachable_anchor_remain_in_denominator(self):
        rows=self.packet["records"]
        self.assertEqual(rows[1]["collection_stop_reason"],"ENDED_BEFORE_BOUNDARY")
        self.assertEqual((rows[1]["success"],rows[1]["total_steps"],rows[1]["probe_steps"]),(True,24,0))
        self.assertEqual(rows[2]["collection_stop_reason"],"ANCHOR_NOT_REACHED")
        self.assertEqual((rows[2]["reposition_steps"],rows[2]["probe_steps"]),(64,0))

    def test_source_population_and_missing_or_extra_events_rejected(self):
        for edit in (lambda p:p["records"].pop(),lambda p:p["events"].pop(),lambda p:p["events"].append(deepcopy(p["events"][-1]))):
            p=deepcopy(self.packet);edit(p)
            with self.assertRaises(ValueError):replay(p)

    def test_changed_command_private_noise_and_physical_cost_rejected(self):
        for field,value in (("command",[.9,0.,0.,0.]),("noise_cursor_after",999),("simulation_time_after",999.)):
            p=deepcopy(self.packet)
            row=next(r for r in p["events"] if r["event"]=="STEP_COMPLETE" and r["phase"]=="WARM_PROBE")
            row[field]=value
            with self.assertRaises(ValueError):replay(p)
        p=deepcopy(self.packet);p["summary"]["controlled_steps"]+=1
        with self.assertRaises(ValueError):replay(p)

    def test_public_truth_injection_and_false_complete_window_rejected(self):
        p=deepcopy(self.packet)
        row=next(r for r in p["events"] if r["event"]=="AGENT_EVENT" and r["agent_event"]=="REACQUIRE_CHOICE")
        row["public_payload"]["start"]["fault_oracle"]={}
        with self.assertRaises(ValueError):replay(p)
        p=deepcopy(self.packet);p["records"][2]["complete_window"]=True
        with self.assertRaises(ValueError):replay(p)

    def test_private_witness_context_and_timing_tampering_rejected(self):
        p=deepcopy(self.packet);p["private"][1]["started_ns"]=0
        with self.assertRaises(ValueError):replay(p)
        p=deepcopy(self.packet);p["private"][2]["witness"]["full_python_sha256"]="0"*64
        with self.assertRaises(ValueError):replay(p)

    def test_proof_does_not_execute_actor_collector_or_physics(self):
        with patch.object(collector,"collect",side_effect=AssertionError("collector called")),patch.object(
                collector,"execute_reprobe",side_effect=AssertionError("actor called")),patch.object(
                mujoco,"mj_step",side_effect=AssertionError("physics called")):
            self.assertEqual(replay(self.packet)["qualification"],"QUALIFIED")

    def test_partial_native_failure_is_saved_and_cannot_restart(self):
        p=pipeline(partial=True);self.assertEqual(p["summary"]["status"],"FAILED_PARTIAL")
        self.assertEqual(p["summary"]["completed_executions"],0)
        self.assertEqual((p["failed"]["host_attempts"],p["failed"]["host_returned"]),(20,19))
        self.assertEqual(p["failed"]["ledger_after_close"]["counts"]["simulation_frames_completed"],25600)

    def test_registered_config_covers_unique_cases_and_keeps_reservation(self):
        config=io.expected_config();io.validate(config)
        self.assertEqual([r["seed"] for r in config["cases"]],list(range(22400,22409)))
        self.assertEqual(config["scheduled_maximum_control_steps"],sum(r["planned_boundary"]+72 for r in config["cases"]))
        self.assertEqual(config["reserved_seeds"],[22409,22599])
        config["cases"][0]["seed"]=22409
        with self.assertRaises(ValueError):io.validate(config)

    def test_one_task_without_window_fails_qualification_despite_valid_records(self):
        p=deepcopy(self.packet);p["records"]=p["records"][:3]
        p["events"]=[r for r in p["events"] if r["unit"]<3];p["private"]=p["private"][:9]
        p["manifest"]["config"]["cases"]=p["manifest"]["config"]["cases"][:3]
        p["manifest"]["config"]["executions"]=3
        p["summary"].update(rows=[io.compact(r) for r in p["records"]], completed_executions=3,
            lifecycle=p["records"][-1]["ledger_after_close"], controlled_steps=sum(r["total_steps"] for r in p["records"]),
            private_witness_records=9, event_count=len(p["events"]))
        result=replay(p)
        self.assertEqual(result["qualification"],"NOT_QUALIFIED")
        self.assertEqual([r["complete_windows"] for r in result["task_rows"]],[1,0,0])

    def test_status_must_match_full_cost_summary(self):
        summary=self.packet["summary"];status={k:v for k,v in summary.items() if k!="rows"}
        audit.audit_status(summary,status)
        status["controlled_steps"]-=1
        with self.assertRaises(ValueError):audit.audit_status(summary,status)


if __name__=="__main__":unittest.main()
