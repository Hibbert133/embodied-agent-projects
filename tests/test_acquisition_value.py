import copy
from collections import deque
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_acquisition_value as run
from scripts import analyze_acquisition_value as audit
from src.probe.acquisition_value import METHODS, deadline_loss, paired_sign, repeat_consistency
from src.probe.action_response_validity import CachedPoint
from src.probe.lifecycle_ledger import LifecycleLedger


def model():
    coefficient=np.zeros((11,2));coefficient[7,0]=.006;coefficient[8,1]=.008
    return {"method":"LINEAR_ARX","training_samples":100,"mean":[0.]*10,"scale":[1.]*10,"physical_response_qualified":False,
            "probability_guarantee":False,"coefficients":coefficient.tolist(),"ridge":.001,"feature_count":11,"training_rmse":0.}


class FakeSimulator:
    def do_simulation(self, ctrl, n_frames):
        self.data.time+=n_frames*.002


class FakeEnv(FakeSimulator):
    def __init__(self):
        self.unwrapped=self;self.data=SimpleNamespace(time=0.);self.model=SimpleNamespace(opt=SimpleNamespace(timestep=.002))
        self.frame_skip=5;self.observation=np.zeros(39);self.calls=0;self.closed=False
    def reset(self,seed=None):
        self.data.time=0.;self.observation=np.zeros(39);self.calls=0
        for _ in range(100):self.do_simulation([0,0],5)
        return self.observation.copy(),{}
    def step(self, action):
        self.do_simulation([0,0],5);self.calls+=1
        self.observation[:3]+=np.asarray(action)[:3]*np.array([.006,.008,.005])
        return self.observation.copy(),0.,False,False,{"success":self.calls>=24}
    def close(self):self.closed=True


class FixedPolicy:
    def get_action(self, observation):return np.array([.15,.1,0,1],dtype=np.float32)


