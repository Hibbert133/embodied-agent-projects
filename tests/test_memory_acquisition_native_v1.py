"""Pure-array acquisition receipts; no simulator construction/reset/advance."""
from copy import deepcopy
from dataclasses import asdict
import unittest
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe import memory_acquisition_program_v1 as actor
from src.analysis.memory_acquisition_audit_v1 import independent_memory,replay
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis import memory_acquisition_io_v1 as alloc


def fixture(action='MOVE_MEASURE8',end_at=45,boundary=16,alter=None,jump=False,anchor=True,use_fixed=False):
    obs=[0.]*39;obs[:3]=[0.,.6,.25] if anchor else [.4,.3,.15];obs[4:7]=[.8,0.,.05]
    current=StepObservation(tuple(obs),False,False,False);initial=current;events=[];steps=[]
    def emit(kind,payload):
        ack={**normalize(payload),'sequence':len(events),'saved_ns':len(events)+1}
        if alter is not None:alter(kind,ack)
        events.append({'sequence':ack['sequence'],'agent_event':kind,'public_payload':deepcopy(ack)});return ack
    def step(saved):
        nonlocal current
        n=len(steps)+1;o=list(current.observation)
        if saved['phase']=='WARM_PROBE':o[0]+=.0001
        current=StepObservation(tuple(o),False,False,end_at is not None and n>=end_at)
        steps.append({'logical_step':n-1,'command':saved['command'],'raw_policy':saved['raw_policy'],'after':normalize(asdict(current)),
            'global_command_sequence':saved['sequence']})
        return StepReceipt(current,n+int(jump))
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy('push-v3') if use_fixed else None
    result=actor.run('push-v3',initial,boundary,action,lambda o:policy.get_action(o) if use_fixed else np.array([.2,-.1,.3,-1.],np.float32),step,emit)
    result['outcome']['initial']=normalize(asdict(initial))
    spec={'task':'push-v3','action':action,'planned_boundary':boundary}
    return result,events,steps,spec


