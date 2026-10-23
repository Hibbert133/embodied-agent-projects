"""Pure arrays and immutable saved cases only. Never load a native simulator test."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import ast
import unittest
from unittest.mock import patch
import numpy as np
import numpy.testing

from src.analysis import response_qualification_failure_v1 as a
from src.analysis import response_qualification_io_v1 as io
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard
from src.probe.response_qualification_model_v1 import predict,features
from src.probe.forward_prediction import ForwardQuery
from scripts.analyze_response_qualification_failure_v1 import compact,SOURCE,expected_config
from scripts.audit_response_qualification_failure_v1 import correlation


def models():
    result={}
    for name in a.MODELS:
        quad=name==a.MODELS[2];p=20 if quad else 10;c=np.zeros((231 if quad else 11,2));c[0]=[.0001,-.0002]
        if quad:c[10,0]=.002;c[11,1]=.002;c[21+list(zip(a.I,a.J)).index((9,9)),0]=.0005
        else:c[7,0]=.002;c[8,1]=.002
        result[name]={"method":name,"mean":[0.]*p,"scale":[1.]*p,"coefficients":c.tolist()}
    return result


def case(n=30,split="TRAIN",key="A"):
    rng=np.random.default_rng(82017);commands=rng.uniform(-.4,.4,(n,4)).astype(np.float32);noise=rng.normal(0,.05,(n,3)).astype(np.float32)
    initial=np.zeros(39);initial[:3]=[0.,.6,.4];initial[3]=.5;initial[4:7]=[.1,.7,.02];initial[-3:]=[.2,.8,.1]
    states=[initial];physical=[]
    for i,u in enumerate(commands):
        actual=u.copy();actual[:3]+=noise[i];actual=np.clip(actual,-1,1);s=states[-1].copy();s[:2]+=.002*actual[:2]+[.0001,-.0002];s[2]+=.001*actual[2]
        states.append(s);physical.append({"logical_step":i,"noise_cursor_after":i+1,"command":u.tolist(),"executed_action_oracle":actual.tolist(),
            "after":{"observation":s.tolist()},"phase":"FIXED_PROBE" if i<8 else "REPOSITION" if i<12 else "TASK_AFTER_MOVEMENT"})
    value={"case_id":key,"split":split,"task":"push-v3","group":0,"variant":"N47001" if split!="QUAL" else "UNCHANGED","planned_boundary":16,
        "initial":{"observation":initial.tolist()},"physical_rows":physical,"fault_oracle":{"matrix_xy":[[1.,0.],[0.,1.]],"bias_xy":[0.,0.],"deadzone_xy":[0.,0.]},
        "fault_transition":None,"behavior":{"events":[] if n<9 else [{"kind":"ACQUISITION_ENTRY","payload":{"anchor":[0.,.6,.5],"before":{"observation":states[8].tolist()}}}]}}
    return value,noise


class ArraysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank=models();c,_=case(40);cls.geometry=a.geometry([c],cls.bank[a.MODELS[2]])

    def test_features_and_fixed_forecasts_match_original_interface(self):
        c,noise=case();states,commands=a.arrays(c);x=a.base_features(states,commands)
        for j in range(len(x)):
            i=j+2;q=ForwardQuery(tuple(states[i]),tuple(states[i,:3]-states[i-1,:3]),tuple(states[i-1,:3]-states[i-2,:3]),tuple(commands[i]))
            np.testing.assert_allclose(x[j],features(q,a.MODELS[2]),atol=1e-14)
            for name,m in self.bank.items():np.testing.assert_allclose(a.forecast(m,x[j:j+1])[0],predict(m,q),atol=1e-14)

    def test_components_reconstruct_polynomial_including_cross_terms(self):
        rng=np.random.default_rng(5);z=rng.normal(size=(9,20));c=rng.normal(size=(231,2));parts=a.components(z,c)
        self.assertEqual(set(parts),set(a.TERMS));np.testing.assert_allclose(sum(parts.values()),a.expanded(z)@c,atol=1e-12)
        c[:]=0;c[21+list(zip(a.I,a.J)).index((0,9)),0]=2
        parts=a.components(z,c);np.testing.assert_allclose(parts["COMMAND_STATE"][:,0],2*z[:,0]*z[:,9])

    def test_geometry_is_training_only_and_uses_equal_trajectory_weight(self):
        c,_=case(12);d,_=case(40,key="B");g=a.geometry([c,d],self.bank[a.MODELS[2]])
        self.assertEqual((g["summary"]["training_trajectories"],g["summary"]["responses"]),(2,48))
        matrices=[]
        for row in (c,d):
            x=a.base_features(*a.arrays(row));phi=a.expanded(x);matrices.append(phi.T@phi/len(phi))
        p=np.diag([0]+[.001]*230);np.testing.assert_allclose((sum(matrices)+p)@g["inverse"],np.eye(231),atol=2e-8)
        with self.assertRaises(ValueError):a.geometry([{**c,"split":"QUAL"}],self.bank[a.MODELS[2]])

    def test_first_two_history_and_all_zero_length_stages_remain_missing(self):
        for n in (0,1,2,3,8):
            c,noise=case(n);rows,cells=a.analyze_case(c,self.bank,self.geometry,noise)
            self.assertEqual(sum(r["eligible"] for r in rows),max(n-2,0))
            self.assertTrue(all("predictions" not in r for r in rows[:2]))
            empty=next(r for r in cells if r["stage"]=="POST_TASK")
            self.assertEqual(empty["responses"],0);self.assertIsNone(empty["rmse"][a.MODES[0]][a.MODELS[2]])

    def test_noise_cursor_noise_offset_and_wrong_clip_order_fail_closed(self):
        c,noise=case();bad=deepcopy(c);bad["physical_rows"][0]["noise_cursor_after"]=2
        with self.assertRaises(ValueError):a.analyze_case(bad,self.bank,self.geometry,noise)
        with self.assertRaises(ValueError):a.analyze_case(c,self.bank,self.geometry,np.roll(noise,1,axis=0))
        bad=deepcopy(c);bad["physical_rows"][0]["executed_action_oracle"][0]+=.1
        with self.assertRaises(ValueError):a.analyze_case(bad,self.bank,self.geometry,noise)

    def test_input_semantics_squared_error_identity(self):
        c,noise=case();rows,cells=a.analyze_case(c,self.bank,self.geometry,noise)
        for cell in cells:
            d=cell["descriptors"]
            if cell["responses"]:self.assertAlmostEqual(d["quad_error_mse"],d["quad_applied_error_mse"]+d["input_semantics_delta_mse"]+d["semantics_cross_term"],places=17)

    def test_future_response_cannot_change_current_prediction(self):
        c,noise=case();bad=deepcopy(c)
        for r in bad["physical_rows"][20:]:r["after"]["observation"][0]+=.2
        original,_=a.analyze_case(c,self.bank,self.geometry,noise);changed,_=a.analyze_case(bad,self.bank,self.geometry,noise)
        for old,new in zip(original[:21],changed[:21]):
            if old["eligible"]:self.assertEqual(old["predictions"],new["predictions"])

    def test_lag_correlations_use_actual_indices_not_concatenated_segments(self):
        x=np.array([[i,i*i] for i in range(12)],float);y=x[::-1];indices=[2,4,7,10]
        for lag in (0,1,2):
            saved=a.correlations(x,y,indices,lag);v,axes,pairs=correlation(x,y,indices,lag)
            self.assertAlmostEqual(saved["value"],v);self.assertEqual((saved["valid_axes"],saved["pairs"]),(axes,pairs))
        self.assertIsNone(a.correlations(x,np.ones_like(x),indices,1)["value"])

    def test_group_summary_prevents_long_episode_weighting(self):
        c,noise=case(30);_,cells=a.analyze_case(c,self.bank,self.geometry,noise)
        population=[]
        for split in ("TRAIN","CAL","QUAL"):
            for task in io.TASKS:
                for variant in (("N47001","N47002") if split!="QUAL" else ("UNCHANGED","CHANGED")):
                    for g in (0,1):population.extend({**r,"split":split,"task":task,"variant":variant,"group":g,"case_id":f"{split}/{task}/{variant}/{g}"} for r in cells)
        summaries=a.grouped_summary(population);self.assertEqual(len(summaries),396)
        self.assertTrue(all(r["allocated"]>0 for r in summaries));self.assertTrue(all(r["rmse"][a.MODES[0]][a.MODELS[0]] is None for r in summaries if r["stage"]=="POST_LIFT"))

    def test_guard_rejects_environment_optimizer_and_network_imports(self):
        for name in ("metaworld","mujoco","gymnasium","openai","requests","scipy.optimize"):
            with read_only_analysis_guard(),self.assertRaises(RuntimeError):__import__(name)

    def test_new_analysis_has_no_training_or_collection_call(self):
        paths=[io.ROOT/"src/analysis/response_qualification_failure_v1.py",io.ROOT/"scripts/analyze_response_qualification_failure_v1.py",io.ROOT/"scripts/audit_response_qualification_failure_v1.py"]
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):self.assertNotIn(node.func.attr,("fit","fit_models","infer_operator","least_squares","lstsq","reset","step","minimize"))


class SavedRecordTests(unittest.TestCase):
    def test_saved_case_and_models_replay_without_environment_or_fit(self):
        bank=io.read(SOURCE/"training/models.json")["models"];raw=next(io.rows(SOURCE/"train/cases.jsonl.gz"));c=compact(raw)
        with read_only_analysis_guard():
            g=a.geometry([c],bank[c["task"]][a.MODELS[2]]);rows,cells=a.analyze_case(c,bank[c["task"]],g,io.noise(c["seed"],c["noise_namespace"])[:len(c["physical_rows"])])
        self.assertEqual(len(rows),c["total_steps"]);self.assertEqual(len(cells),11)
        self.assertFalse(expected_config()["threshold_or_model_search"])


if __name__=="__main__":unittest.main()