class AcquisitionValueTest(unittest.TestCase):
    def setUp(self):
        self.events=[]
        def emit(kind,payload):
            item={"event":kind,"sequence":len(self.events)+1,"saved_ns":run.perf_counter_ns(),**run.normal(payload)}
            self.events.append(item);return item
        self.emit=emit;self.ledger=LifecycleLedger(emit,1000000)
        self.previous=CachedPoint(((1.,0.),(0.,1.)),(0.,0.))
        self.operator={"matrix_xy":[[.8,.1],[0,1.1]],"bias_xy":[.1,-.08]}
        self.key={"experiment_run_id":"test","manifest_id":"manifest","source_git_commit":"source","stream":0,"task":"push-v3",
                  "scenario":"UNCHANGED","replicate":0,"seed":11201,"operator_id_oracle":"A"}
        self.factory=SimpleNamespace(_make_tasks=lambda:None)
    @contextmanager
    def fixtures(self):
        witness=lambda e:{"fixture":True,"time":e.data.time,"observation":e.observation.tolist()}
        with self.ledger.instrument(FakeEnv,FakeSimulator,self.factory),patch.object(run,"create_task_environment",side_effect=lambda *a:FakeEnv()), \
             patch.object(run,"create_task_policy",return_value=FixedPolicy()),patch.object(run,"physics_witness",side_effect=witness), \
             patch.object(audit.runner,"create_task_policy",return_value=FixedPolicy()):
            yield
    def branch(self,method):
        return run.normal(run.execute({**self.key,"method":method},self.operator,self.previous if method in run.PRIOR_CACHE_METHODS else None,model(),.0001,self.emit,self.ledger))
    def test_cold_source_is_fitted_only_from_its_completed_sixteen_steps(self):
        key={**self.key,"method":"CALIBRATE_OLD16","replicate":-1,"seed":11200,"scenario":"SOURCE_A"}
        with self.fixtures():record=run.normal(run.execute(key,self.operator,None,model(),.0001,self.emit,self.ledger))
        self.assertEqual(record["outcome"]["total_steps"],16)
        self.assertIsNotNone(record["new_cache"])
        audit.verify_record(record,model(),None,self.operator,deque(e for e in self.events if not e["event"].startswith("LIFECYCLE")))
    def test_all_actual_programs_replay_with_saved_commands_and_continuous_rng(self):
        audit.verify_record.sigma=.0001
        with self.fixtures():
            for method in METHODS:
                self.events.clear();record=self.branch(method)
                business=deque(e for e in self.events if not e["event"].startswith("LIFECYCLE"))
                audit.verify_record(record,model(),record["source_cache"],self.operator,business)
                self.assertFalse(business)
                self.assertEqual(record["outcome"]["environment_resets"],1)
                self.assertTrue(record["outcome"]["success"] or record["outcome"]["stopped"])
                self.assertLessEqual(record["outcome"]["total_steps"],500)
    def test_six_step_prefixes_match_without_state_restore(self):
        with self.fixtures():
            reference=self.branch("CACHE_CONTINUE")
            for method in run.MID_METHODS:
                target=self.branch(method)
                self.assertEqual(run.pairing_reason(target,reference),"MATCHED")
        target["trace"][0]["rng_after"]="changed"
        with self.assertRaises(ValueError):run.pairing_reason(target,reference)
    def test_keep_and_update_share_the_real_post_probe_state(self):
        with self.fixtures():
            reference=self.branch("CACHE_CONTINUE")
            for method in ("MID8_WIDE","MID16_WIDE"):
                updated=self.branch(method);kept=self.branch(method+"_KEEP")
                self.assertIsNone(kept["new_cache"])
                self.assertEqual(kept["outcome"]["point_fit_failures"],0)
                result=run.update_pair(updated,kept,reference)
                self.assertEqual(result["reason"],"MATCHED_UPDATE")
                self.assertEqual(result["update_loss_difference"]+result["probe_motion_loss_difference"],result["total_loss_difference"])
        kept["post_fixed_probe_physics_witness_oracle"]["time"]+=.01
        with self.assertRaises(ValueError):run.update_pair(updated,kept,reference)
    def test_source_unavailable_stops_instead_of_running_a_baseline(self):
        for method in run.PRIOR_CACHE_METHODS:
            record=run.execute({**self.key,"method":method},self.operator,None,model(),.0001,self.emit,self.ledger)
            self.assertEqual((record["outcome"]["total_steps"],record["outcome"]["deadline_loss"],record["outcome"]["environment_resets"]),(0,500,0))
            audit.verify_record(record,model(),None,self.operator,deque([record["decisions"][0]]))
    def test_illegal_program_and_tampered_intent_or_future_decision_fail(self):
        with self.assertRaises(ValueError):self.branch("UNREGISTERED")
        with self.fixtures():record=self.branch("MID8_WIDE")
        original=deque(e for e in self.events if not e["event"].startswith("LIFECYCLE"))
        variants=[]
        changed=copy.deepcopy(record);changed["trace"][0]["command"][0]+=.01;variants.append(changed)
        changed=copy.deepcopy(record);changed["decisions"][1]["at_host_calls"]=7;variants.append(changed)
        changed=copy.deepcopy(record);changed["trace"][0]["decision_sequence"]=record["decisions"][-1]["sequence"];variants.append(changed)
        for value in variants:
            with self.fixtures(),self.assertRaises(ValueError):
                audit.verify_record(value,model(),value["source_cache"],self.operator,copy.deepcopy(original))
    def test_guard_gets_visible_samples_and_no_evaluator_key(self):
        original=run.agent_validation;seen=[]
        def visible_only(method,nominal,previous,samples,sigma,micro,remaining):
            serialized=json.dumps([run.normal(run.asdict(s)) for s in samples])
            for forbidden in ("seed","oracle","replicate","operator_id","deadline_loss"):
                self.assertNotIn(forbidden,serialized)
            self.assertLessEqual(max(s.step for s in samples),500-remaining)
            seen.append(remaining)
            return original(method,nominal,previous,samples,sigma,micro,remaining)
        with self.fixtures(),patch.object(run,"agent_validation",side_effect=visible_only):self.branch("G_OPTIMAL")
        self.assertTrue(seen)
    def test_stopped_fit_has_deadline_loss_not_low_cost_reward(self):
        self.assertEqual(deadline_loss(False,True,26),500)
        self.assertEqual(paired_sign({"success":False,"stopped":True,"total_steps":26},{"success":True,"stopped":False,"total_steps":98}),-1)
        with self.assertRaises(ValueError):deadline_loss(True,True,5)
        with self.assertRaises(ValueError):deadline_loss(True,False,501)
        with self.assertRaises(ValueError):deadline_loss(1,False,5)
    def test_leave_one_out_ties_abstain_and_reversals_are_counted(self):
        stable=repeat_consistency([1,1,1,1]);self.assertEqual((stable["leave_one_out_checked"],stable["leave_one_out_correct"]),(4,4))
        flipped=repeat_consistency([1,1,-1,-1]);self.assertTrue(flipped["sign_reversal"]);self.assertEqual(flipped["leave_one_out_correct"],0)
        sparse=repeat_consistency([1,0,0,0]);self.assertEqual((sparse["leave_one_out_checked"],sparse["leave_one_out_abstained"]),(0,1))
        self.assertFalse(repeat_consistency([0,0,0,0])["has_non_tie"])
        with self.assertRaises(ValueError):repeat_consistency([1,1])
    def test_new_seed_allocation_and_frozen_config(self):
        c=json.loads(run.CONFIG.read_text(encoding="utf-8"));run.validate(c)
        seeds={run.task_seed(s,t,cold) for s in range(8) for t in run.TASKS for cold in (True,False)}
        self.assertEqual(seeds,set(range(11200,11248)))
        self.assertNotEqual(run.noise_seed(11201,"push-v3",0),run.noise_seed(11201,"push-v3",1))
        c["replicates"]=5
        with self.assertRaises(ValueError):run.validate(c)
    def test_clock_discontinuity_preserves_the_completed_physical_attempt(self):
        class JumpClock(FakeEnv):
            def step(self,action):
                value=super().step(action);self.data.time=0.;return value
        with self.fixtures(),patch.object(run,"create_task_environment",side_effect=lambda *a:JumpClock()),self.assertRaises(run.BranchFailure) as caught:
            self.branch("CACHE_CONTINUE")
        record=caught.exception.record
        self.assertEqual((record["completed_steps"],record["attempted_controlled_steps"],record["unresolved_controlled_step_attempts"]),(1,1,0))
        self.assertEqual(self.ledger.by_phase["CONTROL"]["simulation_frames_completed"],5)


