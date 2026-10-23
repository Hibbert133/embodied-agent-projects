"""Frozen response qualification: pure causal arrays and separate tiny native fixtures."""
from contextlib import ExitStack,contextmanager,redirect_stdout
from copy import deepcopy
from dataclasses import replace
import io as textio
from pathlib import Path
import tempfile
import gzip
import json
import socket
import unittest
from unittest.mock import patch

import gymnasium as gym
import mujoco
import numpy as np

from src.analysis import response_qualification_io_v1 as io
from src.analysis import response_qualification_collect_v1 as collector
from src.analysis import response_qualification_audit_v1 as audit
from src.analysis import response_qualification_evaluation_v1 as evaluation
from src.analysis import delayed_qualification_io_v2 as witness_io
from src.probe import response_qualification_behavior_v1 as behavior
from src.probe import response_qualification_model_v1 as model
from src.probe.continuous import StepObservation
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_paired_probe_host_v1 import TinyPolicy
from tests.test_movement_task_pipeline_v1 import TaskFixture,LAYERS
from tests.test_short_probe_execution_reference_v1 import fit as cold_fit

SOFTWARE_RECEIPTS=[]


def trajectory(n=80,key="SYNTHETIC",split="TRAIN"):
    rng=np.random.default_rng(721);commands=rng.uniform(-.7,.7,(n,4));states=[np.zeros(39)]
    for u in commands:
        obs=states[-1].copy();last=states[-1][:3]-states[-2][:3] if len(states)>1 else np.zeros(3)
        prior=states[-2][:3]-states[-3][:3] if len(states)>2 else np.zeros(3)
        obs[:2]+=.003*u[:2]+.2*last[:2]-.1*prior[:2]+[.0001,-.0002]
        obs[2]+=.001*u[2];obs[3]=u[3];obs[4:7]=[.1,.6,.02];obs[-3:]=[.2,.7,.1];states.append(obs)
    return model.VisibleTrajectory("push-v3",key,split,states[0],commands,states[1:])


@contextmanager
def audit_stubs():
    with patch.object(audit,"create_task_policy",return_value=TinyPolicy()),patch.object(audit,"infer_four",return_value=cold_fit((0.,0.))),patch.object(
            audit,"infer_operator",return_value=cold_fit((0.,0.),nfev=2)):yield


