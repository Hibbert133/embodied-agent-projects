from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,mock
import sys
import numpy as np
import rank_core_v1 as c
import rank_audit_v1 as a
import run_rank_v1 as r

SYNTHETIC_LEDGER=dict(linear_solves=0,symmetric_eigendecompositions=0,projected_model_solutions=0)
INDEPENDENT_LEDGER=dict(kernel_eigendecompositions=0,augmented_lstsq=0,augmented_QR=0,rank_SVD=0,PCA_SVD=0,reconstructed_model_solutions=0)


def arrays():
    rng=np.random.default_rng(20261029);x=rng.normal(size=(24,5));g=np.repeat(np.arange(4),6)
    y=.5+.06*np.tanh(x@rng.normal(size=(5,12)))+.01*rng.normal(size=(24,12))
    return x,y,g


def node():
    def s(i):return dict(observation=[i/100]+[0.]*38,terminated=False,truncated=False,success=False)
    return dict(schema='COMPLETE_RISK_PUBLIC_NODE_V1',stage='PRE',task='push-v3',completed_steps=16,
        current=s(16),integral_xy=[0.,0.],controller=dict(source='UNCORRECTED',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.]*4),
        acquisition_action=None,history=[dict(at_calls=i,before=s(i),command=[.125,0.,0.,0.],after=s(i+1)) for i in range(16)])


