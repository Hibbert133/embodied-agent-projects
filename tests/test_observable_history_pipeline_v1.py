"""Tiny native fixtures are software checks, never new scientific MetaWorld data."""
from contextlib import ExitStack,contextmanager,redirect_stdout
from copy import deepcopy
import io as textio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import gymnasium as gym
import mujoco

from src.analysis import observable_history_io_v1 as io
from src.analysis import observable_history_collect_v1 as collector
from src.analysis import observable_history_audit_v1 as audit
from src.analysis import delayed_qualification_io_v2 as witness_io
from src.probe import observable_history_behavior_v1 as behavior
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_paired_probe_host_v1 import TinyPolicy
from tests.test_movement_task_pipeline_v1 import TaskFixture,LAYERS
from tests.test_short_probe_execution_reference_v1 import fit as cold_fit

SOFTWARE_RECEIPTS=[]


@contextmanager
def stubs():
    with patch.object(audit,"create_task_policy",return_value=TinyPolicy()),patch.object(audit,"infer_four",return_value=cold_fit((0.,0.))),patch.object(audit,"infer_operator",return_value=cold_fit((0.,0.),nfev=2)):yield


def fixture(partial=False):
    modes=["partial"] if partial else ["normal","early_prefix","early_movement","unreachable"]
    specs=[{"case_id":f"SOFTWARE/{i}/{context}/{p}","split":"TEST","group":i,"unit":i,"task":io.TASKS[i%3],"seed":790301+i,"variant":context+"/"+p,
        "context":context,"measurement_program":p,"planned_boundary":16,"noise_namespace":57001} for i in range(len(modes)) for context in ("NOMINAL_UNCHANGED","NOMINAL_CHANGED") for p in io.PROGRAMS]
    if partial:specs=specs[:1]
    manifest={"experiment_run_id":"OBSERVABLE_HISTORY_SOFTWARE_ONLY","manifest_id":"SOFTWARE_MANIFEST","source_git_commit":"SOFTWARE_COMMIT","config":{"population":{"TEST":specs}}}
    cell={};envs=[];frames=0;receipt={"scope":"SOFTWARE_ONLY","partial_requested":partial}
    native_original=mujoco.mj_step;simulate_original=TaskFixture.do_simulation;reset_original=TaskFixture.reset
    def native(*a,**kw):
        nonlocal frames
        result=native_original(*a,**kw);frames+=int(kw.get("nstep",a[2] if len(a)>2 else 1));return result
    def simulate(env,ctrl,n):return cell["ledger"].simulation_call(simulate_original,env,ctrl,n)
    def reset(env,**kw):return cell["ledger"].reset_call(reset_original,env,**kw)
    @contextmanager
    def instrument(ledger,*unused):
        cell["ledger"]=ledger
        with patch.object(TaskFixture,"do_simulation",simulate),patch.object(TaskFixture,"reset",reset),patch.object(mujoco,"mj_step",native):yield
    def factory(task,seed):
        env=gym.wrappers.RecordEpisodeStatistics(TaskFixture(modes[seed-790301]));envs.append(env)
        with cell["ledger"].scope("GOAL_GENERATION"):
            for _ in range(50):env.reset()
        return env
    try:
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);path=root/"manifest.json";io.write(path,manifest);(root/"cal").mkdir();io.write(root/"cal/audit.json",{"integrity":"PASSED"})
            io.write(root/"test_lock.json",{"status":"FROZEN_BEFORE_TEST","saved_ns":0,"artifact_sha256":{}})
            stack.enter_context(patch.object(io,"load",return_value=manifest));stack.enter_context(patch.object(io,"clean"));stack.enter_context(patch.object(io,"git",return_value="SOFTWARE_COMMIT"))
            stack.enter_context(patch.object(collector,"create_task_environment",factory));stack.enter_context(patch.object(collector,"create_task_policy",return_value=TinyPolicy()))
            stack.enter_context(patch.object(LifecycleLedger,"instrument",instrument));stack.enter_context(patch.object(witness_io,"expected_layers",return_value=LAYERS))
            stack.enter_context(patch.object(behavior,"infer_four",return_value=cold_fit((0.,0.))));stack.enter_context(patch.object(behavior,"infer_operator",return_value=cold_fit((0.,0.),nfev=2)))
            stack.enter_context(stubs())
            with redirect_stdout(textio.StringIO()):
                if partial:
                    with unittest.TestCase().assertRaises(RuntimeError):collector.collect(path,"TEST")
                else:collector.collect(path,"TEST")
            folder=root/"test";result=None
            if partial:
                with unittest.TestCase().assertRaises(ValueError):audit.audit_split(path,"TEST")
            else:result=audit.audit_split(path,"TEST")
            packet={"manifest":manifest,"cases":list(io.rows(folder/"cases.jsonl.gz")),"events":list(io.rows(folder/"events.jsonl.gz")),"private":list(io.rows(folder/"witnesses.jsonl.gz")),
                "summary":io.read(folder/"summary.json"),"audit":result,"failed":io.read(folder/"failed_execution.json") if partial else None}
            with unittest.TestCase().assertRaises(FileExistsError):collector.collect(path,"TEST")
            receipt["completed"]=True;return packet
    finally:
        for env in envs:env.close()
        receipt.update(native_frames=frames,constructed_tiny_envs=len(envs),lifecycle=None if "ledger" not in cell else cell["ledger"].snapshot(),new_metaworld_steps=0,new_scientific_seeds=0,new_api_calls=0)
        SOFTWARE_RECEIPTS.append(receipt)