def fixture(*,partial=False):
    variants=("UNCHANGED","CHANGED");modes=["normal","early_prefix","early_movement","unreachable"] if not partial else ["partial"]
    specs=[{"case_id":f"SOFTWARE/{i}/{v}","split":"QUAL","group":i,"unit":i,"task":io.TASKS[i%3],"seed":780301+i,
        "variant":v,"planned_boundary":16,"noise_namespace":47001} for i in range(len(modes)) for v in variants]
    if partial:specs=specs[:1]
    manifest={"experiment_run_id":"RESPONSE_SOFTWARE_ONLY","manifest_id":"SOFTWARE_MANIFEST","source_git_commit":"SOFTWARE_COMMIT",
        "config":{"population":{"QUAL":specs}}}
    cell={};envs=[];frames=0;receipt={"scope":"SOFTWARE_ONLY_NOT_SCIENTIFIC_POPULATION","partial_requested":partial}
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
        env=gym.wrappers.RecordEpisodeStatistics(TaskFixture(modes[seed-780301]));envs.append(env)
        with cell["ledger"].scope("GOAL_GENERATION"):
            for _ in range(50):env.reset()
        return env
    try:
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);path=root/"manifest.json";io.write(path,manifest)
            (root/"cal").mkdir();io.write(root/"cal/audit.json",{"integrity":"PASSED"})
            io.write(root/"qualification_lock.json",{"status":"FROZEN_BEFORE_QUAL_COLLECTION","saved_ns":0,"artifact_sha256":{}})
            stack.enter_context(patch.object(io,"load",return_value=manifest));stack.enter_context(patch.object(io,"clean"));stack.enter_context(patch.object(io,"git",return_value="SOFTWARE_COMMIT"))
            stack.enter_context(patch.object(collector,"create_task_environment",factory));stack.enter_context(patch.object(collector,"create_task_policy",return_value=TinyPolicy()))
            stack.enter_context(patch.object(LifecycleLedger,"instrument",instrument));stack.enter_context(patch.object(witness_io,"expected_layers",return_value=LAYERS))
            stack.enter_context(patch.object(behavior,"infer_four",return_value=cold_fit((0.,0.))));stack.enter_context(patch.object(behavior,"infer_operator",return_value=cold_fit((0.,0.),nfev=2)))
            stack.enter_context(audit_stubs())
            with redirect_stdout(textio.StringIO()):
                if partial:
                    with unittest.TestCase().assertRaises(RuntimeError):collector.collect(path,"QUAL")
                else:collector.collect(path,"QUAL")
            folder=root/"qual";result=None
            if not partial:result=audit.audit_split(path,"QUAL")
            else:
                with unittest.TestCase().assertRaises(ValueError):audit.audit_split(path,"QUAL")
            packet={"manifest":manifest,"cases":list(io.rows(folder/"cases.jsonl.gz")),"events":list(io.rows(folder/"events.jsonl.gz")),
                "private":list(io.rows(folder/"witnesses.jsonl.gz")),"summary":io.read(folder/"summary.json"),"audit":result,
                "failed":io.read(folder/"failed_execution.json") if partial else None}
            with unittest.TestCase().assertRaises(FileExistsError):collector.collect(path,"QUAL")
            if not partial:
                with unittest.TestCase().assertRaises(FileExistsError):audit.audit_split(path,"QUAL")
            receipt["completed"]=True;return packet
    finally:
        for env in envs:env.close()
        receipt.update(native_frames=frames,constructed_tiny_envs=len(envs),lifecycle=None if "ledger" not in cell else cell["ledger"].snapshot(),
            new_metaworld_steps=0,new_scientific_seeds=0,new_api_calls=0)
        SOFTWARE_RECEIPTS.append(receipt)


def replay(packet):
    ledger={"counts":{},"by_phase":{}};models=io.read(io.ROOT/io.C8)["joint"]
    with audit_stubs():
        for spec,case in zip(packet["manifest"]["config"]["population"]["QUAL"],packet["cases"]):
            events=[e for e in packet["events"] if e["case_id"]==spec["case_id"]];private=[e for e in packet["private"] if e["case_id"]==spec["case_id"]]
            ledger,_=audit.audit_case(spec,case,events,private,models[spec["task"]],ledger)
    return ledger


