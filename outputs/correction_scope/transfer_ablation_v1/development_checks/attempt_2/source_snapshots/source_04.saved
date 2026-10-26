"""Constructed arrays/public nodes only; no environment/network creation."""
from copy import deepcopy
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import unittest
import numpy as np
from src.analysis import correction_transfer_ablation_v1 as m
from src.analysis import correction_transfer_ablation_independent_v1 as q
from src.analysis import correction_auxiliary_targets_v1 as labels
from src.analysis import transfer_risk_math_v1 as net
from src.analysis import transfer_risk_independent_math_v1 as numbers
spec=spec_from_file_location('ablation_public_fixture',Path(__file__).parent/'test_correction_scope_risk_reference_v1.py')
fixture=module_from_spec(spec);spec.loader.exec_module(fixture)
SYNTHETIC_LEDGER={}


def fixture_data(n=16):
    nodes=[m.prior.old.node_from_view(fixture.view(n=n,stage='POST',value=i/8)) for i in range(3)]
    for node in nodes:
        for row in node['history']:row['command']=[.25,0.,0.,0.]
    rng=np.random.default_rng(152);p=rng.uniform(.1,1,(3,4,24));p/=p.sum(2,keepdims=True)
    error=rng.uniform(.1,2,(3,4,24));j=p*error
    target=np.concatenate((p,j,j.sum(2,keepdims=True),np.full((3,4,1),.75)),axis=2)
    return nodes,target


