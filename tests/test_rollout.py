import json,tempfile,unittest
from pathlib import Path
import numpy as np
from src.perturbations import ActionBiasPerturbation,IdentityPerturbation
from src.rollout import run_episode
def obs(n=0):
    x=np.zeros(39); x[:3]=[0,0,0]; x[4:7]=[.1+n*.01,0,0]; x[-3:]=[.2,0,0]; return x
class Space:
    low=np.full(4,-1,dtype=np.float32); high=np.full(4,1,dtype=np.float32)
class Env:
    action_space=Space()
    def __init__(self): self.actions=[]
    def reset(self,seed): self.actions=[]; return obs(),{}
    def step(self,a): self.actions.append(a.copy()); n=len(self.actions); return obs(n),1.,False,n>=2,{"success":n==2}
class Policy:
    def __init__(self,a): self.a=np.asarray(a,dtype=np.float32)
    def get_action(self,o): return self.a.copy()
class RolloutTest(unittest.TestCase):
    def test_clipping_statistics(self):
        r=run_episode(Env(),Policy([2,-2,.5,.2]),seed=1,max_steps=2,stop_on_success=False)
        self.assertEqual(r.clipped_step_count,2); self.assertEqual(r.clipped_step_fraction,1); self.assertEqual(r.clipped_element_count,4); self.assertEqual(r.clipped_element_fraction,.5)
    def test_bias_clipped_and_in_range(self):
        e=Env(); r=run_episode(e,Policy([.5,0,0,.2]),seed=1,max_steps=2,stop_on_success=False,perturbation=ActionBiasPerturbation((1.,0,0,0)))
        self.assertTrue(all(np.all(a<=1) and np.all(a>=-1) for a in e.actions)); self.assertEqual(r.clipped_step_count,2)
    def test_identity_matches_baseline(self):
        a=run_episode(Env(),Policy([.2,0,0,.2]),seed=1,max_steps=2); b=run_episode(Env(),Policy([.2,0,0,.2]),seed=1,max_steps=2,perturbation=IdentityPerturbation())
        self.assertEqual((a.success,a.steps,a.episode_return,a.clipped_step_count),(b.success,b.steps,b.episode_return,b.clipped_step_count))
    def test_transition_alignment_and_command_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"trajectory.jsonl"
            run_episode(Env(),Policy([.2,0,0,.2]),seed=1,max_steps=2,trajectory_path=path,stop_on_success=False,perturbation=ActionBiasPerturbation((.1,0,0,0)))
            rows=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        first=rows[0]
        np.testing.assert_array_equal(first["observation"],obs(0))
        np.testing.assert_array_equal(first["next_observation"],obs(1))
        np.testing.assert_array_equal(first["commanded_action"],first["raw_action"])
        self.assertNotEqual(first["commanded_action"],first["perturbed_action"])
        self.assertAlmostEqual(first["task_progress_metrics"]["object_position"][0],obs(1)[4])
        np.testing.assert_array_equal(rows[1]["observation"],first["next_observation"])
if __name__=='__main__': unittest.main()
