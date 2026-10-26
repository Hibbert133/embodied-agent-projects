"""Constructed records/arrays only; no environment or online API."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import importlib.util,unittest
import numpy as np
from src.analysis import correction_trace_value_v1 as m
from src.analysis import correction_trace_value_independent_v1 as q

spec=importlib.util.spec_from_file_location('risk_reference_constructed_fixture',Path(__file__).parent/'test_correction_scope_risk_reference_v1.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

def graph(group=0):
    g=fixture.graph(group)
    for ai in (1,2):g['returns'][ai]=m.old.node_from_view(fixture.view(3,stage='POST',action=m.A[ai]))
    return g

def record(group,value):
    g=graph(group);g['pre']=m.old.node_from_view(fixture.view(value=value));g['returns'][0]=m.old.node_from_view(fixture.view(value=value,stage='POST'))
    return dict(unit=g['unit'],action=0,release='FULL',query=m.query(g,0),target=[.1+value,.2,.3,.4],owner=(*g['unit'],0))

class TraceValueTests(unittest.TestCase):
    def test_literal_full_and_masked_queries(self):
        for full in (True,False):self.assertEqual(m.query(graph(),2,full),q.literal_query(graph(),2,full))

    def test_same_actual_return_prefix_integral_and_clock(self):
        a=m.query(graph(),2,True);b=m.query(graph(),2,False)
        self.assertEqual({k:v for k,v in a.items() if k!='extra_trace'},{k:v for k,v in b.items() if k!='extra_trace'})
        self.assertEqual(a['completed_steps'],3);self.assertEqual(b['completed_steps'],3);self.assertIsNone(b['extra_trace'])

    def test_normal_task_feedback_cannot_be_hidden(self):
        with self.assertRaises(ValueError):m.query(graph(),1,False)

    def test_empty_acquisition_trace_has_identical_inputs(self):
        g=graph();g['returns'][2]=m.old.node_from_view(fixture.view(stage='POST',action='MOVE_MEASURE'))
        full=m.query(g,2,True);mask=m.query(g,2,False)
        self.assertEqual(full,mask);self.assertTrue(np.array_equal(m.features(full),m.features(mask)))

    def test_zero_step_continue_has_no_extra_observation(self):
        query=m.query(graph(),0);self.assertEqual(query['extra_trace'],[])
        self.assertEqual(query['current'],query['prefix']['current'])

    def test_unavailable_trace_not_zero_valued_observation(self):
        full=m.query(graph(),2,True);mask=m.query(graph(),2,False);a=m.features(full);b=m.features(mask)
        self.assertEqual(a[41593+82],1.);self.assertEqual(b[41593+82],0.)
        self.assertTrue(np.array_equal(a[:41593],b[:41593]))

    def test_all_ordinary_prefix_is_preserved(self):
        g=graph();a=m.query(g,2,False);self.assertEqual(a['prefix'],g['pre'])
        self.assertEqual(a['prefix']['history'],m.query(g,2,True)['prefix']['history'])

    def test_literal_feature_coordinates(self):
        for full in (True,False):
            query=m.query(graph(),2,full);self.assertTrue(np.array_equal(m.features(query),q.literal_features(query)))

    def test_no_release_flag_feature(self):
        query=m.query(graph(),2,False);query['release']='MASK'
        with self.assertRaises(ValueError):m.features(query)

    def test_no_registry_or_future_field(self):
        query=m.query(graph(),2);query['group']=5
        with self.assertRaises(ValueError):m.features(query)

    def test_nested_private_noise_rejected(self):
        query=m.query(graph(),2);query['extra_trace'][0]['after']['noise_oracle']=[0.]*3
        with self.assertRaises(ValueError):m.features(query)

    def test_future_extra_rows_rejected(self):
        query=m.query(graph(),2);query['extra_trace'].append(deepcopy(query['extra_trace'][-1]))
        with self.assertRaises(ValueError):m.features(query)

    def test_trace_discontinuity_rejected(self):
        query=m.query(graph(),2);query['extra_trace'][0]['before']['observation'][0]=1.
        with self.assertRaises(ValueError):m.features(query)

    def test_float32_execution_boundary_enforced(self):
        query=m.query(graph(),2);query['extra_trace'][0]['command'][0]=.1
        with self.assertRaises(ValueError):m.features(query)

    def test_duplicate_views_preserve_original_group_weight(self):
        records=[record(0,0.),record(1,.125)];records.append(deepcopy(records[-1]));records[-1]['release']='MASK'
        w=m.weights(records);self.assertTrue(np.array_equal(w,[1.,.5,.5]));self.assertTrue(np.array_equal(w,q.literal_weights(records)))

    def test_identical_view_duplication_does_not_change_regularization(self):
        records=[record(0,0.),record(1,.125)];duplicates=[]
        for r in records:duplicates.extend([deepcopy(r),deepcopy(r)])
        with TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for kind in m.KINDS:
                first=m.fit(records,kind,folder/(kind+'_one.npz'));second=m.fit(duplicates,kind,folder/(kind+'_two.npz'))
                for r in records:self.assertTrue(np.allclose(m.predict(first,folder,r['query']),m.predict(second,folder,r['query']),atol=1e-10,rtol=1e-10))

    def test_held_groups_cannot_enter_training(self):
        records=m.rows([graph(g) for g in range(9)],[0,1,2])
        self.assertEqual({r['unit'][1] for r in records},{3,4,5,6,7,8})
        self.assertTrue(all(r['action']==2 for r in records if r['release']=='MASK'))

    def test_terminal_return_is_not_imputed(self):
        g=graph();g['returns'][2]=None
        self.assertIsNone(m.query(g,2,True));self.assertIsNone(m.query(g,2,False))

    def test_model_bytes_must_remain_fixed_for_both_views(self):
        with TemporaryDirectory() as temporary:
            file=Path(temporary)/'bad.npz';file.write_bytes(b'not a model')
            with self.assertRaises(ValueError):m.predict({'file':file.name,'sha256':'0'*64},file.parent,m.query(graph(),2))

    def test_complete_synthetic_flow_and_second_implementation(self):
        with TemporaryDirectory() as temporary:
            base=Path(temporary);source=base/'source';reference=base/'reference';run=base/'run'
            (source/'train').mkdir(parents=True);reference.mkdir();run.mkdir()
            cases,examples=fixture.source_fixture('TRAIN')
            m.old.write_rows(source/'train/cases.jsonl.gz',cases);m.old.write_rows(source/'train/examples.jsonl.gz',examples)
            graphs=m.old.assemble_graphs(source,'TRAIN');m.old.write_rows(reference/'train_graphs.jsonl.gz',graphs)
            path=run/'manifest.json';path.write_text('{}',encoding='utf8')
            config=dict(source_reference_run=str(reference),source_A1_run=str(source),heldout_groups=[[0,1,2],[3,4,5],[6,7,8]])
            with patch.object(m,'checked',return_value={'manifest_id':'constructed','config':config}):
                fit=m.train(path);audit=q.audit_models(path);result=m.evaluate(path);replay=q.audit_replay(path)
            self.assertEqual(fit['actual_fits'],6);self.assertEqual(audit['independent_refits'],6);self.assertEqual(len(result['results']),540)
            self.assertEqual(replay['integrity'],'PASSED');self.assertEqual(fit['guard']['operation_counts']['simulation'],0)

if __name__=='__main__':unittest.main()
