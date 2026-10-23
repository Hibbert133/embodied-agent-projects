"""Pure arrays: no environment, policy learning, response fitting or API calls."""
from copy import deepcopy
import unittest
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.operator_identification import identity_controller,encode_controller
from src.probe.task_passive_pi_v1 import PIQuery,PIPlan,PlanConsumer,DT,GAINS


def query(task='push-v3',raw=(.5,-.25,.7,-1.),state=(0.,0.),time=.5,step=8,base=None):
    observation=np.zeros(39); observation[:3]=[.1,.6,.2]
    return PIQuery.create(task,step,StepObservation(observation,False,False,False),raw,
                         identity_controller() if base is None else base,state,time)


class TaskPIKernelTests(unittest.TestCase):
    def test_error_units_follow_each_frozen_policy_gain_before_clipping(self):
        for task,p in GAINS.items():
            q=query(task,raw=(p*.125,-p*.25,.3,-1.)); n=PIPlan(q).numbers()
            np.testing.assert_array_equal(n['position_error_xy_m'],[.125,-.25])
            self.assertNotEqual(n['position_error_xy_m'][1],-1./p)

    def test_known_constant_error_integrates_with_physical_period(self):
        q=query(); n=PIPlan(q).numbers()
        np.testing.assert_allclose(n['integral_proposed'],[.0125,-.00625],atol=1e-15,rtol=0)
        self.assertEqual(DT,.0125)
        self.assertFalse(n['send_limit_active'])

    def test_inverse_mapping_applies_to_integral_rate(self):
        base={'source':'ESTIMATED_AFFINE','matrix_xy':[[2.,.25],[-.5,1.]],'offset':[.1,-.2,0.,0.]}
        q=query(base=base); n=PIPlan(q).numbers()
        np.testing.assert_allclose(n['integral_rate_command_per_s'],[1.875,-1.],atol=1e-15,rtol=0)
        np.testing.assert_array_equal(n['base_command'],encode_controller(base,q.raw_policy))

    def test_projection_prevents_saturation_windup(self):
        state=(0.,0.)
        for _ in range(100):
            n=PIPlan(query(raw=(20.,0.,.2,-1.),state=state,time=.125)).numbers()
            self.assertTrue(n['send_limit_active']); self.assertEqual(n['sent_command'][0],1.)
            state=n['integral_after_receipt']; self.assertEqual(state[0],0.)

    def test_saturation_release_can_immediately_change_direction(self):
        n=PIPlan(query(raw=(-.5,0.,0.,-1.),state=(0.,0.),time=.5)).numbers()
        self.assertLess(n['sent_command'][0],-.5); self.assertLess(n['integral_after_receipt'][0],0.)

    def test_limit_bounds_and_z_grip_are_preserved(self):
        n=PIPlan(query(raw=(30.,-30.,3.,-4.),state=(2.,-2.),time=.125)).numbers()
        self.assertTrue(n['integral_limit_active']); self.assertEqual(n['sent_command'],[1.,-1.,1.,-1.])
        self.assertTrue(all(abs(v)<=2 for v in n['integral_after_receipt']))

    def test_rounding_is_separate_from_command_clipping(self):
        n=PIPlan(query(raw=(.31,.27,0.,0.),time=2.)).numbers()
        self.assertFalse(n['send_limit_active']); self.assertTrue(any(v!=0 for v in n['send_roundoff_xy']))
        self.assertEqual(n['sent_command'],np.array(n['sent_command'],np.float32).tolist())
        np.testing.assert_array_equal(np.array(n['base_command'][:2])+n['integral_after_receipt'],n['sent_command'][:2])

    def test_plan_roundtrip_and_arithmetic_tampering(self):
        p=PIPlan(query()); value=p.to_dict(); self.assertEqual(PIPlan.from_dict(value),p)
        value['numbers']['integral_after_receipt'][0]+=.01
        with self.assertRaises(ValueError): PIPlan.from_dict(value)
        self.assertNotEqual(value,p.to_dict())

    def test_stale_observation_policy_integral_or_step_cannot_consume(self):
        original=query(); plan=PIPlan(original)
        for q in (query(step=9),query(raw=(.4,0.,0.,0.)),query(state=(.1,0.))):
            with self.assertRaises(ValueError): PlanConsumer(plan).consume(q,490)
        d=original.to_dict(); d['current']['observation'][0]+=.001
        with self.assertRaises(ValueError): PlanConsumer(plan).consume(PIQuery.from_dict(d),490)

    def test_budget_reuse_and_future_claims_rejected(self):
        p=PIPlan(query()); c=PlanConsumer(p)
        for remaining in (0,493,True):
            with self.assertRaises(ValueError): c.consume(p.query,remaining)
        used=c.consume(p.query,492); self.assertEqual(used['command'],p.numbers()['sent_command'])
        with self.assertRaises(ValueError): c.consume(p.query,492)
        for field in ('physical_response_qualified','task_benefit_established','safety_guarantee'):
            d=p.to_dict(); d[field]=True
            with self.assertRaises(ValueError): PIPlan.from_dict(d)

    def test_nested_oracle_and_unknown_fields_rejected(self):
        original=query().to_dict()
        for location,key in (('', 'seed'),('', 'future_result'),('current','actual_noise'),('controller','fault_oracle')):
            d=deepcopy(original); target=d if not location else d[location]; target[key]=1
            with self.assertRaises(ValueError): PIQuery.from_dict(d)

    def test_invalid_controller_state_raw_and_time_constant_rejected(self):
        for value in (0.,-.5,.7,float('nan'),True):
            with self.assertRaises(ValueError): query(time=value)
        with self.assertRaises(ValueError): query(state=(2.01,0.))
        with self.assertRaises(ValueError): query(raw=(float('nan'),0,0,0))
        base=identity_controller(); base['source']='ORACLE_EVALUATOR'
        with self.assertRaises(ValueError): query(base=base)
        base=identity_controller(); base['matrix_xy']=[[0.,0.],[0.,0.]]
        with self.assertRaises(ValueError): query(base=base)

    def test_different_legal_time_constants_change_saved_numeric_execution(self):
        fast=PIPlan(query(time=.125)).numbers()['sent_command']; slow=PIPlan(query(time=8.)).numbers()['sent_command']
        self.assertNotEqual(fast,slow)
        self.assertGreater((np.array(fast)*.002)[0],(np.array(slow)*.002)[0])


if __name__=='__main__': unittest.main()
