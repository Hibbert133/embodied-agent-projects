import copy
import gzip
import json
from pathlib import Path
import tempfile
from time import perf_counter_ns
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_action_response as runner
from scripts import analyze_action_response as auditor
from src.probe.action_response_validity import CachedPoint
from tests.test_operator_identification import model


class ActionResponsePipelineTest(unittest.TestCase):
    def test_frozen_population_operator_domains_and_private_changes(self):
        c=json.loads(runner.CONFIG.read_text());runner.validate(c);bank=runner.operators(c)
        self.assertEqual(len(bank),8)
        self.assertEqual({r["family_oracle"] for r in bank},{"BIAS_SHIFT","GAIN_COUPLING","PARITY_CHANGE"})
        self.assertGreater(len({r["abrupt_episode_oracle"] for r in bank}),1)
        self.assertEqual(runner.environment_seed(7,"door-open-v3",5),10943)
        bad=copy.deepcopy(c);bad["maximum_micro_steps"]=20
        with self.assertRaisesRegex(ValueError,"frozen"):runner.validate(bad)

    def collect(self,method,operator=None,constant_observations=False,initial_cache=True):
        c=json.loads(runner.CONFIG.read_text());m={"experiment_run_id":"synthetic","manifest_id":"synthetic","source_git_commit":"synthetic","config":c}
        key={**runner.identity(m),"episode_index":1,"stream":0,"task":"push-v3","scenario":"MIXED","method":method,
             "episode_in_stream":1,"seed":10801,"operator_id_oracle":"A"}
        operator=operator or {"matrix_xy":[[.8,.2],[.1,1.1]],"bias_xy":[.1,-.1]}
        state={"cache":CachedPoint(((1.,0.),(0.,1.)),(0.,0.)) if initial_cache else None,"version":1 if initial_cache else 0,"last_update_episode":0}
        initial_state=copy.deepcopy(state);events=[];case=self
        class Env:
            action_space=SimpleNamespace(low=-np.ones(4,dtype=np.float32),high=np.ones(4,dtype=np.float32))
            def reset(self,seed):self.position=np.zeros(39);self.velocity=np.zeros(3);self.calls=0;return self.position.copy(),{}
            def step(self,acted):
                case.assertEqual(events[-1]["event"],"STEP_INTENT")
                case.assertLess(events[-1]["saved_ns"],perf_counter_ns())
                self.calls+=1
                if not constant_observations:
                    self.velocity=.5*self.velocity+np.array([.006*acted[0],.008*acted[1],.003*acted[2]])
                    self.position[:3]+=self.velocity
                return self.position.copy(),0.,False,False,{"success":self.calls==35}
            def close(self):pass
        def emit(kind,row):
            event=runner.normalized({**row,"event":kind,"sequence":len(events)+1,"saved_ns":perf_counter_ns()})
            events.append(copy.deepcopy(event));return event
        policy=SimpleNamespace(get_action=lambda obs:np.array([.4,-.2,0.,1.],dtype=np.float32))
        with patch.object(runner,"create_task_environment",return_value=Env()),patch.object(runner,"create_task_policy",return_value=policy):
            record=runner.run_episode(m,key,operator,state,model("LINEAR_ARX"),.0001,emit)
        return m,runner.normalized(record),operator,initial_state,events,policy

    def verify(self,args):
        m,record,operator,state,events,policy=args;iterator=iter(events)
        with patch.object(runner,"create_task_policy",return_value=policy):
            return auditor.verify_episode(m,record,operator,state,model("LINEAR_ARX"),.0001,lambda:next(iterator))

    def test_every_method_uses_durable_intents_and_replays_without_dynamics(self):
        for method in runner.METHODS:
            with self.subTest(method=method):
                args=self.collect(method)
                outcome,_=self.verify(args)
                self.assertEqual(outcome,args[1]["outcome"])
                self.assertLessEqual(outcome["total_steps"],500)
                self.assertEqual(outcome["environment_resets"],1)
        args=self.collect("FIXED16",initial_cache=False)
        self.assertEqual(args[1]["outcome"]["fixed_probe_steps"],16)
        self.assertIsNotNone(args[1]["cache_after"])

    def test_tampered_command_cache_and_rng_are_rejected(self):
        for kind in ("command","cache","rng"):
            args=self.collect("FIXED16")
            if kind=="command":args[1]["trace"][-1]["command"][0]+=.01
            elif kind=="cache":args[1]["cache_before"]["bias_xy"][0]+=.01
            else:args[1]["trace"][2]["rng_after"]="reset"
            with self.assertRaises(ValueError):self.verify(args)

    def test_changed_private_truth_cannot_change_choices_given_same_visible_history(self):
        first=self.collect("RESPONSE_SET",constant_observations=True)
        second=self.collect("RESPONSE_SET",operator={"matrix_xy":[[-1.,0.],[0.,1.]],"bias_xy":[.2,0.]},constant_observations=True)
        def decisions(args):return [{k:d[k] for k in ("action","controller","validation") if k in d} for d in args[1]["decisions"]]
        self.assertEqual(decisions(first),decisions(second))

    def test_persisted_stop_never_runs_task_or_substitutes_a_baseline(self):
        for action in ("STOP_NUMERICAL","STOP_BUDGET"):
            with patch.object(runner,"agent_validation",return_value={"action":action,"program_id":None}):
                args=self.collect("RESPONSE_SET")
            record=args[1]
            self.assertEqual(record["outcome"]["total_steps"],6)
            self.assertEqual(record["outcome"]["policy_steps"],0)
            self.assertTrue(record["outcome"]["stopped"])
            self.assertIsNone(record["decisions"][-1]["controller"])
            self.assertEqual(record["cache_after"],record["cache_before"])

    def test_unknown_method_is_rejected_before_environment_creation(self):
        with patch.object(runner,"create_task_environment") as factory:
            with self.assertRaisesRegex(ValueError,"unregistered"):
                runner.run_episode({}, {"method":"unknown"}, {}, {}, {}, .0001, lambda *args:None)
            factory.assert_not_called()

    def test_global_denominators_include_stopped_cases(self):
        c=json.loads(runner.CONFIG.read_text());rows=[]
        for s in range(8):
            for task in runner.TASKS:
                for scenario in runner.SCENARIOS:
                    for episode in range(6):
                        for method in runner.METHODS:
                            rows.append({"stream":s,"task":task,"scenario":scenario,"episode_in_stream":episode,"method":method,
                                "success":method=="FIXED16_WIDE","stopped":method=="RESPONSE_SET","total_steps":10 if method=="RESPONSE_SET" else 100,
                                "micro_steps":0,"fixed_probe_steps":16,"reused_cache":False,"point_fit_failures":int(method=="RESPONSE_SET"),"cache_updates":0})
        r=runner.summarize({"config":c},rows)
        self.assertEqual(r["methods"]["RESPONSE_SET"]["denominator"],288)
        self.assertEqual(r["methods"]["RESPONSE_SET"]["stops"],288)
        self.assertFalse(r["strong_baseline_competitive_gate"])

    def test_nominal_scale_uses_calibration_prefix_not_later_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory);declarations=[];records=[];sequence=0
            for seed in range(10300,10316):
                for task in runner.TASKS:
                    for program in ("POLICY_ONLY","PROBE_THEN_POLICY"):
                        trace=[];position=np.zeros(39)
                        for step in range(1,8):
                            before=position.copy();delta=np.array([.0001 if program=="POLICY_ONLY" else .0002,0.]) if step<=6 else np.array([1.,0.])
                            position[:2]+=delta;sequence+=1
                            declarations.append({"stage":"CALIBRATION","step":step,"sequence":sequence,"seed":seed,"task":task,"program":program,
                                                 "predictions":{"LINEAR_ARX":[0.,0.]}})
                            trace.append({"prediction_sequence":sequence,"before":{"observation":before.tolist()},"after":{"observation":position.tolist()},"target_xy":delta.tolist()})
                        records.append({"stage":"CALIBRATION","seed":seed,"task":task,"program":program,"trace":trace,"outcome":{"maximum_error":10000.}})
            (source/"predictions.jsonl").write_text("\n".join(json.dumps(r) for r in declarations))
            with gzip.open(source/"CALIBRATION.jsonl.gz","wt",encoding="utf-8") as handle:
                handle.write("\n".join(json.dumps(r) for r in records))
            profile=runner.nominal_reference_profile({},source,{"experiment_run_id":"fake","manifest_id":"fake","source_git_commit":"fake"})
            for value in profile["rms_m"].values():self.assertAlmostEqual(value,.0002/np.sqrt(2))
            self.assertFalse(profile["confidence_qualified"])
            self.assertEqual(len(profile["included_prefixes"]),96)

    def test_interruption_preserves_partial_cost_and_forbids_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"manifest.json";path.write_text("{}")
            c=json.loads(runner.CONFIG.read_text());m={"experiment_run_id":"fake","manifest_id":"fake","source_git_commit":"fake","config":c,"operators_oracle":runner.operators(c)}
            (path.parent/"nominal_profile.json").write_text(json.dumps({"rms_m":{t:.0001 for t in runner.TASKS}}))
            failure=runner.EpisodeFailure({"error":"synthetic interruption","error_type":"RuntimeError","completed_steps":3,"completed_resets":1,"unconfirmed_attempt":True})
            with patch.object(runner,"check_clean"),patch.object(runner,"load",return_value=m),patch.object(runner,"git",return_value="fake"), \
                 patch.object(runner,"load_bank",return_value=({t:model("LINEAR_ARX") for t in runner.TASKS},None,None)),patch.object(runner,"run_episode",side_effect=failure):
                with self.assertRaises(runner.EpisodeFailure):runner.run(path)
                status=json.loads((path.parent/"status.json").read_text())
                self.assertEqual(status["status"],"INCOMPLETE")
                self.assertEqual(status["partial_completed_steps"],3)
                self.assertEqual(status["partial_completed_resets"],1)
                with self.assertRaises(FileExistsError):runner.run(path)


if __name__=="__main__":unittest.main()
