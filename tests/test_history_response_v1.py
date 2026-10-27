"""Array-only synthetic contracts; never constructs/resets/steps an environment."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
import gzip,json
import numpy as np
from src.probe import history_response_model_v1 as model
from src.analysis import history_response_training_v1 as train
from src.analysis import history_response_independent_math_v1 as independent
from src.analysis import history_response_io_v1 as allocation
from src.analysis import history_response_evaluation_v1 as evaluation
from src.analysis import history_response_statistics_audit_v1 as statistics
from src.probe.paired_packet_query_v1 import validate


def query(index=0):
    def state(obs):return dict(observation=list(obs),success=False,terminated=False,truncated=False)
    obs=np.zeros(39);obs[:3]=[.03+.003*index,.6,.25];obs[4:7]=[.08,.65,.1];obs[36:39]=[.1,.7,.2]
    history=[]
    for i in range(16):
        before=state(obs);u=np.zeros(4,np.float32);u[i%2]=np.float32(.4 if (i//2)%2==0 else -.4)
        obs=obs.copy();obs[:2]+=.001*(1+.03*index)*u[:2];obs[2]+=.00001*(index%3)
        history.append(dict(at_calls=8+i,before=before,command=u.astype(float).tolist(),after=state(obs)))
    plus=np.zeros((16,4),np.float32)
    for t in range(16):
        plus[t,0]=np.float32(.4 if ((t+1)*(2*index+3))%11<5 else -.4)
        plus[t,1]=np.float32(.4 if ((t+2)*(3*index+1))%13<6 else -.4)
    minus=-plus;minus[:,2:]=0
    return validate(dict(schema='PAIRED_PACKET_QUERY_V1',task='push-v3',at_calls=24,acquisition_action='IN_TASK',current=state(obs),history=history,
        integral_carried_xy=[.01*index,-.002*index],packets=dict(ZERO=np.zeros((16,4)).tolist(),PLUS=plus.astype(float).tolist(),MINUS=minus.astype(float).tolist())))


def synthetic():
    rows=[]
    for task in allocation.io.TASKS:
        for i in range(12):
            q=query(i);q['task']=task;positions={r:[] for r in ('ZERO','PLUS','MINUS')}
            coefficients=np.asarray([np.exp(-lag/3)*(1+.03*i)*np.array([[1.,.1],[-.05,.9]]) for lag in range(16)]).reshape(32,2)
            for h in range(1,17):
                p=.01*independent.inputs(q['packets']['PLUS'],h)@coefficients
                base=np.asarray(q['current']['observation'][:2])+[h*.0002,h*.0001];even=np.array([h*.000001,-h*.000002])
                positions['ZERO'].append(base.tolist());positions['PLUS'].append((base+p+even).tolist());positions['MINUS'].append((base-p+even).tolist())
            rows.append(dict(family_index=len(rows),group=i%9,task=task,context='UNCHANGED',boundary=(16,32,64)[i%3],acquisition_action='IN_TASK',query=q,
                packet_positions_xy=positions,packet_lengths={r:16 for r in positions},complete_three_role_H16=True,reasons={r:'COMPLETE_PACKET' for r in positions},saved_forecast=None))
    return rows


class HistoryResponseTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=synthetic();cls.events=[];cls.bank=train.fit(cls.data,lambda event,row:cls.events.append((event,row)))
        cls.independent_counts={};cls.other=independent.refit(cls.data,cls.independent_counts)

    def test_public_descriptor_dimensions(self):
        self.assertEqual(model.descriptor(query(),'STATE').shape,(41,));self.assertEqual(model.descriptor(query(),'HISTORY').shape,(153,))

    def test_unchanged_physical_host_and_collector(self):
        root=allocation.ROOT
        for name in ('host','collect'):
            current=(root/('src/analysis/history_response_'+name+'_v1.py')).read_text('utf8')
            for part in ('io','host','model'):current=current.replace('history_response_'+part+'_v1','paired_packet_'+part+'_v1')
            self.assertEqual(current,(root/('src/analysis/paired_packet_'+name+'_v1.py')).read_text('utf8'))

    def test_allocation_arrays_pair_roles_without_extra_world(self):
        specifications=allocation.population('SOFTWARE')[:3]
        packets=[allocation.packets(s) for s in specifications];self.assertEqual(packets[0],packets[1]);self.assertEqual(packets[1],packets[2])
        tapes=[allocation.noise(s) for s in specifications]
        np.testing.assert_array_equal(tapes[0],tapes[1]);np.testing.assert_array_equal(tapes[1],tapes[2])
        self.assertEqual(tapes[0].shape,(500,3));self.assertFalse(tapes[0].flags.writeable)
        self.assertEqual(allocation.registry()['noise_namespace_base'],2026102910)

    def test_history_descriptor_uses_completed_commands(self):
        q=query();other=deepcopy(q);other['history'][0]['command'][0]=0.
        np.testing.assert_array_equal(model.descriptor(q,'STATE'),model.descriptor(other,'STATE'))
        self.assertFalse(np.array_equal(model.descriptor(q,'HISTORY'),model.descriptor(other,'HISTORY')))

    def test_no_identity_time_or_acquisition_descriptor(self):
        q=query();other=deepcopy(q);other['at_calls']+=1;other['acquisition_action']='MOVE'
        for row in other['history']:row['at_calls']+=1
        np.testing.assert_array_equal(model.descriptor(q,'HISTORY'),model.descriptor(other,'HISTORY'))

    def test_private_root_rejected(self):
        q=query();q['matrix_xy_oracle']=[[1,0],[0,1]]
        with self.assertRaises(ValueError):model.descriptor(q,'HISTORY')

    def test_private_nested_state_rejected(self):
        q=query();q['history'][0]['before']['noise_oracle']=[0,0,0]
        with self.assertRaises(ValueError):model.descriptor(q,'HISTORY')

    def test_future_or_stale_history_rejected(self):
        q=query();q['history'][-1]['at_calls']+=1
        with self.assertRaises(ValueError):model.descriptor(q,'HISTORY')

    def test_discontinuous_history_rejected(self):
        q=query();q['history'][3]['before']['observation'][0]+=.1
        with self.assertRaises(ValueError):model.descriptor(q,'HISTORY')

    def test_terminal_entry_rejected(self):
        q=query();q['current']['success']=True
        with self.assertRaises(ValueError):model.predict(self.bank,q)

    def test_short_history_rejected_not_padded(self):
        q=query();q['history']=q['history'][1:]
        with self.assertRaises(ValueError):model.predict(self.bank,q)

    def test_future_command_causality(self):
        q=query(2);other=deepcopy(q)
        for t in range(8,16):
            for j in (0,1):other['packets']['PLUS'][t][j]*=-1;other['packets']['MINUS'][t][j]*=-1
        left=model.predict(self.bank,q);right=model.predict(self.bank,other)
        for kind in model.METHODS:
            for pair in left[kind]:np.testing.assert_array_equal(np.asarray(left[kind][pair])[:8],np.asarray(right[kind][pair])[:8])

    def test_known_earlier_command_changes_forecast(self):
        q=query(2);other=deepcopy(q);other['packets']['PLUS'][0][0]*=-1;other['packets']['MINUS'][0][0]*=-1
        self.assertNotEqual(model.predict(self.bank,q)['FIR']['ZERO__PLUS'][0],model.predict(self.bank,other)['FIR']['ZERO__PLUS'][0])

    def test_zero_reference_and_pair_signs(self):
        predictions=model.predict(self.bank,query())
        for kind,rows in predictions.items():
            p=np.asarray(rows['ZERO__PLUS']);np.testing.assert_allclose(rows['ZERO__MINUS'],-p,atol=1e-13)
            np.testing.assert_allclose(rows['PLUS__MINUS'],-2*p,atol=1e-13)
            if kind=='ZERO':np.testing.assert_array_equal(p,np.zeros((16,2)))

    def test_forecast_no_online_refitting(self):
        def denied(*args,**kwargs):raise AssertionError('fit during prediction')
        with patch.object(np.linalg,'solve',denied),patch.object(np.linalg,'lstsq',denied),patch.object(np.linalg,'eigh',denied):model.predict(self.bank,query())

    def test_independent_coefficients(self):
        self.assertLess(independent.compare_models(self.bank,self.other),1e-7)
        self.assertEqual(self.independent_counts,dict(augmented_lstsq=42,symmetric_eigendecompositions=6))

    def test_independent_predictions_with_production_disabled(self):
        def denied(*args,**kwargs):raise AssertionError('production function used by literal predictor')
        q=query(6);saved=model.predict(self.bank,q)
        with patch.object(model,'descriptor',denied),patch.object(model,'predict',denied),patch.object(train,'fit',denied):other=independent.evaluate(self.bank,q)
        for k in saved:
            for p in saved[k]:np.testing.assert_allclose(saved[k][p],other[k][p],atol=1e-10,rtol=1e-8)

    def test_unknown_model_field_rejected(self):
        bank=deepcopy(self.bank);bank['by_task']['push-v3']['FIR']['fault_oracle']=1
        with self.assertRaises(ValueError):model.predict(bank,query())

    def test_nonfinite_model_rejected(self):
        bank=deepcopy(self.bank);bank['by_task']['push-v3']['FIR']['coef'][0][0]=float('nan')
        with self.assertRaises(ValueError):model.predict(bank,query())

    def test_train_constant_context_columns_scale_one(self):
        _,sd,_=train.context_bank(self.data[:12],'STATE')
        self.assertEqual(sd[1],1.);self.assertEqual(sd[3],1.)

    def test_prediction_does_not_reestimate_normalizer(self):
        before=deepcopy(self.bank);model.predict(self.bank,query(25));self.assertEqual(self.bank,before)

    def test_stable_nearest_tie_uses_first_saved_matrix(self):
        bank=deepcopy(self.bank);item=bank['by_task']['push-v3']['HISTORY_NN'];item['contexts']=[item['contexts'][0]]*2
        item['coefficients']=[np.ones((32,2)).tolist(),np.zeros((32,2)).tolist()]
        coef=model.coefficients(bank,query())['HISTORY_NN'][1];np.testing.assert_array_equal(coef,np.ones((32,2)))

    def test_constant_context_kernel_equals_primal_fir(self):
        rows=deepcopy(self.data[:12])
        for row in rows:row['query']=deepcopy(rows[0]['query'])
        selected,x,y,w,ids=train.dataset(rows,'push-v3');global_model=train.linear_fit(x,y,w);kernel=train.kernel_fit(selected,x,y,w,ids,'STATE')
        np.testing.assert_allclose(np.sum(kernel['coefficients'],axis=0),global_model['coef'],atol=1e-9,rtol=1e-7)

    def test_symmetric_training_objective_keeps_even_constant(self):
        p=np.array([.03,-.07]);odd=np.array([.02,.01]);even=np.array([.004,.003])
        truth=[odd+even,-odd+even,-2*odd];prediction=[p,-p,-2*p]
        actual=sum(float(np.sum((a-b)**2)) for a,b in zip(prediction,truth))/3
        self.assertAlmostEqual(actual,2*np.sum((p-odd)**2)+2*np.sum(even**2)/3,places=15)

    def test_group_then_family_weights(self):
        selected,_,_,w,ids=train.dataset(self.data,'push-v3');totals={g:0. for g in range(9)}
        for j,f in enumerate(selected):totals[f['group']]+=float(w[ids==j].sum())
        np.testing.assert_allclose(list(totals.values()),np.full(9,1/9),atol=1e-16)

    def test_partial_training_family_retained_but_not_fitted(self):
        data=deepcopy(self.data);data[0]['complete_three_role_H16']=False;data[0]['packet_lengths']['MINUS']=0;data[0]['packet_positions_xy']['MINUS']=[]
        selected,*_=train.dataset(data,'push-v3');self.assertEqual(len(data),36);self.assertEqual(len(selected),11)

    def test_full_physical_budget_and_population(self):
        c=allocation.config();self.assertEqual(c['combined_limits']['executions'],864)
        self.assertEqual(c['combined_limits']['control_steps'],80640);self.assertEqual(c['combined_limits']['all_resets'],44064)
        self.assertEqual(c['combined_limits']['physical_frames'],22435200)
        self.assertEqual(allocation.population('QUAL')[0]['seed'],112300)

    def test_missing_and_invalid_endpoints_preserve_denominator(self):
        family=deepcopy(self.data[0]);family['query']=None;family['packet_lengths']={r:0 for r in family['packet_lengths']}
        scores=evaluation.scores([family]);self.assertEqual(len(scores),36);self.assertEqual({r['loss_nm'] for r in scores},{10**9})
        self.assertEqual({r['availability'] for r in scores},{'ENTRY_UNAVAILABLE'})
        family['saved_forecast']=dict(forecast_error=dict(type='TEST_FAILURE'))
        self.assertEqual({r['availability'] for r in evaluation.scores([family])},{'INVALID_FORECAST'})

    def test_exact_fit_call_accounting(self):
        self.assertEqual(sum(e=='FIT_INTENT' for e,r in self.events),48)
        self.assertEqual(sum(e=='FIT_COMPLETE' for e,r in self.events),48)

    def test_forecast_accounting(self):
        count={};model.predict(self.bank,query(),count)
        self.assertEqual(count,dict(trajectories_started=18,zero_rows=48,trajectories_completed=18,linear_rows=240))

    def test_output_is_not_silently_clipped(self):
        bank=deepcopy(self.bank);bank['by_task']['push-v3']['FIR']['coef']=np.full((32,2),1e9).tolist()
        value=model.predict(bank,query())['FIR']['ZERO__PLUS'][0]
        self.assertGreater(max(abs(x) for x in value),1.)

    def test_all_five_primary_comparisons_and_independent_statistics(self):
        # These are constructed public records for scoring, not simulator data.
        families=[];cases=[];traces=[]
        for g in range(9):
            for task in allocation.io.TASKS:
                for context in ('UNCHANGED','CHANGED'):
                    for action in ('IN_TASK','MOVE'):
                        identity=dict(group=g,task=task,context=context,boundary=(16,32,64)[g%3],acquisition_action=action)
                        positions={role:[[.1+sign*.001*h,.5+sign*.002*h] for h in range(1,17)] for role,sign in (('ZERO',0),('PLUS',1),('MINUS',-1))}
                        forecasts={k:{} for k in model.METHODS}
                        for left,right in independent.PAIRS:
                            truth=np.asarray(positions[right])-np.asarray(positions[left])
                            for method in model.METHODS:forecasts[method][left+'__'+right]=(truth if method==model.SELECTED else np.zeros((16,2))).tolist()
                        record=dict(forecast_error=None,forecasts=forecasts)
                        families.append(dict(identity,family_index=len(families),saved_forecast=record,packet_positions_xy=positions,
                            packet_lengths={r:16 for r in positions},complete_three_role_H16=True))
                        for role in ('ZERO','PLUS','MINUS'):
                            cases.append(dict(identity,packet_kind=role,packet_steps=16,entry_at_calls=0,forecast_record=record))
                            traces.append(dict(steps=[dict(after=dict(observation=p)) for p in positions[role]]))
        with TemporaryDirectory(prefix='constructed_history_response_score_') as tmp:
            root=Path(tmp);manifest=root/'manifest.json';manifest.write_text(json.dumps(dict(manifest_id='CONSTRUCTED_UNIT_TEST_ONLY')),encoding='utf8')
            (root/'qual').mkdir();(root/'model_lock.json').write_text(json.dumps(dict(selected_model='HISTORY_KERNEL')),encoding='utf8')
            (root/'qual/audit.json').write_text(json.dumps(dict(invalid_forecasts=0)),encoding='utf8')
            for name,values in (('cases',cases),('public_trajectories',traces)):
                with gzip.open(root/('qual/'+name+'.jsonl.gz'),'wt',encoding='utf8') as f:
                    for value in values:f.write(json.dumps(value)+'\n')
            with patch.object(allocation,'checked',return_value={}),patch.object(train,'families',side_effect=AssertionError('production reader disabled')),patch.object(evaluation,'families',return_value=families):
                result=evaluation.evaluate_split(manifest,'QUAL');audited=statistics.audit(manifest,'QUAL')
            self.assertEqual(result['status'],'QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY')
            self.assertEqual(set(result['co_primary']),set(model.BASELINES));self.assertTrue(all(result['gates'].values()))
            self.assertEqual(audited['integrity'],'PASSED');self.assertEqual(audited['endpoint_rows'],3888)
