from copy import deepcopy
import unittest
import numpy as np
from src.analysis import correction_effect_horizon_v1 as main
from src.analysis import correction_effect_horizon_independent_v1 as independent

def fixture(n=36):
    def state(x):return dict(observation=[float(x),0.,0.]+[0.]*36,success=False,terminated=False,truncated=False)
    a=[];b=[]
    for j in range(n):
        a.append(dict(command=[0.,0.,0.,0.],raw_policy=[0.,0.,0.,0.],after=state(0)))
        b.append(dict(command=[0. if j<2 else .25,0.,0.,0.],raw_policy=[0.,0.,0.,0.],after=state(0 if j<2 else .01*.25*(j-1))))
    pair=dict(pair_id='synthetic',group=0,task='fixture',context='fixture',boundary=2,acquisition_action='CONTINUE',rates=[.125,.5],
        loss_difference=4,success_a=True,success_b=True,first_difference=2,status='ACTUAL_DIVERGENCE')
    return pair,a,b,np.eye(2)

def run(pair,a,b,J):return main.window(pair,a,b,J,purpose=main.PURPOSE)

class HorizonTests(unittest.TestCase):
    def test_known_integrated_model_and_all_horizons(self):
        rows=run(*fixture());self.assertEqual([r['horizon'] for r in rows],list(main.HORIZONS))
        for r in rows:self.assertAlmostEqual(r['mse']['FROZEN_GLOBAL_MATRIX'],0,places=25)
    def test_future_inputs_cannot_be_claimed_as_entry_forecast(self):
        with self.assertRaises(Exception):main.window(*fixture(),purpose='ENTRY_FORECAST')
    def test_unexecuted_suffix_never_padded(self):
        p,a,b,J=fixture(5);r=run(p,a,b,J);self.assertEqual(r[2]['status'],'BOTH_SOURCES_SHORT');self.assertIsNone(r[2]['mse'])
    def test_one_source_short_is_distinct(self):
        p,a,b,J=fixture();self.assertEqual(run(p,a[:5],b,J)[2]['status'],'SOURCE_A_SHORT');self.assertEqual(run(p,a,b[:5],J)[2]['status'],'SOURCE_B_SHORT')
    def test_terminal_pair_has_no_fabricated_response(self):
        p,a,b,J=fixture();p.update(first_difference=None,status='BEFORE_DECISION_TERMINAL');r=run(p,[],[],J)
        self.assertEqual(len(r),6);self.assertTrue(all(x['mse'] is None for x in r))
    def test_common_start_required(self):
        p,a,b,J=fixture();b[1]['after']['observation'][0]=1
        with self.assertRaises(Exception):run(p,a,b,J)
    def test_earliest_history_cannot_be_fabricated(self):
        p,a,b,J=fixture();p['first_difference']=1
        with self.assertRaises(Exception):run(p,a,b,J)
    def test_z_gripper_and_policy_changes_recorded(self):
        p,a,b,J=fixture();b[3]['command'][2]=.5;b[3]['raw_policy'][0]=.75;r=run(p,a,b,J)[1]
        self.assertEqual((r['z_gripper_difference_steps'],r['raw_policy_difference_steps']),(1,1))
    def test_no_early_command_clipping(self):
        p,a,b,J=fixture();b[2]['command'][0]=1.01
        with self.assertRaises(Exception):run(p,a,b,J)
    def test_scalar_independent_formula_matches(self):
        p,a,b,J=fixture();J=np.asarray([[.12,-.03],[.02,.07]])
        rows=run(p,a,b,J);independent.old_audit.equal(rows,independent.literal(p,a,b,J.tolist()))
        np.testing.assert_allclose(rows[0]['predictions']['FROZEN_GLOBAL_MATRIX'],[.03,-.0075],atol=1e-15)
    def test_group_weight_not_time_step_weight(self):
        rows=run(*fixture());p=deepcopy(rows[0]);q=deepcopy(p);q['group']=1
        p['mse']={k:1. for k in main.METHODS};q['mse']={k:3. for k in main.METHODS}
        metric=main.panels([p,p,q]);overall=next(x for x in metric if not x['axes']);self.assertEqual(overall['registered'],3);self.assertEqual(overall['independent_groups'],2)
        self.assertEqual(overall['mse']['FROZEN_GLOBAL_MATRIX'],2.)
    def test_zero_length_strata_are_missing_not_zero(self):
        p,a,b,J=fixture();p.update(first_difference=None,status='ACQUISITION_TERMINAL');r=main.panels(run(p,[],[],J))
        self.assertTrue(all(v is None for v in r[0]['mse'].values()))

if __name__=='__main__':unittest.main()
