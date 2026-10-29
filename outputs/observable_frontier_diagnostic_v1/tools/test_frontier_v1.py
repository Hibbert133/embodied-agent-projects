"""Synthetic public histories and exact future-cost tables, no real data reads."""
from copy import deepcopy
import unittest
from unittest import mock
import frontier_core_v1 as c
import frontier_audit_v1 as a


def state(x=0.):return dict(observation=[x]+[0.]*38,success=False,terminated=False,truncated=False)


def fixture(tag,trace_only=False):
    initial=state();pre=dict(schema='COMPLETE_RISK_PUBLIC_NODE_V1',stage='PRE',task='push-v3',completed_steps=1,
        current=initial,integral_xy=[0.,0.],controller=dict(source='UNCORRECTED',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.,0.,0.,0.]),
        history=[dict(at_calls=0,before=deepcopy(initial),command=[0.]*4,after=deepcopy(initial))],acquisition_action=None)
    returns=[]
    for action in ('CONTINUE','VALIDATE8','MOVE_MEASURE'):
        v=deepcopy(pre);v.update(stage='RETURN',acquisition_action=action)
        if action!='CONTINUE':
            middle=state(float(tag+1));end=state() if trace_only else deepcopy(middle)
            v['history'] += [dict(at_calls=1,before=deepcopy(initial),command=[0.]*4,after=deepcopy(middle)),
                             dict(at_calls=2,before=deepcopy(middle),command=[0.]*4,after=deepcopy(end))]
            v.update(completed_steps=3,current=end)
        returns.append(v)
    costs=[50]*4+[10 if j==tag else 100 for j in range(4)]+[200]*4
    leaves=[dict(loss=x,steps=x,success=True,source_case_key=['TRAIN',0,'push-v3',str(tag),j],source_case_sha256=f'{tag:01d}{j:02d}') for j,x in enumerate(costs)]
    return dict(unit=['TRAIN',0,'push-v3',str(tag)],boundary=1,pre=pre,returns=returns,leaves=leaves)


class Checks(unittest.TestCase):
    def test_identical_roots_constrain_static_choice(self):
        result=c.solve([fixture(0),fixture(1)])
        self.assertEqual(len(result['root_classes']),1);self.assertEqual(result['totals']['ROOT_STATIC'],100)
        self.assertEqual(result['totals']['UNIT_CLAIRVOYANT'],20)
    def test_observed_return_allows_contingent_rate(self):
        r=c.solve([fixture(0),fixture(1)]);self.assertEqual(r['totals']['ROOT_ADAPTIVE_FULL'],20)
    def test_mask_preserves_current_observation(self):
        r=c.solve([fixture(0),fixture(1)]);self.assertEqual(r['totals']['ROOT_ADAPTIVE_MASK'],20)
    def test_only_extra_trace_separates_returns(self):
        r=c.solve([fixture(0,True),fixture(1,True)])
        self.assertEqual(r['totals']['ROOT_ADAPTIVE_FULL'],20);self.assertEqual(r['totals']['ROOT_ADAPTIVE_MASK'],100)
    def test_same_return_requires_same_rate(self):
        x=fixture(0);y=fixture(1);y['returns']=deepcopy(x['returns']);r=c.solve([x,y])
        self.assertEqual(r['totals']['ROOT_ADAPTIVE_FULL'],100)
    def test_terminal_acquisition_uses_no_rate(self):
        g=fixture(0);g['returns'][1]=None
        for q in g['leaves'][4:8]:q.update(loss=5,steps=5)
        r=c.solve([g]);row=next(q for q in r['records'] if q['functional']=='ROOT_ADAPTIVE_FULL')
        self.assertEqual((row['chosen_acquisition_index'],row['rate_index'],row['loss']),(1,None,5))
    def test_early_terminal_keeps_denominator(self):
        g=fixture(0);g['pre']=None;g['returns']=[None]*3
        for q in g['leaves']:q.update(loss=2,steps=2)
        r=c.solve([g]);self.assertEqual(len(r['records']),18);self.assertTrue(all(q['chosen_acquisition_index'] is None for q in r['records']))
    def test_terminal_with_invented_different_tail_rejected(self):
        g=fixture(0);g['returns'][1]=None
        with self.assertRaises(ValueError):c.solve([g])
    def test_private_or_future_field_rejected(self):
        g=fixture(0);g['pre']['future_loss']=10
        with self.assertRaises(ValueError):c.solve([g])
    def test_private_unit_ids_do_not_separate_public_roots(self):
        g=fixture(0);h=fixture(1);h['unit'][1]=99
        self.assertEqual(len(c.solve([g,h])['root_classes']),1)
    def test_ties_use_original_action_and_rate_order(self):
        g=fixture(0)
        for q in g['leaves']:q.update(loss=100,steps=100)
        r=c.solve([g]);self.assertTrue(all((q['chosen_acquisition_index'],q['rate_index'])==(0,0) for q in r['records'] if q['functional'].startswith('ROOT_')))
    def test_independent_exhaustive_audit_with_main_disabled(self):
        graphs=[fixture(0,True),fixture(1,True)];result=c.solve(graphs)
        def deny(*args,**kwargs):raise RuntimeError('main disabled')
        blocked={n:deny for n,v in vars(c).items() if callable(v) and getattr(v,'__module__',None)==c.__name__}
        with mock.patch.multiple(c,**blocked):self.assertEqual(a.audit(deepcopy(graphs),result)['selection_rows'],36)
    def test_tampered_selection_detected(self):
        graphs=[fixture(0),fixture(1)];r=c.solve(graphs);r['records'][0]['rate_index']=3
        with self.assertRaises(ValueError):a.audit(graphs,r)
    def test_exhaustive_budget_rejection(self):
        with self.assertRaises(ValueError):a.reconstruct([fixture(0),fixture(1)],limit=1)
    def test_nan_and_exact_sign_types(self):
        g=fixture(0);g['pre']['current']['observation'][0]=float('nan')
        with self.assertRaises(ValueError):c.solve([g])
        self.assertNotEqual(c.serialize(-0.),c.serialize(0.));self.assertNotEqual(a.signature(-0.),a.signature(0.))


if __name__=='__main__':unittest.main()
