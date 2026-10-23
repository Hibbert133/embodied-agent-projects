"""Pure arrays/synthetic transcripts only; never instantiate or advance an environment."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
from fractions import Fraction
from unittest import TestCase
from unittest.mock import patch
import io as streams
import json
import numpy as np
from src.analysis import latent_response_io_v1 as a,latent_response_host_v1 as host,latent_response_record_audit_v1 as audit
from src.analysis import latent_response_training_v1 as training,latent_response_model_audit_v1 as ma
from src.analysis import latent_response_evaluation_v1 as ev,latent_response_statistics_audit_v1 as sa
from src.analysis.capsule_record_json_v2 import JsonJournal,normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.nominal_command_target_v1 import INITIAL,LOW,HIGH
from src.probe.latent_response_query_v1 import ForecastQuery,METHODS,context,baseline20,make_query,assert_public_training_window
from src.probe.latent_response_model_v1 import predict
from src.rollout.task_registry import create_task_policy


class ArraySession(ProbeSession):
    def witness(self):
        base=self.env.unwrapped
        return {'native_sha256':a.io.digest({'q':base.data.mocap_pos.tolist(),'t':base.data.time}),
            'python_semantic_sha256':a.io.digest(self.public().observation),'noise_past_sha256':a.io.digest(self.ctx['noise_rows'][:self.ctx['calls']].tolist()),'simulation_time':base.data.time}


def fixture(end_at=500,mutant=None,split='SOFTWARE',context='UNCHANGED',packet_kind=None,model_bank=None):
    spec=next(s for s in a.population(split) if s['group']==0 and s['task']=='push-v3' and s['context']==context and (packet_kind is None or s['packet_kind']==packet_kind))
    source=streams.StringIO();private_stream=streams.StringIO();identity={'experiment_run_id':'ARRAY','manifest_id':'ARRAY','source_git_commit':'ARRAY'}
    journal=JsonJournal(source,identity);private_journal=JsonJournal(private_stream,identity);last={};changed=False
    def emit(kind,payload):
        nonlocal last,changed
        if mutant=='saved_target' and kind=='PUBLIC_SENT_TARGET_PLAN' and not changed:
            payload=deepcopy(payload);payload['plan']['numbers']['target'][0]+=.1;changed=True
        e=journal.emit(kind,{**spec,**payload});last={k:e[k] for k in ('sequence','saved_ns')};return e
    def private(kind,payload):return private_journal.emit(kind,{**spec,**payload})
    ledger=LifecycleLedger(emit,a.limits(split)['physical_frames']);before=ledger.snapshot();emit('FACTORY_INTENT',{'ledger':before})
    def array_only_reset(_):
        for k,n in (('simulation_attempts',100),('simulation_completed',100),('simulation_frames_attempted',500),('simulation_frames_completed',500)):ledger.add(k,n)
    for _ in range(50):
        with ledger.scope('GOAL_GENERATION'):ledger.reset_call(array_only_reset,None)
    emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
    with ledger.scope('CONTROLLED_RESET'):ledger.reset_call(array_only_reset,None)
    observation=[0.]*39;observation[:3]=[.1,.8,.25];observation[4:7]=[.8,0.,.05];observation[-3:]=[.3,.9,.05]
    if mutant=='anchor_miss':observation[2]=.1
    data=SimpleNamespace(time=.625,mocap_pos=np.array([INITIAL]),mocap_quat=np.array([[1.,0.,1.,0.]]),_address=2)
    base=SimpleNamespace(data=data,model=SimpleNamespace(_address=1),mocap_low=np.array(LOW),mocap_high=np.array(HIGH),action_scale=.01);calls=0
    def array_only_step(command):
        nonlocal calls
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        if mutant=='target_scale':data.mocap_pos=np.clip(data.mocap_pos+np.array(command[:3],dtype=np.float64)[None]*.02,LOW,HIGH)
        else:SawyerXYZEnv.set_xyz_action(base,np.asarray(command[:3],np.float32))
        # A real MuJoCo field setter keeps the 1x4 layout; emulate that setter only.
        data.mocap_quat=np.array([[1.,0.,1.,0.]])
        calls+=1;data.time+=.02 if mutant=='clock' else .0125
        for k,n in (('simulation_attempts',1),('simulation_completed',1),('simulation_frames_attempted',5),('simulation_frames_completed',5)):ledger.add(k,n)
        return np.array(observation),0.,False,False,{'success':calls>=end_at}
    session=ArraySession(SimpleNamespace(unwrapped=base,step=array_only_step),create_task_policy('push-v3'),np.array(observation),'push-v3',spec['seed'],a.initial_fault(spec),emit,ledger,{'completed':0,'maximum':a.limits(split)['control_steps']})
    session.ctx['noise_rows']=a.noise(spec);session.branch={'role':'LATENT_RESPONSE_COLLECTION','future':0,'program':'PREDECLARED_PACKET'}
    emit('NOISE_COMMITMENT',{'at_calls':0,'tape_sha256_oracle':a.io.digest(session.ctx['noise_rows'].tolist())})
    initial=normalize(asdict(session.public()));outcome,public=host.run_live(spec,session,emit,private,lambda:deepcopy(last),lambda:None,model_bank,'ARRAY_MODEL' if model_bank else None)
    case={**spec,**outcome,'completed':True,'environment_closed':True,'error':None,'close_error':None,'captures':0,'restores':0,
        'initial':initial,'final':normalize(asdict(session.public())),'ledger_before':before,'ledger_before_close':ledger.snapshot(),
        'ledger_after_close':ledger.snapshot(),'host_attempts':calls,'host_returned':calls,'public_trajectory_sha256':a.io.digest(public)}
    events=[json.loads(line) for line in source.getvalue().splitlines()];p=[json.loads(line) for line in private_stream.getvalue().splitlines()]
    meta={'schema':'PUBLIC_PACKET_METADATA_V1','entry_at_calls':case['entry_at_calls'],'packet_commands':a.packet(spec),'reason':case['reason']}
    return spec,case,events,p,public,meta,ledger.snapshot()


def qsample(n=3):
    obs=np.arange(n*39,dtype=float).reshape(n,39)/100;commands=np.zeros((n,4))
    return ForecastQuery('push-v3',n-1,tuple(obs.tolist()),tuple(commands.tolist()),tuple(int(i>0) for i in range(n)),(.1,-.2,.05),tuple(np.zeros((8,4)).tolist()))


def normal():return {'history_mean':[0.]*43,'history_scale':[1.]*43,'offset_mean':[0.]*3,'offset_scale':[1.]*3}


def netmodel(method):
    def layer(i,o):return {'weight':np.zeros((o,i)).tolist(),'bias':[0.]*o}
    model={'method':method,'task':'push-v3','normalization':normal(),'encoder1':layer(723,32),'encoder2':layer(32,8)}
    if method=='DIRECT_MLP_H8':model.update(direct1=layer(40,32),direct2=layer(32,16))
    else:model.update(transition1=layer(12,32),transition2=layer(32,8),output=layer(8,2))
    return model


def synthetic_rows(split='QUAL'):
    rows=[]
    for spec in a.population(split):
        for i,method in enumerate(METHODS):
            one=ev.score(np.full((8,2),.001*(i+1)),np.zeros((8,2)),1,True,True)
            eight=ev.score(np.full((8,2),.001*(i+1)),np.zeros((8,2)),8,True,True) if method in METHODS[:6] else {'raw_m':None,'loss_nm':None,'reason':'ONE_STEP_MODEL_ONLY','capped':False}
            rows.append({**spec,'method':method,'query_available':True,'forecast_valid':True,'actual_packet_steps':8,'complete_first_eight':True,'collection_reason':'PACKET_COMPLETE',
                'h1_raw_error_m':one['raw_m'],'h1_loss_nm':one['loss_nm'],'h1_reason':one['reason'],'h1_capped':one['capped'],
                'h8_raw_rmse_m':eight['raw_m'],'h8_loss_nm':eight['loss_nm'],'h8_reason':eight['reason'],'h8_capped':eight['capped']})
    return rows


class LatentResponseTests(TestCase):
    @classmethod
    def setUpClass(cls):cls.full=fixture();cls.short=fixture(end_at=24,split='TRAIN');cls.early=fixture(end_at=4);cls.train=fixture(split='TRAIN')

    def test_full_population_and_physical_budget(self):
        self.assertEqual([len(a.population(s)) for s in a.SPLITS],[36,216,108,432]);self.assertEqual(a.config()['combined_limits'],{'executions':792,'control_steps':112896,'controlled_resets':792,'factory_resets':39600,'all_resets':40392,'physical_frames':20760480})
        for s in a.SPLITS:self.assertEqual(len(a.population(s)),len({tuple(v.values()) for v in a.population(s)}))

    def test_nonoverlapping_allocations_and_reserved_ranges(self):
        seeds=[{v['seed'] for v in a.population(s)} for s in a.SPLITS]
        for i in range(4):
            for j in range(i):self.assertFalse(seeds[i]&seeds[j])
        with self.assertRaises(ValueError):a.validate_spec(a.population('TRAIN')[0]|{'seed':1})

    def test_predeclared_packets_and_common_noise(self):
        u=a.population('SOFTWARE')[0];v=u|{'context':'CHANGED'}
        np.testing.assert_array_equal(a.noise(u),a.noise(v));self.assertFalse(a.noise(u).flags.writeable);self.assertEqual(a.packet(u),a.packet(v))
        self.assertEqual(len(a.packet(a.population('TRAIN')[0])),32)

    def test_independent_array_transcript_replay_and_costs(self):
        s,c,e,p,t,m,l=self.full
        with patch.object(host,'native_values',side_effect=RuntimeError('disabled')),patch.object(host,'make_query',side_effect=RuntimeError('disabled')):
            row,actual,*_=audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})
        self.assertEqual(actual,l);self.assertTrue(row['native_target_updates_bit_exact']);self.assertTrue(c['complete_packet']);self.assertFalse(c['full_task_tail_evaluated'])

    def test_forecast_saved_before_all_packet_actions(self):
        _,c,events,*_=self.full;f=next(e for e in events if e.get('agent_event')=='FORECAST_RESULT')
        actions=[e for e in events if e['event']=='STEP_COMPLETE' and e['phase']=='EXOGENOUS_PACKET']
        self.assertEqual(len(actions),8);self.assertTrue(all(f['saved_ns']<e['execution_started_ns'] for e in actions));self.assertEqual(c['policy_queries'],16)

    def test_compact_native_values_do_not_claim_full_step_signatures(self):
        _,c,_,private,*_=self.full;self.assertEqual(len(private),2*c['total_steps']+2)
        self.assertTrue(all((p['native_signature_oracle'] is None)==(p['signature_scope']=='NUMERIC_ONLY') for p in private))
        self.assertTrue(all(p['evaluator_only'] and not p['permitted_training_input_or_label'] for p in private))

    def test_early_success_no_fake_entry_and_full_reset_cost(self):
        s,c,e,p,t,m,l=self.early;row,actual,*_=audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})
        self.assertIsNone(row['entry_at_calls']);self.assertEqual(c['packet_steps'],0);self.assertEqual(training.windows(t,m),[]);self.assertEqual(l['counts']['reset_attempts'],51);self.assertEqual(actual,l)

    def test_short_packet_mask_is_actual_contiguous_prefix(self):
        _,c,_,_,t,m,_=self.short;ws=training.windows(t,m);n=c['packet_steps'];self.assertTrue(0<n<8);self.assertEqual(len(ws),n)
        self.assertEqual(ws[0]['mask'],[True]*n+[False]*(8-n));self.assertTrue(np.all(np.array(ws[0]['targets'])[n:]==0))

    def test_32_packet_sliding_training_has_at_most_25_queries(self):
        _,c,_,_,t,m,_=self.train;ws=training.windows(t,m);self.assertEqual(c['packet_steps'],32);self.assertEqual(len(ws),25);self.assertTrue(all(all(w['mask']) for w in ws))

    def test_declared_eight_commands_only_support_entry_query(self):
        _,_,_,_,t,m,_=self.full;self.assertEqual(len(training.windows(t,m)),1)

    def test_anchor_miss_and_end_during_move_remain_unavailable(self):
        for kwargs,reason in (({'mutant':'anchor_miss'},'ANCHOR_NOT_REACHED'),({'end_at':18},'ENDED_DURING_REPOSITION')):
            s,c,e,p,t,m,_=fixture(**kwargs);row,*_=audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})
            self.assertEqual(c['reason'],reason);self.assertIsNone(c['entry_at_calls']);self.assertEqual(training.windows(t,m),[])

    def test_fault_change_preserves_current_state_and_rng(self):
        s,c,e,p,t,m,_=fixture(context='CHANGED');audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})
        event=next(e for e in e if e['event']=='FAULT_BOUNDARY');self.assertEqual(event['before'],event['after']);self.assertEqual(event['logical_step'],16)

    def test_false_native_scale_detected_without_silent_repair(self):
        s,c,e,p,t,m,_=fixture(mutant='target_scale');row,*_=audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}});self.assertFalse(row['native_target_updates_bit_exact'])

    def test_clock_and_modified_ack_rejected(self):
        for kind in ('clock','saved_target'):
            with self.subTest(kind=kind),self.assertRaises(ValueError):fixture(mutant=kind)

    def test_shifted_noise_cursor_rejected(self):
        s,c,e,p,t,m,_=deepcopy(self.early);next(v for v in e if v['event']=='STEP_COMPLETE')['noise_cursor_after']+=1
        with self.assertRaises(ValueError):audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})

    def test_world_replacement_and_reordered_private_samples_rejected(self):
        for kind in ('world','time'):
            s,c,e,p,t,m,_=deepcopy(self.early)
            if kind=='world':p[1]['model_address_oracle']+=1
            else:p[1]['saved_ns']=p[2]['saved_ns']+1
            with self.subTest(kind=kind),self.assertRaises(ValueError):audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})

    def test_private_injection_in_public_export_rejected(self):
        s,c,e,p,t,m,_=deepcopy(self.early);t['steps'][0]['mocap_oracle']=[0,0,0]
        with self.assertRaises(ValueError):audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})

    def test_public_query_does_not_read_future_observations(self):
        _,_,_,_,t,_,_=self.full;expected=make_query(t,10,np.zeros((8,4)).tolist()).to_dict();future=deepcopy(t)
        future['steps'][10]['observation_after']=['invalid future'];future['steps'].extend([{'future_oracle':True}]*501)
        self.assertEqual(make_query(future,10,np.zeros((8,4)).tolist()).to_dict(),expected)
        with self.assertRaises(ValueError):make_query(future,11,np.zeros((8,4)).tolist())

    def test_strict_query_rejects_private_seed_and_future_fields(self):
        for k in ('seed','fault_oracle','mocap_pos','future_observations','future_success'):
            with self.subTest(k=k),self.assertRaises(ValueError):ForecastQuery.from_dict(qsample().to_dict()|{k:0})

    def test_history_availability_and_no_fabricated_early_displacement(self):
        q=qsample(1);self.assertEqual(q.has_previous,(0,));self.assertEqual(context(q,normal(),'SS_SENT').shape,(723,))
        with self.assertRaises(ValueError):baseline20(q)
        bad=q.to_dict();bad['has_previous']=[1]
        with self.assertRaises(ValueError):ForecastQuery.from_dict(bad)

    def test_nonfinite_queries_and_unbounded_planned_command_rejected(self):
        for value in (float('nan'),float('inf'),1.1):
            q=qsample().to_dict();q['planned_commands']=np.zeros((8,4)).tolist();q['planned_commands'][0][0]=value
            with self.subTest(value=value),self.assertRaises(ValueError):ForecastQuery.from_dict(q)

    def test_float32_planned_commands_required(self):
        q=qsample().to_dict();q['planned_commands']=np.zeros((8,4)).tolist();q['planned_commands'][0][0]=.1
        with self.assertRaises(ValueError):ForecastQuery.from_dict(q)
        q['planned_commands'][0][0]=float(np.float32(.1));ForecastQuery.from_dict(q)

    def test_main_and_independent_context_and_historical_features_match(self):
        q=qsample()
        for method in METHODS:np.testing.assert_array_equal(context(q,normal(),method),ma.independent_context(q.to_dict(),normal(),method))
        np.testing.assert_array_equal(baseline20(q),ma.independent20(q.to_dict()))

    def test_same_capacity_ablation_changes_only_registered_inputs(self):
        q=qsample();full=context(q,normal(),'SS_SENT');no=context(q,normal(),'SS_NO_SENT');current=context(q,normal(),'SS_CURRENT_SENT')
        np.testing.assert_array_equal(full[:-3],no[:-3]);np.testing.assert_array_equal(no[-3:],np.zeros(3));self.assertTrue(np.all(current[:15*45]==0));np.testing.assert_array_equal(current[-48:],full[-48:])

    def test_known_state_space_constant_increment_residual_and_independent_forward(self):
        m=netmodel('SS_SENT');m['output']['bias']=[1.,-2.];expected=np.arange(1,9)[:,None]*[.01,-.02]
        np.testing.assert_allclose(predict(m,[qsample()])[0],expected,atol=1e-15);ma.same_predictions(predict(m,[qsample()]),ma.independent_predict(m,[qsample().to_dict()]))
        self.assertEqual(ev.score(expected,expected,8,True,True)['loss_nm'],0);self.assertGreater(ev.score(expected,np.zeros((8,2)),8,True,True)['loss_nm'],0)

    def test_future_declared_inputs_change_forecast_without_future_state(self):
        m=netmodel('SS_SENT');m['transition1']['weight'][0][8]=1.;m['transition2']['weight'][0][0]=1.;m['output']['weight'][0][0]=1.
        q=qsample();v=q.to_dict();v['planned_commands']=np.zeros((8,4)).tolist();v['planned_commands'][0][0]=float(np.float32(.4));other=ForecastQuery.from_dict(v)
        self.assertGreater(float(np.max(abs(predict(m,[q])-predict(m,[other])))),0)

    def test_direct_mlp_and_independent_forward_share_information(self):
        m=netmodel('DIRECT_MLP_H8');m['direct2']['bias']=list(np.arange(16)/10)
        np.testing.assert_allclose(predict(m,[qsample()])[0],.01*np.arange(16).reshape(8,2)/10);ma.same_predictions(predict(m,[qsample()]),ma.independent_predict(m,[qsample().to_dict()]))

    def test_partial_targets_cannot_smuggle_unused_future_responses(self):
        w={'query':qsample().to_dict(),'targets':np.zeros((8,2)).tolist(),'mask':[True]+[False]*7};assert_public_training_window(w)
        for change in ('nonzero','noncontiguous','none','oracle'):
            v=deepcopy(w)
            if change=='nonzero':v['targets'][1][0]=1
            elif change=='noncontiguous':v['mask']=[True,False,True]+[False]*5
            elif change=='none':v['mask']=[False]*8
            else:v['mocap_label']=0
            with self.subTest(change=change),self.assertRaises(ValueError):assert_public_training_window(v)

    def test_normalization_uses_trajectory_then_window_then_real_frame_weights(self):
        def window(n,shift):
            v=qsample(n).to_dict();v['observations']=(np.full((n,39),shift)).tolist()
            return {'query':v,'targets':np.zeros((8,2)).tolist(),'mask':[True]*8}
        norm=training.statistics([{'windows':[window(1,0)]},{'windows':[window(3,2),window(3,2)]}]);self.assertAlmostEqual(norm['history_mean'][0],1.);self.assertAlmostEqual(norm['history_scale'][0],1.)

    def test_independent_half_even_nanometre_losses_and_cap(self):
        for error in (.5e-9,1.5e-9,2.5e-9,.01,2.):
            p=np.full((8,2),error);one=ev.score(p,np.zeros((8,2)),8,True,True);other=sa.loss(p,np.zeros((8,2)),8,True,True)
            self.assertEqual(one,dict(zip(('raw_m','loss_nm','reason','capped'),other)))
        self.assertEqual(ev.score(np.full((8,2),.5e-9),np.zeros((8,2)),8,True,True)['loss_nm'],0)
        self.assertTrue(ev.score(np.full((8,2),2.),np.zeros((8,2)),8,True,True)['capped'])

    def test_missing_invalid_and_short_forecasts_have_full_penalties(self):
        for valid,present,truth,reason in ((None,False,[],'NO_MEASUREMENT_ENTRY'),(False,True,[],'INVALID_SAVED_FORECAST'),(True,True,[[0,0]],'SHORT_ACTUAL_PACKET')):
            v=ev.score(None,truth,8,valid,present);self.assertEqual(v['loss_nm'],10**9);self.assertIsNone(v['raw_m']);self.assertEqual(v['reason'],reason)

    def test_exact_integer_quantile_near_zero_not_float_rounded_promotion(self):
        seq=[-1,0,0,1];self.assertEqual(ev.quantile(seq,1,40),sa.percentile(seq,1,40));self.assertEqual(ev.quantile([0]*10000,39,40),Fraction(0))

    def test_full_qual_denominators_24_cells_and_independent_statistics(self):
        rows=synthetic_rows();main=ev.statistics(rows,'QUAL');independent=sa.independently_summarize(rows,'QUAL');sa.compare(main,independent)
        self.assertEqual(main['qualification'],'QUALIFIED_FORWARD_COMPONENT_ONLY');self.assertEqual(set(main['coverage'].values()),{18});self.assertTrue(all(v['allocated']==432 for v in main['summaries'].values()))

    def test_no_promotion_for_equal_performance_or_invalid_saved_forecast(self):
        rows=synthetic_rows()
        for r in rows:
            if r['method']=='SS_NO_SENT':r['h8_loss_nm']=1000000
        self.assertFalse(ev.statistics(rows,'QUAL')['gates']['both_co_primary_intervals_pass']);rows[0]['forecast_valid']=False
        self.assertFalse(ev.statistics(rows,'QUAL')['gates']['no_invalid_saved_forecast'])

    def test_cal_descriptive_only_and_independent_summary(self):
        rows=synthetic_rows('CAL');result=ev.statistics(rows,'CAL');sa.compare(result,sa.independently_summarize(rows,'CAL'));self.assertEqual(result['qualification'],'NOT_APPLICABLE_CAL')
        self.assertIsNone(result['summaries']['HISTORY_LINEAR10']['mean_h8_loss_m']);self.assertEqual(result['summaries']['HISTORY_LINEAR10']['valid_h8_count'],0)

    def test_missing_cell_does_not_disappear_from_allocated_population(self):
        rows=synthetic_rows()
        for r in rows:
            if r['task']=='reach-v3' and r['packet_kind']=='FIXED8':r['complete_first_eight']=False
        result=ev.statistics(rows,'QUAL');self.assertFalse(result['gates']['all_24_cells_at_least_three_complete']);self.assertEqual(result['summaries']['SS_SENT']['allocated'],432)

    def test_readonly_guard_counts_forbidden_environment_and_solve_attempts(self):
        from scripts.run_latent_response_v1 import readonly_guard
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        receipt={}
        with readonly_guard(receipt):
            with self.assertRaises(RuntimeError):SawyerXYZEnv.__init__(None)
            with self.assertRaises(ValueError):np.linalg.solve(np.eye(2),np.ones(2))
        self.assertEqual(receipt['blocked_operations']['environment_creations'],1);self.assertEqual(receipt['blocked_operations']['ridge_linear_systems'],1);self.assertEqual(receipt['network'],{'attempted_network_calls':0})

    def test_forecast_output_cannot_choose_or_change_collection_commands(self):
        bank={'push-v3':{m:{'method':m} for m in METHODS}}
        outputs=[]
        for constant in (0.,123.):
            with patch.object(host,'predict',side_effect=lambda m,qs:np.full((1,1 if m['method'] in METHODS[-2:] else 8,2),constant)):
                _,c,e,*_=fixture(split='CAL',model_bank=bank)
            outputs.append([v['command'] for v in e if v['event']=='STEP_COMPLETE'])
            self.assertEqual(len([v for v in e if v.get('agent_event')=='FORECAST_RESULT']),1)
        self.assertEqual(outputs[0],outputs[1])

    def test_invalid_saved_prediction_is_not_replaced_by_baseline(self):
        bank={'push-v3':{m:{'method':m} for m in METHODS}}
        with patch.object(host,'predict',side_effect=ValueError('known failure')):_,c,e,*_=fixture(split='CAL',model_bank=bank)
        rows=ev.loss_rows(c,e);self.assertTrue(all(r['forecast_valid'] is False and r['h1_loss_nm']==10**9 for r in rows))
        self.assertTrue(all(r['h8_loss_nm']==10**9 for r in rows[:6]))

    def test_all_cal_models_independently_replay_the_saved_forecast(self):
        bank={'push-v3':{m:netmodel(m) for m in METHODS[:4]}}
        bank['push-v3']['DIRECT_RIDGE_H8']={'task':'push-v3','method':'DIRECT_RIDGE_H8','normalization':normal(),'horizon_coefficients':np.zeros((8,756,2)).tolist()}
        bank['push-v3']['PERSIST_ZERO']={'task':'push-v3','method':'PERSIST_ZERO'}
        for method,d,n in (('HISTORY_LINEAR10',10,11),('QUADRATIC_STATE20',20,231)):
            bank['push-v3'][method]={'task':'push-v3','method':method,'mean':[0.]*d,'scale':[1.]*d,'coefficients':np.zeros((n,2)).tolist()}
        s,c,e,p,t,m,_=fixture(split='CAL',model_bank=bank)
        row,*_=audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}},bank,'ARRAY_MODEL')
        self.assertEqual(row['invalid_forecasts'],0);sa.compare(ev.loss_rows(c,e),sa.case_rows(c,e))

    def test_saved_query_future_response_or_inverse_mapping_tamper_rejected(self):
        s,c,e,p,t,m,_=deepcopy(self.full)
        next(v for v in e if v.get('agent_event')=='FORECAST_RESULT')['public_payload']['result']['query']['observations'][-1][0]+=.1
        with self.assertRaises(ValueError):audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})
        s,c,e,p,t,m,_=deepcopy(self.full);next(v for v in e if v['event']=='STEP_COMPLETE')['executed_action_oracle'][0]*=-1
        with self.assertRaises(ValueError):audit.audit_case(s,c,e,p,t,m,{'counts':{},'by_phase':{}})