class LifecycleLedgerTest(unittest.TestCase):
    def test_instrumentation_delegates_once_and_restores_functions(self):
        events=[]
        def emit(kind,payload):
            e={"sequence":len(events)+1,"event":kind,**payload};events.append(e);return e
        ledger=LifecycleLedger(emit,1000);factory=SimpleNamespace(_make_tasks=lambda e:e.reset())
        old=(FakeEnv.reset,FakeSimulator.do_simulation,factory._make_tasks)
        with ledger.instrument(FakeEnv,FakeSimulator,factory):
            env=FakeEnv();factory._make_tasks(env)
            with ledger.scope("CONTROL"):env.step([0,0,0,1])
        self.assertEqual((FakeEnv.reset,FakeSimulator.do_simulation,factory._make_tasks),old)
        self.assertEqual(ledger.counts["reset_completed"],1)
        self.assertEqual(ledger.counts["simulation_frames_completed"],505)
        self.assertEqual(ledger.by_phase["GOAL_GENERATION"]["simulation_completed"],100)
    def test_frame_cap_checked_before_call_and_exception_frames_remain_uncertain(self):
        ledger=LifecycleLedger(lambda *a:None,4);called=[]
        with self.assertRaises(RuntimeError):ledger.simulation_call(lambda *a:called.append(1),None,[0,0],5)
        self.assertFalse(called);self.assertEqual(ledger.counts["simulation_frames_completed"],0)
        ledger=LifecycleLedger(lambda *a:None,100)
        def error(*args):raise RuntimeError("partial engine failure")
        with self.assertRaises(RuntimeError):ledger.simulation_call(error,None,[0,0],5)
        self.assertEqual((ledger.counts["simulation_frames_attempted"],ledger.counts["simulation_frames_completed"],ledger.counts["uncertain_simulation_frames"]),(5,0,5))
    def test_ledger_arithmetic_preserves_phase_and_rejects_invalid_scope(self):
        before={"counts":{},"by_phase":{}}
        after=audit.advance_ledger(before,"CONTROL",{"simulation_frames_completed":5})
        self.assertEqual(before,{"counts":{},"by_phase":{}})
        self.assertEqual(after["by_phase"]["CONTROL"]["simulation_frames_completed"],5)
        with self.assertRaises(ValueError):
            with LifecycleLedger(lambda *a:None,100).scope("UNKNOWN"):pass