class ModelTests(unittest.TestCase):
    def test_exact_feature_dimensions_and_independent_prediction(self):
        q=next(model.samples(trajectory()))[1]
        for kind,base,expanded in (("FRESH_LINEAR_ARX",10,11),("FRESH_QUADRATIC_STATE",20,231)):
            self.assertEqual(len(model.features(q,kind)),base);self.assertEqual(model.design(np.zeros(base),kind.endswith("STATE")).shape,(1,expanded))
            fitted=model.fit([trajectory()],"push-v3",kind)
            np.testing.assert_allclose(model.predict(fitted,q),audit.independent_prediction(fitted,audit.feature_array(np.array(q.observation),np.array(q.last_displacement),np.array(q.prior_displacement),q.command,kind)),atol=1e-12)

    def test_known_linear_response_and_misspecified_zero_response(self):
        t=trajectory();fitted=model.fit([t],"push-v3","FRESH_LINEAR_ARX")
        errors=[target-model.predict(fitted,q) for _,q,target in model.samples(t)]
        # Fixed ridge has a small, deliberate shrinkage residual on this collinear model.
        self.assertLess(np.sqrt(np.mean(np.array(errors)**2)),2e-6)
        wrong=deepcopy(fitted);wrong["coefficients"]=np.zeros((11,2)).tolist()
        self.assertGreater(np.sqrt(np.mean([(target-model.predict(wrong,q))**2 for _,q,target in model.samples(t)])),.0005)

    def test_weighted_means_equal_trajectory_means(self):
        a=trajectory(40,"A");b=trajectory(110,"B");m=model.fit([a,b],"push-v3","FRESH_LINEAR_ARX")
        means=[np.mean([model.features(q,"FRESH_LINEAR_ARX") for _,q,_ in model.samples(t)],axis=0) for t in (a,b)]
        np.testing.assert_allclose(m["mean"],np.mean(means,axis=0),atol=1e-14)
        self.assertEqual(m["training_responses"],146)

    def test_training_rejects_cal_qual_duplicates_and_empty_history(self):
        for t in (trajectory(split="CAL"),trajectory(split="QUAL"),trajectory(2)):
            with self.subTest(split=t.split,n=len(t.commands)),self.assertRaises(ValueError):model.fit([t],"push-v3","FRESH_LINEAR_ARX")
        with self.assertRaises(ValueError):model.fit([trajectory(),trajectory()],"push-v3","FRESH_LINEAR_ARX")

    def test_oracle_fields_and_unbounded_commands_rejected(self):
        from dataclasses import asdict
        base=asdict(trajectory())
        for key in ("seed","fault_oracle","actual_noise","executed_action_oracle","future_result"):
            with self.subTest(key=key),self.assertRaises(ValueError):model.VisibleTrajectory.from_dict({**base,key:0})
        with self.assertRaises(ValueError):replace(trajectory(),commands=[(2,0,0,0)]*80)

    def test_real_initial_history_no_padding_and_future_not_in_query(self):
        t=trajectory();rows=list(model.samples(t));self.assertEqual(rows[0][0],2)
        np.testing.assert_allclose(rows[0][1].prior_displacement,np.array(t.observations[0])[:3]-np.array(t.initial)[:3])
        later=np.array(t.observations);later[20:]+=100
        changed=list(model.samples(replace(t,observations=later)))
        for i in range(17):self.assertEqual(rows[i][1],changed[i][1]);np.testing.assert_array_equal(rows[i][2],changed[i][2])


class AllocationTests(unittest.TestCase):
    def test_online_transport_is_rejected_and_attempt_is_recorded(self):
        receipt={}
        with io.forbid_online_calls(receipt),self.assertRaises(RuntimeError):socket.create_connection(("invalid.example",443))
        self.assertEqual(receipt["attempted_network_calls"],1)

    def test_frozen_design_budget_and_disjoint_full_population(self):
        self.assertEqual(io.design()["new_data_budget"]["executions"],270)
        sets=[set(r["seed"] for r in io.population(s)) for s in io.SPLITS]
        self.assertEqual([len(io.population(s)) for s in io.SPLITS],[108,54,108])
        self.assertTrue(sets[0].isdisjoint(sets[1]) and sets[0].isdisjoint(sets[2]) and sets[1].isdisjoint(sets[2]))
        self.assertEqual(270*(25500+160*5),7101000);io.validate(io.expected_config())

    def test_operator_pairing_and_independent_noise_namespaces(self):
        specs=io.population("QUAL")
        for g in range(18):
            same_group=[io.destination(r) for r in specs if r["group"]==g and r["variant"]=="CHANGED"]
            self.assertTrue(all(v==same_group[0] for v in same_group))
            self.assertEqual(io.destination(specs[6*g]),io.initial_fault("QUAL"))
        self.assertFalse(np.array_equal(io.noise(780001,47001),io.noise(780001,47002)))
        self.assertFalse(io.noise(780001,47001).flags.writeable)

    def test_stage_gates_fail_closed_and_lock_artifacts_cannot_change(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            for s in ("CAL","QUAL"):
                with self.assertRaises(FileNotFoundError):io.phase_gate(p,s)
            io.write(p/"models.json",{})
            io.write(p/"qualification_lock.json",{"status":"FROZEN_BEFORE_QUAL_COLLECTION","artifact_sha256":{"models.json":io.sha(p/"models.json")}})
            io.phase_gate(p,"QUAL");io.write(p/"models.json",{"modified":True},exclusive=False)
            with self.assertRaises(ValueError):io.phase_gate(p,"QUAL")

    def test_saved_source_is_strict_and_manifest_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"x.json";io.write(p,{"a":1})
            with self.assertRaises(FileExistsError):io.write(p,{})
            p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):io.read(p)


