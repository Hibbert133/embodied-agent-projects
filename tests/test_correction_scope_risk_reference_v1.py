"""Pure arrays and constructed saved-branch fixtures. No simulator or API."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import numpy as np
from src.analysis import correction_scope_risk_reference_v1 as m
from src.analysis import correction_scope_risk_reference_independent_v1 as q


def state(value=0.,success=False):
    obs=[0.]*39;obs[0]=float(value)
    return dict(observation=obs,success=success,terminated=False,truncated=False)


def view(n=1,value=0.,stage='PRE',action='CONTINUE',rate=.5,task='push-v3'):
    current=state(value);history=[dict(at_calls=i,before=deepcopy(current),command=[0.]*4,after=deepcopy(current)) for i in range(n)]
    memory=dict(schema='TASK_MEMORY_OPTION_V1',task=task,completed_steps=n,current=deepcopy(current),integral_xy=[0.,0.],
        controller=dict(source='UNCORRECTED',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.]*4),time_constant_s=.5 if stage=='PRE' else rate)
    return dict(schema='CORRECTION_SCOPE_PUBLIC_V1',stage=stage,memory=memory,history=history,acquisition_action=action,time_constant_s=rate)


def graph(group=6,cohort='TRAIN'):
    pre=m.node_from_view(view());returns=[m.node_from_view(view(stage='POST',action=a)) for a in m.ACTIONS]
    return dict(unit=[cohort,group,'push-v3','UNCHANGED'],boundary=16,pre=pre,returns=returns,
        leaves=[dict(loss=100+10*a+r,success=True,steps=100+10*a+r) for a in range(3) for r in range(4)])


def source_fixture(cohort='CAL'):
    specs=m.a.population(cohort);cases=[];examples=[]
    for spec in specs:
        ai=m.ACTIONS.index(spec['acquisition_action']);ri=m.RATES.index(spec['time_constant_s']);boundary=spec['planned_boundary']
        pre=view(boundary,task=spec['task'],action=spec['acquisition_action'],rate=spec['time_constant_s'])
        post=view(boundary+(0 if ai==0 else 8),task=spec['task'],stage='POST',action=spec['acquisition_action'],rate=spec['time_constant_s'])
        ended=spec['group']==0 and spec['task']=='push-v3' and spec['context']=='UNCHANGED'
        acquired_end=spec['group']==0 and spec['task']=='reach-v3' and ai==2
        loss=10 if ended else 40 if acquired_end else 80+10*ai+ri
        cases.append(dict(**spec,completed=True,error=None,close_error=None,environment_closed=True,success=True,deadline_loss=loss,total_steps=loss,
            movement_steps=0 if ai!=2 else 8,measurement_steps=8 if ai==2 else 0,final_memory={'same':0 if ended or acquired_end else ri}))
        for stage,v in (('PRE',None if ended else pre),('POST',None if ended or acquired_end else post)):
            examples.append(dict(spec=spec,stage=stage,view=v))
    return cases,examples


class RiskReferenceTests(unittest.TestCase):
    def test_pre_candidate_assignments_are_not_physical_inputs(self):
        self.assertEqual(m.node_from_view(view(action='MOVE_MEASURE',rate=8.)),m.node_from_view(view()))

    def test_return_rate_only_projection_preserves_actual_history(self):
        self.assertEqual(m.node_from_view(view(stage='POST',rate=.125)),m.node_from_view(view(stage='POST',rate=8.)))

    def test_public_private_top_level_rejected(self):
        node=m.node_from_view(view());node['context']='CHANGED'
        with self.assertRaises(ValueError):m.features(node)

    def test_nested_oracle_rejected(self):
        node=m.node_from_view(view());node['current']['noise_oracle']=[0.]*3
        with self.assertRaises(ValueError):m.features(node)

    def test_future_history_rejected(self):
        node=m.node_from_view(view());node['history'].append(deepcopy(node['history'][0]))
        with self.assertRaises(ValueError):m.features(node)

    def test_history_discontinuity_rejected(self):
        node=m.node_from_view(view(2));node['history'][1]['before']['observation'][0]=1.
        with self.assertRaises(ValueError):m.features(node)

    def test_terminal_node_not_given_fake_features(self):
        v=view();v['memory']['current']['success']=True;v['history'][-1]['after']['success']=True
        with self.assertRaises(ValueError):m.node_from_view(v)

    def test_non_float32_command_rejected(self):
        v=view();v['history'][0]['command'][0]=.1
        with self.assertRaises(ValueError):m.node_from_view(v)

    def test_all_earliest_history_is_represented(self):
        v=view(10);other=deepcopy(v);other['history'][0]['before']['observation'][0]=1.
        self.assertFalse(np.array_equal(m.features(m.node_from_view(v)),m.features(m.node_from_view(other))))

    def test_literal_feature_mapping_and_padding_mask(self):
        node=m.node_from_view(view(2,.125));actual=m.features(node)
        self.assertTrue(np.array_equal(actual,q.literal_features(node)));self.assertEqual(actual[48+82],1.)
        self.assertEqual(actual[48+2*83+82],0.);self.assertTrue(np.all(actual[48+2*83:]==0))

    def test_linear_and_rbf_kernels_independently_recomputed(self):
        x=np.array([[1.,0.],[0.,2.],[-.5,.25]])
        for kind in m.KINDS:
            self.assertTrue(np.allclose(m.kernel(x,x,kind),[q.literal_kernel(r,x,kind) for r in x],atol=1e-14,rtol=1e-14))

    def test_empty_active_columns_have_constant_kernels(self):
        z=np.empty((2,0));self.assertTrue(np.array_equal(m.kernel(z,z,'RBF'),np.ones((2,2))))
        self.assertTrue(np.array_equal(m.kernel(z,z,'LINEAR'),np.zeros((2,2))))

    def test_weighted_linear_fit_and_literal_prediction(self):
        self.check_fit('LINEAR')

    def test_weighted_rbf_fit_and_literal_prediction(self):
        self.check_fit('RBF')

    def check_fit(self,kind):
        nodes=[m.node_from_view(view(value=v)) for v in (0.,.125,.25)];y=[[.1,.8],[.4,.3],[.6,.2]]
        with TemporaryDirectory() as folder:
            model=m.fit_model(nodes,y,[0,1,1],kind,Path(folder)/'model.npz')
            for node in nodes:self.assertTrue(np.allclose(m.predict(model,folder,node),q.literal_predict(model,folder,node),atol=1e-11,rtol=1e-11))

    def test_constant_targets_use_unpenalized_intercept(self):
        nodes=[m.node_from_view(view())]*2
        with TemporaryDirectory() as folder:
            model=m.fit_model(nodes,[[.2,.7]]*2,[0,1],'RBF',Path(folder)/'model.npz')
            self.assertTrue(np.allclose(m.predict(model,folder,nodes[0]),[.2,.7],atol=1e-12))

    def test_model_byte_changes_rejected(self):
        with TemporaryDirectory() as folder:
            p=Path(folder)/'model.npz';p.write_bytes(b'not model');model={'file':p.name,'sha256':'0'*64}
            with self.assertRaises(ValueError):m.predict(model,folder,m.node_from_view(view()))

    def test_precision_ties_are_first_not_future_costs(self):
        self.assertEqual(m.choice([.2,.2-1e-12]),0);self.assertEqual(m.choice([.2,.2-1e-8]),1)
        self.assertEqual(m.choice([.2,.1,.1]),1)

    def test_receiver_choice_not_clairvoyant_training_label(self):
        g=graph();g['leaves'][3]['loss']=1
        models={'receiver_RBF':{'sha256':'frozen'}}
        with patch.object(m,'predict',return_value=[.1,.2,.3,.4]):
            nodes,ys,groups,bindings=m.training_rows('sequential_RBF',[g],models,Path('.'))
        self.assertEqual(ys[0][0],g['leaves'][0]['loss']/500);self.assertEqual(bindings[0]['rates'],[.125]*3)
        self.assertEqual(groups,[6]);self.assertEqual(len(nodes),1)

    def test_receiver_and_acquisition_training_groups_are_separate(self):
        gs=[graph(g) for g in range(9)];models={'receiver_RBF':{'sha256':'fixed'}}
        with patch.object(m,'predict',return_value=[.2,.1,.3,.4]):
            self.assertEqual(set(m.training_rows('receiver_RBF',gs,models,Path('.'))[2]),set(range(6)))
            self.assertEqual(set(m.training_rows('sequential_RBF',gs,models,Path('.'))[2]),{6,7,8})

    def test_CAL_cannot_enter_training_rows(self):
        with self.assertRaises(ValueError):m.training_rows('static_RBF',[graph(cohort='CAL')],{},Path('.'))

    def test_TEST_reader_rejected_before_access(self):
        with patch.object(m.io,'rows',side_effect=AssertionError('data opened')):
            with self.assertRaises(ValueError):m.assemble_graphs(Path('.'),'TEST')

    def test_different_saved_legal_choices_change_supported_leaf(self):
        node=m.node_from_view(view());bank={'models':{'static_RBF':{'sha256':'saved'}}}
        with patch.object(m,'predict',return_value=[.9]*5+[.1]+[.9]*6):first=m.pre_choice('STATIC_RBF',bank,Path('.'),node)
        with patch.object(m,'predict',return_value=[.9]*11+[.1]):second=m.pre_choice('STATIC_RBF',bank,Path('.'),node)
        self.assertEqual((first['action'],first['rate']),(1,1));self.assertEqual((second['action'],second['rate']),(2,3))

    def test_terminal_return_uses_existing_leaf_not_fake_prediction(self):
        g=graph();g['returns'][1]=None
        with patch.object(m,'predict',return_value=[.1,.2,.3,.4]):
            _,ys,_,bindings=m.training_rows('sequential_RBF',[g],{'receiver_RBF':{'sha256':'fixed'}},Path('.'))
        self.assertEqual(ys[0][1],g['leaves'][5]['loss']/500);self.assertEqual(bindings[0]['rates'][1],.5)

    def test_complete_constructed_branch_registry_and_early_ends(self):
        cases,examples=source_fixture()
        def rows(path):return iter(cases if Path(path).name=='cases.jsonl.gz' else examples)
        with patch.object(m.io,'rows',side_effect=rows):graphs=m.assemble_graphs(Path('.'),'CAL')
        self.assertEqual(len(graphs),18);self.assertEqual(sum(g['pre'] is None for g in graphs),1)
        self.assertEqual(sum(n is None for g in graphs for n in g['returns']),5)

    def test_missing_factual_leaf_is_rejected(self):
        cases,examples=source_fixture();cases.pop()
        def rows(path):return iter(cases if Path(path).name=='cases.jsonl.gz' else examples)
        with patch.object(m.io,'rows',side_effect=rows):
            with self.assertRaises(ValueError):m.assemble_graphs(Path('.'),'CAL')

    def test_changed_return_state_across_rates_is_rejected(self):
        cases,examples=source_fixture()
        for ex in examples:
            if ex['view'] is not None and ex['stage']=='POST':
                ex['view']['memory']['integral_xy'][0]=.5;break
        def rows(path):return iter(cases if Path(path).name=='cases.jsonl.gz' else examples)
        with patch.object(m.io,'rows',side_effect=rows):
            with self.assertRaises(ValueError):m.assemble_graphs(Path('.'),'CAL')

    def test_journal_acknowledgements_precede_result_disclosure(self):
        import json
        with TemporaryDirectory() as folder:
            path=Path(folder)/'trace.jsonl';j=m.Journal(path)
            a=j.write('PRE_INPUT',{'node':m.node_from_view(view())});b=j.write('PRE_DECISION',{'input_sequence':a,'rate':1})
            c=j.write('OUTCOME',{'loss':50});j.close();records=[json.loads(v) for v in path.read_text(encoding='utf8').splitlines()]
        self.assertLess(a,b);self.assertLess(b,c);self.assertEqual([r['sequence'] for r in records],[0,1,2])

    def test_constructed_entire_pipeline_and_independent_audits(self):
        with TemporaryDirectory() as temporary:
            base=Path(temporary);source=base/'source';run=base/'run';run.mkdir()
            for cohort in ('TRAIN','CAL'):
                folder=source/cohort.lower();folder.mkdir(parents=True)
                cases,examples=source_fixture(cohort)
                m.write_rows(folder/'cases.jsonl.gz',cases);m.write_rows(folder/'examples.jsonl.gz',examples)
            manifest=run/'manifest.json';manifest.write_text('{}',encoding='utf8')
            with patch.object(m,'checked',return_value={'manifest_id':'constructed','input_sha256':{},'config':{'source_run':str(source)}}):
                fit=m.train(manifest);audit=q.audit_models(manifest);result=m.evaluate(manifest);replay=q.audit_replay(manifest)
            self.assertEqual(fit['actual_model_fits'],8);self.assertEqual(audit['independent_refits'],8)
            self.assertEqual(result['offline_replays'],216);self.assertEqual(replay['integrity'],'PASSED')
            self.assertEqual(fit['guard']['operation_counts']['simulation'],0)

if __name__=='__main__':unittest.main()
