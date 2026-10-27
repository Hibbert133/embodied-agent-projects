"""Collector/model support contracts; constructed public arrays only."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
import tempfile,gzip,json
import numpy as np
from src.probe import graybox_packet_query_v1 as query
from src.probe import graybox_arx_reference_v1 as arx
from src.probe.graybox_observer_v1 import digest
from tests.test_graybox_observer_v1 import trace,commands
from src.analysis import graybox_response_training_v1 as training,graybox_response_training_audit_v1 as training_audit
from src.analysis import graybox_response_independent_v1 as independent,graybox_response_io_v1 as allocation,graybox_response_evaluation_v1 as evaluation
from src.probe import graybox_response_model_v1 as models

def fixture(n=24):
    t=trace(n)
    def state(xy):return dict(observation=list(xy)+[.25]+[0.]*36,success=False,terminated=False,truncated=False)
    initial=state(t['initial_xy']);current=initial;history=[]
    for r in t['steps']:
        after=state(r['after_xy']);history.append(dict(at_calls=r['at_calls'],before=deepcopy(current),command=r['command'],after=after));current=after
    plus=commands(16);minus=[[-u[0],-u[1],0.,0.] for u in plus]
    return query.make('push-v3',n,'IN_TASK',initial,current,history,[0.,0.],dict(ZERO=[[0.]*4 for _ in range(16)],PLUS=plus,MINUS=minus))

class GrayboxResponse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.bank=arx.fit([trace(80)])
    def test_complete_history_keeps_real_initial_observation(self):
        q=fixture();t=query.nominal_trace(q)
        self.assertEqual(t['initial_xy'],[0.,.6]);self.assertEqual(len(t['steps']),24);self.assertEqual(t['steps'][0]['at_calls'],0)
    def test_missing_initial_history_is_rejected(self):
        q=fixture();q['history']=q['history'][8:]
        with self.assertRaises(ValueError):query.validate(q)
    def test_future_or_private_data_is_rejected(self):
        for key in ('seed','executed_action_oracle','actual_noise','future_response'):
            q=fixture();q[key]=0
            with self.subTest(key=key),self.assertRaises(ValueError):query.validate(q)
    def test_initial_and_final_history_boundary_must_match(self):
        for field in ('initial','current'):
            q=fixture();q[field]['observation'][0]+=.01
            with self.subTest(field=field),self.assertRaises(ValueError):query.validate(q)
    def test_unchanged_reference_projection_is_exact_last16(self):
        q=fixture();p=query.project_last16(q)
        self.assertEqual(p['history'],q['history'][-16:]);self.assertEqual(p['current'],q['current']);self.assertNotIn('initial',p)
    def test_no_post_terminal_or_unbounded_packet(self):
        q=fixture();q['history'][4]['after']['terminated']=True
        with self.assertRaises(ValueError):query.validate(q)
        q=fixture();q['packets']['PLUS'][0][0]=2.
        with self.assertRaises(ValueError):query.validate(q)
    def test_working_graybox_mean_has_linear_arx2_realization(self):
        t=trace(80);positions=[t['initial_xy']]+[r['after_xy'] for r in t['steps']];cmd=[r['command'] for r in t['steps']]
        coef=np.zeros((9,2));rho=.5;beta=.1;coef[:2,:]=beta*np.eye(2);coef[4:6,:]=(1+rho-beta)*np.eye(2);coef[6:8,:]=-rho*np.eye(2)
        for i in range(2,80):np.testing.assert_allclose(arx.features(positions,cmd,i)@coef,(np.array(positions[i+1])-positions[i])/.01,atol=2e-14)
    def test_arx2_realization_includes_forward_cross_axis_transform_and_bias(self):
        a=np.array([[.8,.2],[-.1,1.1]]);b=np.array([.1,-.08]);rho=.5;beta=.1
        cmd=commands(50);target=np.array([0.,.6]);position=target.copy();velocity=np.zeros(2);positions=[position.copy()]
        for u in cmd:
            target=target+.01*(a@np.array(u[:2])+b);velocity=rho*velocity+beta*(target-position);position=position+velocity;positions.append(position.copy())
        coef=np.zeros((9,2));coef[:2]=beta*a.T;coef[4:6]=(1+rho-beta)*np.eye(2);coef[6:8]=-rho*np.eye(2);coef[-1]=beta*b
        for i in range(2,50):np.testing.assert_allclose(arx.features(positions,cmd,i)@coef,(positions[i+1]-positions[i])/.01,atol=3e-14)
    def test_arx_forecast_uses_all_actual_history_without_changing_bank(self):
        q=fixture();before=digest(self.bank);ledger={};out=arx.forecast(self.bank,query.nominal_trace(q),q['packets'],ledger)
        self.assertEqual(before,digest(self.bank));self.assertEqual(ledger['rls_updates'],22);self.assertEqual(ledger['rls_forecast_steps'],48)
        self.assertEqual(np.array(out['PLUS']).shape,(16,2));self.assertGreater(np.linalg.norm(np.array(out['PLUS'])-out['MINUS']),.001)
    def test_arx_does_not_invent_two_earliest_displacements(self):
        with self.assertRaises(ValueError):arx.features([[0.,0.],[1.,1.]],[[0.]*4]*2,1)
        with self.assertRaises(ValueError):arx.fit([trace(2)])
    def test_arx_bank_rejects_truth_and_invalid_covariance(self):
        b=dict(self.bank,oracle=0)
        with self.assertRaises(ValueError):arx.validate(b)
        b=deepcopy(self.bank);b['covariance'][0][0]=-1.
        with self.assertRaises(ValueError):arx.validate(b)

def training_fixture():
    nominal=[];families=[]
    for task in ('push-v3','reach-v3','door-open-v3'):
        for g in range(9):
            n=40 if g<6 else g-6
            t=trace(n) if n else dict(initial_xy=[0.,.6],steps=[]);nominal.append(dict(group=g,task=task,trace=t))
            for context in ('UNCHANGED','CHANGED'):
                for action in ('IN_TASK','MOVE'):
                    q=fixture();q['task']=task;q['acquisition_action']=action;positions={}
                    for role in ('ZERO','PLUS','MINUS'):
                        cumulative=np.cumsum(np.array(q['packets'][role])[:,:2],axis=0)*.008
                        positions[role]=(np.array(q['current']['observation'][:2])+cumulative).tolist()
                    families.append(dict(family_index=len(families),group=g,task=task,context=context,boundary=(16,32,64)[g%3],acquisition_action=action,query=q,
                        packet_positions_xy=positions,packet_lengths={r:16 for r in positions},complete_three_role_H16=True,reasons={r:'PACKET_COMPLETE' for r in positions},saved_forecast=None))
    return nominal,families

class GrayboxLearningContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nominal,cls.families=training_fixture();cls.count={};cls.bank,cls.metadata=training.fit_data(cls.nominal,cls.families,counter=cls.count)
    def test_training_all_tasks_and_counted_sources(self):
        self.assertEqual(set(self.bank['by_task']),{'push-v3','reach-v3','door-open-v3'});self.assertEqual(self.count['ridge_solve_attempts'],9);self.assertEqual(self.count['nominal_grid_candidate_evaluations'],27)
        for value in self.metadata.values():self.assertEqual(value['zero_length_source_groups'],[6]);self.assertEqual(value['RLS_short_history_source_groups'],[6,7,8])
    def test_separate_nominal_grid_matches_all_nonempty_and_short_sources(self):
        traces=[r['trace'] for r in self.nominal if r['task']=='push-v3' and r['trace']['steps']];counter={}
        expected=independent.nominal_scores(traces,counter)
        np.testing.assert_allclose(expected,self.metadata['push-v3']['per_candidate_per_axis_nll'],atol=1e-6,rtol=2e-8)
        self.assertEqual(counter['independent_nominal_grid_passes'],9)
    def test_independent_augmented_fits_for_every_task(self):
        for task in self.bank['by_task']:
            traces=[r['trace'] for r in self.nominal if r['task']==task];expected=training_audit.rls_fit(traces);saved=self.bank['by_task'][task]['RLS_ARX']
            for field in expected:np.testing.assert_allclose(expected[field],saved[field],atol=2e-7,rtol=2e-8)
            for kind in ('INSTANT','FIR'):
                expected=independent.augmented_linear(*training_audit.linear_data(self.families,task,kind));saved=self.bank['by_task'][task][kind]
                for field in expected:np.testing.assert_allclose(expected[field],saved[field],atol=2e-7,rtol=2e-8)
    def test_cal_forecast_matches_separate_scalar_and_batch_reconstruction(self):
        q=fixture();actual,errors=models.predict(self.bank,q);expected,other_errors=independent.evaluate(self.bank,q)
        self.assertEqual(errors,{});self.assertEqual(other_errors,{});self.assertEqual(len(actual),8)
        for name in actual:
            for pair in actual[name]:np.testing.assert_allclose(actual[name][pair],expected[name][pair],atol=2e-8,rtol=2e-7)
    def test_qual_uses_only_locked_process_choice(self):
        q=fixture();cal,_=models.predict(self.bank,q);bank=deepcopy(self.bank);bank['selected_q_index']=1;qual,errors=models.predict(bank,q)
        self.assertEqual(errors,{});self.assertEqual(len(qual),6);self.assertEqual(qual['GRAY_JOINT'],cal['GRAY_Q1']);self.assertNotIn('GRAY_Q0',qual)
    def test_partial_model_failure_never_substitutes_a_baseline(self):
        bank=deepcopy(self.bank);bank['by_task']['push-v3']['RLS_ARX']['coef'][0][0]=float('nan');pred,errors=models.predict(bank,fixture())
        self.assertEqual(set(errors),{'RLS_ARX'});self.assertNotIn('RLS_ARX',pred);self.assertIn('GRAY_FIXED',pred)
    def test_calibration_is_exact_equal_group_with_stable_ties(self):
        rows=[]
        for g in range(3):
            rows.extend(dict(method='GRAY_Q0',group=g,loss_nm=9 if g==0 else 0) for _ in range(1 if g==0 else 9))
            rows.append(dict(method='GRAY_Q1',group=g,loss_nm=2));rows.append(dict(method='GRAY_Q2',group=g,loss_nm=3))
        index,scores=evaluation.choose_q(rows);self.assertEqual(index,1);self.assertEqual(scores[0]['numerator'],3)
        for r in rows:r['loss_nm']=1
        self.assertEqual(evaluation.choose_q(rows)[0],0)
    def test_unavailable_population_remains_in_denominator(self):
        family=deepcopy(self.families[0]);family['saved_forecast']=None;family['packet_lengths']={r:0 for r in ('ZERO','PLUS','MINUS')}
        scores=evaluation.scores([family],['ZERO','GRAY_JOINT']);self.assertEqual(len(scores),12);self.assertTrue(all(r['loss_nm']==10**9 and r['availability']=='ENTRY_UNAVAILABLE' for r in scores))
    def test_declared_cost_caps_reconstructed_by_literal_enumeration(self):
        n=steps=0
        for split,groups in (('SOFTWARE',3),('NOMINAL',9),('TRAIN',9),('CAL',3),('QUAL',9)):
            pop=allocation.population(split);n+=len(pop)
            if split=='NOMINAL':self.assertEqual(len(pop),27);steps+=27*80
            else:
                self.assertEqual(len(pop),groups*36)
                steps+=sum(((16,32,64)[g%3]+24+(64 if anchor=='MOVE' else 0))*18 for g in range(groups) for anchor in ('IN_TASK','MOVE'))
        self.assertEqual((n,steps),(891,82800));self.assertEqual(n*51,45441);self.assertEqual(n*25500+5*steps,23134500)
        self.assertEqual(allocation.config()['combined_limits']['control_steps'],steps)

class NominalHostContracts(unittest.TestCase):
    def fake(self,stop=None):
        from src.probe.continuous import StepObservation
        class Session:
            def __init__(self):
                data=SimpleNamespace(_address=2,time=0.,mocap_pos=np.array([[0.,.6,.2]]));base=SimpleNamespace(model=SimpleNamespace(_address=1),data=data,action_scale=.01,mocap_low=np.array([-.5,.4,.05]),mocap_high=np.array([.5,1.,.5]))
                self.env=SimpleNamespace(unwrapped=base);self.ctx=dict(calls=0,noise_rows=np.zeros((500,3),np.float32));self.run_budget={'completed':0};self.ledger=SimpleNamespace(counts=dict(simulation_frames_completed=0,reset_attempts=0))
                self.captures=self.restores=self.policy_queries=0;self._snapshots={};self._pending=None;self.local=0;self.obs=[0.,.6,.2]+[0.]*36
            def public(self):return StepObservation(tuple(self.obs),bool(stop is not None and self.ctx['calls']>=stop),False,False)
            def alive(self):return not self.public().success
            def _agent_emit(self,kind,payload):
                ack=deepcopy(payload)|dict(sequence=self.local,saved_ns=self.local+1);self.local+=1
                if kind=='COMMAND':self._pending=deepcopy(ack)
                return ack
            def _agent_step(self,saved):
                assert saved==self._pending;self._pending=None;self.ctx['calls']+=1;self.run_budget['completed']+=1;self.ledger.counts['simulation_frames_completed']+=5;self.env.unwrapped.data.time+=.0125
                for j in range(2):self.obs[j]+=.001*saved['command'][j]
                return self.public()
            def policy_query(self,*args):raise AssertionError('Nominal qualification must not query a policy')
        return Session()
    def test_nominal_host_completes_without_a_fictional_zero_role(self):
        from src.analysis import graybox_response_host_v1 as host
        spec=allocation.population('NOMINAL')[0];s=self.fake();cache={}
        with patch.object(host,'native_values',lambda session,label,position:dict(label=label,at_calls=session.ctx['calls'])):
            result,public=host.run_live(spec,s,lambda *x:None,lambda *x:None,lambda:{},lambda:None,cache)
        self.assertEqual(result['total_steps'],80);self.assertEqual(result['policy_queries'],0);self.assertIsNone(result['forecast_record']);self.assertEqual(cache,{});self.assertEqual(len(public['steps']),80)
    def test_nominal_early_success_keeps_actual_short_length(self):
        from src.analysis import graybox_response_host_v1 as host
        spec=allocation.population('NOMINAL')[0];s=self.fake(stop=2)
        with patch.object(host,'native_values',lambda session,label,position:dict(label=label,at_calls=session.ctx['calls'])):
            result,public=host.run_live(spec,s,lambda *x:None,lambda *x:None,lambda:{},lambda:None,{})
        self.assertEqual(result['total_steps'],2);self.assertEqual(len(public['steps']),2);self.assertEqual(result['reason'],'NOMINAL_EARLY_END')

class GrayboxStageContracts(unittest.TestCase):
    def test_ordered_pipeline_has_nominal_and_independent_gates_before_qual(self):
        from scripts.run_graybox_response_pipeline_v1 import stages
        names=[n for n,_ in stages('unused-manifest')]
        self.assertEqual(names[:8],['SOFTWARE_collect','SOFTWARE_record_audit','NOMINAL_collect','NOMINAL_record_audit','TRAIN_collect','TRAIN_record_audit','train','training_audit'])
        self.assertEqual(names[8:13],['CAL_collect','CAL_record_audit','CAL_evaluate','CAL_statistics_audit','model_lock'])
        self.assertEqual(names[13:],['QUAL_collect','QUAL_record_audit','QUAL_evaluate','QUAL_statistics_audit'])
    def test_independent_audit_disables_production_prediction_and_readers(self):
        from scripts.run_graybox_response_v1 import production_disabled
        from src.probe import graybox_observer_v1 as observer
        with production_disabled():
            for fn in (models.predict,arx.forecast,arx.fit,observer.advance,observer.observe,observer.fit_nominal_grid,training.nominal,training.families,training.fit_data):
                with self.subTest(fn=fn),self.assertRaises(RuntimeError):fn()
    def test_no_offline_bank_fit_allowed_during_collection(self):
        from src.analysis.graybox_response_collect_v1 import no_fits
        receipt={}
        with no_fits(receipt):
            with self.assertRaises(RuntimeError):np.linalg.solve(np.eye(2),np.ones(2))
        self.assertEqual(receipt['attempted_fits'],1)
    def test_independent_query_rebuilds_real_initial_and_all_actual_history(self):
        from src.analysis.graybox_response_record_audit_v1 import independent_query
        q=fixture();spec=allocation.population('CAL')[0]
        rebuilt=independent_query(spec,q['initial'],q['history'],q['integral_carried_xy'])
        self.assertEqual(rebuilt['history'],q['history']);self.assertEqual(rebuilt['initial'],q['initial']);self.assertEqual(len(rebuilt['history']),24)
        with self.assertRaises(ValueError):independent_query(spec,q['initial'],q['history'][:2],[0.,0.])
    def test_nominal_literal_audit_rejects_mutated_saved_command(self):
        from src.analysis import graybox_response_host_v1 as host,graybox_response_record_audit_v1 as audit
        spec=allocation.population('NOMINAL')[0];s=NominalHostContracts().fake(stop=2);events=[];original=s._agent_emit
        def emit(kind,payload):
            ack=original(kind,payload);events.append(dict(agent_event=kind,public_payload=deepcopy(ack)));return ack
        s._agent_emit=emit
        with patch.object(host,'native_values',lambda *x:dict(dummy=True)):
            result,public=host.run_live(spec,s,lambda *x:None,lambda *x:None,lambda:{},lambda:None,{})
        result['final']=deepcopy(public['steps'][-1]['after'])
        self.assertEqual(audit.replay_nominal(spec,result,events,public['steps']),0)
        events[1]['public_payload']['command'][0]*=-1
        with self.assertRaises(ValueError):audit.replay_nominal(spec,result,events,public['steps'])
    def test_qual_model_digest_includes_locked_choice_and_leaves_training_intact(self):
        io=allocation.io
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);path=root/'manifest.json';(root/'training').mkdir();bank=dict(selected_q_index=None)
            io.write(root/'training/models.json',dict(bank=bank));io.write(root/'model_lock.json',dict(selected_q_index=2))
            actual,digest=allocation.phase_model(path,'QUAL');self.assertEqual(actual,dict(selected_q_index=2));self.assertEqual(digest,io.digest(actual))
            self.assertEqual(io.read(root/'training/models.json')['bank'],bank)
    def test_lock_rejects_invalid_cal_and_any_qual_attempt(self):
        io=allocation.io
        with tempfile.TemporaryDirectory() as name,patch.object(allocation,'checked',return_value={}):
            root=Path(name);path=root/'manifest.json';(root/'cal_evaluation').mkdir()
            io.write(root/'cal_evaluation/audit.json',dict(integrity='PASSED'));io.write(root/'cal_evaluation/result.json',dict(invalid_forecasts=1))
            with self.assertRaises(ValueError):evaluation.lock(path)
            (root/'qual').mkdir()
            with self.assertRaises(ValueError):evaluation.lock(path)
            self.assertFalse((root/'model_lock.json').exists())

def write_gzip(path,rows):
    with gzip.open(path,'xt',encoding='utf8',newline='\n') as f:
        for row in rows:f.write(json.dumps(row,allow_nan=False)+'\n')

def saved_evaluation_fixture(root,split):
    """Constructed saved predictions/outcomes; not a native-collector witness."""
    _,data=training_fixture();data=[deepcopy(f) for f in data if split!='CAL' or f['group']<3]
    names=['ZERO','INSTANT','FIR','RLS_ARX','GRAY_FIXED']+(['GRAY_Q0','GRAY_Q1','GRAY_Q2'] if split=='CAL' else ['GRAY_JOINT'])
    cases=[];traces=[]
    for i,f in enumerate(data):
        f['family_index']=i;pred={}
        for j,method in enumerate(names):
            pred[method]={}
            for left,right in (('ZERO','PLUS'),('ZERO','MINUS'),('PLUS','MINUS')):
                actual=np.array(f['packet_positions_xy'][right])-f['packet_positions_xy'][left]
                pred[method][left+'__'+right]=(actual+.0001*(len(names)-j)).tolist()
        rec=dict(forecast_error=None,method_errors={},forecasts=pred)
        if i==0:rec=None;f['packet_lengths']={r:0 for r in allocation.ROLES};f['complete_three_role_H16']=False
        f['saved_forecast']=rec
        for role in allocation.ROLES:
            cases.append({k:f[k] for k in ('group','task','context','boundary','acquisition_action')}|dict(packet_kind=role,forecast_record=rec,packet_steps=f['packet_lengths'][role],entry_at_calls=None if rec is None else 0))
            traces.append(dict(steps=[dict(after=dict(observation=p+[.2]+[0.]*36)) for p in f['packet_positions_xy'][role][:f['packet_lengths'][role]]]))
    folder=root/split.lower();folder.mkdir();write_gzip(folder/'cases.jsonl.gz',cases);write_gzip(folder/'public_trajectories.jsonl.gz',traces)
    allocation.io.write(folder/'audit.json',dict(integrity='PASSED',invalid_forecasts=0));return data

class GrayboxSavedStatistics(unittest.TestCase):
    def test_both_saved_population_statistics_reconstruct_without_main_scoring(self):
        from scripts.run_graybox_response_v1 import audit_statistics
        io=allocation.io
        with tempfile.TemporaryDirectory() as name,patch.object(allocation,'checked',return_value={}):
            root=Path(name);path=root/'manifest.json';io.write(path,dict(manifest_id='CONSTRUCTED_NOT_SCIENCE'))
            for split in ('CAL','QUAL'):
                data=saved_evaluation_fixture(root,split);bank=dict(q_choices=[0.,.001,.01],selected_q_index=None if split=='CAL' else 2)
                with patch.object(allocation,'phase_model',return_value=(bank,'CONSTRUCTED')),patch.object(evaluation,'families',return_value=data):value=evaluation.evaluate_split(path,split)
                receipt=audit_statistics(path,split);self.assertEqual(receipt['integrity'],'PASSED')
                self.assertEqual(receipt['endpoint_rows'],len(data)*6*(8 if split=='CAL' else 6));self.assertEqual(value['allocated_families'],len(data))
                if split=='CAL':self.assertEqual(value['selected_q_index'],2)
                else:self.assertEqual(value['status'],'QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY')
    def test_short_and_per_method_failures_keep_distinct_reasons(self):
        _,data=training_fixture();f=deepcopy(data[0]);f['saved_forecast']=dict(forecast_error=None,method_errors={'FIR':dict(type='ValueError')},forecasts={'ZERO':{a+'__'+b:[[0.,0.]]*16 for a,b in evaluation.PAIRS}})
        f['packet_lengths']['PLUS']=7;rows=evaluation.scores([f],['ZERO','FIR'])
        self.assertEqual(sum(r['availability']=='INVALID_FORECAST' for r in rows),6)
        self.assertEqual(sum(r['availability']=='SHORT_OR_TERMINAL_PAIR' for r in rows),4)
        self.assertEqual(sum(r['availability']=='AVAILABLE' for r in rows),2)
    def test_both_training_readers_reconstruct_all_saved_sources_and_detect_mutation(self):
        nominal,paired=training_fixture();io=allocation.io
        def state(xy):return dict(observation=list(xy)+[.2]+[0.]*36,success=False,terminated=False,truncated=False)
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);path=root/'manifest.json'
            for split in ('NOMINAL','TRAIN'):
                folder=root/split.lower();folder.mkdir();cc=[];tt=[]
                for spec in allocation.population(split):
                    if split=='NOMINAL':
                        trace=next(r['trace'] for r in nominal if r['group']==spec['group'] and r['task']==spec['task']);initial=state(trace['initial_xy']);steps=[];current=initial
                        for r in trace['steps']:
                            after=state(r['after_xy']);steps.append(dict(at_calls=r['at_calls'],before=deepcopy(current),command=r['command'],after=after));current=after
                        case=dict(spec)
                    else:
                        f=next(f for f in paired if all(f[k]==spec[k] for k in ('group','task','context','acquisition_action')));q=f['query'];initial=q['initial'];steps=deepcopy(q['history']);current=q['current'];role=spec['packet_kind']
                        for u,p in zip(q['packets'][role],f['packet_positions_xy'][role]):
                            after=state(p);steps.append(dict(at_calls=len(steps),before=deepcopy(current),command=u,after=after));current=after
                        case=dict(spec,forecast_record={'query':q},entry_at_calls=24,packet_steps=16,reason='PACKET_COMPLETE',preallocated_packets=q['packets'])
                    public=dict(initial=initial,steps=steps);case['public_trajectory_sha256']=io.digest(public);cc.append(case);tt.append(public)
                write_gzip(folder/'cases.jsonl.gz',cc);write_gzip(folder/'public_trajectories.jsonl.gz',tt)
                io.write(folder/'audit.json',dict(integrity='PASSED',nominal_contract='PASSED',artifact_sha256={n:io.sha(folder/n) for n in ('cases.jsonl.gz','public_trajectories.jsonl.gz')}))
            main_n=training.nominal(path);main_f=training.training_family_export(training.families(path,'TRAIN'));other_n,other_f=training_audit.sources(path)
            self.assertEqual(main_n,other_n);self.assertEqual(main_f,other_f);self.assertEqual((len(main_n),len(main_f)),(27,108))
            with (root/'train/cases.jsonl.gz').open('ab') as f:f.write(b'x')
            with self.assertRaises(ValueError):training_audit.sources(path)
if __name__=='__main__':unittest.main()
