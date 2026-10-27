"""Public-array pairs and separately charged synthetic ridge probes only."""
from copy import deepcopy
import unittest
import numpy as np
from src.analysis import correction_effect_learning_v1 as main
from src.analysis import correction_effect_independent_v1 as independent
from src.probe import correction_effect_model_v1 as model


def state(x=0.):
    o=[0.]*39;o[:3]=[x,.7,.2];o[4:7]=[.2,.7,.05]
    return dict(observation=o,success=False,terminated=False,truncated=False)


def fixture():
    initial=state();common=[dict(command=[0.,0.,0.,-1.],after=state(.001)),dict(command=[0.,0.,0.,-1.],after=state(.002))]
    a=[*deepcopy(common),dict(command=[.25,0.,0.,-1.],after=state(.0025))]
    b=[*deepcopy(common),dict(command=[.5,0.,0.,-1.],after=state(.003))]
    return initial,a,b


def packet():
    s,a,b=fixture();return main.first_difference(s,a,s,b)[1]


class EffectTests(unittest.TestCase):
    def test_known_paired_public_effect(self):
        s,a,b=fixture();at,p,t=main.first_difference(s,a,s,b)
        self.assertEqual(at,2);np.testing.assert_allclose(t['effect'],[.05,0],atol=1e-15)
        self.assertEqual(p['completed_steps'],2);self.assertEqual([r['at_calls'] for r in p['history2']],[0,1])

    def test_common_prefix_response_mismatch_rejected(self):
        s,a,b=fixture();b[0]['after']['observation'][0]+=.001
        with self.assertRaises(ValueError):main.first_difference(s,a,s,b)

    def test_unmatched_source_lengths_are_not_missing_at_random(self):
        s,a,b=fixture()
        with self.assertRaises(ValueError):main.first_difference(s,a,s,a[:2])

    def test_identical_commands_have_no_invented_fork(self):
        s,a,_=fixture();self.assertEqual(main.first_difference(s,a,s,a),(None,None,None))

    def test_no_fabricated_first_two_displacements(self):
        s,a,b=fixture();b[0]['command'][0]=.25
        with self.assertRaises(ValueError):main.first_difference(s,a,s,b)

    def test_private_or_future_input_keys_rejected(self):
        for name in ('seed','noise_oracle','future_result'):
            p=packet();p[name]=0
            with self.subTest(field=name),self.assertRaises(ValueError):model.features(p)

    def test_future_history_clock_rejected(self):
        p=packet();p['history2'][0]['at_calls']=2
        with self.assertRaises(ValueError):model.features(p)

    def test_missing_history_is_not_zero_filled(self):
        p=packet();p['history2']=p['history2'][:1]
        with self.assertRaises(ValueError):model.features(p)

    def test_changed_Z_or_gripper_not_XY_rate_effect(self):
        p=packet();p['command_b'][2]=.25
        with self.assertRaises(ValueError):model.features(p)

    def test_main_and_literal_features_agree(self):
        p=packet();x,a,b=model.features(p);xi,ai,bi=independent.feature(p)
        np.testing.assert_array_equal(x,xi);np.testing.assert_array_equal(a,ai);np.testing.assert_array_equal(b,bi)
        for kind in model.KINDS:np.testing.assert_array_equal(model.design(p,kind),independent.design(p,kind))

    def test_antisymmetry_zero_and_triangle_consistency(self):
        p=packet();saved=dict(kind='PAIRED_CONTEXT',scale=[1.]*32,coef=np.arange(64).reshape(32,2).astype(float).tolist())
        reverse=deepcopy(p);reverse['command_a'],reverse['command_b']=p['command_b'],p['command_a']
        np.testing.assert_array_equal(model.predict(saved,p),-np.asarray(model.predict(saved,reverse)))
        same=deepcopy(p);same['command_b']=same['command_a'];self.assertEqual(model.predict(saved,same),[0.,0.])
        pbc=deepcopy(p);pbc['command_a']=p['command_b'];pbc['command_b']=[.75,0.,0.,-1.]
        pac=deepcopy(p);pac['command_b']=pbc['command_b']
        np.testing.assert_allclose(np.asarray(model.predict(saved,p))+model.predict(saved,pbc),model.predict(saved,pac),atol=1e-12)

    def test_group_unit_node_weights_do_not_reward_pair_duplication(self):
        r=[dict(group=0,task='push-v3',context='UNCHANGED',acquisition_action='CONTINUE'),
           dict(group=1,task='push-v3',context='UNCHANGED',acquisition_action='CONTINUE')]
        duplicated=[r[0],r[0],r[0],r[1]];w=main.weights(duplicated)
        self.assertAlmostEqual(sum(w[:3]),.5);self.assertEqual(w[-1],.5);np.testing.assert_array_equal(w,independent.weights(duplicated))

    def test_synthetic_scalar_ridge_has_expected_finite_penalty(self):
        p=packet();r=dict(pair_id='synthetic',group=0,task='push-v3',context='UNCHANGED',acquisition_action='CONTINUE',input=p,
            target=dict(effect=[.5,0.],displacement_a=[0.,0.],displacement_b=[.5,0.]))
        saved=main.fit_one([r],'GLOBAL_SCALAR');other=independent.fit_one([r],'GLOBAL_SCALAR')
        np.testing.assert_allclose(model.predict(saved,p),[.5/1.01,0.],atol=1e-12);np.testing.assert_allclose(saved['coef'],other['coef'],atol=1e-12)

    def test_nominal_and_zero_have_distinct_meanings(self):
        p=packet();self.assertEqual(model.predict(dict(kind='ZERO_EFFECT'),p),[0.,0.]);self.assertEqual(model.predict(dict(kind='NOMINAL_SENT'),p),[.25,0.])
