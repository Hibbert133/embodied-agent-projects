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

from scripts import collect_selected_response_v1 as collector
from scripts import audit_selected_response_v1 as audit
from src.analysis import selected_response_io_v1 as io
from src.analysis import delayed_qualification_io_v2 as witness_io
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit
import boundary_prefix

PIPELINE_RECEIPTS = []


from tests import test_local_reprobe_qualification_v1 as fixture
QualificationEnv = fixture.QualificationEnv
LAYERS = fixture.LAYERS


@contextmanager
def audit_stubs():
    with patch.object(audit,"create_task_policy",return_value=TinyPolicy()), patch.object(
            audit,"infer_four",return_value=fit((0.,0.))), patch.object(
            audit,"infer_operator",return_value=fit((0.,0.),nfev=2)), patch.object(io,"expected_layers",return_value=LAYERS):
        yield


def read_lines(path):
    with gzip.open(path,"rt",encoding="utf-8") as f:return [json.loads(line) for line in f]


def pipeline(stage="train", *, partial=False, failure_mode="partial"):
    config=io.expected_config()
    specs=[("push-v3",16,"normal"),("reach-v3",32,"early"),("door-open-v3",64,"unreachable"),
           ("reach-v3",16,"normal"),("door-open-v3",16,"normal")]
    if partial:specs=[("push-v3",16,failure_mode)]
    variants = ("TRAIN",) if stage == "train" else ("UNCHANGED","CHANGED")
    config[stage+"_cases"]=[{"unit":i,"task":task,"seed":700111+i,"variant":variant,"planned_boundary":boundary}
                     for i,(task,boundary,_) in enumerate(specs) for variant in variants]
    if partial:config[stage+"_cases"]=config[stage+"_cases"][:1]
    models={task:{**model(),"task":task} for task in io.TASKS}
    manifest={"experiment_run_id":"SELECTED_RESPONSE_TINY_SOFTWARE_ONLY","manifest_id":"SOFTWARE_MANIFEST",
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
            stack.enter_context(patch.object(io,"bank",return_value=(manifest,{**manifest,"models_sha256":"SOFTWARE_ONLY_BANK","models_closed_ns":1,"model_audit_completed_ns":2,"model_audit_sha256":"SOFTWARE_AUDIT"})))
            if partial:
                with redirect_stdout(textio.StringIO()):
                    try:collector.collect(path,stage)
                    except collector.CollectionFailure:pass
                    else:raise AssertionError("partial native failure was hidden")
            else:
                with redirect_stdout(textio.StringIO()):collector.collect(path,stage)
            folder=path.parent/stage;hashes={p.name:io.sha(p) for p in folder.iterdir()}
            if partial:
                with unittest.TestCase().assertRaises(ValueError):audit.audit(path,stage)
                result=None
            else:result=audit.audit(path,stage)
            assert hashes=={p.name:io.sha(p) for p in folder.iterdir()}
            packet={"manifest":manifest,"models":models,"records":read_lines(folder/"cases.jsonl.gz"),
                "events":read_lines(folder/"events.jsonl.gz"),"private":read_lines(folder/"state_witnesses.jsonl.gz"),
                "summary":io.read(folder/"summary.json"),"audit":result,
                "failed":io.read(folder/"failed_execution.json") if partial else None}
            with unittest.TestCase().assertRaises(FileExistsError):collector.collect(path,stage)
            if not partial:
                with unittest.TestCase().assertRaises(FileExistsError):audit.audit(path,stage)
            record.update(completed=True,rows=packet["summary"]["rows"],audit=result)
            return packet
    finally:
        for env in envs:env.close()
        record.update(native_frames=frames,actual_policy_queries=queries,constructed_tiny_envs=len(envs),
            lifecycle=None if "ledger" not in cell else cell["ledger"].snapshot(),
            new_metaworld_steps=0,new_scientific_seeds=0,new_api_calls=0)
        PIPELINE_RECEIPTS.append(record)


def replay(packet):
    with audit_stubs():
        return audit.audit_stream(packet["manifest"],packet["models"],packet["summary"]["stage"],
            iter(packet["records"]),iter(packet["events"]),iter(packet["private"]),packet["summary"])


class SelectedResponsePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train = pipeline();cls.qualify = pipeline("qualify")

    def test_nominal_and_paired_collection_independently_reconstructed(self):
        self.assertEqual(self.train["audit"]["executions"],5)
        self.assertEqual(self.qualify["audit"]["executions"],10)
        self.assertEqual(len(self.qualify["audit"]["matched_pairs"]),5)
        self.assertEqual([r["complete_window"] for r in self.train["records"]],[True,False,False,True,True])
        self.assertTrue(all(not r["context_applied"] for r in self.train["records"]))
        self.assertTrue(all(r["fault_oracle"] == io.NOMINAL for r in self.train["records"]))

    def test_program_assignment_precedes_factory_and_commands_are_consumed(self):
        for row in self.train["records"]:
            events = [e for e in self.train["events"] if e["unit"] == row["unit"]]
            self.assertEqual(events[0]["event"],"COLLECTION_ASSIGNMENT")
            self.assertEqual(events[0]["nominal_program"],io.program(row["seed"]))
            sent = [e["command"] for e in events if e["event"] == "STEP_COMPLETE" and e["phase"] == "WARM_PROBE"]
            self.assertEqual(sent,io.program(row["seed"])[:len(sent)])
        self.assertNotEqual(io.program(700111),io.program(700112))

    def test_nominal_assignment_and_state_leakage_tampering_rejected(self):
        edits = [lambda p:p["events"][0]["nominal_program"][0].__setitem__(0,.1),
                 lambda p:p["events"][0].__setitem__("model_bank_sha256","WRONG"),
                 lambda p:p["summary"].__setitem__("collection_started_ns",p["events"][0]["saved_ns"]+1),
                 lambda p:p["records"][0].__setitem__("complete_window",False)]
        for edit in edits:
            p=deepcopy(self.train);edit(p)
            with self.assertRaises(ValueError):replay(p)
        p=deepcopy(self.train)
        event=next(e for e in p["events"] if e["event"]=="AGENT_EVENT" and e["agent_event"]=="REACQUIRE_CHOICE")
        event["public_payload"]["start"]["seed"]=700111
        with self.assertRaises(ValueError):replay(p)

    def test_missing_extra_case_event_and_private_record_rejected(self):
        for key in ("records","events","private"):
            for extra in (False,True):
                p=deepcopy(self.qualify)
                if extra:p[key].append(deepcopy(p[key][-1]))
                else:p[key].pop()
                with self.assertRaises(ValueError):replay(p)

    def test_audit_never_calls_physics_collector_or_actor(self):
        with patch.object(collector,"collect",side_effect=AssertionError),patch.object(collector,"execute_nominal",side_effect=AssertionError),patch.object(mujoco,"mj_step",side_effect=AssertionError):
            self.assertEqual(replay(self.train)["executions"],5)

    def test_partial_failure_retains_native_cost_and_no_restart(self):
        packet=pipeline(partial=True)
        self.assertEqual(packet["summary"]["status"],"FAILED_PARTIAL")
        self.assertEqual(packet["summary"]["completed_executions"],0)
        self.assertEqual((packet["failed"]["host_attempts"],packet["failed"]["host_returned"]),(20,19))
        self.assertEqual(packet["failed"]["ledger_after_close"]["counts"]["simulation_frames_completed"],25600)

    def test_missing_model_bank_prevents_environment_creation(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(io,"clean"),patch.object(io,"load",return_value=(self.qualify["manifest"],{})),patch.object(io,"git",return_value="SOFTWARE_COMMIT"),patch.object(collector,"create_task_environment",side_effect=AssertionError) as factory:
            path=Path(folder)/"manifest.json";io.write(path,self.qualify["manifest"])
            with self.assertRaises(FileNotFoundError):collector.collect(path,"qualify")
            factory.assert_not_called();self.assertFalse((path.parent/"qualify").exists())

    def test_registered_allocation_and_independent_operator_groups(self):
        c=io.expected_config();io.validate(c)
        self.assertEqual([r["seed"] for r in c["train_cases"]],list(range(23200,24352)))
        self.assertEqual([r["seed"] for r in c["qualify_cases"]],[s for s in range(24500,24644) for _ in range(2)])
        for stage in io.STAGES:self.assertLessEqual(io.limits(c,stage)["scheduled_maximum_control_steps"],500*len(c[stage+"_cases"]))
        changed=[r for r in c["qualify_cases"] if r["variant"]=="CHANGED"]
        self.assertEqual(io.destination(changed[0]),io.destination(changed[8]))
        self.assertNotEqual(io.destination(changed[8]),io.destination(changed[9]))
        c["train_cases"][0]["seed"]=24352
        with self.assertRaises(ValueError):io.validate(c)


from scripts import evaluate_selected_response_v1 as evaluation
from scripts import audit_selected_response_analysis_v1 as numeric
from tests import test_selected_response_reference_v1 as algebra


class SelectedResponseNumericalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dataclasses import asdict
        cls.samples=algebra.training();cls.mappings=[asdict(s) for s in cls.samples]
        cls.models={m:algebra.selected.fit_response(cls.samples,"push-v3",method=m) for m in algebra.selected.METHODS}

    def test_training_audit_uses_separate_regression_and_detects_coefficients(self):
        with patch.object(algebra.selected,"fit_response",side_effect=AssertionError):
            for model in self.models.values():self.assertEqual(numeric.train_check(self.mappings,model)["windows"],320)
        model=deepcopy(self.models["SELECTED_POSE_HISTORY"]);model["offset"][0]+=.0001
        with self.assertRaises(ValueError):numeric.train_check(self.mappings,model)

    def test_independent_inverse_and_pose_rejection_match(self):
        from dataclasses import asdict
        window=algebra.window([[1.15,.12,.13],[-.08,.91,-.09]])
        for model in self.models.values():
            expected=algebra.selected.infer_operator(model,window)
            with patch.object(algebra.selected,"infer_operator",side_effect=AssertionError):actual=numeric.inference(model,asdict(window))
            self.assertEqual(actual["valid"],expected["valid"])
            for key in ("matrix_xy","bias_xy"):numeric.close(actual[key],expected[key])
        model=deepcopy(self.models["SELECTED_POSE_HISTORY"]);model["training_hand_max"][0]=0.
        self.assertEqual(numeric.inference(model,asdict(window))["reason"],"OUTSIDE_OBSERVED_TRAINING_POSE_BOX")

    def test_evaluator_only_supplies_visible_window_and_retains_failures(self):
        from dataclasses import asdict
        window=algebra.window([[1.,0.,0.],[0.,1.,0.]])
        source={"task":"push-v3","boundary_ready":True,"fault_oracle":{"SHOULD_NOT_ENTER":123},
            "reacquisition":{"public":{"window":asdict(window),"relocation_evidence":{"controller":{"matrix_xy":[[1.,0.],[0.,1.]],"offset":[.1,-.2,0.,0.]}},"reason":"COMPLETE_UNQUALIFIED"}},
            "prefix":{"public":{"events":[{"kind":"FIT_RESULT","payload":{"at_calls":8,"fit":{"valid":True,"matrix_xy":[[1.,0.],[0.,1.]],"bias_xy":[0.,0.]}}}]}}}
        seen=[]
        def infer(model,passed):
            self.assertIs(type(passed),algebra.SelectedAnchorWindow);seen.append(passed)
            return {"valid":False,"reason":"SOFTWARE_INVALID","nfev":0}
        with patch.object(evaluation,"infer_operator",side_effect=infer):fits=evaluation.estimates(source,{"push-v3":self.models})
        self.assertEqual(len(seen),3);self.assertEqual(fits["RELOCATION_INTEGRAL"]["bias_xy"],[-.1,.2])
        source["reacquisition"]["public"]["window"]=None
        with patch.object(evaluation,"infer_operator",side_effect=AssertionError):fits=evaluation.estimates(source,{})
        self.assertFalse(fits["SELECTED_POSE_HISTORY"]["valid"]);self.assertTrue(fits["SAVED_C8"]["valid"])
        source["boundary_ready"]=False
        fits=evaluation.estimates(source,{})
        self.assertTrue(all(not f["valid"] for f in fits.values()))
        self.assertEqual(evaluation.score(fits["SAVED_C8"],io.INITIAL,io.expected_config())["score"],10.5)

    def test_full_population_statistics_costs_and_tamper_detection(self):
        c=io.expected_config();rows=[]
        for spec in c["qualify_cases"]:
            row={**spec,"group":spec["unit"]//9,"total_steps":40,"reposition_steps":16,"probe_steps":8,
                "success":False,"boundary_ready":True,"complete_window":True,"collection_stop_reason":"COMPLETE_UNQUALIFIED","fits":{},"errors":{}}
            for method in evaluation.ALL_METHODS:
                value=.1 if method==c["candidate"] else .3
                row["fits"][method]={"valid":True,"reason":"SOFTWARE","nfev":2 if method in evaluation.METHODS else 0}
                row["errors"][method]={"score":value,"matrix_error":value,"bias_error":0.,"penalty_applied":False}
            rows.append(row)
        train={"total_steps":1000,"lifecycle":{"counts":{"reset_completed":510,"simulation_frames_completed":260000},"by_phase":{"CONTROLLED_RESET":{"reset_completed":10}}}}
        bank={"training_costs":train};audit={"costs":{"SOFTWARE":True}}
        summary={**evaluation.summarize(rows,c),"costs":evaluation.costs(rows,bank,audit,c)}
        numeric.summary_check(rows,summary,c,bank,audit)
        self.assertEqual(summary["qualification"],"QUALIFIED_IDENTIFICATION_ONLY")
        self.assertEqual(summary["contrasts"][0]["groups"],16)
        for edit in (lambda s:s["contrasts"][0]["ci95"].__setitem__(1,.2),lambda s:s["costs"]["method_accounting"][0].__setitem__("new_nominal_steps",0)):
            changed=deepcopy(summary);edit(changed)
            with self.assertRaises(ValueError):numeric.summary_check(rows,changed,c,bank,audit)
        for row in rows[:18]:
            row["boundary_ready"]=False;row["complete_window"]=False;row["collection_stop_reason"]="ENDED_BEFORE_BOUNDARY"
            for method in evaluation.ALL_METHODS:
                row["fits"][method].update(valid=False,reason="PLANNED_BOUNDARY_UNAVAILABLE")
                row["errors"][method].update(score=10.5,matrix_error=8.,bias_error=1.,penalty_applied=True)
        summary={**evaluation.summarize(rows,c),"costs":evaluation.costs(rows,bank,audit,c)}
        numeric.summary_check(rows,summary,c,bank,audit)
        self.assertEqual(summary["planned_boundary_unavailable"],18)
        self.assertTrue(all(r["attempts"]==288 for r in summary["methods"]))

    def prepare_algebra_training(self,path):
        """Trusted record-audit fixture, not physical data or a grammar-audit substitute."""
        identity={"experiment_run_id":"ALGEBRA_ONLY","manifest_id":"ALGEBRA_MANIFEST","source_git_commit":"SOFTWARE_COMMIT"}
        c=io.expected_config();train=[]
        for task in io.TASKS:
            for sample in self.mappings:
                sample=deepcopy(sample);sample["task"]=task
                train.append({"task":task,"variant":"TRAIN","fault_oracle":io.NOMINAL,"complete_window":True,"reacquisition":{"public":{"nominal_trajectory":sample}}})
        c["train_cases"]=[{"unit":i,"task":r["task"],"seed":710000+i,"variant":"TRAIN","planned_boundary":16} for i,r in enumerate(train)]
        manifest={**identity,"config":c};io.write(path,manifest)
        folder=path.parent/"train";folder.mkdir()
        with gzip.open(folder/"cases.jsonl.gz","xt",encoding="utf-8") as handle:
            for r in train:handle.write(json.dumps(r)+"\n")
        for name in ("events.jsonl.gz","state_witnesses.jsonl.gz"):
            with gzip.open(folder/name,"xt",encoding="utf-8"):pass
        io.write(folder/"summary.json",{"collection_closed_ns":1});io.write(folder/"status.json",{"scope":"ALGEBRA_ONLY"})
        cost={"total_steps":1000,"lifecycle":{"counts":{"reset_completed":510,"simulation_frames_completed":260000},"by_phase":{"CONTROLLED_RESET":{"reset_completed":10}}}}
        (path.parent/"train_audit").mkdir()
        io.write(path.parent/"train_audit/record_audit.json",{**identity,"integrity":"PASSED","stage":"train",
            "rows":[{"task":r["task"],"complete_window":True} for r in train],"costs":cost,
            "collection_artifact_sha256":{p.name:io.sha(p) for p in folder.iterdir()}})
        return manifest

    def test_frozen_bank_then_file_evaluation_and_independent_numeric_audit(self):
        from dataclasses import asdict
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            path=Path(temp)/"manifest.json";manifest=self.prepare_algebra_training(path)
            stack.enter_context(patch.object(io,"load",return_value=(manifest,{})))
            stack.enter_context(patch.object(io,"clean"));stack.enter_context(patch.object(io,"git",return_value="SOFTWARE_COMMIT"))
            with redirect_stdout(textio.StringIO()):collector.fit_models(path)
            with self.assertRaises(FileNotFoundError):io.bank(path)
            numeric.check_models(path);bank,done=io.bank(path)
            self.assertGreater(done["model_audit_completed_ns"],done["models_closed_ns"])
            with self.assertRaises(FileExistsError):collector.fit_models(path)
            with self.assertRaises(FileExistsError):numeric.check_models(path)
            # Every stored dependency is rehashed, including raw TRAIN and audit.
            for changed in ("models.json","train/cases.jsonl.gz","train_audit/record_audit.json"):
                target=path.parent/changed;original=target.read_bytes();target.write_bytes(original+b" ")
                with self.assertRaises(ValueError):io.bank(path)
                target.write_bytes(original)
            manifest["config"]["qualify_cases"]=manifest["config"]["qualify_cases"][:18]
            for spec in manifest["config"]["qualify_cases"]:spec["seed"]=720000+spec["unit"]
            io.write(path,manifest,exclusive=False)
            sources=[]
            for spec in manifest["config"]["qualify_cases"]:
                window=asdict(algebra.window([[1.1,.05,.07],[-.04,.9,-.06]]));window["task"]=spec["task"]
                source={**spec,"boundary_ready":True,"complete_window":True,"collection_stop_reason":"COMPLETE_UNQUALIFIED",
                    "success":False,"total_steps":40,"reposition_steps":16,"probe_steps":8,
                    "reacquisition":{"public":{"window":window,"reason":"COMPLETE_UNQUALIFIED","relocation_evidence":{"controller":{"matrix_xy":[[1.,0.],[0.,1.]],"offset":[-.12,.08,0.,0.]}}}},
                    "prefix":{"public":{"events":[{"kind":"FIT_RESULT","payload":{"at_calls":8,"fit":{"valid":True,"matrix_xy":[[1.,0.],[0.,1.]],"bias_xy":[.12,-.08]}}}]}}}
                if spec["unit"]==0:source.update(boundary_ready=False,complete_window=False,collection_stop_reason="ENDED_BEFORE_BOUNDARY",success=True,total_steps=14,reposition_steps=0,probe_steps=0)
                if spec["unit"]==1:
                    source.update(complete_window=False,collection_stop_reason="ANCHOR_NOT_REACHED",total_steps=80,reposition_steps=64,probe_steps=0)
                    source["reacquisition"]["public"].update(window=None,reason="ANCHOR_NOT_REACHED")
                sources.append(source)
            folder=path.parent/"qualify";folder.mkdir()
            with gzip.open(folder/"cases.jsonl.gz","xt",encoding="utf-8") as handle:
                for r in sources:handle.write(json.dumps(r)+"\n")
            (path.parent/"qualify_audit").mkdir()
            identity={k:manifest[k] for k in io.IDENTITY}
            io.write(path.parent/"qualify_audit/record_audit.json",{**identity,"integrity":"PASSED","stage":"qualify","costs":{"SOFTWARE":True},"collection_artifact_sha256":{"cases.jsonl.gz":io.sha(folder/"cases.jsonl.gz")}})
            summary=evaluation.evaluate(path)
            with patch.object(evaluation,"evaluate",side_effect=AssertionError),patch.object(evaluation,"summarize",side_effect=AssertionError),patch.object(algebra.selected,"infer_operator",side_effect=AssertionError):
                checked=numeric.check_evaluation(path)
            self.assertEqual(checked["cases"],18);self.assertEqual(checked["integrity"],"PASSED")
            self.assertEqual(summary["planned_boundary_unavailable"],2)
            self.assertFalse(summary["task_utility_demonstrated"])
            with self.assertRaises(FileExistsError):evaluation.evaluate(path)
            with self.assertRaises(FileExistsError):numeric.check_evaluation(path)

    def test_training_support_failure_is_persisted_and_blocks_qualification(self):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            path=Path(temp)/"manifest.json";manifest=self.prepare_algebra_training(path)
            stack.enter_context(patch.object(io,"load",return_value=(manifest,{})))
            stack.enter_context(patch.object(io,"clean"));stack.enter_context(patch.object(io,"git",return_value="SOFTWARE_COMMIT"))
            stack.enter_context(patch.object(collector,"fit_response",side_effect=ValueError("UNSUPPORTED_SOFTWARE_FIXTURE")))
            with redirect_stdout(textio.StringIO()):collector.fit_models(path)
            bank=io.read(path.parent/"models.json")
            self.assertEqual(bank["status"],"FAILED_TRAIN_SUPPORT");self.assertEqual(len(bank["fits"]),9)
            with patch.object(collector,"create_task_environment",side_effect=AssertionError) as factory:
                with self.assertRaises(ValueError):collector.collect(path,"qualify")
                factory.assert_not_called()
            self.assertFalse((path.parent/"qualify").exists())
            with self.assertRaises(FileExistsError):collector.fit_models(path)


if __name__ == "__main__":unittest.main()
