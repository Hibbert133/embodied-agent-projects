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
from src.probe import acquisition_reference_program_v1 as actor
from src.analysis import acquisition_reference_io_v1 as allocation
from src.analysis.acquisition_reference_audit_v1 import independent_raw,replay,pid_numbers
from src.analysis.acquisition_reference_host_v1 import run_live
from src.analysis.acquisition_reference_statistics_v1 import compute,indices
from src.analysis.acquisition_reference_statistics_audit_v1 import independently_compute,same
from src.analysis.capsule_record_json_v2 import normalize


def observation(success=False):
    o=[0.]*39;o[:3]=[.1,.8,.25];o[4:7]=[.8,0.,.05];return StepObservation(tuple(o),False,False,success)


def evidence(x=-.12,y=.08):return {'integral_xy':[x,y],'at_anchor':True,'controller':{'source':'RELOCATION_INTEGRAL_REFERENCE','matrix_xy':[[1.,0.],[0.,1.]],'offset':[x,y,0.,0.]},'parameter_estimate_qualified':False,'task_utility_demonstrated':False}


def fixture(program='LOCAL_PID_REFERENCE_RESET',end_at=120,fixed_policy=False,invalid_four=False):
    spec=next(s for s in allocation.population('SOFTWARE_NATIVE') if s['task']=='push-v3' and s['context']=='UNCHANGED' and s['program']==program)
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
        if p=='LOCAL_PID_KEEP':loss=160
        if p=='LOCAL_PID_REFERENCE_RESET':loss=140
        if p=='LOCAL_PID_REFERENCE_CARRY':loss=170
        if p=='LOCAL_PID_REFERENCE_RESET_NO_PROBE':loss=130
        loss+=spec['group'];window=p.startswith('LOCAL_PID') and not p.endswith('_NO_PROBE')
        rows.append({**spec,'deadline_loss':loss,'total_steps':loss,'success':True,'movement_steps':0 if p in ('RAW_CONTINUE','DIRECT_C8') else 20,
            'warm_probe_steps':8 if window else 0,'complete_warm_window':window,'reference_update_applied':'REFERENCE' in p,
            'c4_c8_fit_attempts':2 if actor.is_legacy(p) else 0})
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


class ReferenceUpdateTests(unittest.TestCase):
    def test_reset_and_carry_preserve_actual_state_and_change_sent_command(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=30,integral_xy=(.2,-.1))
        plans=[ref.propose(m,evidence(),mode=v) for v in ('RESET','CARRY')];sent=[]
        for p in plans:
            machine=TaskMemoryMachine(m);ref.consume(machine,p,evidence());self.assertEqual(machine.memory.current,m.current);self.assertEqual(machine.memory.completed_steps,30)
            sent.append(machine.plan([.1,-.1,.2,-1.])['pi_plan']['numbers']['sent_command'])
            self.assertFalse(p['parameter_identification_qualified']);self.assertFalse(p['bumpless_transfer_established'])
        self.assertNotEqual(sent[0],sent[1])

    def test_changed_stale_or_repeated_reference_plan_is_rejected(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=20);p=ref.propose(m,evidence(),mode='RESET');machine=TaskMemoryMachine(m)
        changed=deepcopy(p);changed['after_memory']['controller']['offset'][0]+=.01
        with self.assertRaises(ValueError):ref.consume(machine,changed,evidence())
        ref.consume(machine,p,evidence())
        with self.assertRaises(ValueError):ref.consume(machine,p,evidence())

    def test_unknown_truth_fields_invalid_mapping_and_false_ready_rejected(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=20)
        for change in ({'seed':1},{'at_anchor':False},{'parameter_estimate_qualified':True},{'integral_xy':[.6,0.]},{'controller':{'source':'ORACLE'}}):
            with self.assertRaises(ValueError):ref.propose(m,{**evidence(),**change},mode='RESET')

    def test_task_controller_cannot_update_while_pending_or_suspended(self):
        m=replace(TaskMemory.initial('push-v3',observation()),completed_steps=20);p=ref.propose(m,evidence(),mode='RESET');machine=TaskMemoryMachine(m);machine.suspend()
        with self.assertRaises(ValueError):ref.consume(machine,p,evidence())
        machine=TaskMemoryMachine(m);machine.plan([.1,0,0,-1])
        with self.assertRaises(ValueError):ref.consume(machine,p,evidence())


