from copy import deepcopy
import unittest
import numpy as np
from src.analysis import state_coupled_actuation_design_v1 as m
from src.analysis.state_coupled_actuation_independent_v1 import literal
from src.rollout.chronological_faults import deterministic_action


class SpatialDesignTests(unittest.TestCase):
    def test_smoothstep_known_interior_and_plateaus(self):
        d=m.fixture_definition()
        for x,w in ((-1.,0.),(-.1,0.),(-.05,.15625),(0.,.5),(.05,.84375),(.1,1.),(1.,1.)):
            self.assertAlmostEqual(m.weight(x,d),w,places=14)

    def test_parameter_palette_and_invalid_scale(self):
        d=m.fixture_definition()
        for key,value in (('axis',3),('half_width',0.),('center',float('nan')),('kind','UNKNOWN')):
            bad=deepcopy(d);bad[key]=value
            with self.assertRaises(ValueError):m.spec(bad)
        for field,value in (('matrix_xy',[[.74,0.],[0.,1.]]),('deadzone_xy',[.1,0.]),('bias_xy',[.21,0.])):
            bad=deepcopy(d);bad['left'][field]=value
            with self.assertRaises(ValueError):m.spec(bad)
        for x in (-.2,-.05,0.,.05,.2):
            r=m.evaluate(m.fixture_before(x),[0.,0.,0.,0.],[0.,0.,0.],d)
            self.assertGreaterEqual(r['matrix_det_oracle'],.5224999)

    def test_private_and_future_fields_rejected(self):
        d=m.fixture_definition()
        for key in ('seed','true_fault','after_observation','future_result'):
            before=m.fixture_before(0.);before[key]=0
            with self.assertRaises(ValueError):m.evaluate(before,[0.]*4,[0.]*3,d)
        before=m.fixture_before(0.);before['current']['noise_oracle']=[0.]*3
        with self.assertRaises(ValueError):m.evaluate(before,[0.]*4,[0.]*3,d)

    def test_terminal_and_budget_rejected(self):
        d=m.fixture_definition()
        m.evaluate(m.fixture_before(0.,499),[0.]*4,[0.]*3,d)
        with self.assertRaises(ValueError):m.evaluate(m.fixture_before(0.,500),[0.]*4,[0.]*3,d)
        for flag in ('success','terminated','truncated'):
            before=m.fixture_before(0.);before['current'][flag]=True
            with self.assertRaises(ValueError):m.evaluate(before,[0.]*4,[0.]*3,d)

    def test_transform_then_noise_then_clip(self):
        d=m.fixture_definition('FLAT_LEFT');r=m.evaluate(m.fixture_before(-.2),[1.,0.,0.,0.],[-.2,0.,0.],d)
        self.assertAlmostEqual(r['transformed_action_oracle'][0],1.12,places=6)
        self.assertAlmostEqual(r['executed_action_oracle'][0],.92,places=6)
        self.assertNotAlmostEqual(r['executed_action_oracle'][0],.8,places=4)
        self.assertFalse(r['final_clip_oracle'][0])

    def test_xyz_noise_and_gripper_semantics(self):
        r=m.evaluate(m.fixture_before(0.),[0.,0.,.4,.7],[.1,-.2,.5],m.fixture_definition())
        self.assertAlmostEqual(r['executed_action_oracle'][2],.9,places=6)
        self.assertEqual(np.float32(r['executed_action_oracle'][3]).tobytes(),np.float32(.7).tobytes())
        for command,noise in (([float('inf'),0.,0.,0.],[0.]*3),([0.]*4,[float('nan'),0.,0.]),([1.1,0.,0.,0.],[0.]*3)):
            with self.assertRaises(ValueError):m.evaluate(m.fixture_before(0.),command,noise,m.fixture_definition())

    def test_flat_modes_match_legacy_float32_bytes(self):
        for kind in ('FLAT_LEFT','FLAT_RIGHT'):
            d=m.fixture_definition(kind);fault=d['left' if kind=='FLAT_LEFT' else 'right']
            for u in ([1.,-1.,-1.,1.],[-1.,1.,1.,-1.],[0.,0.,0.,0.],[.25,-.25,.4,.7]):
                for noise in ([0.,0.,0.],[.05,-.05,.05],[-.2,.2,-.2]):
                    expected=deterministic_action(u,fault);expected[:3]+=np.asarray(noise,np.float32);expected=np.clip(expected,-1,1)
                    actual=m.evaluate(m.fixture_before(.2),u,noise,d)['executed_action_oracle']
                    self.assertEqual(np.asarray(actual,np.float32).tobytes(),expected.tobytes())

    def test_separate_scalar_stage_calculation(self):
        d=m.fixture_definition();u=[.25,-1.,.4,-.7];noise=[.05,-.05,.05]
        for x in (-.2,-.05,0.,.05,.2):
            before=m.fixture_before(x);actual=m.evaluate(before,u,noise,d);expected=literal(before,u,noise,d)
            for key in ('matrix_xy_oracle','bias_xy_oracle','transformed_action_oracle','before_final_clip_oracle','executed_action_oracle'):
                np.testing.assert_allclose(actual[key],expected[key],rtol=0,atol=5e-7)

    def test_pure_function_does_not_mutate_inputs(self):
        d=m.fixture_definition();before=m.fixture_before(0.);command=[.25,0.,0.,0.];noise=[.05,0.,0.]
        original=deepcopy([d,before,command,noise]);a=m.evaluate(before,command,noise,d);b=m.evaluate(before,command,noise,d)
        self.assertEqual([d,before,command,noise],original);self.assertEqual(a,b)

    def test_adoption_changes_future_model_applicability(self):
        small,large=m.adoption_counterexample()
        self.assertEqual((small['initial_prediction_error'],large['initial_prediction_error']),(0.,0.))
        self.assertEqual((small['next_weight'],large['next_weight']),(0.,1.))
        self.assertEqual(small['next_prediction_error'],0.)
        self.assertAlmostEqual(large['next_prediction_error'],-.24,places=6)
        self.assertTrue(small['not_a_robot_or_task_result'] and large['not_a_robot_or_task_result'])

    def test_legal_matrix_does_not_prevent_saturation_collapse(self):
        d=m.fixture_definition('FLAT_LEFT');before=m.fixture_before(-.2)
        a=m.evaluate(before,[1.,0.,0.,0.],[0.]*3,d);b=m.evaluate(before,[.99,0.,0.,0.],[0.]*3,d)
        self.assertGreater(a['matrix_det_oracle'],0.)
        self.assertEqual((a['executed_action_oracle'][0],b['executed_action_oracle'][0]),(1.,1.))

    def test_collection_is_not_allocated(self):
        with self.assertRaisesRegex(ValueError,'DESIGN_ONLY'):m.collection_allocation()


if __name__=='__main__':unittest.main()
