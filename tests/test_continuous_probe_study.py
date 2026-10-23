import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from scripts import run_continuous_probe as runner
from src.probe.continuous import StepObservation,collect_continuous,symmetric_program
from src.probe.continuous_baselines import decision,static_fit


class ContinuousStudyTest(unittest.TestCase):
    def test_static_fit_and_common_bounded_quantization(self):
        position=np.zeros(3)
        def step(command):
            position[:2]+=.01*(command[:2]+np.array([.145,-.18]))
            return StepObservation(tuple(position),False,False,False)
        evidence=collect_continuous(step,StepObservation((0.,0.,0.),False,False,False),symmetric_program(),remaining_budget=500,task_reserve=484)
        np.testing.assert_allclose(static_fit(evidence)["bias_in_command_units"],[.145,-.18],atol=1e-9)
        np.testing.assert_allclose(decision("CONT_STATIC",evidence)["correction"],[-.145,.18,0,0],atol=1e-7)
        self.assertEqual(decision("CONT_NO_CORRECTION",evidence)["correction"],[0.,0.,0.,0.])

    def test_full_mocked_study_keeps_rng_and_state_across_handoff(self):
        config=json.loads(runner.CONFIG.read_text()); config["bootstrap_samples"]=100
        manifest={"config":config,"source_git_commit":"test","experiment_run_id":"synthetic","input_sha256":{}}
        manifest["manifest_id"]=runner.manifest_digest(manifest)
        resets=[]
        class Env:
            action_space=SimpleNamespace(low=np.full(4,-1.),high=np.full(4,1.))
            def reset(self,**kwargs):
                resets.append(kwargs); self.obs=np.zeros(39); self.calls=0
                return self.obs.copy(),{}
            def step(self,command):
                self.calls+=1; self.obs[:3]+=.01*command[:3]
                return self.obs.copy(),0.,False,False,{"success":self.calls==18,"context_oracle":"must_not_escape"}
            def close(self): pass
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"manifest.json"; path.write_text(json.dumps(manifest))
            with patch.object(runner,"check_clean"),patch.object(runner,"git",return_value="test"), \
                 patch.object(runner,"create_push_environment",side_effect=lambda seed:Env()), \
                 patch.object(runner,"create_push_policy",return_value=SimpleNamespace(get_action=lambda obs:np.zeros(4))),patch("builtins.print"):
                runner.run(path)
                with self.assertRaises(FileExistsError): runner.run(path)
            events=[json.loads(x) for x in (path.parent/"events.jsonl").read_text().splitlines()]
            self.assertEqual(len(resets),288)
            self.assertEqual([x["sequence"] for x in events],list(range(1,len(events)+1)))
            outcomes=[x for x in events if x["kind"]=="outcome"]
            self.assertEqual(len(outcomes),160)
            for probe in (x for x in events if x["kind"]=="probe" and x["method"].startswith("CONT_")):
                group=[x for x in events if (x["seed"],x["condition_oracle"],x["method"]) ==
                       (probe["seed"],probe["condition_oracle"],probe["method"])]
                steps=[x for x in group if x["kind"]=="step"]
                self.assertEqual(steps[0]["host_calls"],17)
                self.assertEqual(steps[0]["before_hash"],runner.state_hash(probe["handoff"]["observation"]))
                self.assertEqual(steps[0]["rng_before"],probe["rng_handoff"])
                self.assertNotIn("context_oracle",probe["continuous"]["final"])
                self.assertEqual([x for x in group if x["kind"]=="outcome"][0]["total_steps"],18)
            status=json.loads((path.parent/"status.json").read_text())
            self.assertEqual(status["environment_resets"],288)
            self.assertEqual(status["physical_steps"],32*(18*4+34))
            self.assertEqual(status["status"],"COMPLETED_FEASIBILITY_FAILED")

    def test_live_host_rejects_post_terminal_step_and_never_reseeds(self):
        from src.perturbations import BiasNoisePerturbation
        env=SimpleNamespace(reset=lambda **kw:(np.zeros(39),{}),
            step=lambda a:(np.zeros(39),0.,False,False,{"success":True}),
            action_space=SimpleNamespace(low=-np.ones(4),high=np.ones(4)))
        fault=BiasNoisePerturbation([0,0,0,0],.05)
        with patch.object(fault,"reset",wraps=fault.reset) as reset:
            host=runner.LiveHost(env,fault,0,1)
            host.step(np.zeros(4))
            with self.assertRaises(ValueError): host.step(np.zeros(4))
            self.assertEqual(reset.call_count,1)
            self.assertEqual(host.calls,1)


if __name__=="__main__": unittest.main()
