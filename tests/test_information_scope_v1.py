"""Pure arrays and exact finite examples; never instantiate or step an environment."""
from fractions import Fraction as F
from math import log
from unittest import TestCase
from unittest.mock import patch
import numpy as np
from src.analysis import information_scope_reference_v1 as r
from src.analysis import information_scope_audit_v1 as audit


class InformationScope(TestCase):
    def problem(self):
        return dict(problem_id=0,direction='FORWARD',fine_cost=8,coarse_cost=1,fine_shift=0,coarse_shift=0,budget=500)

    def test_full_support_common_prior_exact_rational(self):
        w=r.witness()
        for name in ('p','q'):
            j=[[F(x) for x in row] for row in w[name]]
            self.assertTrue(all(x>0 for row in j for x in row))
            self.assertEqual([sum(row) for row in j],[F(1,2),F(1,2)])
        self.assertEqual([sum(F(w['p'][z][y]) for z in range(2)) for y in range(3)],[F(1,4),F(1,2),F(1,4)])

    def test_conditional_contraction_counterexample(self):
        v=r.probability_result(r.witness())
        self.assertAlmostEqual(v['fine']['conditional_posterior_KL'],0,14)
        self.assertAlmostEqual(v['coarse']['conditional_posterior_KL'],0.033544671567053856,14)
        self.assertFalse(v['unconditional_posterior_contraction_holds'])
        self.assertTrue(v['joint_KL_contraction_holds'])

    def test_correct_chain_rule_and_slack(self):
        v=r.probability_result(r.witness())
        self.assertAlmostEqual(v['fine']['joint_KL'],log(1.25),14)
        self.assertLessEqual(v['posterior_penalty_increase'],v['predictive_slack'])
        for d in ('fine','coarse'):
            self.assertAlmostEqual(v[d]['chain_rule_residual'],0,14)
            self.assertAlmostEqual(v[d]['EGIG_decomposition_residual'],0,14)

    def test_matched_predictive_marginal_is_a_positive_control(self):
        p=r.float_joint(r.rational_joint(('1/4','1/2','1/4'),'1/10'))
        q=r.float_joint(r.rational_joint(('1/4','1/2','1/4'),'2/5'))
        f=r.information(p,q);c=r.information(r.coarsen(p,[0,0,1]),r.coarsen(q,[0,0,1]))
        self.assertAlmostEqual(f['predictive_marginal_KL'],0,14)
        self.assertGreater(f['conditional_posterior_KL'],c['conditional_posterior_KL'])

    def test_noninformative_no_posterior_change_does_not_remove_joint_penalty(self):
        v=r.noninformative_witness()
        self.assertTrue(v['working_posterior_equals_prior'])
        self.assertAlmostEqual(v['metrics']['EGIG'],0,14)
        self.assertAlmostEqual(v['metrics']['RFIM_KL'],-.5*log(4/3),14)

    def test_mismatched_prior_not_silently_certified(self):
        with self.assertRaises(ValueError):r.information([[.1,.4],[.2,.3]],[[.1,.2],[.3,.4]])

    def test_invalid_joint_laws_rejected(self):
        for j in ([[0,.5],[.2,.3]],[[-.1,.6],[.2,.3]],[[.1,.4],[.2,.4]],[[float('nan'),.4],[.2,.3]]):
            with self.subTest(j=j),self.assertRaises(ValueError):r.float_joint(j)

    def test_channel_must_be_common_total_surjection(self):
        p=r.float_joint(r.witness()['p'])
        for m in ([0,0,0],[0,1],[0,1,2],[False,1,0]):
            with self.subTest(m=m),self.assertRaises(ValueError):r.coarsen(p,m)

    def test_failed_full_task_pays_cutoff_once(self):
        v=r.terminal(0,'ADOPT_100',8,-5,500)
        self.assertAlmostEqual(v['cutoff_loss'],.8*(8+70)+.2*500)
        self.assertNotAlmostEqual(v['cutoff_loss'],.8*(8+70)+.2*(500+8))

    def test_stop_retains_spent_cost_but_full_failure_penalty(self):
        v=r.terminal(0,'STOP',12,20,500)
        self.assertEqual(v,dict(cutoff_loss=500.,success_probability=0.,interaction_equivalent=12.))

    def test_keep_does_not_undo_acquired_state(self):
        self.assertEqual(r.terminal(1,'KEEP',8,20,500)['cutoff_loss'],148)
        self.assertEqual(r.terminal(1,'KEEP',8,-5,500)['cutoff_loss'],123)

    def test_budget_and_completion_censoring(self):
        self.assertEqual(r.terminal(1,'KEEP',499,0,500)['cutoff_loss'],500)
        with self.assertRaises(ValueError):r.terminal(0,'KEEP',501,0,500)
        p=self.problem()|dict(budget=4,fine_cost=8)
        self.assertNotIn('FINE',r.plan(p,'WORKING_BAYES')['arm_predictions'])
        with self.assertRaises(ValueError):r.plan(p,'ALWAYS_FINE_WORKING')

    def test_saved_choice_changes_evaluation(self):
        p=self.problem();base=r.plan(p,'DIRECT_KEEP');changed=base|dict(saved_continuations=['ADOPT_100'])
        self.assertEqual(r.evaluate(p,base)['cutoff_loss'],120)
        self.assertAlmostEqual(r.evaluate(p,changed)['cutoff_loss'],90,12)

    def test_working_planners_cannot_query_true_law(self):
        original=r.arm_law
        def guarded(arm,truth,direction='FORWARD'):
            if truth:raise AssertionError('true synthetic law is evaluator/oracle only')
            return original(arm,False,direction)
        with patch.object(r,'arm_law',guarded):
            for method in r.METHODS:
                if 'ORACLE' not in method and method!='OPTIMISTIC_POST_MISMATCH':r.plan(self.problem(),method)

    def test_oracle_permissions_and_post_rule_mismatch_are_visible(self):
        p=self.problem();o=r.plan(p,'OPTIMISTIC_POST_MISMATCH')
        self.assertEqual(o['role'],'PRIVILEGED_FINITE_REFERENCE_NOT_DEPLOYABLE')
        c=o['arm_predictions']['COARSE']
        self.assertNotEqual(c['scored_continuations'],c['executed_continuations'])

    def test_mismatch_directions_include_harm_and_missed_opportunity(self):
        p=self.problem();ledger=r.plan(p,'ALWAYS_COARSE_WORKING');v=r.evaluate(p,ledger)
        self.assertGreater(v['keep_missing_benefit_probability'],0)
        p=p|dict(direction='REVERSE');v=r.evaluate(p,r.plan(p,'ALWAYS_COARSE_WORKING'))
        self.assertGreater(v['harmful_adoption_probability'],0)

    def test_ties_preserve_order_with_numerical_tolerance_only(self):
        self.assertEqual(r.first_min([2.,2.-1e-12,2.]),0)
        self.assertEqual(r.first_min([2.,2.-1e-8,2.]),1)
        with self.assertRaises(ValueError):r.first_min([])

    def test_unknown_policy_or_tail_rejected(self):
        with self.assertRaises(ValueError):r.plan(self.problem(),'NEW_UNREGISTERED_RULE')
        with self.assertRaises(ValueError):r.terminal(0,'RETRY',0,0,500)

    def test_independent_math_does_not_call_main(self):
        w=r.witness()
        with patch.object(r,'information',side_effect=AssertionError('disabled')),patch.object(r,'coarsen',side_effect=AssertionError('disabled')):
            v=audit.result(w)
        self.assertGreater(float(v['coarse']['conditional_posterior_KL']),.03)

    def test_independent_terminal_handles_cutoff_without_float_or_main(self):
        with patch.object(r,'terminal',side_effect=AssertionError('disabled')):
            v=audit.terminal(0,'ADOPT_100',8,-5,500)
        self.assertEqual(v['cutoff_loss'],F(812,5))
