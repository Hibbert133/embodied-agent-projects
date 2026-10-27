import unittest
import numpy as np
try:
    import torch
except ImportError:
    torch=None
from src.probe import occam_performance_core_v1 as core
from src.analysis.occam_performance_independent_v1 import batch_posterior


@unittest.skipIf(torch is None,'isolated pinned CPU Torch runtime is required')
class MetaPerformanceTests(unittest.TestCase):
    def setUp(self):
        from src.analysis import occam_meta_torch_v1 as module
        self.module=module;torch.manual_seed(37)

    def fixture(self):
        m=self.module.PerformanceBasis(4,3,bases=3,outputs=2,context_size=3,encoder_hidden=(5,),head_hidden=(6,))
        h=torch.randn(5,4,dtype=torch.float64);d=torch.randn(5,3,dtype=torch.float64);y=torch.randn(5,2,dtype=torch.float64)
        return m,h,d,y

    def test_tensor_filter_matches_numpy_and_joint_conditioning(self):
        rng=np.random.default_rng(9);H=rng.normal(size=(4,2,3));Y=rng.normal(size=(4,2));m=np.zeros(3);p=np.eye(3);q=np.diag([.1,.2,0.]);r=np.array([[.3,.1],[.1,.2]])
        tm,tp=torch.tensor(m),torch.tensor(p)
        for h,y in zip(H,Y):tm,tp=self.module.filter_step(tm,tp,torch.tensor(h),torch.tensor(y),torch.tensor(q),torch.tensor(r))
        a,b=batch_posterior(m,p,H,Y,q,r);np.testing.assert_allclose(tm.numpy(),a,atol=1e-11);np.testing.assert_allclose(tp.numpy(),b,atol=1e-11)

    def test_exported_numpy_basis_matches_tensor(self):
        m,h,d,y=self.fixture();expected=m(h,d).detach().numpy();actual=core.basis_forward(m.export(),h.numpy(),d.numpy())
        np.testing.assert_allclose(actual,expected,atol=1e-12)

    def test_meta_gradient_matches_central_difference(self):
        m,h,d,y=self.fixture();loss,_=self.module.meta_loss(m,h,d,y,[0,2]);loss.backward()
        analytical=m.process_factor.grad[0,0].item();initial=m.process_factor[0,0].item();values=[]
        for delta in (-1e-6,1e-6):
            with torch.no_grad():m.process_factor[0,0]=initial+delta
            values.append(self.module.meta_loss(m,h,d,y,[0,2])[0].item())
        with torch.no_grad():m.process_factor[0,0]=initial
        self.assertAlmostEqual(analytical,(values[1]-values[0])/2e-6,places=7)

    def test_one_synthetic_optimizer_step_updates_all_parameter_families(self):
        m,h,d,y=self.fixture();optimizer=torch.optim.Adam(m.parameters(),lr=1e-3);before={n:p.detach().clone() for n,p in m.named_parameters()}
        loss,_=self.module.meta_loss(m,h,d,y,[0,2]);loss.backward()
        for family in ('encoder','head','prior_mean','prior_factor','process_factor','measurement_factor'):
            self.assertTrue(any(p.grad is not None and torch.isfinite(p.grad).all() and p.grad.abs().sum()>0 for n,p in m.named_parameters() if n.startswith(family)),family)
        optimizer.step();self.assertTrue(any(not torch.equal(p,before[n]) for n,p in m.named_parameters()))

    def test_meta_support_is_explicit_and_full_loss_has_all_rows(self):
        m,h,d,y=self.fixture();loss,result=self.module.meta_loss(m,h,d,y,[0,2])
        self.assertAlmostEqual(loss.item(),((result['predictions']-y)**2).mean().item())
        for indices in ([],[0,0],[5]):
            with self.assertRaises(ValueError):self.module.meta_loss(m,h,d,y,indices)

    def test_transposed_basis_and_singular_measurement_rejected(self):
        with self.assertRaises(ValueError):self.module.filter_step(torch.zeros(3,dtype=torch.float64),torch.eye(3,dtype=torch.float64),torch.ones(3,2,dtype=torch.float64),torch.zeros(2,dtype=torch.float64),torch.eye(3,dtype=torch.float64),torch.eye(2,dtype=torch.float64))
        with self.assertRaises(ValueError):self.module.filter_step(torch.zeros(1,dtype=torch.float64),torch.eye(1,dtype=torch.float64),torch.ones(1,1,dtype=torch.float64),torch.zeros(1,dtype=torch.float64),torch.zeros(1,1,dtype=torch.float64),torch.zeros(1,1,dtype=torch.float64))
