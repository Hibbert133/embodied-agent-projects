import gzip
import itertools
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_calibrated_tasks as runner
from tests.test_response_calibration import linear_trajectory
from src.probe.response_calibration import fit_response


class CalibratedTasksTest(unittest.TestCase):
    def test_prior_plan_uses_visible_evidence_and_same_bounded_grid(self):
        model=fit_response([(o,linear_trajectory(o)) for o in itertools.product((-.2,0.,.2),repeat=2)])
        evidence=linear_trajectory((.13,-.17),hidden=True)
        plan=runner.plan("PRIOR_AFFINE",evidence,model)
        self.assertLess(plan["correction"][0],0)
        self.assertGreater(plan["correction"][1],0)
        self.assertEqual(plan["correction"][2:],[0.,0.])
        self.assertLessEqual(max(abs(x) for x in plan["correction"]),.200001)
        with self.assertRaises(TypeError): runner.plan("PRIOR_AFFINE",evidence,model,true_bias=(.13,-.17))
        self.assertEqual(runner.plan("CONT_NO_CORRECTION",evidence,model)["correction"],[0.,0.,0.,0.])

    def test_complete_mocked_population_logs_decision_before_task_and_charges_prior(self):
        c=json.loads(runner.CONFIG.read_text()); c["bootstrap_samples"]=100
        model,sha=runner.load_model(c)
        m={"config":c,"source_git_commit":"test","experiment_run_id":"synthetic","input_sha256":{},"model_sha256":sha}
        m["manifest_id"]=runner.manifest_digest(m)
        resets=[]; created=[]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"manifest.json"; path.write_text(json.dumps(m))
            class Env:
                action_space=SimpleNamespace(low=-np.ones(4),high=np.ones(4))
                def __init__(self):
                    self.method=runner.METHODS[len(created)%5]; self.index=len(created)+1; created.append(self)
                def reset(self,**kw):
                    resets.append(kw); self.observation=np.zeros(39); self.calls=0
                    return self.observation.copy(),{}
                def step(self,command):
                    self.calls+=1
                    if (self.method=="NO_PROBE" and self.calls==1) or (self.method!="NO_PROBE" and self.calls==17):
                        declaration=json.loads((path.parent/"decisions.jsonl").read_text().splitlines()[-1])
                        self_case.assertEqual(declaration["episode_index"],self.index)
                        self_case.assertEqual(declaration["method"],self.method)
                    self.observation[:3]+=.01*command[:3]
                    return self.observation.copy(),0.,False,False,{"success":self.calls==18}
                def close(self): pass
            self_case=self
            with patch.object(runner,"check_clean"),patch.object(runner,"git",return_value="test"), \
                 patch.object(runner,"load_model",return_value=(model,sha)), \
                 patch.object(runner,"create_push_environment",side_effect=lambda seed:Env()), \
                 patch.object(runner,"create_push_policy",return_value=SimpleNamespace(get_action=lambda obs:np.zeros(4))),patch("builtins.print"):
                runner.run(path)
                with self.assertRaises(FileExistsError): runner.run(path)
            with gzip.open(path.parent/"episodes.jsonl.gz","rt",encoding="utf-8") as handle:
                rows=[json.loads(x) for x in handle]
            self.assertEqual(len(rows),320)
            self.assertEqual(len(resets),320)
            self.assertEqual([r["episode_index"] for r in rows],list(range(1,321)))
            for row in rows:
                if row["method"]!="NO_PROBE":
                    first=row["task_trace"][0]
                    self.assertEqual(first["host_calls"],17)
                    self.assertEqual(first["rng_before"],row["probe"]["rng_handoff"])
                    self.assertEqual(first["before_hash"],runner.state_hash(row["probe"]["handoff"]["observation"]))
            summary=json.loads((path.parent/"summary.json").read_text())
            self.assertEqual(summary["physical_steps"],320*18)
            self.assertEqual(summary["statistics"]["methods"]["PRIOR_AFFINE"]["mean_amortized_steps"],54)
            self.assertEqual(summary["statistics"]["methods"]["PRIOR_NEAREST"]["mean_amortized_resets"],3.25)
            self.assertFalse(summary["statistics"]["gate_passed"])


if __name__=="__main__": unittest.main()
