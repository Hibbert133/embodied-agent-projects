from dataclasses import replace
import itertools
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

from scripts import run_response_calibration as runner
from src.probe.continuous import StepObservation,collect_continuous,symmetric_program
from src.probe.response_calibration import (
    fit_response,trajectory_features,known_offset_program,infer_offset,infer_features,
)


def linear_trajectory(offset,*,hidden=False):
    position=np.zeros(39); velocity=np.zeros(2)
    response=np.array([[.012,.003],[-.002,.015]])
    def step(command):
        nonlocal velocity
        effective=command[:2]+np.array(offset) if hidden else command[:2]
        velocity=.6*velocity+response@effective
        position[:2]+=velocity
        return StepObservation(tuple(position),False,False,False)
    program=symmetric_program() if hidden else known_offset_program(offset)
    return collect_continuous(step,StepObservation(tuple(position),False,False,False),program,
                              remaining_budget=16,task_reserve=0)


class ResponseCalibrationTest(unittest.TestCase):
    def training(self):
        return [(offset,linear_trajectory(offset)) for offset in itertools.product((-.2,0.,.2),repeat=2)]

    def test_known_command_fit_generalizes_to_hidden_execution_offset(self):
        model=fit_response(self.training())
        self.assertEqual(model.training_trials,9)
        hidden=(.13,-.17)
        evidence=linear_trajectory(hidden,hidden=True)
        np.testing.assert_allclose(infer_offset(model,evidence),hidden,atol=1e-7)
        self.assertEqual(infer_offset(model,evidence,method="nearest"),(.2,-.2))

    def test_features_ignore_absolute_initial_pose_and_reject_discontinuity(self):
        evidence=linear_trajectory((.2,0.))
        shift=(10.,20.,0.)+(0.,)*36
        shifted=tuple(replace(row,before=tuple(np.array(row.before)+shift),after=tuple(np.array(row.after)+shift))
                      for row in evidence.transitions)
        final=replace(evidence.final,observation=shifted[-1].after)
        np.testing.assert_allclose(trajectory_features(replace(evidence,transitions=shifted,final=final)),trajectory_features(evidence),atol=1e-14)
        rows=list(evidence.transitions); rows[3]=replace(rows[3],before=(0.,)*39)
        with self.assertRaisesRegex(ValueError,"discontinuous"):
            trajectory_features(replace(evidence,transitions=tuple(rows)))

    def test_no_label_argument_at_deployment_and_nominal_program_required(self):
        model=fit_response(self.training())
        with self.assertRaises(TypeError):
            infer_features(model,np.zeros(32),known_command_offset=(.2,0.))
        with self.assertRaisesRegex(ValueError,"nominal"):
            infer_offset(model,linear_trajectory((.2,0.)))
        with self.assertRaisesRegex(ValueError,"known commanded"):
            fit_response([((0.,.2),linear_trajectory((.2,0.)))])

    def test_unidentifiable_training_and_incomplete_probe_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"full planar rank"):
            fit_response([((0.,0.),linear_trajectory((0.,0.)))])
        evidence=linear_trajectory((0.,0.))
        with self.assertRaisesRegex(ValueError,"complete"):
            trajectory_features(replace(evidence,transitions=evidence.transitions[:5]))
        for offset in ((.3,0.),(float("nan"),0.),(0.,)):
            with self.assertRaises(ValueError): known_offset_program(offset)

    def test_full_mocked_run_freezes_model_before_qualification_and_audits(self):
        c=json.loads(runner.CONFIG.read_text())
        m={"config":c,"source_git_commit":"test","experiment_run_id":"synthetic","input_sha256":{}}
        m["manifest_id"]=runner.manifest_digest(m)
        resets=[]
        class Env:
            action_space=SimpleNamespace(low=-np.ones(4),high=np.ones(4))
            def reset(self,**kw):
                resets.append(kw); self.position=np.zeros(39); self.calls=0
                return self.position.copy(),{}
            def step(self,command):
                self.calls+=1; self.position[:3]+=.01*command[:3]
                return self.position.copy(),0.,False,False,{"success":False}
            def close(self): pass
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"manifest.json"; path.write_text(json.dumps(m))
            frozen=[]
            def environment(seed):
                if seed==8908 and not frozen:
                    model_path=path.parent/"model.json"
                    self.assertTrue(model_path.exists())
                    frozen.append(runner.digest(model_path))
                    self.assertEqual(json.loads(model_path.read_text())["frozen_after_sequence"],72)
                    self.assertFalse((path.parent/"qualification.jsonl").exists())
                return Env()
            with patch.object(runner,"check_clean"),patch.object(runner,"git",return_value="test"), \
                 patch.object(runner,"create_push_environment",side_effect=environment),patch("builtins.print"):
                runner.run(path)
                with self.assertRaises(FileExistsError): runner.run(path)
            self.assertEqual(len(resets),144)
            self.assertEqual(runner.digest(path.parent/"model.json"),frozen[0])
            result=runner.audit(path)
            self.assertEqual(result["physical_steps"],2304)
            self.assertEqual(result["integrity"],"PASSED")
            self.assertTrue(result["statistics"]["gate_passed"])
            saved_path=path.parent/"model.json"
            saved=json.loads(saved_path.read_text()); saved["model"]["training_trials"]=73
            saved_path.write_text(json.dumps(saved))
            with self.assertRaisesRegex(ValueError,"training-only model"):
                runner.audit(path)


if __name__=="__main__": unittest.main()