class MemoryAcquisitionTests(unittest.TestCase):
    def test_new_native_population_and_complete_budget(self):
        p=alloc.population();self.assertEqual(len(p),54);self.assertEqual(len({(s['seed'],s['context']) for s in p}),18)
        self.assertEqual({s['planned_boundary'] for s in p},{16,32,64});self.assertEqual({s['task'] for s in p},set(alloc.io.TASKS))
        self.assertEqual(alloc.limits()['all_resets'],54*51);self.assertEqual(alloc.limits()['physical_frames'],54*(25500+500*5))

    def test_tape_is_full_immutable_reproducible_and_uses_new_namespace(self):
        a=alloc.noise(65000);self.assertEqual(a.shape,(500,3));self.assertFalse(a.flags.writeable)
        np.testing.assert_array_equal(a,alloc.noise(65000));self.assertFalse(np.array_equal(a,alloc.noise(65001)))

    def test_continue_validation_and_movement_execute_distinct_actual_commands(self):
        rows={a:fixture(a) for a in actor.ACTIONS}
        self.assertEqual(rows['CONTINUE'][0]['outcome']['option_steps'],0)
        self.assertEqual(rows['VALIDATE8'][0]['outcome']['option_steps'],8)
        self.assertEqual(rows['MOVE_MEASURE8'][0]['outcome']['warm_probe_steps'],8)
        self.assertNotEqual(rows['CONTINUE'][2][16]['command'],rows['MOVE_MEASURE8'][2][16]['command'])

    def test_movement_freezes_integral_and_resumes_actual_poststate(self):
        result,events,steps,spec=fixture();count=independent_memory(spec,result['outcome'],events,steps)
        before=next(e['public_payload']['memory'] for e in events if e['agent_event']=='TASK_MEMORY_SUSPEND')
        after=next(e['public_payload']['memory'] for e in events if e['agent_event']=='TASK_MEMORY_RETURN')
        self.assertEqual(before['integral_xy'],after['integral_xy']);self.assertNotEqual(before['current'],after['current'])
        self.assertEqual(count['returns'],1);self.assertGreater(count['pi_plans'],16)

    def test_validation_commits_task_integral_instead_of_freezing_it(self):
        result,events,steps,spec=fixture('VALIDATE8');independent_memory(spec,result['outcome'],events,steps)
        before=next(e['public_payload']['before_memory'] for e in events if e['agent_event']=='ACQUISITION_CHOICE')
        after=next(e['public_payload']['memory'] for e in events if e['agent_event']=='TASK_MEMORY_RETURN')
        self.assertNotEqual(before['integral_xy'],after['integral_xy'])

    def test_early_success_before_boundary_has_no_acquisition_or_tail(self):
        result,events,steps,spec=fixture(end_at=10);independent_memory(spec,result['outcome'],events,steps)
        self.assertFalse(result['outcome']['boundary_reached']);self.assertIsNone(result['outcome']['option_steps'])
        self.assertFalse(any(e['agent_event']=='TAIL_CHOICE' for e in events))

    def test_early_success_in_validation_keeps_actual_cost_and_no_tail(self):
        result,events,steps,spec=fixture('VALIDATE8',end_at=20);independent_memory(spec,result['outcome'],events,steps)
        self.assertEqual(result['outcome']['option_steps'],4);self.assertEqual(result['outcome']['deadline_loss'],20)
        self.assertFalse(any(e['agent_event']=='TAIL_CHOICE' for e in events))

    def test_movement_cap_and_failed_measurement_continue_from_current_state(self):
        result,events,steps,spec=fixture(end_at=100,anchor=False);independent_memory(spec,result['outcome'],events,steps)
        self.assertEqual(result['outcome']['option_reason'],'ANCHOR_NOT_REACHED');self.assertEqual(result['outcome']['movement_steps'],64)
        self.assertEqual(result['outcome']['warm_probe_steps'],0);self.assertTrue(any(s['raw_policy'] is not None for s in steps[80:]))

    def test_deadline_retains_full_denominator_and_actual_step_cap(self):
        result,events,steps,spec=fixture('CONTINUE',end_at=None);independent_memory(spec,result['outcome'],events,steps)
        self.assertEqual((result['outcome']['deadline_loss'],len(steps),result['outcome']['success']),(500,500,False))

    def test_changed_acquisition_acknowledgement_is_rejected(self):
        def alter(kind,p):
            if kind=='ACQUISITION_CHOICE':p['action']='CONTINUE'
        with self.assertRaisesRegex(ValueError,'acknowledgement'):fixture(alter=alter)

    def test_jump_receipt_and_unqualified_adoption_are_rejected(self):
        with self.assertRaises(ValueError):fixture(jump=True)
        with self.assertRaises(ValueError):fixture('ADOPT_WARM_C8')

    def test_independent_audit_rejects_silent_integral_reset(self):
        result,events,steps,spec=fixture()
        changed=deepcopy(events);returned=next(e for e in changed if e['agent_event']=='TASK_MEMORY_RETURN')
        returned['public_payload']['memory']['integral_xy']=[0.,0.]
        with self.assertRaisesRegex(ValueError,'integral'):independent_memory(spec,result['outcome'],changed,steps)

    def test_independent_audit_rejects_altered_probe_command(self):
        result,events,steps,spec=fixture();changed=deepcopy(events)
        command=next(e for e in changed if e['agent_event']=='COMMAND' and e['public_payload']['phase']=='WARM_PROBE')
        command['public_payload']['command'][0]=.25
        with self.assertRaises(ValueError):independent_memory(spec,result['outcome'],changed,steps)

    def test_saved_array_transcript_replays_with_frozen_policy_without_world(self):
        result,events,steps,spec=fixture(use_fixed=True)
        count=replay(spec,result['outcome'],events,steps)
        self.assertEqual(count['fixed_policy_requeries'],result['outcome']['policy_queries'])
        independent_memory(spec,result['outcome'],events,steps)


if __name__=='__main__':unittest.main()
