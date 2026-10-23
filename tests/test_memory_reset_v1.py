"""Synthetic/public-record tests only; no world, physical reset, fit or API."""
from copy import deepcopy
from contextlib import ExitStack
from dataclasses import asdict,replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe import relocation_reference_update_v1 as ref
from src.probe import memory_reset_program_v1 as actor
from src.analysis import memory_reset_io_v1 as allocation
from src.analysis.memory_reset_audit_v1 import independent_raw,replay,pid_numbers
from src.analysis.memory_reset_host_v1 import run_live
from src.analysis.memory_reset_statistics_v1 import compute,indices
from src.analysis.memory_reset_statistics_audit_v1 import independently_compute,same
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import controller_memory_transition_v1 as transition
from src.analysis.memory_reset_audit_v1 import reset_numbers
from src.analysis.memory_reset_seed_scope_v1 import inspect


def observation(success=False):
    o=[0.]*39;o[:3]=[.1,.8,.25];o[4:7]=[.8,0.,.05];return StepObservation(tuple(o),False,False,success)


def evidence(x=-.12,y=.08):return {'integral_xy':[x,y],'at_anchor':True,'controller':{'source':'RELOCATION_INTEGRAL_REFERENCE','matrix_xy':[[1.,0.],[0.,1.]],'offset':[x,y,0.,0.]},'parameter_estimate_qualified':False,'task_utility_demonstrated':False}