class ProgramTests(unittest.TestCase):
    def test_complete_budget_has_all_ten_programs_and_two_independent_phases(self):
        self.assertEqual(len(actor.PROGRAMS),10);self.assertEqual(len(allocation.population('SOFTWARE_NATIVE')),60);self.assertEqual(len(allocation.population('QUAL')),540)
        self.assertEqual(allocation.config()['combined_limits']['physical_frames'],600*28000)
        self.assertEqual(allocation.config()['combined_limits']['all_resets'],600*51)
        self.assertEqual(allocation.limits('QUAL')['c4_c8_fit_attempts'],216)

    def test_all_ten_programs_execute_registered_array_procedures(self):
        for p in actor.PROGRAMS:
            with self.subTest(program=p):
                s,c,e,t,n=fixture(p);self.assertEqual(c['total_steps'],len(t));self.assertLessEqual(len(t),500)
                if not actor.is_legacy(p):independent_raw(s,c,e,t)
                else:self.assertEqual(c['c4_c8_fit_attempts'],2)

    def test_legacy_invalid_C4_stops_with_full_loss_and_no_substitution(self):
        _,case,_,steps,_=fixture('DIRECT_C8',invalid_four=True)
        self.assertEqual((case['deadline_loss'],case['total_steps'],case['success']),(500,4,False));self.assertEqual(len(steps),4)

    def test_three_warm_local_PID_modes_share_actual_acquisition_until_return(self):
        data=[fixture(p) for p in ('LOCAL_PID_KEEP','LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY')]
        ends=[]
        for s,c,e,t,n in data:
            ret=next(v['public_payload'] for v in e if v['agent_event']=='TASK_MEMORY_RETURN');ends.append(ret['at_calls'])
            self.assertEqual(c['complete_warm_window'],True)
        self.assertEqual(ends,[ends[0]]*3)
        for j in range(1,3):self.assertEqual(data[0][3][:ends[0]],data[j][3][:ends[0]])
        self.assertTrue(data[1][1]['reference_update_applied']);self.assertTrue(data[2][1]['reference_update_applied'])

    def test_no_probe_reference_uses_same_relocation_and_does_not_fake_window(self):
        warm=fixture('LOCAL_PID_REFERENCE_RESET');bare=fixture('LOCAL_PID_REFERENCE_RESET_NO_PROBE')
        self.assertEqual(bare[1]['warm_probe_steps'],0);self.assertFalse(bare[1]['complete_warm_window']);self.assertTrue(bare[1]['reference_update_applied'])
        n=16+bare[1]['movement_steps']
        for a,b in zip(warm[3][:n],bare[3][:n]):
            self.assertEqual(a['command'],b['command']);self.assertEqual(a['after'],b['after'])

    def test_early_success_does_not_manufacture_acquisition_or_adoption(self):
        s,c,e,t,n=fixture('LOCAL_PID_REFERENCE_RESET',end_at=10);independent_raw(s,c,e,t)
        self.assertFalse(c['acquisition_entered']);self.assertFalse(c['reference_update_applied']);self.assertEqual(c['total_steps'],10)

    def test_incomplete_window_keeps_actual_current_controller_and_memory(self):
        s,c,e,t,n=fixture('LOCAL_PID_REFERENCE_RESET',end_at=20);independent_raw(s,c,e,t)
        self.assertFalse(c['complete_warm_window']);self.assertFalse(c['reference_update_applied'])
        self.assertFalse(any(x['agent_event']=='REFERENCE_UPDATE_COMMIT' for x in e))

    def test_replay_of_frozen_policy_arrays_and_mocked_C8_has_no_world(self):
        for p in ('RAW_CONTINUE','LOCAL_PID_REFERENCE_RESET'):
            s,c,e,t,n=fixture(p,fixed_policy=True);self.assertEqual(replay(s,c,e,t,n)['independent_policy_queries'],c['policy_queries'])

    def test_independent_state_audit_rejects_carry_reset_confusion(self):
        s,c,e,t,n=fixture('LOCAL_PID_REFERENCE_CARRY');changed=deepcopy(e)
        committed=next(x for x in changed if x['agent_event']=='REFERENCE_UPDATE_COMMIT');committed['public_payload']['memory']['integral_xy']=[0.,0.]
        with self.assertRaises(ValueError):independent_raw(s,c,changed,t)

    def test_separate_scalar_PID_conditional_integration_matches_registered_rule(self):
        from src.probe.local_reprobe_v1 import control_update
        from src.probe.physical_reprobe_v1 import Start
        h=[list(observation().observation),list(observation().observation)];h[-1][0]+=.01;anchor=[.1,.8,.25]
        start=Start('push-v3',16,observation(),[[1.,0.],[0.,1.]],[0.,0.]);old=[-.1,.1]
        for m in ('LOCAL_PD','LOCAL_PID'):
            state=[0.,0.] if m.endswith('_PD') else old
            expected=control_update(start,h,True,state,m);actual=pid_numbers(h,anchor,True,state,m)
            self.assertEqual(actual,expected)


