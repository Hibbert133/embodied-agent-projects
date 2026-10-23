import copy
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_forward_prediction as runner
from scripts import analyze_forward_prediction as auditor
from src.probe.continuous import ContinuousTransition
from src.probe.frame_identification import NominalARX
from src.probe.forward_prediction import ForwardQuery,ForwardHistory,TrainingSample,fit_models,Predictors,conformal_radius


def legacy():return NominalARX(((.5,0.),(0.,.5)),((.003,0.),(0.,.003)),(0.,0.),1080,72,5,2.,0.,"synthetic")


def training():
    rng=np.random.default_rng(17);samples=[]
    for _ in range(64):
        observation=rng.normal(0,.02,39);old=rng.normal(0,.005,3);prior=rng.normal(0,.005,3);sent=rng.uniform(-.5,.5,4)
        query=ForwardQuery(tuple(observation),tuple(old),tuple(prior),tuple(sent))
        target=.5*old[:2]+.003*sent[:2];samples.append(TrainingSample(query,tuple(target)))
    return samples


class ForwardPredictionTest(unittest.TestCase):
    def test_prediction_query_needs_two_executed_steps_and_cannot_use_future(self):
        before=(0.,)*39;history=ForwardHistory(before);sent=(.2,0.,0.,0.)
        for step in range(2):
            self.assertIsNone(history.request(sent))
            with self.assertRaisesRegex(ValueError,"not been observed"):history.request(sent)
            after=(float(step+1)*.001,)+(0.,)*38
            history.observe(ContinuousTransition(sent,before,after));before=after
        query=history.request(sent);saved=asdict(query)
        history.observe(ContinuousTransition(sent,before,(.999,)+(0.,)*38))
        self.assertEqual(asdict(query),saved);self.assertEqual(query.observation[0],.002)
        with self.assertRaisesRegex(ValueError,"earlier command"):history.observe(ContinuousTransition(sent,before,before))

    def test_history_rejects_discontinuity_and_non_numeric_or_oracle_input(self):
        history=ForwardHistory((0.,)*39);history.request((0.,)*4)
        with self.assertRaisesRegex(ValueError,"continuity"):history.observe(ContinuousTransition((.2,0.,0.,0.),(0.,)*39,(0.,)*39))
        for value in (True,float("nan"),"0"):
            with self.assertRaises(ValueError):ForwardHistory((value,)+(0.,)*38)
        with self.assertRaises(TypeError):ForwardQuery((0.,)*39,(0.,)*3,(0.,)*3,(0.,)*4,true_operator=[])
        with self.assertRaisesRegex(ValueError,"causal"):Predictors(fit_models(training()),legacy()).predict({"future_observation":[]})

    def test_fits_only_training_and_different_commands_change_actual_predictions(self):
        rows=training();models=fit_models(rows);predictors=Predictors(models,legacy());query=rows[0].query
        prediction=predictors.predict(query)
        np.testing.assert_allclose(prediction["LINEAR_ARX"],rows[0].displacement,atol=1e-6)
        changed=ForwardQuery(query.observation,query.last_displacement,query.prior_displacement,(-.5,.5,0.,0.))
        self.assertNotEqual(prediction["LINEAR_ARX"],predictors.predict(changed)["LINEAR_ARX"])
        for value in models.values():self.assertFalse(value["physical_response_qualified"])
        poisoned=list(rows);poisoned[-1]=TrainingSample(query,(0.,0.),"QUALIFICATION")
        with self.assertRaisesRegex(ValueError,"training-only"):fit_models(poisoned)

    def test_trajectory_quantile_is_finite_sample_rank_not_interpolated_p90(self):
        scores=[i/1000 for i in range(16)];result=conformal_radius(scores)
        self.assertEqual((result["rank"],result["radius"]),(16,.015))
        self.assertIsNone(conformal_radius(scores[:8])["radius"])
        self.assertEqual(conformal_radius(scores[:9])["radius"],.008)
        self.assertIsNone(conformal_radius([None,*scores])["radius"])
        self.assertFalse(result["exchangeability_verified"])

    def test_config_and_missing_test_scores_fail_without_dropping_denominator(self):
        c=json.loads(runner.CONFIG.read_text());bad=copy.deepcopy(c);bad["maximum_radius_m"]*=10
        with self.assertRaisesRegex(ValueError,"changed"):runner.validate(bad)
        rows=[]
        for seed,task,program in runner.population(c,"QUALIFICATION"):
            rows.append({"seed":seed,"task":task,"program":program,"prediction_steps":10,
                "maximum_errors":dict.fromkeys(runner.METHODS,.01),"rmse_inf":dict.fromkeys(runner.METHODS,.005)})
        cal={"radii":{t+"|"+p:{n:{"radius":.02} for n in runner.METHODS} for t in runner.TASKS for p in runner.PROGRAMS}}
        rows[0]["maximum_errors"]=dict.fromkeys(runner.METHODS,None);rows[0]["rmse_inf"]=dict.fromkeys(runner.METHODS,None)
        result=runner.summarize({},rows,cal);group=result["strata"]["push-v3|POLICY_ONLY"]["LINEAR_ARX"]
        self.assertEqual((group["covered"],group["denominator"],group["observed_episodes"]),(15,16,15))
        self.assertFalse(group["precision_and_coverage_gate"])
        self.assertIsNone(result["contrasts_vs_legacy"]["LINEAR_ARX"]["paired_seed_bootstrap_95_m"])

    def test_full_mocked_three_stage_pipeline_and_independent_adversarial_replay(self):
        c=json.loads(runner.CONFIG.read_text());hashes=dict.fromkeys(runner.TASKS,"synthetic")
        m={"experiment_run_id":"synthetic","source_git_commit":"test","config":c,"policy_sha256":hashes,"input_sha256":{}}
        m["manifest_id"]=runner.manifest_digest(m);policy=SimpleNamespace(get_action=lambda obs:np.array([.05,-.1,0.,1.]))
        created=[];resets=[];case=self
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"manifest.json";path.write_text(json.dumps(m))
            class Env:
                action_space=SimpleNamespace(low=-np.ones(4),high=np.ones(4))
                def __init__(self):self.index=len(created)+1;created.append(self)
                def reset(self,**kwargs):
                    resets.append(kwargs);self.position=np.zeros(39);self.velocity=np.zeros(3);self.calls=0
                    return self.position.copy(),{}
                def step(self,sent):
                    with (path.parent/"predictions.jsonl").open("rb") as stream:
                        stream.seek(0,2);stream.seek(max(0,stream.tell()-16384));last=json.loads(stream.read().splitlines()[-1])
                    case.assertEqual((last["episode_index"],last["step"]),(self.index,self.calls+1))
                    case.assertNotIn("target_xy",last)
                    self.calls+=1;self.velocity=.5*self.velocity+.003*sent[:3];self.position[:3]+=self.velocity
                    return self.position.copy(),0.,False,False,{"success":self.calls==22}
                def close(self):pass
            with patch.object(runner,"check_clean"),patch.object(runner,"git",return_value="test"), \
                 patch.object(runner,"policy_hashes",return_value=hashes),patch.object(runner,"model",return_value=legacy()), \
                 patch.object(runner,"create_task_environment",side_effect=lambda task,seed:Env()), \
                 patch.object(runner,"create_task_policy",return_value=policy),patch.object(auditor,"create_task_policy",return_value=policy),patch("builtins.print"):
                runner.run(path)
                with self.assertRaisesRegex(FileExistsError,"cannot restart"):runner.run(path)
                result=auditor.analyze(path)
            self.assertEqual((len(resets),result["episodes"],result["physical_steps"]),(288,288,6336))
            self.assertEqual(result["prediction_declarations_checked"],6336);self.assertEqual(result["continuous_handoffs"],144)
            saved=json.loads((path.parent/"models.json").read_text());pred=auditor.IndependentPredictors(saved["models"],legacy())
            with gzip.open(path.parent/"QUALIFICATION.jsonl.gz","rt",encoding="utf-8") as stream:record=json.loads(next(stream))
            declarations=[]
            with (path.parent/"predictions.jsonl").open() as stream:
                for line in stream:
                    d=json.loads(line)
                    if d["episode_index"]==193:declarations.append(d)
            model_sha=runner.digest(path.parent/"models.json");cal_sha=runner.digest(path.parent/"calibration.json")
            def replay(r,d=declarations):
                with patch.object(auditor,"create_task_policy",return_value=policy):return auditor.verify_record(m,r,d,pred,model_sha,cal_sha)
            poisoned=copy.deepcopy(declarations);poisoned[2]["query"]["observation"][0]+=.1
            with self.assertRaisesRegex(ValueError,"future/input"):replay(record,poisoned)
            poisoned=copy.deepcopy(declarations);poisoned[0]["before_ns"]=record["trace"][0]["after_ns"]+1
            with self.assertRaisesRegex(ValueError,"before execution"):replay(record,poisoned)
            poisoned=copy.deepcopy(record);poisoned["trace"][2]["rng_after"]="reset"
            with self.assertRaisesRegex(ValueError,"RNG"):replay(poisoned)
            poisoned=copy.deepcopy(declarations);poisoned[2]["predictions"]["LINEAR_ARX"][0]+=.01
            with self.assertRaisesRegex(ValueError,"prediction mismatch"):replay(record,poisoned)


if __name__=="__main__":unittest.main()