class PublicActorTests(unittest.TestCase):
    def run_actor(self,end=None,invalid=False):
        state=np.zeros(39);state[:3]=[0,.6,.05];state[4:7]=[0,.8,.02]
        initial=StepObservation(tuple(state),False,False,False);events=[];commands=[];queries=[]
        def emit(kind,payload):
            value={**deepcopy(payload),"sequence":len(events),"saved_ns":len(events)+1};events.append({"kind":kind,"payload":value});return value
        def step(saved):
            self.assertEqual(events[-1]["payload"],saved);commands.append(saved)
            return StepObservation(tuple(state),False,False,len(commands)==end)
        def policy(obs):queries.append(obs.copy());return np.array([2.,.2,0,0],np.float32)
        bank=io.read(io.ROOT/io.C8)["joint"]["push-v3"];fit=cold_fit((0.,0.))
        if invalid:fit={**fit,"valid":False,"reason":"SYNTHETIC_INVALID"}
        with patch.object(behavior,"infer_four",return_value=fit),patch.object(behavior,"infer_operator",return_value=cold_fit((0.,0.),nfev=2)):
            result=behavior.run("push-v3",initial,bank,64,policy,step,emit)
        return result,commands,queries

    def test_caps_and_single_policy_query_and_saved_c8_consumption(self):
        result,commands,queries=self.run_actor();r=result["outcome"]
        self.assertEqual((r["total_steps"],r["reposition_steps"],r["task_steps"]),(160,64,32));self.assertEqual(len(queries),88)
        self.assertTrue(all(abs(u)<=1 for c in commands for u in c["command"]))
        choices=[e for e in result["events"] if e["kind"]=="CHOICE"]
        self.assertEqual([e["payload"]["action"] for e in choices],["PROBE_FOUR","SAVE_C4_ONLY","PROBE_FOUR","RUN_C8"])

    def test_early_success_and_invalid_estimate_retained(self):
        r,c,q=self.run_actor(end=6);self.assertEqual((r["outcome"]["total_steps"],len(q)),(6,0))
        r,c,q=self.run_actor(invalid=True);self.assertEqual(r["outcome"]["stop_reason"],"INVALID_FOUR");self.assertEqual(len(c),4)


class NativePipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.packet=fixture()

    def test_full_records_costs_pairs_and_early_endings(self):
        p=self.packet;a=p["audit"];self.assertEqual((a["integrity"],a["executions"],a["qual_paired_prefixes_checked"]),("PASSED",8,4))
        self.assertEqual(a["lifecycle"]["counts"]["reset_completed"],8*51)
        self.assertEqual(a["lifecycle"]["counts"]["simulation_frames_completed"],8*25500+5*a["costs"]["steps"])
        self.assertEqual({r["total_steps"] for r in p["cases"] if r["unit"]==1},{6})
        self.assertTrue(all(r["task_steps"]==0 for r in p["cases"] if r["unit"] in (1,2)))

    def test_audit_does_not_run_environment_collector_actor_or_fit_response(self):
        with patch.object(TaskFixture,"step",side_effect=AssertionError),patch.object(collector,"execute_case",side_effect=AssertionError),patch.object(
                behavior,"run",side_effect=AssertionError),patch.object(model,"fit",side_effect=AssertionError):
            self.assertEqual(replay(self.packet),self.packet["audit"]["lifecycle"])

    def test_noise_cursor_and_wrong_noise_or_clip_order_detected(self):
        for key in ("noise_cursor_after","executed_action_oracle"):
            p=deepcopy(self.packet);e=next(e for e in p["events"] if e["event"]=="STEP_COMPLETE")
            if key=="noise_cursor_after":e[key]-=1
            else:e[key][0]+=.05
            with self.subTest(key=key),self.assertRaises(ValueError):replay(p)
        u=[1.,0.,0.,0.];f={"matrix_xy":[[1,0],[0,1]],"bias_xy":[.2,0],"deadzone_xy":[0,0]}
        self.assertNotEqual(audit.applied(u,f,np.array([-.15,0,0],np.float32))[0],float(np.float32(1)-np.float32(.15)))

    def test_future_choice_stale_policy_inverse_mapping_and_extra_reset_rejected(self):
        for mode in ("future","raw","inverse","reset"):
            p=deepcopy(self.packet)
            if mode=="reset":
                e=next(e for e in p["events"] if e["event"]=="LIFECYCLE_RESET_INTENT");e["phase"]="CONTROL"
            else:
                e=next(e for e in p["events"] if e["event"]=="AGENT_EVENT" and e["agent_event"]=="COMMAND" and e["public_payload"]["phase"]=="POLICY")["public_payload"]
                if mode=="future":e["decision_sequence"]=e["sequence"]+1
                elif mode=="raw":e["raw_policy"][0]+=.1
                else:e["command"][0]*=-1
            with self.subTest(mode=mode),self.assertRaises(ValueError):replay(p)

    def test_partial_native_failure_keeps_cost_and_stops_without_replacement(self):
        p=fixture(partial=True);self.assertEqual(p["summary"]["status"],"FAILED_PARTIAL")
        self.assertEqual(p["summary"]["executions"],0);self.assertEqual(p["failed"]["host_attempts"],20)
        self.assertEqual(p["failed"]["host_returned"],19);self.assertTrue(p["failed"]["environment_closed"])
        self.assertEqual(p["summary"]["lifecycle"]["counts"]["simulation_frames_completed"],25500+20*5)


def synthetic_metrics(missing=False,bad_cell=False):
    registry=io.population("QUAL");rows=[]
    for case in registry:
        for i,n in enumerate(evaluation.MODELS):
            value=(.03,.02,.01)[i]+case["group"]*.0001
            if bad_cell and i==2 and case["task"]=="push-v3" and case["variant"]=="CHANGED":value=.05
            rows.append({**case,"condition":case["variant"],"method":n,"input_mode":"TRUE_INTERFACE","stage":"POST_TASK","rmse":None if missing and case["group"]==0 else value})
    return rows,registry


class StatisticsTests(unittest.TestCase):
    def test_whole_groups_and_full_denominators(self):
        rows,registry=synthetic_metrics();result=evaluation.statistics(rows,registry)
        self.assertEqual(result["qualification"],"PASSED_PREDICTIVE_QUALIFICATION_ONLY")
        self.assertAlmostEqual(result["primary_difference"],-.01);np.testing.assert_allclose(result["primary_group_bootstrap_95"],[-.01,-.01])
        self.assertEqual(result["independent_groups"],18);self.assertEqual([r["available_units"] for r in result["groups"]],[6]*18)
        with self.assertRaises(ValueError):evaluation.statistics(rows,registry[:-1])

    def test_missing_group_not_zero_filled_and_bad_cell_cannot_be_hidden(self):
        rows,registry=synthetic_metrics(missing=True);result=evaluation.statistics(rows,registry)
        self.assertEqual(result["qualification"],"NOT_QUALIFIED");self.assertIsNone(result["primary_difference"])
        rows,registry=synthetic_metrics(bad_cell=True);result=evaluation.statistics(rows,registry)
        self.assertFalse(result["requirements"]["no_cell_worse_than_both_linears"])

    def test_real_record_prediction_missing_stages_and_semantics(self):
        p=NativePipelineTests.packet;case=next(c for c in p["cases"] if c["unit"]==1)
        linear=model.fit([trajectory()],"push-v3","FRESH_LINEAR_ARX");quad=model.fit([trajectory()],"push-v3","FRESH_QUADRATIC_STATE")
        models={"FROZEN_OLD_LINEAR_ARX":{**linear,"method":"FROZEN_OLD_LINEAR_ARX"},"FRESH_LINEAR_ARX":linear,"FRESH_QUADRATIC_STATE":quad}
        rows,metrics=evaluation.evaluate_case(case,models)
        self.assertEqual(len(rows),(6-2)*9);self.assertEqual(len(metrics),63)
        self.assertTrue(all(r["rmse"] is None and r["n"]==0 for r in metrics if r["stage"]=="POST_TASK"))
        self.assertTrue(all(r["applied_input_semantics_changed"]==(r["input_mode"]=="APPLIED_INPUT_DIAGNOSTIC") for r in rows))


