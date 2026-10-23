import copy
import unittest
import numpy as np
from scripts.audit_state_capsule_qualification_v1 import compare_pair, expected_applied
from scripts.run_state_capsule_qualification_v1 import validate, population, CONFIG
from scripts import run_strong_chronological_reference_v1 as io


class StateCapsuleRecordAuditTest(unittest.TestCase):
    def setUp(self):
        self.rows=[{'observation':[1.,2.], 'command':[.1,0,0,0], 'reward':2.,'rng_witness':[.2,.3],
            'simulation_time_before':.1,'simulation_time_after':.1125,'logical_step':8,'noise_cursor_after':9,
            'terminated':False,'truncated':True,'info':{'success':True,'episode':{'r':3.,'l':9,'t':.5}},
            'intent_sequence':12,'execution_started_ns':20,'completed_ns':30,'ledger_before':{},'ledger_after':{}}]

    def test_only_declared_wall_and_event_cost_metadata_are_ignored(self):
        other=copy.deepcopy(self.rows);other[0]['info']['episode']['t']=6.;other[0]['intent_sequence']=900
        other[0]['ledger_after']={'physical_steps':999};compare_pair(self.rows,other)

    def test_observation_reward_rng_termination_and_clock_tampering_rejected(self):
        for key,value in [('observation',[1.,3.]),('reward',2.001),('rng_witness',[.2,.31]),
                          ('truncated',False),('simulation_time_after',.125),('noise_cursor_after',10)]:
            other=copy.deepcopy(self.rows);other[0][key]=value
            with self.assertRaises(ValueError):compare_pair(self.rows,other)
        other=copy.deepcopy(self.rows);other[0]['info']['episode']['l']=10
        with self.assertRaises(ValueError):compare_pair(self.rows,other)

    def test_record_count_and_unknown_extra_fields_are_not_silently_dropped(self):
        with self.assertRaises(ValueError):compare_pair(self.rows,[])
        other=copy.deepcopy(self.rows);other[0]['new_observation']=1
        with self.assertRaises(ValueError):compare_pair(self.rows,other)

    def test_independent_float32_actuator_replay_includes_noise_and_clip(self):
        applied=expected_applied([1.,-1.,.1,.4],np.asarray([.2,-.2,.3],np.float32))
        np.testing.assert_array_equal(applied,np.asarray([1.,-1.,.4,.4],np.float32))

    def test_population_reservations_and_protocol_changes_fail_closed(self):
        c=io.read(CONFIG);validate(c);p=population(c)
        self.assertEqual([r['seed'] for r in p],list(range(18800,18812)))
        self.assertEqual(sum(r['prefix_steps']==488 for r in p),6)
        for key,value in [('seed_end',18812),('reserved',[18813,18999]),('branch_horizon',64),('api_calls',1)]:
            changed=copy.deepcopy(c);changed[key]=value
            with self.assertRaises(ValueError):validate(changed)


if __name__=='__main__':unittest.main()
