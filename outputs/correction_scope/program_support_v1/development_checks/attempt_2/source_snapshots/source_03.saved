from copy import deepcopy
from fractions import Fraction
import unittest
from src.analysis import correction_program_support_v1 as m


def fixture(losses=None):
    losses=losses or [30,50,40,45,25,35,55,60,70,80,90,100]
    return dict(unit=['TRAIN',0,'push-v3','UNCHANGED'],boundary=16,pre={'synthetic':True},returns=[{'synthetic':True}]*3,
        leaves=[dict(loss=x,success=x<500,steps=x if x<500 else 200,movement_steps=0,measurement_steps=0,
            source_case_key=['TRAIN',0,'push-v3',80100,'UNCHANGED',16,m.A[i//4],m.R[i%4]],source_case_sha256='0'*64) for i,x in enumerate(losses)])


class SupportTests(unittest.TestCase):
    def test_failure_penalty_not_short_actual_cost(self):
        g=fixture();g['leaves'][0].update(loss=500,steps=1,success=False)
        self.assertEqual(m.unit_row(g)['leaves'][0]['loss'],500)
        g['leaves'][0]['loss']=1
        with self.assertRaises(ValueError):m.validate_graph(g)

    def test_complete_unique_ordered_factual_support(self):
        g=fixture();g['leaves'][1]['source_case_key']=list(g['leaves'][0]['source_case_key'])
        with self.assertRaises(ValueError):m.validate_graph(g)
        g=fixture();g['leaves'].pop()
        with self.assertRaises(ValueError):m.validate_graph(g)

    def test_other_cohort_rejected(self):
        for cohort in ('CAL','TEST','NATIVE'):
            g=fixture();g['unit'][0]=cohort
            with self.assertRaises(ValueError):m.validate_graph(g)

    def test_early_terminal_keeps_denominator_and_loss(self):
        g=fixture([8]*12);g['pre']=None;g['returns']=[None]*3
        row=m.unit_row(g);summary=m.aggregate([row])
        self.assertEqual((summary['units'],summary['prefix_unavailable']),(1,1))
        self.assertEqual(row['baseline_loss'],8)
        self.assertEqual(row['return_availability'],['PREFIX_ALREADY_TERMINAL']*3)

    def test_terminal_acquisition_cannot_invent_candidate_tail(self):
        g=fixture();g['returns'][2]=None
        with self.assertRaises(ValueError):m.validate_graph(g)
        g=fixture([20]*8+[31]*4);g['returns'][2]=None
        self.assertEqual(m.unit_row(g)['return_availability'][2],'ACQUISITION_ALREADY_TERMINAL')

    def test_equal_cost_success_and_failure_not_hidden_by_tie(self):
        g=fixture([500]*12);g['leaves'][1].update(success=True,steps=500)
        env=m.unit_row(g)['families']['CONTINUE']
        self.assertEqual(env['optimal_leaf_indices'],[0,1,2,3])
        self.assertFalse(env['all_minima_success']);self.assertTrue(env['any_minimum_success'])

    def test_groups_not_long_trajectories_receive_weight(self):
        rows=[dict(unit=['TRAIN',0],x=0),dict(unit=['TRAIN',0],x=0),dict(unit=['TRAIN',1],x=90)]
        self.assertEqual(m.group_average(rows,'x'),Fraction(45))

    def test_full_cost_envelopes_and_signed_difference(self):
        row=m.unit_row(fixture())
        self.assertEqual((row['baseline_loss'],row['B_minus_F'],row['B_minus_P'],row['F_minus_P'],row['F_minus_H']),(50,25,-20,-45,0))
        g=fixture();g['leaves'][8].update(loss=10,steps=10)
        row=m.unit_row(g)
        self.assertEqual((row['F_minus_P'],row['F_minus_H']),(15,15))

    def test_negative_paid_advantage_is_not_truncated(self):
        row=m.unit_row(fixture([10]*8+[80]*4));s=m.aggregate([row])
        self.assertEqual((s['paid_better'],s['paid_worse'],s['paid_tie']),(0,1,0))
        self.assertEqual((s['paid_negative_steps'],s['means_exact']['F_minus_P']),(70,'-70'))

    def test_empty_or_duplicate_family_not_imputed_zero(self):
        for family in ([],[0,0],[20]):
            with self.assertRaises(ValueError):m.envelope(fixture()['leaves'],family)


if __name__=='__main__':unittest.main()
