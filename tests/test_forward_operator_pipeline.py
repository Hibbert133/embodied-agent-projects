import copy
import json
from pathlib import Path
import tempfile
from time import perf_counter_ns
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_forward_operator as runner
from scripts import analyze_forward_operator as auditor
from src.probe.response_calibration import ResponseModel
from src.probe.operator_identification import identity_controller
from tests.test_operator_identification import model


class ForwardOperatorPipelineTest(unittest.TestCase):
    def priors(self):
        old=json.loads((runner.ROOT/json.loads(runner.CONFIG.read_text())["legacy_model_path"]).read_text())
        return {"forward":{t:{k:model(k) for k in ("LINEAR_ARX","QUADRATIC_STATE")} for t in runner.TASKS},"legacy":ResponseModel(**old["model"])}

    def test_config_and_oracle_boundary_are_strict(self):
        c=json.loads(runner.CONFIG.read_text());runner.validate(c);changed=copy.deepcopy(c);changed["operators_oracle"][0]["bias_xy"][0]=.1
        with self.assertRaisesRegex(ValueError,"population"):runner.validate(changed)
        with self.assertRaisesRegex(ValueError,"evaluator"):runner.choose_agent_plan("ORACLE16","push-v3",[],None,{})
        last=identity_controller();last["source"]="ORACLE_EVALUATOR"
        with self.assertRaisesRegex(ValueError,"Oracle"):runner.choose_agent_plan("PASSIVE_LINEAR","push-v3",[],None,{},last)
        self.assertEqual(len(runner.probe_program("FWD_LINEAR8")),8)
        self.assertNotEqual(runner.probe_program("FWD_LINEAR8"),runner.probe_program("FWD_LINEAR16")[:8])

    def test_actual_execution_uses_saved_choices_and_independent_replay_rejects_tampering(self):
        c=json.loads(runner.CONFIG.read_text());m={"experiment_run_id":"synthetic","manifest_id":"synthetic","source_git_commit":"test","config":c}
        policy=SimpleNamespace(get_action=lambda obs:np.array([.05,-.1,0.,1.]));priors=self.priors();created=[];resets=[];declarations=[];case=self
        class Env:
            action_space=SimpleNamespace(low=-np.ones(4),high=np.ones(4))
            def __init__(self):created.append(self)
            def reset(self,**kwargs):
                resets.append(kwargs);self.position=np.zeros(39);self.velocity=np.zeros(3);self.calls=0
                return self.position.copy(),{}
            def step(self,acted):
                if self.calls>=8 and declarations and declarations[-1]["episode_index"]==len(created):
                    case.assertLess(declarations[-1]["saved_ns"],perf_counter_ns())
                self.calls+=1;self.velocity=.5*self.velocity+np.array([.006*acted[0]+.001*acted[0]**2,.008*acted[1],.003*acted[2]])
                self.position[:3]+=self.velocity
                return self.position.copy(),0.,False,False,{"success":self.calls==22}
            def close(self):pass
        def emit(d):
            d={**d,"sequence":len(declarations)+1,"saved_ns":perf_counter_ns()};declarations.append(copy.deepcopy(d));return d
        with patch.object(runner,"create_task_environment",side_effect=lambda task,seed:Env()),patch.object(runner,"create_task_policy",return_value=policy),patch.object(auditor,"create_task_policy",return_value=policy):
            after=0;records=[]
            for index,method in enumerate(runner.METHODS,1):
                key={**runner.identity(m),"episode_index":index,"seed":10600,"task":"push-v3","operator_oracle":"REFLECTED_SHEAR","method":method}
                record=json.loads(json.dumps(runner.run_episode(m,key,c["operators_oracle"][3],priors,emit),allow_nan=False))
                outcome,after=auditor.verify_record(m,record,priors,after);records.append(record)
                self.assertEqual(outcome,record["outcome"])
            self.assertEqual(len(resets),12)
            record=records[7]
            self.assertGreater(len(record["trace"]),16)
            poisoned=copy.deepcopy(record);poisoned["trace"][16]["decision_sequence"]+=99
            with self.assertRaisesRegex(ValueError,"saved choice"):auditor.verify_record(m,poisoned,priors)
            poisoned=copy.deepcopy(record);poisoned["trace"][16]["command"][0]*=-1
            with self.assertRaisesRegex(ValueError,"bounded command"):auditor.verify_record(m,poisoned,priors)
            self.assertEqual(records[10]["decisions"][-1]["choice"]["status"],"UPDATE_REJECTED_RETAIN_PRIOR")
            self.assertEqual(records[10]["decisions"][-1]["choice"]["controller"],identity_controller())
            poisoned=copy.deepcopy(record);poisoned["trace"][2]["rng_before"]="reseeded"
            with self.assertRaisesRegex(ValueError,"RNG"):auditor.verify_record(m,poisoned,priors)
            poisoned=copy.deepcopy(record);poisoned["decisions"][0]["at_host_calls"]+=1
            with self.assertRaisesRegex(ValueError,"past prefix"):auditor.verify_record(m,poisoned,priors)

    def test_stops_and_invalid_updates_remain_in_full_statistical_denominator(self):
        c=json.loads(runner.CONFIG.read_text());rows=[]
        for seed,task,operator,method in runner.population(c):
            rows.append({"seed":seed,"task":task,"operator_oracle":operator,"method":method,"success":method in ("NO_PROBE","ORACLE16"),
                "total_steps":16 if method.startswith("FWD_") else 100,"probe_steps":len(runner.probe_program(method)),
                "stopped_point_fit":method.startswith("FWD_"),"invalid_fit_choices":int(method.startswith("FWD_"))})
        result=runner.summarize({"config":c},rows)
        self.assertEqual(result["methods"]["FWD_LINEAR16"]["denominator"],96)
        self.assertEqual(result["methods"]["FWD_LINEAR16"]["successes"],0)
        self.assertEqual(result["methods"]["FWD_LINEAR16"]["stopped_point_fits"],96)
        self.assertFalse(result["matched_motion_contrasts"]["FWD_LINEAR16"]["point_task_bridge_gate"])
        self.assertFalse(result["physical_response_qualified"])


if __name__=="__main__":unittest.main()
