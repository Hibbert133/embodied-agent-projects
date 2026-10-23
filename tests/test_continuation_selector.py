import copy
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from scripts import run_continuation_selector as run
from scripts import analyze_continuation_selector as audit
from src.probe.continuation_selector import (BRANCHES, FULL_BRANCHES, SELECTORS, TASKS, ContinuationEvidence,
                                            TrainingCase, choose, train, validate_model)
from src.probe.lifecycle_ledger import LifecycleLedger
from tests.test_acquisition_value import FakeEnv, FakeSimulator, FixedPolicy, model


def visible(task="push-v3"):
    observations=np.zeros((9,39)); observations[:,-3:]=(.1,.8,.1)
    commands=np.asarray(run.symmetric_program(.4,steps_per_direction=2),np.float32)
    return ContinuationEvidence(task,observations,commands,(.8,.1,.1,0.,1.1,-.08),np.eye(6)*.001,(.15,.1,0.,1.),492)


def training_cases(branch="DIRECT_G8", losses=None):
    costs=np.full((7,4),200.) if losses is None else np.asarray(losses,float)
    if losses is None: costs[FULL_BRANCHES.index(branch)]=100.
    return [TrainingCase(f"source-{s}-{task}",s,visible(task),costs) for s in range(8) for task in TASKS]


class SelectorModelTest(unittest.TestCase):
    def test_strict_evidence_excludes_identity_truth_and_future_fields(self):
        view=visible(); self.assertEqual(view.features().shape,(28,))
        for name in ("seed","stream","rng_state","future_noise","operator_oracle","outcome"):
            with self.assertRaises(ValueError): ContinuationEvidence.from_dict({**asdict(view),name:0})
        with self.assertRaises(ValueError): replace(view,observations=(*view.observations,view.observations[-1]))
        with self.assertRaises(ValueError): replace(view,reference_covariance=np.zeros((6,6)))
        with self.assertRaises(ValueError): replace(view,commands=np.zeros((8,4)))
        with self.assertRaises(ValueError): replace(view,remaining_steps=493)

    def test_all_legal_branch_predictions_select_their_registered_action(self):
        for branch in BRANCHES:
            artifact=train(training_cases(branch)); validate_model(artifact)
            for selector in SELECTORS:
                self.assertEqual(choose(visible(),artifact,selector)["selected_branch"],branch)

    def test_mean_supervision_and_single_future_are_different_fixed_estimators(self):
        losses=np.full((7,4),200.); losses[FULL_BRANCHES.index("PASSIVE_G16")]=(100,400,400,400)
        artifact=train(training_cases(losses=losses))
        self.assertEqual(choose(visible(),artifact,"MEAN_COST_RBF")["selected_branch"],"DIRECT_G8")
        self.assertEqual(choose(visible(),artifact,"SINGLE_FUTURE_RBF")["selected_branch"],"PASSIVE_G16")

    def test_task_only_ignores_history_and_budget_cannot_be_overridden(self):
        artifact=train(training_cases("PASSIVE_G16")); first=visible()
        second=replace(first,reference_mean=(1.,0.,0.,0.,1.,0.))
        a,b=choose(first,artifact,"TASK_MEAN"),choose(second,artifact,"TASK_MEAN")
        self.assertEqual(a["loss_minus_direct_predictions"],b["loss_minus_direct_predictions"])
        self.assertNotEqual(a["evidence_sha256"],b["evidence_sha256"])
        with self.assertRaises(ValueError): choose(replace(first,remaining_steps=39),artifact,"MEAN_COST_RBF")
        with self.assertRaises(ValueError): choose(first,artifact,"UNREGISTERED")

    def test_training_and_model_must_have_complete_separate_offline_source(self):
        cases=training_cases(); artifact=train(cases)
        for bad in (cases[:-1],cases[:-1]+[cases[0]]):
            with self.assertRaises(ValueError): train(bad)
        with self.assertRaises(ValueError): TrainingCase("bad",0,visible(),np.zeros((5,3)))
        with self.assertRaises(ValueError): validate_model({**artifact,"current_test_outcome":0})
        with self.assertRaises(ValueError): choose(asdict(visible()),artifact,"MEAN_COST_RBF")

    def test_prediction_does_not_update_the_frozen_artifact(self):
        artifact=train(training_cases("UPDATE_G16")); saved=copy.deepcopy(artifact)
        for selector in SELECTORS: choose(visible(),artifact,selector)
        self.assertEqual(saved,artifact)

    def test_exact_config_and_fresh_operator_population(self):
        c=json.loads(run.CONFIG.read_text(encoding="utf-8")); run.validate(c)
        with self.assertRaises(ValueError): run.validate({**c,"replicates":3})
        operators=run.operators(c)
        self.assertEqual(len(operators),16); self.assertEqual(run.task_seed(15,"door-open-v3"),12647)
        self.assertEqual(c["reserved_seeds"],[12648,12999])
        signatures=[json.dumps(r["states_oracle"][0],sort_keys=True) for r in operators]
        self.assertEqual(len(set(signatures)),16)