class StatisticsTests(unittest.TestCase):
    def test_independent_group_sums_and_rational_quantiles_match_all_statistics(self):
        r=statistics_rows();d=indices();x=compute(r,d);same(x,independently_compute(r,d.tolist()))
        self.assertEqual(x['reference_update_status'],'QUALIFIED_STANDARD_REFERENCE_BRANCH_ONLY');self.assertTrue(x['joint_component_gate_passed'])

    def test_missing_duplicate_or_misordered_population_is_rejected(self):
        r=statistics_rows()
        for bad in (r[:-1],[r[1],r[0],*r[2:]]):
            with self.assertRaises(ValueError):compute(bad,indices())

    def test_zero_difference_fails_strict_gate_and_does_not_promote_CARRY(self):
        r=statistics_rows()
        for v in r:
            if v['program']=='LOCAL_PID_REFERENCE_RESET':v['deadline_loss']=v['total_steps']=160+v['group']
            if v['program']=='LOCAL_PID_REFERENCE_CARRY':v['deadline_loss']=v['total_steps']=100+v['group']
        x=compute(r,indices());same(x,independently_compute(r,indices().tolist()))
        self.assertEqual(x['registered_contrasts'][1]['group_bootstrap95'],[0.,0.]);self.assertEqual(x['reference_update_status'],'NOT_QUALIFIED')

    def test_bootstrap_keeps_three_groups_in_each_boundary_stratum(self):
        d=indices()
        self.assertEqual(d.shape,(10000,9))
        for j in range(3):self.assertTrue(np.all(d[:,j*3:j*3+3]%3==j))


class HostContractTests(unittest.TestCase):
    def test_all_program_host_bindings_with_only_array_receipts_and_mocked_fits(self):
        nominal=allocation.source_models()[0]['push-v3'];fit={'valid':True,'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'nfev':0}
        with patch('src.probe.task_passive_program_v1.infer_four',return_value=fit),patch('src.probe.task_passive_program_v1.infer_operator',return_value=fit):
            for p in actor.PROGRAMS:
                with self.subTest(program=p):
                    spec=next(s for s in allocation.population('SOFTWARE_NATIVE') if s['task']=='push-v3' and s['context']=='UNCHANGED' and s['program']==p)
                    session=ArraySession(spec);labels=[];out=run_live(spec,nominal if actor.is_legacy(p) else None,session,labels.append,lambda:None)
                    self.assertEqual(out['total_steps'],session.completed);self.assertEqual(out['policy_queries'],session.policy_queries);self.assertTrue(out['boundary_applied'])

    def test_host_detects_clock_drift_and_mutable_noise_before_claiming_continuity(self):
        spec=allocation.population('SOFTWARE_NATIVE')[0]
        session=ArraySession(spec);session.clock_delta=.01
        with self.assertRaisesRegex(ValueError,'clock'):run_live(spec,None,session,lambda label:None,lambda:None)
        session=ArraySession(spec);session.ctx['noise_rows'].flags.writeable=True
        with self.assertRaisesRegex(ValueError,'noise tape'):run_live(spec,None,session,lambda label:None,lambda:None)


if __name__=='__main__':unittest.main()