class AuxiliaryAblationTests(unittest.TestCase):
    def test_marginal_replacement_preserves_all_other_factual_channels(self):
        nodes,y=fixture_data();z=labels.supervision(nodes,y,'FUTURE_MARGINAL_PRODUCT')
        np.testing.assert_array_equal(z[:,:,:24],y[:,:,:24]);np.testing.assert_array_equal(z[:,:,48:],y[:,:,48:])

    def test_marginal_error_covariance_is_removed(self):
        nodes,y=fixture_data();z=labels.supervision(nodes,y,'FUTURE_MARGINAL_PRODUCT')
        np.testing.assert_allclose(z[:,:,24:48]-z[:,:,:24]*z[:,:,48:49],0,atol=1e-14)
        self.assertGreater(np.max(abs(y[:,:,24:48]-z[:,:,24:48])),.01)

    def test_marginal_still_retains_rate_specific_information(self):
        nodes,y=fixture_data();z=labels.supervision(nodes,y,'FUTURE_MARGINAL_PRODUCT')
        self.assertGreater(np.max(abs(z[:,0]-z[:,1])),.01)

    def test_rate_mean_heads_identical_and_keep_node_average(self):
        nodes,y=fixture_data();z=labels.supervision(nodes,y,'FUTURE_RATE_MEAN')
        for r in range(4):np.testing.assert_array_equal(z[:,r],y.mean(1))

    def test_rate_mean_is_not_a_single_executed_branch(self):
        nodes,y=fixture_data();z=labels.supervision(nodes,y,'FUTURE_RATE_MEAN')
        self.assertTrue(all(not np.array_equal(z[0,0],y[0,r]) for r in range(4)))

    def test_short_history_real_fraction_and_observed_error(self):
        nodes,y=fixture_data(16);z=labels.supervision(nodes,y,'HISTORY_RECONSTRUCT')
        np.testing.assert_array_equal(z[:,:,49],.5);np.testing.assert_array_equal(z[:,:,48],.25**2)
        np.testing.assert_array_equal(z[:,:,:24].sum(2),1)

    def test_history_at_most32_no_virtual_earliest_displacements(self):
        nodes,y=fixture_data(40)
        for node in nodes:
            for r in node['history'][:8]:r['command']=[1.,0.,0.,0.]
        z=labels.supervision(nodes,y,'HISTORY_RECONSTRUCT');np.testing.assert_array_equal(z[:,:,48],.25**2);np.testing.assert_array_equal(z[:,:,49],1)

    def test_history_control_does_not_read_query_specific_future_target(self):
        nodes,y=fixture_data();z=labels.supervision(nodes,y,'HISTORY_RECONSTRUCT');y[:,:,24:49]*=123
        np.testing.assert_array_equal(z,labels.supervision(nodes,y,'HISTORY_RECONSTRUCT'))

    def test_empty_past_is_missing_not_zero_label(self):
        node=m.prior.old.node_from_view(fixture.view(n=0,stage='POST'))
        with self.assertRaises(ValueError):labels.past_summary(node)
        with self.assertRaises(ValueError):q.literal_past(node)

    def test_targets_and_nodes_not_mutated_or_aliased(self):
        nodes,y=fixture_data();saved=deepcopy(nodes);original=y.copy()
        for kind in labels.KINDS:
            z=labels.supervision(nodes,y,kind);z[:]=5;np.testing.assert_array_equal(y,original);self.assertEqual(nodes,saved)

    def test_all_transforms_independently_reconstructed(self):
        nodes,y=fixture_data()
        for kind in labels.KINDS:np.testing.assert_allclose(labels.supervision(nodes,y,kind),q.literal_supervision(nodes,y,kind),atol=2e-12,rtol=2e-12)

    def test_main_and_independent_training_on_each_transformed_label(self):
        nodes,y=fixture_data();r=np.random.default_rng(55)
        data=dict(phi=r.normal(0,.2,(3,5)),historical=r.uniform(.05,2,(3,24)),known=r.integers(0,2,(3,24)).astype(float),
            cost=r.uniform(.1,.9,(3,4)),weights=np.array([.25,.25,.5]),gamma=.9)
        for kind in labels.KINDS:
            data['target']=labels.supervision(nodes,y,kind);a,_=net.fit(data,'JOINT_SPO',78,3,ledger=SYNTHETIC_LEDGER)
            local={};independent_data=dict(data,target=q.literal_supervision(nodes,y,kind));b=numbers.refit(independent_data,'JOINT_SPO',78,3,local)
            for key in net.PARAMS:np.testing.assert_allclose(a[key],b[key],atol=2e-12,rtol=2e-12)
            for key,value in local.items():SYNTHETIC_LEDGER['independent_'+key]=SYNTHETIC_LEDGER.get('independent_'+key,0)+value

    def test_private_history_noise_rejected(self):
        nodes,y=fixture_data();nodes[0]['history'][0]['after']['noise_oracle']=[0,0,0]
        with self.assertRaises(ValueError):labels.supervision(nodes,y,'HISTORY_RECONSTRUCT')

    def test_future_history_rejected(self):
        nodes,y=fixture_data();nodes[0]['history'].append(deepcopy(nodes[0]['history'][-1]))
        with self.assertRaises(ValueError):labels.supervision(nodes,y,'FUTURE_RATE_MEAN')

    def test_missing_nodes_cannot_receive_fabricated_labels(self):
        nodes,y=fixture_data();nodes[0]=None
        with self.assertRaises(ValueError):labels.supervision(nodes,y,'FUTURE_MARGINAL_PRODUCT')

    def test_unknown_kind_and_nonfinite_target_fail_closed(self):
        nodes,y=fixture_data()
        with self.assertRaises(ValueError):labels.supervision(nodes,y,'RETUNED')
        y[0,0,3]=np.nan
        with self.assertRaises(ValueError):labels.supervision(nodes,y,'FUTURE_RATE_MEAN')

    def test_original_complete_cost_is_not_an_auxiliary_input(self):
        nodes,y=fixture_data()
        with self.assertRaises(TypeError):labels.supervision(nodes,y,'FUTURE_RATE_MEAN',cost=np.zeros((3,4)))

    def test_all44_selectors_and_original32_exactly_preserved(self):
        self.assertEqual(len(m.SELECTORS),44);self.assertEqual(len(set(m.SELECTORS)),44)
        self.assertEqual(m.SELECTORS[:32],m.prior.SELECTORS);self.assertEqual(len(m.NEW_SELECTORS),12)

    def test_config_keeps_source_architecture_training_and_roles(self):
        c=m.io.read(m.CONFIG);old=m.io.read(m.prior.CONFIG)
        self.assertEqual(c['controls'],list(labels.KINDS));self.assertEqual(c['folds'],old['folds'])
        for key in ('model_rng_seed','steps','learning_rate','gradient_norm_clip','ridge','auxiliary_loss_weight'):self.assertEqual(c[key],old[key])
        self.assertEqual(c['source_candidate_refits'],0);self.assertEqual(c['scientific_neural_fits'],9);self.assertEqual(c['scientific_neural_updates'],9000)
