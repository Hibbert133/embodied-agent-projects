"""Synthetic native array containers and records; no environment, reset or fit."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import io as streams
import json
import numpy as np
from src.analysis import native_command_witness_io_v1 as a,native_command_witness_host_v1 as host,native_command_witness_audit_v1 as audit
from src.analysis.capsule_record_json_v2 import JsonJournal,normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.nominal_command_target_v1 import INITIAL,LOW,HIGH,PublicNominalTarget
from src.rollout.task_registry import create_task_policy


class ArraySession(ProbeSession):
    def witness(self):
        base=self.env.unwrapped
        return {'native_sha256':a.io.digest({'q':base.data.mocap_pos.tolist(),'t':base.data.time}),
            'python_semantic_sha256':a.io.digest(self.public().observation),'noise_past_sha256':a.io.digest(self.ctx['noise_rows'][:self.ctx['calls']].tolist()),'simulation_time':base.data.time}


def fixture(end_at=48,mutant=None,context='UNCHANGED'):
    spec=next(s for s in a.population() if s['group']==0 and s['task']=='push-v3' and s['context']==context)
    source=streams.StringIO();private_stream=streams.StringIO();identity={'experiment_run_id':'ARRAY','manifest_id':'ARRAY','source_git_commit':'ARRAY'}
    journal=JsonJournal(source,identity);private_journal=JsonJournal(private_stream,identity);last={};changed=False
    def emit(kind,payload):
        nonlocal last,changed
        if mutant=='saved_target' and kind=='PUBLIC_SENT_TARGET_PLAN' and not changed:
            payload=deepcopy(payload);payload['plan']['numbers']['target'][0]+=.1;changed=True
        e=journal.emit(kind,{**spec,**payload});last={k:e[k] for k in ('sequence','saved_ns')};return e
    def private(kind,payload):return private_journal.emit(kind,{**spec,**payload})
    ledger=LifecycleLedger(emit,504000);before=ledger.snapshot()
    emit('FACTORY_INTENT',{'ledger':before})
    def array_only_reset(_):
        for k,n in (('simulation_attempts',100),('simulation_completed',100),('simulation_frames_attempted',500),('simulation_frames_completed',500)):ledger.add(k,n)
    for _ in range(50):
        with ledger.scope('GOAL_GENERATION'):ledger.reset_call(array_only_reset,None)
    emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
    with ledger.scope('CONTROLLED_RESET'):ledger.reset_call(array_only_reset,None)
    observation=[0.]*39;observation[:3]=[.1,.8,.25];observation[4:7]=[.8,0.,.05];observation[-3:]=[.3,.9,.05]
    data=SimpleNamespace(time=.625,mocap_pos=np.array([INITIAL]),mocap_quat=np.array([[1.,0.,1.,0.]]),_address=2)
    base=SimpleNamespace(data=data,model=SimpleNamespace(_address=1),mocap_low=np.array(LOW),mocap_high=np.array(HIGH),action_scale=.01)
    calls=0
    def array_only_step(command):
        nonlocal calls
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        if mutant=='target_scale':data.mocap_pos=np.clip(data.mocap_pos+np.array(command[:3],dtype=np.float64)[None]*.02,LOW,HIGH)
        else:SawyerXYZEnv.set_xyz_action(base,np.asarray(command[:3],np.float32))
        data.mocap_quat=np.array([[1.,0.,1.,0.]])
        calls+=1;data.time+=.02 if mutant=='clock' else .0125
        for k,n in (('simulation_attempts',1),('simulation_completed',1),('simulation_frames_attempted',5),('simulation_frames_completed',5)):ledger.add(k,n)
        return np.array(observation),0.,False,False,{'success':calls>=end_at}
    env=SimpleNamespace(unwrapped=base,step=array_only_step)
    session=ArraySession(env,create_task_policy('push-v3'),np.array(observation),'push-v3',spec['seed'],a.initial_fault(),emit,ledger,{'completed':0,'maximum':9000})
    session.ctx['noise_rows']=a.noise(spec);session.branch={'role':'NATIVE_COMMAND_TARGET_WITNESS','future':0,'program':spec['program']}
    emit('NOISE_COMMITMENT',{'at_calls':0,'tape_sha256_oracle':a.io.digest(session.ctx['noise_rows'].tolist()),'noise_namespace_oracle':2026102301})
    initial=normalize(asdict(session.public()));outcome,public=host.run_live(spec,session,private,emit,lambda:deepcopy(last),lambda:None)
    case={**spec,**outcome,'completed':True,'environment_closed':True,'error':None,'close_error':None,'captures':0,'restores':0,
        'initial':initial,'final':normalize(asdict(session.public())),'ledger_before':before,'ledger_before_close':ledger.snapshot(),
        'ledger_after_close':ledger.snapshot(),'host_attempts':calls,'host_returned':calls,'public_trajectory_sha256':a.io.digest(public)}
    events=[json.loads(line) for line in source.getvalue().splitlines()];p=[json.loads(line) for line in private_stream.getvalue().splitlines()]
    return spec,case,events,p,public,ledger.snapshot()


class NativeCommandWitnessTests(TestCase):
    def test_frozen_population_and_full_budget(self):
        rows=a.population();self.assertEqual(len(rows),18);self.assertEqual(len({r['seed'] for r in rows}),9)
        self.assertEqual({r['planned_boundary'] for r in rows},{16,32,64})
        v=a.config()['limits'];self.assertEqual((v['all_resets'],v['physical_frames']),(18*51,18*25500+18*500*5))
        with self.assertRaises(ValueError):a.validate_spec(rows[0]|{'seed':69999})

    def test_separate_noise_and_context_random_sources(self):
        u=a.population()[0];v=u|{'context':'CHANGED'}
        np.testing.assert_array_equal(a.noise(u),a.noise(v));self.assertFalse(a.noise(u).flags.writeable)
        self.assertEqual(a.destination(u),a.initial_fault());self.assertNotEqual(a.destination(v),a.initial_fault())

    def test_full_array_host_independent_replay_and_native_arithmetic(self):
        spec,c,events,private,p,ledger=fixture()
        with patch.object(host,'native_values',side_effect=RuntimeError('disabled')),patch.object(host,'public_prefix',side_effect=RuntimeError('disabled')):
            row,rebuilt,*_=audit.audit_case(spec,c,events,private,p,{'counts':{},'by_phase':{}})
        self.assertTrue(row['all_native_target_updates_bit_exact']);self.assertEqual(row['max_native_target_error_m'],0.)
        self.assertEqual(ledger,rebuilt);self.assertTrue(c['complete_warm_window']);self.assertEqual(len(private),2*c['total_steps']+2)

    def test_known_target_model_mismatch_is_retained_as_failed_contract(self):
        spec,c,events,private,p,_=fixture(mutant='target_scale')
        row,*_=audit.audit_case(spec,c,events,private,p,{'counts':{},'by_phase':{}})
        self.assertFalse(row['all_native_target_updates_bit_exact']);self.assertGreater(row['max_native_target_error_m'],0)

    def test_changed_fault_boundary_preserves_continuity(self):
        spec,c,events,private,p,_=fixture(context='CHANGED');row,*_=audit.audit_case(spec,c,events,private,p,{'counts':{},'by_phase':{}})
        self.assertTrue(c['boundary_applied']);self.assertTrue(row['all_native_target_updates_bit_exact'])
        boundary=next(e for e in events if e['event']=='FAULT_BOUNDARY');self.assertEqual(boundary['before'],boundary['after'])

    def test_early_success_keeps_missing_measurement_and_all_costs(self):
        spec,c,events,private,p,ledger=fixture(end_at=4);row,actual,*_=audit.audit_case(spec,c,events,private,p,{'counts':{},'by_phase':{}})
        self.assertFalse(c['boundary_applied']);self.assertFalse(c['complete_warm_window']);self.assertIsNone(row['entry_sent_native_gap_mm'])
        self.assertEqual(actual,ledger);self.assertEqual(ledger['counts']['reset_attempts'],51)

    def test_public_query_does_not_read_future_rows_or_responses(self):
        *_,p,_=fixture(end_at=4);expected=host.public_prefix(p,2);changed=deepcopy(p)
        changed['steps'][2]['observation_after']=['invalid future'];changed['steps'].extend([{'future_oracle':True}]*501)
        self.assertEqual(host.public_prefix(changed,2),expected)
        with self.assertRaises(ValueError):host.public_prefix(changed,3)

    def test_private_fields_and_fabricated_past_rejected(self):
        *_,p,_=fixture(end_at=4)
        for key in ('seed','fault_oracle','mocap_pos_oracle','future_success'):
            changed=deepcopy(p);changed[key]=1
            with self.assertRaises(ValueError):host.public_prefix(changed,2)
        changed=deepcopy(p);changed['steps'][1]['observation_before'][0]+=.01
        with self.assertRaises(ValueError):host.public_prefix(changed,2)

    def test_false_public_reference_rejected(self):
        *_,p,_=fixture(end_at=4);changed=deepcopy(p);changed['steps'][0]['reference_after']['target'][0]+=.1
        with self.assertRaises(ValueError):host.public_prefix(changed,1)

    def test_native_values_are_copied_not_mutated_or_exposed(self):
        _,_,_,private,p,_=fixture(end_at=4);self.assertTrue(all(r['evaluator_only'] for r in private))
        encoded=json.dumps(p);self.assertNotIn('oracle',encoded);self.assertNotIn('mocap',encoded);self.assertNotIn('seed',encoded)
        q=deepcopy(private[0]['mocap_pos_oracle']);private[-1]['mocap_pos_oracle'][0][0]=99
        self.assertEqual(private[0]['mocap_pos_oracle'],q)

    def test_changed_plan_acknowledgement_rejected(self):
        with self.assertRaises(ValueError):fixture(mutant='saved_target')

    def test_clock_discontinuity_rejected(self):
        with self.assertRaises(ValueError):fixture(mutant='clock')

    def test_noise_cursor_shift_rejected(self):
        spec,c,events,private,p,_=fixture(end_at=4);next(e for e in events if e['event']=='STEP_COMPLETE')['noise_cursor_after']+=1
        with self.assertRaises(ValueError):audit.audit_case(spec,c,events,private,p,{'counts':{},'by_phase':{}})

    def test_reordered_native_witness_rejected(self):
        spec,c,events,private,p,_=fixture(end_at=4);private[1]['saved_ns']=private[2]['saved_ns']+1
        with self.assertRaises(ValueError):audit.audit_case(spec,c,events,private,p,{'counts':{},'by_phase':{}})

    def test_private_world_replacement_rejected(self):
        spec,c,events,private,p,_=fixture(end_at=4);private[1]['model_address_oracle']+=1
        with self.assertRaises(ValueError):audit.audit_case(spec,c,events,private,p,{'counts':{},'by_phase':{}})

    def test_export_oracle_injection_rejected_by_audit(self):
        spec,c,events,private,p,_=fixture(end_at=4);p['steps'][0]['executed_action_oracle']=[0.,0.,0.,0.]
        with self.assertRaises(ValueError):audit.audit_case(spec,c,events,private,p,{'counts':{},'by_phase':{}})

    def test_actuator_order_and_target_precision_counterexamples(self):
        u=[.123456789,0.,0.,0.];v=audit.target([0.,.6,.2],u)
        self.assertNotEqual(v['target'][0],float(np.float32(u[0]))*.01)
        from src.analysis.short_probe_journal_audit_v1 import applied
        q=applied([.95,0.,0.,0.],a.initial_fault(),np.array([-.2,0,0],np.float32))
        early=np.clip(np.array([.95,0.,0.,0.],np.float32)+np.array([.12,-.08,0,0],np.float32),-1,1);early[:3]+=np.array([-.2,0,0],np.float32)
        self.assertNotEqual(q,early.tolist())

    def test_fit_guard_blocks_real_optimization(self):
        receipt={}
        with a.forbid_fitting(receipt):
            with self.assertRaises(RuntimeError):np.linalg.lstsq(np.eye(2),np.ones(2),rcond=None)
        self.assertEqual(receipt,{'attempted_fits':1})