def fixture(program='LOCAL_PID_REFERENCE_RESET',end_at=120,fixed_policy=False,invalid_four=False):
    spec=next(s for s in allocation.population('QUAL') if s['task']=='push-v3' and s['context']=='UNCHANGED' and s['program']==program)
    current=observation();initial=current;events=[];steps=[];nominal=allocation.source_models()[0]['push-v3'] if actor.is_legacy(program) else None
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy('push-v3') if fixed_policy else None
    def emit(kind,payload):
        p={**normalize(payload),'sequence':len(events),'saved_ns':len(events)+1};events.append({'sequence':p['sequence'],'agent_event':kind,'public_payload':deepcopy(p)});return p
    def query(o):return policy.get_action(o) if fixed_policy else np.asarray([.2,-.1,.3,-1.],np.float32)
    def step(saved):
        nonlocal current
        n=len(steps)+1;o=list(current.observation)
        if saved['phase']=='REPOSITION':o[0]+=.001
        if saved['phase']=='WARM_PROBE':o[1]+=.0001
        current=StepObservation(tuple(o),False,False,end_at is not None and n>=end_at)
        steps.append({'logical_step':n-1,'command':saved['command'],'raw_policy':saved['raw_policy'],'phase':saved['phase'],'after':normalize(asdict(current)),
            'global_command_sequence':saved['sequence']});return StepReceipt(current,n)
    fit={'valid':True,'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'nfev':0}
    with ExitStack() as stack:
        stack.enter_context(patch('src.probe.task_passive_program_v1.infer_four',return_value={**fit,'valid':not invalid_four}))
        stack.enter_context(patch('src.probe.task_passive_program_v1.infer_operator',return_value=fit))
        r=actor.run('push-v3',initial,16,program,nominal,query,step,emit)
    case={**r['outcome'],'initial':normalize(asdict(initial))};return spec,case,events,steps,nominal


def statistics_rows():
    rows=[]
    for spec in allocation.population('QUAL'):
        p=spec['program'];loss=180 if p=='RAW_CONTINUE' else 220
        if p=='RAW_RESET_I':loss=150
        if p=='LOCAL_PID_KEEP':loss=160
        if p=='LOCAL_PID_REFERENCE_RESET':loss=140
        if p=='LOCAL_PID_REFERENCE_CARRY':loss=170
        if p=='LOCAL_PID_REFERENCE_RESET_NO_PROBE':loss=130
        loss+=spec['group'];window=p.startswith('LOCAL_PID') and not p.endswith('_NO_PROBE')
        rows.append({**spec,'deadline_loss':loss,'total_steps':loss,'success':True,'movement_steps':0 if p in ('RAW_CONTINUE','DIRECT_C8') else 20,
            'warm_probe_steps':8 if window else 0,'complete_warm_window':window,'reference_update_applied':'REFERENCE' in p,
            'c4_c8_fit_attempts':2 if actor.is_legacy(p) else 0,'memory_transition_applied':p in ('RAW_NOOP','RAW_RESET_I','LOCAL_PID_RESET_I'),'memory_nonzero_changed':p in ('RAW_RESET_I','LOCAL_PID_RESET_I')})
    return rows


class ArraySession:
    """Public receipt source only; this creates no simulator or native object."""
    def __init__(self,spec):
        self.current=observation();self.env=SimpleNamespace(unwrapped=SimpleNamespace(action_scale=.01,model=SimpleNamespace(_address=1),data=SimpleNamespace(_address=2,time=0.)))
        self.ctx={'calls':0,'initial_observation':np.array(self.current.observation),'commands':[],'observations':[],'noise_rows':allocation.noise(spec)}
        self.run_budget={'completed':0,'maximum':500};self.ledger=SimpleNamespace(counts={'simulation_frames_completed':0,'reset_attempts':1,'reset_completed':1,'reset_errors':0})
        self.attempts=self.completed=self.policy_queries=self.captures=self.restores=0;self.last_rows=[];self._snapshots={};self._pending=None;self.local=0;self.fault=allocation.initial_fault();self.clock_delta=.0125
    def public(self):return self.current
    def alive(self):return not self.current.success
    def witness(self):return {'logical_step':self.ctx['calls'],'time':self.env.unwrapped.data.time}
    def policy_query(self,o):self.policy_queries+=1;return np.array([.2,-.1,.3,-1.],np.float32)
    def emit(self,name,payload):return {'sequence':0,**payload}
    def _agent_emit(self,name,payload):
        p={'sequence':self.local,'saved_ns':self.local+1,**normalize(payload)};self.local+=1
        if name=='COMMAND':self._pending=deepcopy(p)
        return p
    def _agent_step(self,saved):
        assert self._pending==saved
        n=self.ctx['calls']+1;o=list(self.current.observation)
        if saved['phase']=='REPOSITION':o[0]+=.001
        if saved['phase']=='WARM_PROBE':o[1]+=.0001
        self.current=StepObservation(tuple(o),False,False,n>=120)
        self.ctx['calls']=n;self.attempts+=1;self.completed+=1;self.run_budget['completed']+=1;self.last_rows.append(saved)
        self.ledger.counts['simulation_frames_completed']+=5;self.env.unwrapped.data.time+=self.clock_delta
        if n<=8:self.ctx['commands'].append(np.array(saved['command'],np.float32));self.ctx['observations'].append(np.array(o))
        self._pending=None;return self.current


class MemoryResetTests(unittest.TestCase):
    def test_zero_integral_changes_only_memory_and_next_real_command(self):
        memory=replace(TaskMemory.initial('push-v3',observation()),completed_steps=16,integral_xy=(.25,-.2))
        left=TaskMemoryMachine(memory);right=TaskMemoryMachine(memory)
        plan=transition.propose(memory,mode='ZERO_INTEGRAL');receipt=transition.consume(right,plan)
        self.assertEqual(right.memory.current,memory.current);self.assertEqual(right.memory.completed_steps,16)
        self.assertEqual(right.memory.saved_controller,memory.saved_controller);self.assertEqual(right.memory.time_constant_s,.5)
        self.assertNotEqual(left.plan([.2,-.1,.3,-1.]),right.plan([.2,-.1,.3,-1.]))
        self.assertTrue(receipt['nonzero_integral_changed']);self.assertEqual(receipt['new_control_steps'],0)

    def test_noop_is_identity_but_saved_transition_is_consumed_only_once(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=16,integral_xy=(.2,.1))
        machine=TaskMemoryMachine(m);p=transition.propose(m,mode='NOOP');transition.consume(machine,p)
        self.assertEqual(machine.memory,m)
        with self.assertRaisesRegex(ValueError,'already consumed'):transition.consume(machine,p)

    def test_already_zero_reset_is_recorded_and_cannot_be_replayed(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=16);machine=TaskMemoryMachine(m)
        p=transition.propose(m,mode='ZERO_INTEGRAL');r=transition.consume(machine,p)
        self.assertFalse(r['nonzero_integral_changed'])
        with self.assertRaises(ValueError):transition.consume(machine,p)

    def test_unknown_private_or_future_plan_fields_rejected(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=16);p=transition.propose(m,mode='ZERO_INTEGRAL')
        for extra in ({'true_fault':[.1,.2]},{'seed':73000},{'future_success':True}):
            with self.assertRaises(ValueError):transition.consume(TaskMemoryMachine(m),{**p,**extra})

    def test_tampered_controller_gain_state_clock_or_integral_rejected(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=16)
        for field,value in (('time_constant_s',2.),('completed_steps',17),('integral_xy',[.1,0.]),('controller',{'source':'ORACLE'})):
            p=transition.propose(m,mode='ZERO_INTEGRAL');p['after_memory'][field]=value
            with self.assertRaises(ValueError):transition.consume(TaskMemoryMachine(m),p)

    def test_pending_or_suspended_memory_cannot_be_changed(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=16);p=transition.propose(m,mode='ZERO_INTEGRAL')
        for pending in (True,False):
            machine=TaskMemoryMachine(m)
            if pending:machine.plan([0.,0.,0.,-1.])
            else:machine.suspend()
            with self.assertRaises(ValueError):transition.consume(machine,p)

    def test_ended_or_exhausted_task_rejects_transition(self):
        for m in (replace(TaskMemory.initial('push-v3',observation()),completed_steps=500),TaskMemory.initial('push-v3',observation(True))):
            with self.assertRaises(ValueError):transition.propose(m,mode='ZERO_INTEGRAL')

    def test_independent_mapping_does_not_call_main_transition(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=16,integral_xy=(.1,-.3))
        plans={mode:transition.propose(m,mode=mode) for mode in ('NOOP','ZERO_INTEGRAL')}
        with patch.object(transition,'propose',side_effect=RuntimeError('disabled')):
            for mode,p in plans.items():self.assertEqual(normalize(p),reset_numbers(normalize(m.to_dict()),mode))


class ProgramTests(unittest.TestCase):
    def test_all_ten_programs_and_native_costs_are_frozen(self):
        self.assertEqual(len(actor.PROGRAMS),10);self.assertEqual(len(allocation.population('SOFTWARE_NATIVE')),90)
        self.assertEqual(len(allocation.population('QUAL')),540);self.assertEqual(allocation.config()['combined_limits']['all_resets'],32130)
        self.assertEqual(allocation.config()['combined_limits']['physical_frames'],17640000)
        self.assertEqual(allocation.limits('SOFTWARE_NATIVE')['c4_c8_fit_attempts'],0)

    def test_every_registered_program_executes_array_receipts(self):
        for name in actor.PROGRAMS:
            with self.subTest(program=name):
                s,c,e,t,n=fixture(name);self.assertEqual(c['total_steps'],len(t))
                if not actor.is_legacy(name):independent_raw(s,c,e,t)
                else:self.assertEqual(c['c4_c8_fit_attempts'],2)

    def test_noop_entire_command_policy_response_trace_matches_raw(self):
        a=fixture('RAW_CONTINUE');b=fixture('RAW_NOOP')
        for x,y in zip(a[3],b[3]):
            for k in ('command','raw_policy','phase','after'):self.assertEqual(x[k],y[k])
        self.assertEqual(a[1]['final_memory'],b[1]['final_memory']);self.assertTrue(b[1]['memory_transition_applied'])

    def test_direct_reset_changes_first_tail_command_without_movement(self):
        a=fixture('RAW_CONTINUE');b=fixture('RAW_RESET_I')
        self.assertEqual(a[3][:16],b[3][:16]);self.assertNotEqual(a[3][16]['command'],b[3][16]['command'])
        self.assertEqual(b[1]['movement_steps'],0);self.assertEqual(b[1]['warm_probe_steps'],0)

    def test_four_measured_local_branches_share_actual_acquisition_state(self):
        runs=[fixture(p) for p in ('LOCAL_PID_KEEP','LOCAL_PID_RESET_I','LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY')]
        ret=[next(e['public_payload'] for e in run[2] if e['agent_event']=='TASK_MEMORY_RETURN') for run in runs]
        self.assertEqual([p['at_calls'] for p in ret],[ret[0]['at_calls']]*4)
        for run in runs[1:]:
            for x,y in zip(runs[0][3][:ret[0]['at_calls']],run[3][:ret[0]['at_calls']]):
                self.assertEqual(x['command'],y['command']);self.assertEqual(x['after'],y['after'])
        self.assertTrue(runs[1][1]['memory_transition_applied']);self.assertFalse(runs[1][1]['reference_update_applied'])

    def test_early_success_before_boundary_keeps_denominator_and_missing_reason(self):
        for name in ('RAW_RESET_I','LOCAL_PID_RESET_I'):
            s,c,e,t,n=fixture(name,end_at=10);independent_raw(s,c,e,t)
            self.assertFalse(c['memory_transition_applied']);self.assertEqual(c['memory_transition_reason'],'EARLY_END_BEFORE_BOUNDARY')
            self.assertEqual((c['deadline_loss'],c['total_steps']),(10,10))

    def test_ended_acquisition_does_not_reset_memory_or_undo_movement(self):
        s,c,e,t,n=fixture('LOCAL_PID_RESET_I',end_at=20);independent_raw(s,c,e,t)
        self.assertEqual(c['total_steps'],20);self.assertFalse(c['memory_transition_applied'])
        self.assertEqual(c['memory_transition_reason'],'EARLY_END_DURING_ACQUISITION')

    def test_failed_anchor_keeps_actual_state_and_original_memory(self):
        from src.probe import acquisition_reference_operation_v1 as macro
        real=macro.acquire
        def failed(start,step,emit,**kw):
            result=real(start,step,emit,**kw);return {**result,'window':None,'reason':'ANCHOR_NOT_REACHED'}
        with patch.object(macro,'acquire',side_effect=failed):s,c,e,t,n=fixture('LOCAL_PID_RESET_I')
        self.assertFalse(c['memory_transition_applied']);self.assertEqual(c['memory_transition_reason'],'INCOMPLETE_ACQUISITION_KEEP')
        self.assertGreater(c['movement_steps'],0);self.assertEqual(c['total_steps'],120)

    def test_legacy_invalid_C4_remains_failed_with_full_cutoff_loss(self):
        _,c,_,t,_=fixture('DIRECT_C8',invalid_four=True)
        self.assertEqual((c['success'],c['deadline_loss'],len(t)),(False,500,4))

    def test_fixed_policy_replay_and_independent_audit_detect_changed_saved_reset(self):
        s,c,e,t,n=fixture('RAW_RESET_I',fixed_policy=True)
        self.assertEqual(replay(s,c,e,t,n)['independent_policy_queries'],c['policy_queries'])
        with patch.object(transition,'propose',side_effect=RuntimeError('disabled')),patch.object(transition,'consume',side_effect=RuntimeError('disabled')):independent_raw(s,c,e,t)
        changed=deepcopy(e);next(v for v in changed if v['agent_event']=='MEMORY_TRANSITION_PLAN')['public_payload']['plan']['after_memory']['integral_xy'][0]=.1
        with self.assertRaises(ValueError):independent_raw(s,c,changed,t)

    def test_full_500_step_failure_is_retained(self):
        s,c,e,t,n=fixture('RAW_RESET_I',end_at=None);independent_raw(s,c,e,t)
        self.assertFalse(c['success']);self.assertEqual((c['total_steps'],c['deadline_loss']),(500,500))


class HostTests(unittest.TestCase):
    def test_all_host_bindings_use_only_array_receipts(self):
        fit={'valid':True,'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'nfev':0};nominal=allocation.source_models()[0]['push-v3']
        with patch('src.probe.task_passive_program_v1.infer_four',return_value=fit),patch('src.probe.task_passive_program_v1.infer_operator',return_value=fit):
            for p in actor.PROGRAMS:
                spec=next(s for s in allocation.population('QUAL') if s['task']=='push-v3' and s['context']=='UNCHANGED' and s['program']==p)
                session=ArraySession(spec);labels=[];out=run_live(spec,nominal if actor.is_legacy(p) else None,session,labels.append,lambda:None)
                self.assertEqual(out['total_steps'],session.completed)
                self.assertEqual(labels.count('MEMORY_TRANSITION_PRE'),int(out['memory_transition_applied']))
                self.assertEqual(labels.count('MEMORY_TRANSITION_POST'),int(out['memory_transition_applied']))

    def test_memory_commit_detects_hidden_physical_mutation(self):
        spec=next(s for s in allocation.population('QUAL') if s['program']=='RAW_RESET_I');session=ArraySession(spec);old=session._agent_emit
        def bad(name,payload):
            saved=old(name,payload)
            if name=='MEMORY_TRANSITION_COMMIT':session.env.unwrapped.data.time+=.0125
            return saved
        session._agent_emit=bad
        with self.assertRaisesRegex(ValueError,'world/RNG/clock'):run_live(spec,None,session,lambda label:None,lambda:None)

    def test_clock_or_mutable_noise_is_rejected_before_continuity_claim(self):
        spec=allocation.population('SOFTWARE_NATIVE')[0];session=ArraySession(spec);session.clock_delta=.01
        with self.assertRaisesRegex(ValueError,'clock'):run_live(spec,None,session,lambda label:None,lambda:None)
        session=ArraySession(spec);session.ctx['noise_rows'].flags.writeable=True
        with self.assertRaisesRegex(ValueError,'noise tape'):run_live(spec,None,session,lambda label:None,lambda:None)


class StatisticsTests(unittest.TestCase):
    def test_independent_integer_group_statistics_match_full_population(self):
        rows=statistics_rows();d=indices();x=compute(rows,d);same(x,independently_compute(rows,d.tolist()))
        self.assertEqual(x['primary_status'],'SUPPORTED_STANDARD_RESET_REFERENCE_ONLY');self.assertEqual(len(x['full_assignment_panels']),180)

    def test_zero_primary_difference_fails_even_with_good_moved_reference(self):
        rows=statistics_rows()
        for r in rows:
            if r['program']=='RAW_RESET_I':r['deadline_loss']=r['total_steps']=180+r['group']
        result=compute(rows,indices());same(result,independently_compute(rows,indices().tolist()))
        self.assertEqual(result['registered_contrasts'][0]['group_bootstrap95'],[0.,0.]);self.assertEqual(result['primary_status'],'NOT_QUALIFIED')

    def test_missing_or_reordered_population_rejected(self):
        rows=statistics_rows()
        for bad in (rows[:-1],[rows[1],rows[0],*rows[2:]]):
            with self.assertRaises(ValueError):compute(bad,indices())

    def test_group_bootstrap_retains_boundary_strata(self):
        d=indices();self.assertEqual(d.shape,(10000,9))
        for j in range(3):self.assertTrue(np.all(d[:,3*j:3*j+3]%3==j))


class SeedTests(unittest.TestCase):
    def test_nested_seed_range_context_is_not_lost(self):
        for data in ({'reserved_seed_ranges':[[[72999,74001]]]}, {'episode_seeds':{'future':[[73001,73002]]}},
                     {'episode_seeds':{'reserved':[[72999,74001]]}},
                     {'seed_intervals':{'outer':[{'inner':[72999,74001]}]}}, {'seed_start':72999,'num_seeds':1003}):
            self.assertTrue(inspect(data,'fixture',73000,73999))

    def test_seed_list_is_not_accidentally_interpreted_as_interval(self):
        self.assertFalse(inspect({'episode_seeds':[72999,74001]},'fixture',73000,73999))

    def test_noise_bootstrap_and_generator_namespaces_are_not_episode_seeds(self):
        self.assertFalse(inspect({'bootstrap_seed':73000,'noise_seed_range':[73000,73999],
            'operator_generation_seed':73001,'episode_seed_ranges':[[100,200]]},'fixture',73000,73999))


if __name__=='__main__':unittest.main()