class RankTests(TestCase):
    def test_public_decoder_matches_independent(self):self.assertTrue(np.array_equal(c.features(node()),a.feature_vector(node())))
    def test_private_future_fields_rejected(self):
        for key in ('seed','fault_oracle','future_loss','context'):
            n=node();n[key]=1
            with self.assertRaises(ValueError):c.features(n)
    def test_future_history_rejected(self):
        n=node();n['history'].append(deepcopy(n['history'][-1]))
        with self.assertRaises(ValueError):c.features(n)
    def test_wrong_current_and_phase_rejected(self):
        n=node();n['current']=n['history'][0]['before']
        with self.assertRaises(ValueError):c.features(n)
        n=node();n['stage']='RETURN'
        with self.assertRaises(ValueError):c.features(n)
    def test_terminal_not_padded_as_decision(self):
        n=node();n['current']['success']=True
        with self.assertRaises(ValueError):c.features(n)
    def test_float32_clipped_send_required(self):
        for u in (.1,1.1):
            n=node();n['history'][0]['command'][0]=u
            with self.assertRaises(ValueError):c.features(n)
    def test_group_weight_mass(self):
        g=[0,0,0,1];w=c.weights(g);self.assertEqual(sum(w[:3]),w[3]);self.assertTrue(np.allclose(w,a.group_weights(g)))
    def test_contrast_basis_preserves_common_direction(self):
        d=c.contrast_basis();self.assertTrue(np.allclose(d.T@d,np.eye(11)));self.assertTrue(np.allclose(d.T@np.ones(12),0))
    def test_normalization_only_training_columns(self):
        x=np.array([[1.,0.],[1.,2.]]);active,mean,scale,z=c.normalize(x,np.ones(2));self.assertEqual(active.tolist(),[1]);self.assertTrue(np.allclose(z[:,0],[-1,1]))
    def test_kernel_symmetry_and_psd(self):
        x,_,_=arrays()
        for kind in c.KINDS:self.assertGreaterEqual(np.linalg.eigvalsh(c.kernel(x,x,kind)).min(),-1e-10)
    def test_full_matches_original_intercept_system(self):
        x,y,g=arrays()
        for kind in c.KINDS:
            b=c.fit_base(x,y,g,kind,SYNTHETIC_LEDGER);k=b['k'];w=b['weights'];n=len(x)
            system=np.block([[k+np.diag(.01/w),np.ones((n,1))],[np.ones((1,n)),np.zeros((1,1))]])
            beta=np.linalg.solve(system,np.vstack([y,np.zeros((1,12))]))
            self.assertTrue(np.allclose(c.predict(b,x,np.eye(12)),k@beta[:-1]+beta[-1],atol=1e-9))
    def test_reduced_rank_total_matches_control(self):
        x,y,g=arrays();models,_=c.fit_models(x,y,g,SYNTHETIC_LEDGER)
        self.assertEqual(np.linalg.matrix_rank(models['RBF_RR2'][1],tol=1e-8),3)
        self.assertEqual(np.linalg.matrix_rank(models['RBF_RAW_RR3'][1],tol=1e-8),3)
    def test_common_signal_not_leaked_into_contrasts(self):
        x,y,g=arrays();common=np.linspace(.3,.7,len(x))[:,None];yy=np.tile(common,(1,12))
        models,_=c.fit_models(x,yy,g,SYNTHETIC_LEDGER)
        for name,(b,p) in models.items():
            if 'RAW' not in name:
                scores=c.predict(b,x,p);self.assertLess(float(np.ptp(scores,axis=1).max()),1e-8)
    def test_adding_shared_cost_preserves_contrast_prediction(self):
        x,y,g=arrays();models,_=c.fit_models(x,y,g,SYNTHETIC_LEDGER);other,_=c.fit_models(x,y+.02*np.tanh(x[:,0,None]),g,SYNTHETIC_LEDGER)
        for name in ('RBF_RR2','LINEAR_RR2','RBF_PCA2'):
            p=c.predict(*models[name][:1],x,models[name][1]);q=c.predict(*other[name][:1],x,other[name][1])
            self.assertTrue(np.allclose(p-p.mean(1)[:,None],q-q.mean(1)[:,None],atol=1e-8))
    def test_full_training_targets_not_used_in_geometry(self):
        x,y,g=arrays();b=c.fit_base(x,y,g,'RBF',SYNTHETIC_LEDGER);other=c.fit_base(x,1-y,g,'RBF',SYNTHETIC_LEDGER)
        self.assertTrue(np.array_equal(b['centers'],other['centers']))
    def test_tied_eigenspace_is_canonical(self):
        vals,v=c.canonical_eigenspace(np.eye(4));self.assertTrue(np.allclose(v,np.eye(4)));self.assertTrue(np.all(vals==1))
    def test_constant_feature_kernel(self):
        x=np.zeros((12,3));y=np.tile(np.linspace(.2,.8,12),(12,1));g=np.repeat([0,1],6)
        models,_=c.fit_models(x,y,g,SYNTHETIC_LEDGER)
        for b,p in models.values():self.assertTrue(np.allclose(c.predict(b,x,p),y,atol=1e-9))
    def test_independent_augmented_svd_main_disabled(self):
        x,y,g=arrays();models,_=c.fit_models(x,y,g,SYNTHETIC_LEDGER)
        expected={n:c.predict(b,x,p) for n,(b,p) in models.items()}
        def deny(*args,**kw):raise RuntimeError('disabled')
        disabled={n:deny for n,v in vars(c).items() if callable(v) and getattr(v,'__module__',None)==c.__name__}
        with mock.patch.multiple(c,**disabled):
            for kind in ('LINEAR','RBF'):
                scores,_=a.reconstruct(x,y,g,kind,x,INDEPENDENT_LEDGER)
                for n,v in scores.items():self.assertTrue(np.allclose(v,expected[n],atol=1e-7))
    def test_fixed_tie_and_risk_clipping(self):
        self.assertEqual(c.choice(np.full(12,-2.)),0);self.assertEqual(c.choice(np.full(12,2.)),0)
    def test_heldout_group_never_fits_or_normalizes(self):
        x,y,g=arrays();train=g!=0;before=c.fit_base(x[train],y[train],g[train],'RBF',SYNTHETIC_LEDGER)
        y[g==0]=0;x[g==0]=1000;after=c.fit_base(x[train],y[train],g[train],'RBF',SYNTHETIC_LEDGER)
        self.assertTrue(np.array_equal(before['alpha'],after['alpha']));self.assertTrue(np.array_equal(before['centers'],after['centers']))
    def test_guard_forbids_environment_network_and_QUAL(self):
        with r.guard([]) as guard:
            with self.assertRaises(RuntimeError):sys.audit('import','metaworld',None,None,None,None)
            with self.assertRaises(RuntimeError):sys.audit('socket.connect',None,None)
            with self.assertRaises(RuntimeError):open(r.ROOT/'QUAL_UNDECLARED','rb')
        self.assertEqual(sum(guard.values()),3)
    def test_invalid_label_range_rejected(self):
        x,y,g=arrays();y[0,0]=2
        with self.assertRaises(ValueError):c.fit_base(x,y,g,'RBF',SYNTHETIC_LEDGER)
