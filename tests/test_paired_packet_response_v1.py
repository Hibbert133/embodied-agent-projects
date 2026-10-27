"""Arrays, synthetic records and a callback-only command source; no Env operations."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
from time import perf_counter_ns
import unittest
from unittest.mock import patch
import numpy as np
from src.probe import paired_packet_query_v1 as query,paired_packet_model_v1 as model,paired_packet_program_v1 as actor
from src.analysis import paired_packet_io_v1 as allocation,paired_packet_training_v1 as training,paired_packet_independent_math_v1 as independent
from src.analysis import paired_packet_evaluation_v1 as evaluation,paired_packet_statistics_audit_v1 as statistics,paired_packet_record_audit_v1 as records
from src.analysis import paired_packet_host_v1 as host
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation


def state(x=0.):
    o=[0.]*39;o[:3]=[x,.7,.3];o[4:7]=[.25,.85,.05]
    return dict(observation=o,success=False,terminated=False,truncated=False)


def fixture():
    rows=[dict(at_calls=i,before=state(i*.0001),command=[0.]*4,after=state((i+1)*.0001)) for i in range(24)]
    return query.make('push-v3',24,'IN_TASK',rows[-1]['after'],rows,[0.,0.],allocation.packets(allocation.population('SOFTWARE')[0]))


def bank():
    saved=lambda d:dict(scale=[1.]*d,coef=np.zeros((d,2)).tolist())
    return dict(protocol='PAIRED_PACKET_MODELS_V1',by_task={t:dict(INSTANT=saved(2),FIR=saved(32),CENTERED_FIR=saved(32),FREE_CAUSAL=[saved(2*h) for h in range(1,17)]) for t in allocation.io.TASKS})


def synthetic_families():
    result=[];rng=np.random.default_rng(91827);kernels=np.zeros((16,2,2));kernels[0]=[[.1,.03],[-.02,.08]];kernels[1]=[[.04,0.],[0.,.02]]
    for group in range(9):
        for j in range(2):
            plus=np.zeros((16,4),np.float32);plus[:,:2]=rng.choice([-.4,.4],(16,2));packets=dict(ZERO=np.zeros_like(plus).tolist(),PLUS=plus.tolist(),MINUS=(-plus).tolist());positions={}
            for role in query.ROLES:
                u=np.asarray(packets[role]);positions[role]=[(np.array([.2,.7])+.01*sum((u[:h-lag,:2].sum(axis=0)@kernels[lag] for lag in range(h)),np.zeros(2))).tolist() for h in range(1,17)]
            q=fixture();q['packets']=packets
            result.append(dict(group=group,task='push-v3',complete_three_role_H16=True,query=q,packet_positions_xy=positions))
    return result


class PacketQueryTests(unittest.TestCase):
    def test_actual_chronological_history_is_preserved(self):
        q=fixture();self.assertEqual(query.validate(q),q);self.assertEqual([r['at_calls'] for r in q['history']],list(range(8,24)))
    def test_future_clock_or_missing_history_rejected(self):
        for mutation in ('future','missing'):
            q=fixture()
            if mutation=='future':q['history'][-1]['at_calls']+=1
            else:q['history']=q['history'][1:]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):query.validate(q)
    def test_terminal_history_rejected(self):
        q=fixture();q['history'][0]['before']['success']=True
        with self.assertRaises(ValueError):query.validate(q)
    def test_private_identity_and_future_response_fields_rejected(self):
        for key in ('seed','noise_oracle','fault','future_response','native_state'):
            q=fixture();q[key]=0
            with self.subTest(key=key),self.assertRaises(ValueError):query.validate(q)
    def test_nested_private_state_rejected(self):
        q=fixture();q['current']['oracle']=0
        with self.assertRaises(ValueError):query.validate(q)
    def test_discontinuous_history_is_not_zero_filled(self):
        q=fixture();q['history'][2]['before']['observation'][0]+=.01
        with self.assertRaises(ValueError):query.validate(q)
    def test_asymmetric_packet_rejected(self):
        q=fixture();q['packets']['MINUS'][0][0]=0.
        with self.assertRaises(ValueError):query.validate(q)
    def test_changed_grip_and_unbounded_commands_rejected(self):
        for axis in (0,3):
            q=fixture();q['packets']['PLUS'][0][axis]=2.
            with self.subTest(axis=axis),self.assertRaises(ValueError):query.validate(q)
    def test_unrepresentable_float32_history_command_rejected(self):
        q=fixture();q['history'][0]['command'][0]=.1
        with self.assertRaises(ValueError):query.validate(q)


class PacketMathTests(unittest.TestCase):
    def test_literal_and_main_causal_designs_agree(self):
        u=np.arange(32,dtype=float).reshape(16,2)/30
        for kind in independent.KINDS:
            for h in (1,2,8,16):np.testing.assert_allclose(model.design(u,h,kind),independent.row(u,h,kind),atol=2e-15)
    def test_later_known_inputs_cannot_affect_earlier_prediction(self):
        u=np.ones((16,2));v=u.copy();v[8:]*=100
        for kind in independent.KINDS:np.testing.assert_array_equal(model.design(u,8,kind),model.design(v,8,kind))
    def test_synthetic_two_lag_response_has_expected_units_and_memory(self):
        f=synthetic_families()[0];u=np.asarray(f['query']['packets']['PLUS'])[:,:2];k=np.zeros((32,2));k[:4]=[[.1,.03],[-.02,.08],[.04,0.],[0.,.02]]
        for h in (1,8,16):np.testing.assert_allclose(.01*model.design(u,h,'FIR')@k,np.asarray(f['packet_positions_xy']['PLUS'][h-1])-f['packet_positions_xy']['ZERO'][h-1],atol=1e-16)
    def test_weighted_fir_and_centered_fir_are_equivalent(self):
        data=synthetic_families();a=training.ridge(*training.arrays(data,'push-v3','FIR'));b=training.ridge(*training.arrays(data,'push-v3','CENTERED_FIR'))
        np.testing.assert_allclose(np.asarray(a['coef'])/np.asarray(a['scale'])[:,None],np.asarray(b['coef'])/np.asarray(b['scale'])[:,None],atol=1e-11)
    def test_augmented_lstsq_independently_reconstructs_ridge(self):
        data=synthetic_families();a=training.ridge(*training.arrays(data,'push-v3','FREE_CAUSAL',8));b=independent.refit(data,'push-v3','FREE_CAUSAL',8)
        np.testing.assert_allclose(a['coef'],b['coef'],atol=2e-11);np.testing.assert_allclose(a['scale'],b['scale'],atol=1e-15)
    def test_incomplete_families_cannot_be_silently_used_for_fit(self):
        data=synthetic_families()
        for f in data:
            if f['group']>=2:f['complete_three_role_H16']=False
        with self.assertRaises(ValueError):training.arrays(data,'push-v3','FIR')
    def test_known_bank_antisymmetry_cycle_and_compute_cost(self):
        q=fixture();b=bank()
        for task in b['by_task']:
            b['by_task'][task]['INSTANT']['coef']=[[.1,.02],[0.,.08]]
        counter={};p=model.predict(b,q,counter);literal=independent.evaluate(b,q)
        self.assertEqual(counter,dict(trajectories_started=15,zero_rows=48,linear_rows=192,trajectories_completed=15))
        for kind in model.METHODS:
            for pair in p[kind]:np.testing.assert_allclose(p[kind][pair],literal[kind][pair],atol=1e-15)
            z=np.asarray(p[kind]['ZERO__PLUS']);m=np.asarray(p[kind]['ZERO__MINUS']);d=np.asarray(p[kind]['PLUS__MINUS'])
            np.testing.assert_allclose(z,-m,atol=1e-15);np.testing.assert_allclose(z+d,m,atol=1e-15)
    def test_invalid_saved_parameters_fail_closed_with_partial_cost(self):
        b=bank();b['by_task']['push-v3']['INSTANT']['scale']=[0.,1.];counter={}
        with self.assertRaises(ValueError):model.predict(b,fixture(),counter)
        self.assertEqual(counter['trajectories_completed'],3);self.assertEqual(counter['linear_rows'],1)
    def test_model_bank_private_fields_rejected(self):
        b=bank();b['true_fault']=0
        with self.assertRaises(ValueError):model.predict(b,fixture())
    def test_endpoint_decimal_zero_cap_and_independent_reconstruction(self):
        for p,l,r in (([.01,0.],[.2,.3],[.21,.3]),([2.,0.],[0.,0.],[0.,0.]),([0.,0.],[0.,0.],[.003,.004])):
            self.assertEqual(evaluation.endpoint_nm(p,l,r),statistics.endpoint(p,l,r))
        self.assertEqual(evaluation.endpoint_nm([0.,0.],[0.,0.],[0.,0.]),0);self.assertEqual(evaluation.endpoint_nm([2.,0.],[0.,0.],[0.,0.]),10**9)
    def test_early_pair_missing_endpoints_keep_full_denominator(self):
        q=fixture();rec=dict(forecast_error=None,forecasts=model.predict(bank(),q));f=dict(family_index=0,group=0,task='push-v3',context='UNCHANGED',boundary=16,acquisition_action='IN_TASK',
            saved_forecast=rec,packet_lengths=dict(ZERO=16,PLUS=7,MINUS=16),packet_positions_xy=dict(ZERO=[[0.,0.]]*16,PLUS=[[0.,0.]]*7,MINUS=[[0.,0.]]*16))
        rows=evaluation.scores([f]);self.assertEqual(len(rows),30);self.assertEqual(sum(r['availability']=='SHORT_OR_TERMINAL_PAIR' for r in rows),20);self.assertEqual(sum(r['loss_nm'] for r in rows),20*10**9)
    def test_absent_entry_has_no_invented_zero_loss(self):
        f=dict(family_index=0,group=0,task='push-v3',context='UNCHANGED',boundary=16,acquisition_action='MOVE',saved_forecast=None,packet_lengths=dict.fromkeys(query.ROLES,0),packet_positions_xy=dict.fromkeys(query.ROLES,[]))
        self.assertTrue(all(r['loss_nm']==10**9 and r['availability']=='ENTRY_UNAVAILABLE' for r in evaluation.scores([f])))
    def test_actuator_order_noise_cursor_and_mapping_mismatches_are_detectable(self):
        fault=dict(matrix_xy=[[1.2,.1],[0.,.8]],bias_xy=[.2,-.1],deadzone_xy=[0.,0.]);u=[1.,0.,0.,0.];noise=np.array([-.3,.02,.04],np.float32)
        correct=applied(u,fault,noise);wrong=np.clip(np.clip(np.array([1.4,-.1,0.,0.],np.float32),-1,1)+np.r_[noise,np.float32(0)],-1,1).tolist()
        self.assertNotEqual(correct,wrong);self.assertNotEqual(correct,applied(u,fault,np.zeros(3,np.float32)))
        inverse=dict(fault,matrix_xy=np.linalg.inv(fault['matrix_xy']).tolist());self.assertNotEqual(correct,applied(u,inverse,noise))
    def test_lifecycle_population_caps_include_factory_reset_cost(self):
        limits=allocation.config()['combined_limits'];self.assertEqual(limits['executions'],864);self.assertEqual(limits['control_steps'],80640);self.assertEqual(limits['all_resets'],44064);self.assertEqual(limits['physical_frames'],22435200)


def callback_run(end_at=None,action='IN_TASK',mutate=False):
    current=StepObservation(**state());events=[];steps=[];forecasts=[];total=0
    spec=next(s for s in allocation.population('SOFTWARE') if s['acquisition_action']==action);packets=allocation.packets(spec)
    def emit(kind,payload):
        value=normalize(payload)|dict(sequence=len(events),saved_ns=perf_counter_ns());events.append((kind,deepcopy(value)));return value
    def step(saved):
        nonlocal current,total
        if mutate:saved['command'][0]=.9
        total+=1;d=asdict(current);d['observation']=list(d['observation']);d['observation'][:3]=(np.array(d['observation'][:3])+.01*np.asarray(saved['command'])[:3]).tolist();d['success']=total==end_at;current=StepObservation(**d);steps.append(deepcopy(saved));return StepReceipt(current,total)
    def forecast(request):forecasts.append(total);return dict(test_saved=True)
    result=actor.run('push-v3',current,16,action,packets['PLUS'],packets,lambda obs:np.zeros(4,np.float32),step,emit,forecast)
    return result,events,steps,forecasts


class PacketActorTests(unittest.TestCase):
    def test_saved_known_commands_drive_real_callback_order(self):
        result,events,steps,forecasts=callback_run();self.assertEqual(forecasts,[24]);self.assertEqual(result['packet_steps'],16);self.assertEqual(result['total_steps'],40)
        forecast=next(p for k,p in events if k=='FORECAST_RESULT');packet=[s for s in steps if s['phase']=='EXOGENOUS_PACKET'];self.assertTrue(all(s['sequence']>forecast['sequence'] for s in packet))
        expected=allocation.packets(allocation.population('SOFTWARE')[0])['PLUS'];self.assertEqual([s['command'] for s in packet],expected)
    def test_ended_before_boundary_is_retained_without_forecast(self):
        r,_,_,f=callback_run(end_at=4);self.assertEqual(r['reason'],'ENDED_BEFORE_BOUNDARY');self.assertEqual(r['total_steps'],4);self.assertEqual(f,[])
    def test_ended_common_measure_is_not_complete_packet(self):
        r,_,_,f=callback_run(end_at=20);self.assertEqual(r['reason'],'ENDED_DURING_COMMON_MEASURE');self.assertEqual(r['common_measure_steps'],4);self.assertEqual(f,[])
    def test_short_packet_stops_at_actual_terminal_state(self):
        r,_,steps,f=callback_run(end_at=27);self.assertEqual(r['packet_steps'],3);self.assertEqual(len(steps),27);self.assertEqual(f,[24]);self.assertFalse(r['complete_packet'])
    def test_step_cannot_change_saved_command(self):
        with self.assertRaises(ValueError):callback_run(mutate=True)
    def test_independent_query_rejects_missing_early_history(self):
        with self.assertRaises(ValueError):records.independent_query(allocation.population('SOFTWARE')[0],state(),[],[0.,0.])
    def test_actual_prefix_difference_is_rejected(self):
        l=[dict(command=[0.]*4,raw_policy=None,after=state(),executed_action_oracle=[0.]*4,simulation_time_before=0.,simulation_time_after=.0125,noise_cursor_after=1)];r=deepcopy(l);r[0]['executed_action_oracle'][0]=.1
        with self.assertRaises(ValueError):records.compare_prefix(l,r,1)


def synthetic_host_case(spec,family_cache,models=None,model_sha=None):
    """Synthetic arrays behind callbacks; no environment constructor/reset/step."""
    from src.analysis.paired_probe_host_v1 import ProbeSession
    from src.rollout.task_registry import create_task_policy
    events=[];private=[];counts=dict(counts={},by_phase={})
    def emit(kind,payload):
        value=normalize(dict(event=kind,sequence=len(events),saved_ns=perf_counter_ns(),**payload));events.append(value);return value
    def priv(kind,payload):
        value=normalize(dict(event=kind,sequence=len(private),saved_ns=perf_counter_ns(),**payload));private.append(value);return value
    emit('CASE_ALLOCATION',dict(assignment='FROZEN_PAIRED_KNOWN_PACKET',preallocated_packets=allocation.packets(spec),model_sha256=model_sha))
    emit('FACTORY_INTENT',dict(ledger=deepcopy(counts)))
    for phase in ['GOAL_GENERATION']*50+['CONTROLLED_RESET']:
        if phase=='CONTROLLED_RESET':emit('FACTORY_COMPLETE',dict(ledger=deepcopy(counts)))
        intent=emit('LIFECYCLE_RESET_INTENT',dict(phase=phase,before=deepcopy(counts)));counts=ledger_add(counts,phase,'reset_attempts',1);counts=simulation(counts,phase,100,500);counts=ledger_add(counts,phase,'reset_completed',1)
        emit('LIFECYCLE_RESET_COMPLETE',dict(phase=phase,intent_sequence=intent['sequence'],after=deepcopy(counts)))
    class ArraySession:
        public=ProbeSession.public;alive=ProbeSession.alive;policy_query=ProbeSession.policy_query;_agent_emit=ProbeSession._agent_emit;_agent_step=ProbeSession._agent_step
        def witness(self):
            return dict(native_sha256=allocation.io.digest(self.env.unwrapped.data.mocap_pos.tolist()),python_semantic_sha256=allocation.io.digest(normalize(self.ctx)),
                noise_past_sha256=allocation.io.digest(self.ctx['noise_rows'][:self.ctx['calls']].tolist()),simulation_time=self.env.unwrapped.data.time)
        def _step(self,command,phase,raw,global_command):
            n=self.ctx['calls'];before=deepcopy(counts);b=self.env.unwrapped;intent=emit('STEP_INTENT',dict(logical_step=n,global_command_sequence=global_command,phase=phase,command=command,ledger_before=before))
            started=perf_counter_ns();oldtime=b.data.time;action=applied(command,self.fault,self.ctx['noise_rows'][n]);b.data.mocap_pos[0]=records.target(b.data.mocap_pos[0],action)['target'];b.data.time+=.0125
            self.ctx['calls']+=1;self.ctx['observation'][:3]=b.data.mocap_pos[0];self.run_budget['completed']+=1;self.ledger.value=simulation(self.ledger.value,'CONTROL',1,5)
            row=normalize(dict(logical_step=n,phase=phase,command=command,raw_policy=raw,executed_action_oracle=action,after=asdict(self.public()),info=dict(success=False),reward=0.,
                simulation_time_before=oldtime,simulation_time_after=b.data.time,noise_cursor_after=n+1,intent_sequence=intent['sequence'],global_command_sequence=global_command,
                execution_started_ns=started,completed_ns=perf_counter_ns(),ledger_before=before,ledger_after=self.ledger.snapshot()))
            counts.clear();counts.update(deepcopy(self.ledger.value));emit('STEP_COMPLETE',row);return self.public()
    class ArrayLedger:
        def __init__(self,value):self.value=deepcopy(value)
        @property
        def counts(self):return self.value['counts']
        def snapshot(self):return deepcopy(self.value)
    s=ArraySession();s.env=SimpleNamespace(unwrapped=SimpleNamespace(model=SimpleNamespace(_address=10),data=SimpleNamespace(_address=20,mocap_pos=np.array([[0.,.6,.2]]),mocap_quat=np.array([[1.,0.,1.,0.]]),time=0.),
        action_scale=.01,mocap_low=np.array([-.5,.4,.05]),mocap_high=np.array([.5,1.,.5])))
    s.policy=create_task_policy(spec['task']);s.task=spec['task'];s.ctx=dict(observation=np.asarray(state()['observation']),terminated=False,truncated=False,success=False,calls=0,noise_rows=allocation.noise(spec))
    s.fault=allocation.initial_fault(spec);s.emit=emit;s.ledger=ArrayLedger(counts);s.run_budget=dict(completed=0,maximum=allocation.case_cap(spec));s.captures=s.restores=s.policy_queries=0;s._snapshots={};s._pending=None;s._local=0;s._map={};s.choice_refs=[];s.branch={}
    initial=normalize(asdict(s.public()));emit('CONTROLLED_INITIAL',dict(ledger=deepcopy(counts),task=spec['task'],observation=initial['observation'],simulation_time=0.));emit('NOISE_COMMITMENT',dict(at_calls=0,tape_sha256_oracle=allocation.io.digest(s.ctx['noise_rows'].tolist())))
    with patch.object(host,'paired_witness',lambda s:(s.witness(),s.witness()['python_semantic_sha256'])):
        result,public=host.run_live(spec,s,emit,priv,lambda:{k:events[-1][k] for k in ('sequence','saved_ns')},lambda:None,family_cache,models,model_sha)
    case={**spec,**result,'initial':initial,'completed':True,'environment_closed':True,'error':None,'close_error':None,'captures':0,'restores':0,
        'ledger_before':dict(counts={},by_phase={}), 'ledger_before_close':s.ledger.snapshot(),'ledger_after_close':s.ledger.snapshot(),
        'initial_fault_oracle':allocation.initial_fault(spec),'destination_oracle':allocation.destination(spec),'preallocated_packets':allocation.packets(spec),
        'public_trajectory_sha256':allocation.io.digest(public)}
    return case,events,private,public


class HostRecordTests(unittest.TestCase):
    def test_pair_projection_excludes_only_registered_timer_without_mutation(self):
        value=dict(layers=[dict(episode_start_time=1.,episode_length=7)],context=dict(noise_cursor=7),numpy_global=[1,2]);copy=deepcopy(value)
        projected,omitted=host.without_episode_wall_clock(value,['gymnasium.wrappers.common.RecordEpisodeStatistics']);other=deepcopy(value);other['layers'][0]['episode_start_time']=2.
        self.assertEqual(host.without_episode_wall_clock(other,['gymnasium.wrappers.common.RecordEpisodeStatistics'])[0],projected);self.assertEqual(value,copy);self.assertEqual(omitted[0]['field'],'episode_start_time')
        other['context']['noise_cursor']=8;self.assertNotEqual(host.without_episode_wall_clock(other,['gymnasium.wrappers.common.RecordEpisodeStatistics'])[0],projected)
    def test_unknown_timer_wrapper_cannot_be_silently_excluded(self):
        with self.assertRaises(ValueError):host.without_episode_wall_clock(dict(layers=[dict(episode_start_time=1.)]),['unknown.wrapper'])
    def test_synthetic_pi_pid_and_saved_memory_for_all_tasks_and_anchors(self):
        for task in allocation.io.TASKS:
            for action in ('IN_TASK','MOVE'):
                spec=next(s for s in allocation.population('SOFTWARE') if s['task']==task and s['acquisition_action']==action)
                with self.subTest(task=task,action=action):
                    c,e,p,x=synthetic_host_case(spec,{});row,_,_,_,_=records.audit_case(spec,c,e,p,x,dict(counts={},by_phase={}))
                    self.assertTrue(row['native_target_updates_bit_exact']);self.assertLessEqual(row['total_steps'],allocation.case_cap(spec))
    def test_synthetic_host_and_literal_record_audit_agree(self):
        spec=allocation.population('SOFTWARE')[0];cache={};c,e,p,x=synthetic_host_case(spec,cache)
        summary,_,_,_,_=records.audit_case(spec,c,e,p,x,dict(counts={},by_phase={}))
        self.assertTrue(summary['native_target_updates_bit_exact']);self.assertEqual(summary['packet_steps'],16)
    def test_only_canonical_entry_computes_and_siblings_use_saved_forecast(self):
        specs=allocation.population('CAL')[:3];cache={};models=bank();trio=[synthetic_host_case(s,cache,models,'saved_model_sha') for s in specs]
        self.assertEqual(trio[0][0]['forecast_record']['model_compute_counts']['linear_rows'],192)
        self.assertEqual(trio[1][0]['forecast_record']['model_compute_counts'],{});self.assertEqual(trio[1][0]['forecast_record']['compute_wall_ns'],0)
        self.assertEqual(trio[0][0]['entry_witness_oracle'],trio[2][0]['entry_witness_oracle'])
        for spec,(c,e,p,x) in zip(specs,trio):records.audit_case(spec,c,e,p,x,dict(counts={},by_phase={}),models,'saved_model_sha')
    def test_independent_record_audit_detects_corrupted_noise_cursor(self):
        spec=allocation.population('SOFTWARE')[0];c,e,p,x=synthetic_host_case(spec,{})
        next(v for v in e if v['event']=='STEP_COMPLETE')['noise_cursor_after']+=1
        with self.assertRaises(ValueError):records.audit_case(spec,c,e,p,x,dict(counts={},by_phase={}))
    def test_mismatched_cached_entry_is_rejected_before_packet_response(self):
        specs=allocation.population('SOFTWARE')[:2];cache={};synthetic_host_case(specs[0],cache);cache[allocation.family_key(specs[0])]['query']['current']['observation'][0]+=.01
        with self.assertRaises(ValueError):synthetic_host_case(specs[1],cache)


if __name__=='__main__':unittest.main()