class SelectorExecutionTest(unittest.TestCase):
    def setUp(self):
        self.events=[]
        def emit(kind,payload):
            item={"event":kind,"sequence":len(self.events)+1,"saved_ns":run.perf_counter_ns(),**run.normal(payload)}
            self.events.append(item); return item
        self.emit=emit; self.ledger=LifecycleLedger(emit,1000000); self.factory=SimpleNamespace(_make_tasks=lambda:None)
        self.key={"experiment_run_id":"test","manifest_id":"manifest","source_git_commit":"source","stream":0,
                  "task":"push-v3","replicate":0,"seed":12600,"operator_id_oracle":"A"}
        self.operator={"matrix_xy":[[.8,.1],[0,1.1]],"bias_xy":[.1,-.08]}

    @contextmanager
    def fixtures(self):
        witness=lambda env:{"fixture":True,"time":env.data.time,"observation":env.observation.tolist()}
        with self.ledger.instrument(FakeEnv,FakeSimulator,self.factory), patch.object(run,"create_task_environment",side_effect=lambda *a:FakeEnv()), \
             patch.object(run,"create_task_policy",return_value=FixedPolicy()), patch.object(run,"physics_witness",side_effect=witness), \
             patch.object(audit.fixed.run,"create_task_policy",return_value=FixedPolicy()):
            yield

    def branch(self,method,artifact,future=0):
        return run.normal(run.execute({**self.key,"method":method,"replicate":future},self.operator,model(),.0001,self.emit,self.ledger,artifact))

    def replay(self,record,artifact,events=None):
        business=deque(e for e in (self.events if events is None else events) if not e["event"].startswith("LIFECYCLE"))
        return audit.verify_record(record,model(),.0001,self.operator,business,.01,artifact)

    def test_legal_saved_choices_drive_different_physical_continuations(self):
        outputs={}
        with self.fixtures():
            for branch in BRANCHES:
                artifact=train(training_cases(branch)); self.events.clear()
                record=self.branch("MEAN_COST_RBF",artifact); checked=self.replay(record,artifact)
                self.assertEqual(checked["selected_branch"],branch)
                decision=next(d for d in record["decisions"] if d["action"]=="SELECT_CONTINUATION")
                self.assertEqual(decision["at_host_calls"],8)
                self.assertLess(decision["sequence"],record["trace"][8]["intent_sequence"])
                self.assertEqual(record["outcome"]["environment_resets"],1)
                self.assertLessEqual(record["outcome"]["fixed_probe_steps"],16)
                outputs[branch]=record
        self.assertNotEqual(outputs["DIRECT_G8"]["trace"][8]["command"],outputs["KEEP_G8_AFTER16"]["trace"][8]["command"])
        self.assertEqual(outputs["PASSIVE_G16"]["outcome"]["policy_measure_steps"],8)

    def test_all_fixed_and_learned_programs_pass_recorded_action_replay(self):
        artifact=train(training_cases("PASSIVE_G16"))
        with self.fixtures():
            for method in run.METHODS:
                self.events.clear(); record=self.branch(method,artifact); self.replay(record,artifact)

    def test_same_prefix_futures_cannot_change_choice_or_evidence(self):
        artifact=train(training_cases("PASSIVE_G16")); records=[]
        with self.fixtures():
            for future in range(2):
                self.events.clear(); record=self.branch("MEAN_COST_RBF",artifact,future); self.replay(record,artifact); records.append(record)
        self.assertEqual(run.prefix_match(*records),"MATCHED_ACTIVE_PREFIX")
        decisions=[next(d for d in r["decisions"] if d["action"]=="SELECT_CONTINUATION") for r in records]
        self.assertEqual(decisions[0]["selection"],decisions[1]["selection"])

    def test_unknown_evidence_action_and_forged_journal_are_rejected(self):
        artifact=train(training_cases("PASSIVE_G16"))
        with self.fixtures():
            record=self.branch("MEAN_COST_RBF",artifact)
            original_events=copy.deepcopy(self.events)
            for field,value in (("selection",{"selected_branch":"NO_PROBE"}),("visible_evidence",{"seed":12600})):
                changed=copy.deepcopy(record); decision=next(d for d in changed["decisions"] if d["action"]=="SELECT_CONTINUATION")
                decision[field]=value
                with self.assertRaises((ValueError,KeyError)): self.replay(changed,artifact,original_events)
            events=copy.deepcopy(original_events)
            event=next(e for e in events if e.get("action")=="SELECT_CONTINUATION"); event["decision_latency_ns"]+=1
            with self.assertRaises(ValueError): self.replay(record,artifact,events)

    def test_missing_or_invalid_model_fails_before_environment_creation(self):
        with patch.object(run,"create_task_environment") as factory:
            for artifact in (None,{"test_outcome":0}):
                with self.assertRaises(ValueError): self.branch("MEAN_COST_RBF",artifact)
            factory.assert_not_called()

    def test_task_only_initial_portfolio_can_choose_all_seven_before_any_step(self):
        with self.fixtures():
            for branch in FULL_BRANCHES:
                self.events.clear(); artifact=train(training_cases(branch))
                record=self.branch("TASK_FULL_PORTFOLIO",artifact)
                checked=self.replay(record,artifact)
                self.assertEqual(checked["selected_branch"],branch)
                decision=next(d for d in record["decisions"] if d["action"]=="SELECT_INITIAL_PORTFOLIO")
                self.assertEqual(decision["at_host_calls"],0)
                self.assertLess(decision["sequence"],record["trace"][0]["intent_sequence"])
                self.assertNotIn("visible_evidence",decision)
                if branch=="NO_PROBE": self.assertEqual(record["outcome"]["fixed_probe_steps"],0)

    def test_full_population_statistics_preserve_failure_denominators_and_costs(self):
        rows=[]; pairs=[]; repeats=[]
        for stream in range(16):
            for task in run.TASKS:
                for future in range(2):
                    for method in run.METHODS:
                        rows.append({"stream":stream,"task":task,"replicate":future,"method":method,"success":True,"stopped":False,
                                     "deadline_loss":80 if method=="MEAN_COST_RBF" else 100,"total_steps":80 if method=="MEAN_COST_RBF" else 100,
                                     "fixed_probe_steps":8,"policy_measure_steps":0})
                    pairs.extend({"stream":stream,"task":task,"replicate":future,"method":m,"reason":"MATCHED_ACTIVE_PREFIX"} for m in run.PORTFOLIO)
                repeats.extend({"stream":stream,"task":task,"replicate":1,"method":m,"reason":"MATCHED_ACTIVE_PREFIX"} for m in run.METHODS)
        manifest={"config":json.loads(run.CONFIG.read_text(encoding="utf-8"))}
        stats=audit.statistics(manifest,rows,pairs,repeats)
        self.assertTrue(stats["development_signal"]); self.assertEqual(stats["methods"]["MEAN_COST_RBF"]["cases"],96)
        self.assertEqual(stats["methods"]["MEAN_COST_RBF"]["training_offline_steps"],101069)
        self.assertEqual(stats["main_minus_each_baseline"]["POINT16_CYCLE"]["deadline_loss"]["paired_cluster_percentile_95"],[-20.,-20.])
        with self.assertRaises(ValueError): audit.statistics(manifest,rows[:-1],pairs,repeats)