def replay(packet):
    ledger={"counts":{},"by_phase":{}};models=io.read(io.ROOT/io.C8)["joint"]
    with stubs():
        for spec,case in zip(packet["manifest"]["config"]["population"]["TEST"],packet["cases"]):
            events=[e for e in packet["events"] if e["case_id"]==spec["case_id"]];private=[e for e in packet["private"] if e["case_id"]==spec["case_id"]]
            ledger,_=audit.audit_case(spec,case,events,private,models[spec["task"]],ledger)
    return ledger


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.packet=fixture()

    def test_common_actual_pre_measurement_and_divergent_post_state(self):
        p=self.packet;self.assertEqual(p["audit"]["common_pre_measurement_pairs"],8);self.assertGreater(p["audit"]["post_measurement_diverged_pairs"],0)
        self.assertEqual(p["audit"]["witness_records_checked"],80);self.assertEqual(p["summary"]["executions"],16)
        self.assertEqual(p["summary"]["lifecycle"]["counts"]["reset_completed"],16*51)
        self.assertEqual(p["summary"]["lifecycle"]["counts"]["simulation_frames_completed"],16*25500+p["summary"]["control_steps"]*5)

    def test_saved_measurement_program_drives_actual_commands(self):
        a,b=self.packet["cases"][:2];commands=[]
        for case in (a,b):
            measurement=[e["payload"] for e in case["behavior"]["events"] if e["kind"]=="COMMAND" and e["payload"]["phase"].startswith("MEASURE_")]
            self.assertEqual(len(measurement),8);commands.append([r["command"] for r in measurement])
            self.assertTrue(all((r["raw_policy"] is None)==(case["measurement_program"]=="BALANCED8") for r in measurement))
        self.assertNotEqual(*commands)

    def test_early_success_short_history_and_partial_work_retained(self):
        self.assertEqual(self.packet["cases"][4]["stop_reason"],"EARLY_PREFIX_END");self.assertEqual(self.packet["cases"][4]["measurement_steps"],0)
        self.assertEqual(self.packet["cases"][12]["reposition_steps"],64);self.assertEqual(self.packet["cases"][12]["measurement_steps"],8)

    def test_tampering_noise_future_choice_or_measurement_is_rejected(self):
        for mutation in ("noise","future","measurement","clip","clock"):
            p=deepcopy(self.packet);event=next(e for e in p["events"] if e["event"]=="STEP_COMPLETE")
            if mutation=="noise":event["noise_cursor_after"]+=1
            elif mutation=="clip":event["executed_action_oracle"][0]=.123
            elif mutation=="clock":event["simulation_time_after"]+=.1
            else:
                e=next(e for e in p["events"] if e["event"]=="AGENT_EVENT" and e["agent_event"]=="COMMAND" and e["public_payload"]["phase"]=="MEASURE_BALANCED")
                if mutation=="future":e["public_payload"]["decision_sequence"]=e["public_payload"]["sequence"]+1
                else:e["public_payload"]["measurement_desired"][0]=.3
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):replay(p)

    def test_common_pair_physical_mismatch_fails(self):
        a,b=deepcopy(self.packet["cases"][:2]);b["physical_rows"][0]["command"][0]=.1
        with self.assertRaises(ValueError):audit.compare_pair(a,b,(0,1,2),16)

    def test_partial_native_failure_not_replaced(self):
        p=fixture(True);self.assertEqual(p["summary"]["status"],"FAILED_PARTIAL");self.assertEqual(p["summary"]["executions"],0)
        self.assertEqual(p["failed"]["host_attempts"],20);self.assertEqual(p["failed"]["host_returned"],19);self.assertTrue(p["failed"]["environment_closed"])


if __name__=="__main__":unittest.main()
