import unittest
import numpy as np
from src.perturbations import ActionBiasPerturbation,ActionScalePerturbation,BiasNoisePerturbation,GaussianNoisePerturbation,IdentityPerturbation
class PerturbationTest(unittest.TestCase):
    def setUp(self): self.action=np.array([.5,-.25,1.,-.7],dtype=np.float32)
    def test_identity(self): np.testing.assert_array_equal(IdentityPerturbation().apply(self.action),self.action)
    def test_scale_mask_and_gripper(self):
        out=ActionScalePerturbation(.4).apply(self.action); np.testing.assert_allclose(out[:3],self.action[:3]*.4); self.assertEqual(out[3],self.action[3])
    def test_noise_mask_gripper_and_seed(self):
        a=GaussianNoisePerturbation(.1); b=GaussianNoisePerturbation(.1); c=GaussianNoisePerturbation(.1)
        a.reset(3); b.reset(3); c.reset(4); x=a.apply(self.action); y=b.apply(self.action); z=c.apply(self.action)
        np.testing.assert_array_equal(x,y); self.assertFalse(np.array_equal(x,z)); self.assertEqual(x[3],self.action[3])
    def test_bias_axis_and_gripper(self):
        out=ActionBiasPerturbation((0,.08,0,0)).apply(self.action); np.testing.assert_allclose(out,self.action+[0,.08,0,0]); self.assertEqual(out[3],self.action[3])
    def test_bias_noise_is_seeded_and_keeps_gripper(self):
        a=BiasNoisePerturbation((.1,0,0,0),.05); b=BiasNoisePerturbation((.1,0,0,0),.05)
        a.reset(12); b.reset(12); x=a.apply(self.action); y=b.apply(self.action)
        np.testing.assert_array_equal(x,y); self.assertEqual(x[3],self.action[3]); self.assertNotEqual(x[0],self.action[0])
    def test_scalar_bias_rejected(self):
        with self.assertRaises(ValueError): ActionBiasPerturbation(.08)  # type: ignore[arg-type]
if __name__=='__main__': unittest.main()
