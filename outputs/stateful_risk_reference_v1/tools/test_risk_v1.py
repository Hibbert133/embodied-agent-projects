from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,mock
import sys
import risk_core_v1 as c
import risk_audit_v1 as a
import risk_examples_v1 as e
import run_risk_v1 as r


class RiskTests(TestCase):
    def setup_case(self,name='STATE_CHANGE'):
        return deepcopy(e.definitions()[name])
    def test_correct_direct_model(self):
        law,m,pi=self.setup_case();v,_=c.evaluate(law,m,pi,law['logging'],mode='DM')
        self.assertEqual(v,dict(C=F(70),V=F(50),M=F(25)))
    def test_correct_logging_wrong_model(self):
        law,m,pi=self.setup_case();mm={h:{k:x+12 for k,x in z.items()} for h,z in m.items()}
        v,_=c.evaluate(law,mm,pi,law['logging']);self.assertEqual(v,a.truth(law,pi))
    def test_correct_model_wrong_logging(self):
        law,m,pi=self.setup_case();p={h:dict(K0='1/2',K1='1/2') for h in m}
        v,_=c.evaluate(law,m,pi,p);self.assertEqual(v,a.truth(law,pi))
    def test_both_wrong_can_bias(self):
        law,m,pi=self.setup_case();mm={h:{k:x+12 for k,x in z.items()} for h,z in m.items()};p={h:dict(K0='1/2',K1='1/2') for h in m}
        v,_=c.evaluate(law,mm,pi,p);self.assertEqual(v['C']-a.truth(law,pi)['C'],-6)
    def test_actual_return_state_changes_option_ranking(self):
        law,m,pi=self.setup_case();v,_=c.evaluate(law,m,pi,law['logging'])
        l2,m2,p2=self.setup_case('NO_STATE_EFFECT');v2,_=c.evaluate(l2,m2,p2,l2['logging'])
        self.assertEqual(c.choose(v,tuple(v)),'M');self.assertEqual(c.choose(v2,tuple(v2)),'V');self.assertEqual(v2['M'],62)
    def test_drop_terminal_failure_changes_choice(self):
        law,m,pi=self.setup_case('TERMINAL_FAILURE');v,_=c.evaluate(law,m,pi,law['logging'])
        wrong=a.conditional_selection_shortcut(law,pi)
        self.assertEqual(v['V'],258);self.assertEqual(wrong['V'],32)
        self.assertEqual(c.choose(v,tuple(v)),'C');self.assertEqual(c.choose(wrong,tuple(wrong)),'V')
    def test_drop_terminal_success_loses_benefit(self):
        law,m,pi=self.setup_case('TERMINAL_SUCCESS');v,_=c.evaluate(law,m,pi,law['logging']);wrong=a.conditional_selection_shortcut(law,pi)
        self.assertEqual(v['V'],88);self.assertEqual(wrong['V'],168)
        self.assertEqual(c.choose(v,tuple(v)),'V');self.assertEqual(c.choose(wrong,tuple(wrong)),'C')
    def test_terminal_success_paid_once(self):
        self.assertEqual(c.complete_score(e.public('S',8,True,True),None,None,None,None,mode='DR'),8)
    def test_terminal_failure_penalty_paid_once(self):
        self.assertEqual(c.terminal_cost(e.public('F',8,True,False)),484)
    def test_no_overlap_rejected(self):
        law,m,pi=self.setup_case('NO_OVERLAP')
        with self.assertRaisesRegex(ValueError,'unsupported'):c.evaluate(law,m,pi,law['logging'])
    def test_missing_probability_not_default_quarter(self):
        with self.assertRaises(ValueError):c.support(dict(K0=1,K1=0),dict(K0=0,K1=1))
        with self.assertRaises(ValueError):c.support(dict(K0=1,K1=0),dict(K0=1))
    def test_unnormalized_probability_rejected(self):
        with self.assertRaises(ValueError):c.distribution(dict(K0=1,K1=1),('K0','K1'))
    def test_random_tail_is_not_static_label(self):
        label=dict(schema='FACTUAL_COMPLETE_STATIC_LABEL_V1',selected='K0',gain_history=['K0','K1'],remaining_loss=10)
        with self.assertRaises(ValueError):c.static_label(label,('K0','K1'))
    def test_private_or_future_input_rejected(self):
        for k in ('seed','fault_oracle','future_loss','next_gain'):
            x=e.public('H',8);x[k]=1
            with self.assertRaises(ValueError):c.public_return(x)
    def test_terminal_has_no_fictitious_gain_label(self):
        with self.assertRaises(ValueError):c.complete_score(e.public('S',8,True,True),{},None,None,None,mode='DR')
    def test_reverse_budget_and_live_deadline_rejected(self):
        x=e.public('H',8);x['after_steps']=15
        with self.assertRaises(ValueError):c.public_return(x)
        x=e.public('H',484)
        with self.assertRaises(ValueError):c.public_return(x)
    def test_exact_arithmetic_not_float_tolerance(self):
        with self.assertRaises(ValueError):c.number(.25)
        self.assertEqual(c.number('1/4'),F(1,4))
    def test_candidate_tie_order_fixed(self):
        self.assertEqual(c.choose(dict(C=F(1),V=F(1)),('C','V')),'C')
    def test_unsupported_candidate_not_hidden_by_selection(self):
        with self.assertRaises(ValueError):c.choose(dict(C=F(1),V=None),('C','V'))
    def test_independent_main_functions_disabled(self):
        law,m,pi=self.setup_case();expected,_=c.evaluate(law,m,pi,law['logging'])
        def deny(*args,**kw):raise RuntimeError('disabled')
        funcs={n:deny for n,v in vars(c).items() if callable(v) and getattr(v,'__module__',None)==c.__name__}
        with mock.patch.multiple(c,**funcs):self.assertEqual(a.expanded(law,m,pi,law['logging'],'DR'),expected)
    def test_pseudo_outcome_not_clipped(self):
        returned=e.public('H',8);model=dict(K0=400,K1=400);target=dict(K0=1,K1=0);mu=dict(K0='1/4',K1='3/4')
        label=dict(schema='FACTUAL_COMPLETE_STATIC_LABEL_V1',selected='K0',gain_history=['K0'],remaining_loss=0)
        self.assertEqual(c.complete_score(returned,label,model,target,mu,mode='DR'),-1192)
    def test_guard_rejects_process_science_and_private_reads(self):
        with TemporaryDirectory() as d:
            with r.shared.record_only(Path(d),[]) as guard:
                with self.assertRaises(RuntimeError):sys.audit('subprocess.Popen','never',[],None,None)
                with self.assertRaises(RuntimeError):sys.audit('import','mujoco',None,None,None,None)
                with self.assertRaises(RuntimeError):open(r.ROOT/'QUAL_PRIVATE_UNDECLARED','rb')
            self.assertEqual(sum(guard.values()),3)
