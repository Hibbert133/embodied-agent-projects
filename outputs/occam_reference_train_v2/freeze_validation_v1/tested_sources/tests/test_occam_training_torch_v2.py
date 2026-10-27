"""Seven repeated optimizer checks of the new namespace; not seven new unique tests."""
from copy import deepcopy
import unittest
import numpy as np
try:
    import torch
except ImportError:torch=None


@unittest.skipIf(torch is None,'training Torch runtime tested in isolated process')
class TorchTrainingTests(unittest.TestCase):
    def setUp(self):
        from src.analysis.occam_meta_torch_v1 import PerformanceBasis
        torch.manual_seed(183);self.model=PerformanceBasis(664,87,bases=2,outputs=1,context_size=2,encoder_hidden=(3,),head_hidden=(4,))
        with torch.no_grad():self.model.prior_mean.fill_(.5)
        rng=np.random.default_rng(77);self.seq=dict(history=rng.normal(0,.05,(3,664)),descriptor=rng.normal(0,.05,(3,87)),targets=np.array([[.2],[-.1],[.4]]),full_window=np.array([True,True,False]),terminal=np.array([False,False,True]))

    def counters(self):return dict(Adam_updates=0,optimizer_step_attempts=0,attempts=0,allocated_episode_draws=0,inner_filter_updates=0,empty_batches=0)

    def test_real_meta_stage_has_gradients_and_one_counted_optimizer_step(self):
        from src.analysis.occam_reference_learner_v2 import stage
        class Support:
            def integers(self,low,high):return high-1
        opt=torch.optim.AdamW(self.model.parameters(),lr=.001);c=self.counters();before=self.model.head[0].weight.detach().clone()
        stage(self.model,opt,[self.seq],attempts=1,batch_size=1,mode='META',rng=np.random.default_rng(1),support_rng=Support(),max_support=4,counters=c)
        self.assertEqual(c['Adam_updates'],1);self.assertEqual(c['inner_filter_updates'],2);self.assertFalse(torch.equal(before,self.model.head[0].weight))

    def test_terminal_partial_rows_score_but_never_enter_filter_support(self):
        from src.analysis.occam_reference_learner_v2 import sequence_loss
        class Support:
            def integers(self,low,high):return high-1
        _,n=sequence_loss(self.model,self.seq,'META',Support(),4);self.assertEqual(n,2)
        s=deepcopy(self.seq);s['targets'][-1]=[10.];a,_=sequence_loss(self.model,self.seq,'META',Support(),4);b,_=sequence_loss(self.model,s,'META',Support(),4)
        self.assertGreater(b.item(),a.item())

    def test_all_empty_batch_does_not_invent_gradient_or_optimizer_update(self):
        from src.analysis.occam_reference_learner_v2 import stage
        empty={k:v[:0] for k,v in self.seq.items()};c=self.counters();opt=torch.optim.AdamW(self.model.parameters(),lr=.001)
        stage(self.model,opt,[empty],attempts=1,batch_size=2,mode='META',rng=np.random.default_rng(4),max_support=4,counters=c)
        self.assertEqual(c['attempts'],1);self.assertEqual(c['Adam_updates'],0);self.assertEqual(c['allocated_episode_draws'],2)

    def test_matched_data_draws_are_independent_of_meta_support_randomness(self):
        from src.analysis.occam_reference_learner_v2 import stage
        seen=[];records=[];c=self.counters();m=deepcopy(self.model);opt=torch.optim.AdamW(self.model.parameters(),lr=.001);o=torch.optim.AdamW(m.parameters(),lr=.001)
        empty={k:v[:0] for k,v in self.seq.items()};sources=[empty,empty,empty]
        stage(self.model,opt,sources,attempts=2,batch_size=3,mode='META',rng=np.random.default_rng(99),support_rng=np.random.default_rng(9),max_support=4,counters=c,progress=lambda a,l,i:seen.append(i))
        stage(m,o,sources,attempts=2,batch_size=3,mode='ERM',rng=np.random.default_rng(99),max_support=4,counters=self.counters(),progress=lambda a,l,i:records.append(i))
        self.assertEqual(seen,records)

    def test_public_learning_spec_rejects_CAL_and_budget_changes(self):
        from src.analysis.occam_reference_learner_v2 import validate_spec
        from src.analysis import occam_reference_train_io_v2 as a
        base=a.OUTPUT/'fixture';spec=dict(schema='OCCAM_PUBLIC_LEARNING_SPEC_V1',learning=a.learning(),allocated_episodes=648,public_trajectories=str(base/'train/public_trajectories.jsonl.gz'),public_sha256='a'*64,learning_source_sha256={},source_manifest_id='b'*64,no_private_or_registry_input=True)
        validate_spec(spec,base/'learning_spec.json',base/'learning')
        bad={**spec,'public_trajectories':str(base/'cal/public_trajectories.jsonl.gz')}
        with self.assertRaises(ValueError):validate_spec(bad,base/'learning_spec.json',base/'learning')
        bad=deepcopy(spec);bad['learning']['meta_attempts']=5000
        with self.assertRaises(ValueError):validate_spec(bad,base/'learning_spec.json',base/'learning')

    def test_nonfinite_target_fails_without_optimizer_step(self):
        from src.analysis.occam_reference_learner_v2 import stage
        bad=deepcopy(self.seq);bad['targets'][0,0]=float('nan');c=self.counters();opt=torch.optim.AdamW(self.model.parameters(),lr=.001)
        with self.assertRaises(ValueError):stage(self.model,opt,[bad],attempts=1,batch_size=1,mode='ERM',rng=np.random.default_rng(1),max_support=4,counters=c)
        self.assertEqual(c['optimizer_step_attempts'],0)

    def test_real_Torch_export_folds_masked_features_and_scalar_units(self):
        from src.analysis.occam_training_data_v1 import normalize,export_raw
        from src.probe.occam_performance_core_v1 import basis_forward
        stats=dict(schema='OCCAM_TRAIN_NORMALIZATION_V1',history_mean=[.02]*82,history_scale=[.3]*82,
            descriptor_mean=[.03]*87,descriptor_scale=[.4]*87,target_mean=.1,target_scale=.3,episodes=1,nonempty_episodes=1,
            fit_source='TRAIN_ONLY_EQUAL_EPISODE_THEN_WINDOW',scale_floor=.05)
        H=np.zeros((1,8,83));H[:,-2:,:82]=.125;H[:,-2:,82]=1.;X=self.seq['descriptor'][:1]
        h,x,_=normalize(stats,H.reshape(1,664),X)
        with torch.no_grad():expected=self.model(torch.as_tensor(h),torch.as_tensor(x)).numpy()
        raw=export_raw(self.model.export(),stats);actual=basis_forward(raw,H.reshape(1,664),X)
        np.testing.assert_allclose(actual[:,:,:2],expected*.3,atol=1e-13);np.testing.assert_allclose(actual[:,:,2],.1,atol=1e-14)

    def test_v2_learner_cannot_consume_closed_v1_public_data(self):
        from src.analysis.occam_reference_learner_v2 import validate_spec
        from src.analysis import occam_reference_train_io_v1 as old
        from src.analysis import occam_reference_train_io_v2 as new
        base=old.OUTPUT/'fixture'
        spec=dict(schema='OCCAM_PUBLIC_LEARNING_SPEC_V1',learning=new.learning(),allocated_episodes=648,
            public_trajectories=str(base/'train/public_trajectories.jsonl.gz'),public_sha256='a'*64,learning_source_sha256={},source_manifest_id='b'*64,no_private_or_registry_input=True)
        with self.assertRaises(ValueError):validate_spec(spec,base/'learning_spec.json',base/'learning')
