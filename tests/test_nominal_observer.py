import copy
from dataclasses import replace
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from src.probe.continuous import ContinuousTransition,symmetric_program
from src.probe.frame_identification import NominalARX
from src.probe.nominal_observer import NominalObserver,passive_affine_fit,mean_blocks
from src.rollout.task_registry import create_task_environment,create_task_policy
from scripts import run_nominal_observer as runner
from scripts import analyze_nominal_observer as auditor


def nominal():
    return NominalARX(((.6,0.),(0.,.6)),((.012,.003),(-.002,.015)),(0.,0.),1080,72,5,2.,0.,"synthetic")


def samples_for(commands,operator=None):
    observer=NominalObserver(nominal());position=np.zeros(39);velocity=np.zeros(2);samples=[]
    operator=np.array([[1.,0.,0.],[0.,1.,0.]]) if operator is None else operator
    for sent in commands:
        before=tuple(position);velocity=.6*velocity+np.array(nominal().response)@(operator@np.array([*sent[:2],1.]))
        position[:2]+=velocity
        sample=observer.observe(ContinuousTransition(tuple(sent),before,tuple(position)),phase="PROBE")
        if sample:samples.append(sample)
    return observer,samples


class NominalObserverTest(unittest.TestCase):
    def test_visible_inverse_recovers_affine_response_without_truth_argument(self):
        operator=np.array([[0.,-1.,.1],[1.,0.,-.1]])
        observer,samples=samples_for(symmetric_program(),operator)
        self.assertEqual(observer.calls,16);self.assertEqual(len(samples),15)
        self.assertEqual(samples[0].step,2)
        for row in samples:
            np.testing.assert_allclose(row.estimate,operator@np.array([*row.command[:2],1.]),atol=1e-12)
        fit=passive_affine_fit(samples)
        self.assertTrue(fit["valid"]);np.testing.assert_allclose(fit["matrix"],operator,atol=1e-12)
        self.assertFalse(fit["model_validity_qualified"])
        with self.assertRaises(TypeError):observer.observe(None,phase="PROBE",true_operator=operator)

    def test_inverse_rejects_discontinuity_and_invalid_visible_data(self):
        observer,_=samples_for(symmetric_program()[:1])
        bad=ContinuousTransition((0.,0.,0.,0.),(0.,)*39,(0.,)*39)
        with self.assertRaisesRegex(ValueError,"continuity"):observer.observe(bad,phase="POLICY")
        for value in (float("nan"),True):
            fresh=NominalObserver(nominal());row=replace(bad,before=(value,)+(0.,)*38)
            with self.assertRaisesRegex(ValueError,"visible"):fresh.observe(row,phase="PROBE")

    def test_blocks_use_four_past_samples_and_label_boundary(self):
        _,samples=samples_for(symmetric_program())
        samples=[replace(s,phase="PROBE" if s.step<=8 else "POLICY") for s in samples]
        blocks=mean_blocks(samples)
        self.assertEqual(len(blocks),3)
        self.assertEqual((blocks[0]["start_step"],blocks[0]["end_step"]),(2,5))
        self.assertEqual(blocks[1]["phase"],"MIXED")
        self.assertTrue(all(b["nominal_mean_error_inf"]<1e-12 for b in blocks))
        bad=list(samples);bad[2]=replace(bad[2],step=99)
        with self.assertRaisesRegex(ValueError,"consecutive"):mean_blocks(bad)

    def test_passive_fit_rejects_small_or_unexcited_history(self):
        _,samples=samples_for(symmetric_program()[:8])
        self.assertEqual(passive_affine_fit(samples)["reason"],"INSUFFICIENT_SAMPLES")
        _,samples=samples_for(symmetric_program()[:4]*4)
        self.assertEqual(passive_affine_fit(samples)["reason"],"MISSING_INPUT_SUPPORT")
        with self.assertRaisesRegex(ValueError,"visible inverse"):passive_affine_fit([{"true_model":[]}])

    def test_task_registry_fails_closed_before_environment_creation(self):
        with self.assertRaisesRegex(ValueError,"unregistered"):create_task_environment("unknown",0)
        with self.assertRaisesRegex(ValueError,"unregistered"):create_task_policy("unknown")

    def test_full_mocked_collection_and_adversarial_independent_replay(self):
        c=json.loads(runner.CONFIG.read_text());fake_model=nominal();policy=SimpleNamespace(get_action=lambda obs:np.array([.01,-.02,0.,1.]))
        hashes={task:"synthetic" for task in c["tasks"]}
        m={"experiment_run_id":"synthetic","source_git_commit":"test","config":c,"policy_sha256":hashes,"input_sha256":{}}
        m["manifest_id"]=runner.manifest_digest(m);created=[];resets=[];case=self
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"manifest.json";path.write_text(json.dumps(m))
            class Env:
                action_space=SimpleNamespace(low=-np.ones(4),high=np.ones(4))
                def __init__(self):self.index=len(created)+1;created.append(self)
                def reset(self,**kwargs):
                    resets.append(kwargs);self.position=np.zeros(39);self.velocity=np.zeros(2);self.calls=0
                    return self.position.copy(),{}
                def step(self,sent):
                    if self.calls in c["snapshot_steps"]:
                        last=json.loads((path.parent/"snapshots.jsonl").read_text().splitlines()[-1])
                        case.assertEqual((last["episode_index"],last["step"]),(self.index,self.calls))
                        case.assertNotIn("nominal_identity_error_inf",last)
                    self.calls+=1;self.velocity=.6*self.velocity+np.array(fake_model.response)@sent[:2];self.position[:2]+=self.velocity
                    return self.position.copy(),0.,False,False,{"success":self.calls==20}
                def close(self):pass
            with patch.object(runner,"check_clean"),patch.object(runner,"git",return_value="test"), \
                 patch.object(runner,"policy_hashes",return_value=hashes),patch.object(runner,"model",return_value=fake_model), \
                 patch.object(runner,"create_task_environment",side_effect=lambda task,seed:Env()), \
                 patch.object(runner,"create_task_policy",return_value=policy),patch("builtins.print"):
                runner.run(path)
                with self.assertRaisesRegex(FileExistsError,"cannot restart"):runner.run(path)
            with patch.object(runner,"policy_hashes",return_value=hashes),patch.object(auditor,"model",return_value=fake_model), \
                 patch.object(auditor,"create_task_policy",return_value=policy):
                result=auditor.analyze(path)
            self.assertEqual(len(resets),96);self.assertEqual(result["physical_steps"],1920)
            self.assertEqual(result["snapshots"],192);self.assertEqual(result["integrity"],"PASSED")
            with gzip.open(path.parent/"episodes.jsonl.gz","rt",encoding="utf-8") as handle:record=json.loads(next(handle))
            declarations=[json.loads(line) for line in (path.parent/"snapshots.jsonl").read_text().splitlines()[:2]]
            def replay(row,decl=declarations):
                with patch.object(auditor,"create_task_policy",return_value=policy):return auditor.verify_record(m,row,decl,fake_model)
            changed=copy.deepcopy(record);changed["trace"][1]["inverse_sample"]["estimate"][0]+=.1
            with self.assertRaisesRegex(ValueError,"inverse-formula"):replay(changed)
            changed=copy.deepcopy(declarations);changed[0]["samples_seen"]+=1
            with self.assertRaisesRegex(ValueError,"future/evaluator"):replay(record,changed)
            changed=copy.deepcopy(record);changed["trace"][1]["rng_before"]="reset"
            with self.assertRaisesRegex(ValueError,"reseeded"):replay(changed)


if __name__=="__main__":unittest.main()