class PureEndToEndTests(unittest.TestCase):
    def test_train_cal_lock_qual_and_independent_numeric_audit_without_environment(self):
        from scripts.report_response_model_qualification_v1 import report
        manifest={"experiment_run_id":"PURE_ARRAYS_ONLY","manifest_id":"SYNTHETIC_MANIFEST","source_git_commit":"SYNTHETIC",
            "config":{"population":{s:io.population(s) for s in io.SPLITS}}}
        t=trajectory(15)
        with tempfile.TemporaryDirectory() as temp,patch.object(io,"load",return_value=manifest),patch.object(collector,"execute_case",side_effect=AssertionError("NO_ENV")):
            root=Path(temp)/"run";root.mkdir();path=root/"manifest.json";io.write(path,manifest)
            for split in io.SPLITS:
                folder=root/split.lower();folder.mkdir()
                with gzip.open(folder/"cases.jsonl.gz","xt",encoding="utf-8") as f:
                    for spec in manifest["config"]["population"][split]:
                        observations=[(np.array(obs)*(1+.01*spec["group"] if split=="QUAL" else 1)).tolist() for obs in t.observations]
                        row={**spec,"initial":{"observation":t.initial},"physical_rows":[{"command":u,"after":{"observation":obs},"phase":"TASK_AFTER_MOVEMENT","logical_step":i,"executed_action_oracle":u}
                                for i,(u,obs) in enumerate(zip(t.commands,observations))],"fault_oracle":io.initial_fault(split),"fault_transition":None,"behavior":{"events":[]},
                            "success":False,"completed":True,"host_returned":15,"c4_c8_fit_attempts":0,"c4_c8_optimizer_nfev":0,
                            "total_steps":15,"reposition_steps":0,"task_steps":15,"stop_reason":"SOFTWARE_SYNTHETIC"}
                        f.write(json.dumps(row)+"\n")
                io.write(folder/"completion.json",{"status":"COLLECTED_FOR_INDEPENDENT_AUDIT","artifact_sha256":{"cases.jsonl.gz":io.sha(folder/"cases.jsonl.gz")}})
                io.write(folder/"audit.json",{"integrity":"PASSED"})
            evaluation.train(path);audit.audit_models(path);evaluation.calibrate(path);audit.audit_calibration(path)
            # This synthetic test intentionally made all arrays; production must not open QUAL before lock.
            (root/"qual").rename(root/"not_yet_opened_qual")
            evaluation.lock(path);(root/"not_yet_opened_qual").rename(root/"qual")
            io.phase_gate(root,"QUAL");evaluation.evaluate(path);result=audit.audit_numeric(path)
            self.assertEqual(result["integrity"],"PASSED");self.assertEqual(result["predictions_checked"],108*13*9)
            self.assertEqual(result["trajectory_stage_metrics_checked"],108*63)
            io.write(root/"pipeline_completion.json",{"status":"COMPLETE","failure":None,"wall_ns":1,"new_api_calls":0})
            (Path(temp)/"reports").mkdir()
            with patch.object(io,"ROOT",Path(temp)):report(path)
            self.assertEqual(len(io.read(root/"allocation_registry.json")),270)
            self.assertEqual(len(io.read(root/"failure_registry.json")),270)
            text=(Path(temp)/"reports/response_model_qualification_v1_zh.md").read_text(encoding="utf-8")
            self.assertIn("预测",text);self.assertIn("零在线 LLM API",text)



if __name__=="__main__":unittest.main()