class JournalAuditTest(unittest.TestCase):
    def event(self,kind,sequence,**fields):return {"event":kind,"sequence":sequence,"manifest_id":"test",**fields}
    def test_reset_and_control_phase_arithmetic_is_independent(self):
        j=audit.JournalAudit({"manifest_id":"test"});before=copy.deepcopy(j.ledger)
        j.accept(self.event("LIFECYCLE_RESET_INTENT",1,phase="GOAL_GENERATION",before=before))
        delta={"reset_attempts":1,"reset_completed":1,"simulation_attempts":100,"simulation_completed":100,
               "simulation_frames_attempted":500,"simulation_frames_completed":500}
        after=audit.advance_ledger(before,"GOAL_GENERATION",delta)
        j.accept(self.event("LIFECYCLE_RESET_COMPLETE",2,phase="GOAL_GENERATION",intent_sequence=1,after=after))
        j.accept(self.event("STEP_INTENT",3,ledger_before=after))
        done=audit.advance_ledger(after,"CONTROL",{"simulation_attempts":1,"simulation_completed":1,"simulation_frames_attempted":5,"simulation_frames_completed":5})
        j.accept(self.event("STEP_COMPLETE",4,intent_sequence=3,ledger_before=after,ledger_after=done));j.boundary()
        self.assertEqual((j.resets,j.ledger["counts"]["simulation_frames_completed"]),(1,505))
    def test_missing_completion_reordered_or_foreign_events_fail_closed(self):
        j=audit.JournalAudit({"manifest_id":"test"});j.accept(self.event("STEP_INTENT",1,ledger_before=j.ledger))
        with self.assertRaises(ValueError):j.boundary()
        with self.assertRaises(ValueError):audit.JournalAudit({"manifest_id":"test"}).accept(self.event("DECISION",2))
        event=self.event("DECISION",1);event["manifest_id"]="foreign"
        with self.assertRaises(ValueError):audit.JournalAudit({"manifest_id":"test"}).accept(event)
    def test_reset_frames_cannot_be_relabelled_as_control_steps(self):
        j=audit.JournalAudit({"manifest_id":"test"});before=copy.deepcopy(j.ledger)
        j.accept(self.event("LIFECYCLE_RESET_INTENT",1,phase="CONTROLLED_RESET",before=before))
        wrong=audit.advance_ledger(before,"CONTROLLED_RESET",{"reset_attempts":1,"reset_completed":1,"simulation_frames_completed":5})
        with self.assertRaises(ValueError):j.accept(self.event("LIFECYCLE_RESET_COMPLETE",2,phase="CONTROLLED_RESET",intent_sequence=1,after=wrong))


class RepeatStatisticsTest(unittest.TestCase):
    def population(self,flips=False):
        config=json.loads(run.CONFIG.read_text(encoding="utf-8"));rows=[];sources=[];pairs=[]
        for s in range(8):
            for t in run.TASKS:
                sources.append({"stream":s,"task":t,"total_steps":16,"environment_resets":1})
                for z in run.SCENARIOS:
                    for v in range(4):
                        for method in METHODS:
                            steps=40 if method=="MID16_WIDE" and (not flips or v%2==0) else 60 if method=="MID16_WIDE" else 50
                            rows.append({"stream":s,"task":t,"scenario":z,"replicate":v,"method":method,"total_steps":steps,
                                         "success":True,"stopped":False,"deadline_loss":steps,"environment_resets":1,"micro_steps":0,
                                         "fixed_probe_steps":0,"point_fit_failures":0})
                        for method in run.MID_METHODS:
                            pairs.append({"stream":s,"task":t,"scenario":z,"replicate":v,"method":method,"reason":"MATCHED"})
        return {"config":config},rows,sources,pairs
    def test_repeat_gate_uses_complete_population_and_full_source_cost(self):
        m,rows,sources,pairs=self.population();result=audit.statistics(m,rows,sources,pairs)
        self.assertTrue(result["repeat_gate"]["passed"])
        self.assertEqual(result["repeat_gate"]["leave_one_out_checked"],192)
        self.assertEqual(result["methods"]["MID16_WIDE"]["cold_source_steps"],384)
        self.assertEqual(result["methods"]["EARLY16_WIDE"]["cold_source_steps"],0)
        self.assertEqual(result["methods"]["NO_PROBE"]["offline_nominal_steps"],0)
        with self.assertRaises(ValueError):audit.statistics(m,rows[:-1],sources,pairs)
    def test_reversals_and_unpaired_states_block_promotion(self):
        m,rows,sources,pairs=self.population(True);result=audit.statistics(m,rows,sources,pairs)
        self.assertFalse(result["repeat_gate"]["passed"])
        self.assertEqual(result["repeat_gate"]["sign_reversal_contexts"],48)
        self.assertEqual(result["repeat_gate"]["leave_one_out_agreement"],0)
        m,rows,sources,pairs=self.population();pairs[0]["reason"]="NO_SOURCE_CACHE"
        # The first comparison can belong to MID8; explicitly remove the primary one.
        next(r for r in pairs if r["method"]=="MID16_WIDE")["reason"]="NO_SOURCE_CACHE"
        self.assertFalse(audit.statistics(m,rows,sources,pairs)["repeat_gate"]["passed"])


if __name__=="__main__":unittest.main()
