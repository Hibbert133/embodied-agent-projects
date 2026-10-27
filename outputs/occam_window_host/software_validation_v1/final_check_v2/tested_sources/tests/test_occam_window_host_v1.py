"""Pure arrays and record callbacks: no environment construction or advancement."""
from copy import deepcopy
from dataclasses import asdict
import unittest
import numpy as np
from src.probe import occam_window_program_v1 as actor
from src.probe import occam_window_cost_v1 as cost
from src.probe.occam_public_history_v1 import features
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.analysis.occam_window_audit_v1 import scalar_cost
from src.analysis import occam_window_io_v1 as allocation


def initial():
    x=[0.]*39;x[2]=.25;x[5]=.7;x[36]=.2;x[37]=.8
    return dict(observation=x,success=False,terminated=False,truncated=False)


def rows(n,*,start=0,before=None,success=False,terminated=False):
    result=[];current=deepcopy(initial() if before is None else before)
    for i in range(n):
        after=deepcopy(current);after['observation'][0]+=.001
        if i==n-1:after.update(success=success,terminated=terminated)
        result.append(dict(at_calls=start+i,before=current,command=[.125,0.,0.,0.],after=after));current=after
    return result


def fixture(sign=1,stop=50,*,success=True,action='CONTINUE',mutate=None):
    saved=[];commands=[];current=initial();queries=0
    def emit(kind,payload):
        v=dict(sequence=len(saved),saved_ns=len(saved)+1,**deepcopy(payload))
        if mutate is not None:mutate(kind,v)
        saved.append(dict(kind=kind,payload=deepcopy(v)));return v
    def policy(observation):
        nonlocal queries
        queries+=1;np.testing.assert_array_equal(observation,current['observation']);return np.array([.1,-.05,0.,0.],np.float32)
    def step(command):
        nonlocal current
        commands.append(deepcopy(command));n=len(commands);after=deepcopy(current)
        after['observation'][0]+=.0001*command['command'][0]
        if n==stop:after.update(success=success,terminated=not success)
        current=after;return StepReceipt(StepObservation(**after),n)
    provider=actor.OccamProvider(actor.constructed_bank(sign))
    result=actor.run('push-v3',StepObservation(**current),16,action,provider,policy,step,emit)
    return result,saved,commands,queries,provider


class WindowCostTests(unittest.TestCase):
    def test_public_task_potential(self):
        cur=initial();self.assertNotEqual(cost.potential('reach-v3',cur,0),cost.potential('push-v3',cur,0))
        self.assertEqual(cost.potential('push-v3',cur,0),cost.potential('door-open-v3',cur,0))

    def test_terminal_and_horizon_potential_zero(self):
        for flag in ('success','terminated','truncated'):
            cur=initial();cur[flag]=True;self.assertEqual(cost.potential('push-v3',cur,10),0.)
        self.assertEqual(cost.potential('push-v3',initial(),500),0.)

    def test_factual_short_success_is_not_padded_or_dropped(self):
        r=rows(3,success=True);m=cost.measure('push-v3',0,initial(),r,16)
        self.assertEqual(m['actual_steps'],3);self.assertEqual(m['deadline_charge_steps'],3);self.assertFalse(m['full_window'])
        self.assertAlmostEqual(cost.total_cost('push-v3',initial(),[m],3,True)['reconstructed_deadline_loss'],3.)

    def test_failure_penalty_is_distinct_from_actual_interaction(self):
        r=rows(4,terminated=True);m=cost.measure('push-v3',0,initial(),r,16)
        self.assertEqual(m['actual_steps'],4);self.assertEqual(m['unexecuted_failure_penalty_steps'],496)
        self.assertEqual(cost.total_cost('push-v3',initial(),[m],4,False)['deadline_loss'],500)

    def test_multiple_windows_telescope_with_independent_step_sum(self):
        r=rows(7,success=True);first=cost.measure('reach-v3',0,initial(),r[:4],4)
        second=cost.measure('reach-v3',4,r[3]['after'],r[4:],4)
        steps=[dict(after=x['after']) for x in r]
        for m in (first,second):
            alt=scalar_cost('reach-v3',initial(),steps,m['start_at'],m['end_at'],m['terminal'])
            self.assertAlmostEqual(alt['cost'],m['cost'],places=14)
        self.assertAlmostEqual(cost.total_cost('reach-v3',initial(),[first,second],7,True)['reconstructed_deadline_loss'],7.)

    def test_500_step_failure_reconstruction(self):
        r=rows(500);m=cost.measure('door-open-v3',0,initial(),r,500)
        self.assertTrue(m['terminal']);self.assertEqual(m['unexecuted_failure_penalty_steps'],0)
        self.assertAlmostEqual(cost.total_cost('door-open-v3',initial(),[m],500,False)['reconstructed_deadline_loss'],500.)

    def test_noise_or_oracle_fields_rejected(self):
        r=rows(1);r[0]['noise']=[0.,0.,0.]
        with self.assertRaises(ValueError):cost.measure('push-v3',0,initial(),r,1)
        s=initial();s['private']={}
        with self.assertRaises(ValueError):cost.potential('push-v3',s,0)

    def test_live_short_zero_length_and_non_float32_rejected(self):
        for r in ([],rows(1)):
            with self.assertRaises(ValueError):cost.measure('push-v3',0,initial(),r,16)
        r=rows(1);r[0]['command'][0]=.1
        with self.assertRaises(ValueError):cost.measure('push-v3',0,initial(),r,1)

    def test_zero_length_host_failure_has_explicit_penalty(self):
        m=cost.measure('push-v3',0,initial(),[],16,host_failure=True)
        self.assertEqual(m['deadline_charge_steps'],500);self.assertEqual(m['actual_steps'],0)
        self.assertAlmostEqual(cost.total_cost('push-v3',initial(),[m],0,False)['reconstructed_deadline_loss'],500.)

    def test_skipped_history_and_terminal_continuation_rejected(self):
        r=rows(2);r[0]['at_calls']=1
        with self.assertRaises(ValueError):cost.measure('push-v3',0,initial(),r,2)
        r=rows(2);r[0]['after']['success']=True;r[1]['before']=r[0]['after']
        with self.assertRaises(ValueError):cost.measure('push-v3',0,initial(),r,2)

    def test_gaps_duplicate_penalties_and_wrong_final_status_rejected(self):
        m=cost.measure('push-v3',0,initial(),rows(2,terminated=True),16)
        for segments,n,s in (([m,m],2,False),([m],3,False),([m],2,True)):
            with self.assertRaises(ValueError):cost.total_cost('push-v3',initial(),segments,n,s)


class WindowActorTests(unittest.TestCase):
    def test_different_saved_legal_choices_change_actual_commands(self):
        _,events,a,_,_=fixture(1);_,_,b,_,_=fixture(-1)
        self.assertEqual([x['command'] for x in a[:16]],[x['command'] for x in b[:16]])
        self.assertNotEqual(a[16]['command'],b[16]['command'])
        for e in events:
            if e['kind']=='COMMAND':self.assertLess(e['payload']['decision_sequence'],e['payload']['sequence'])

    def test_full_windows_update_only_after_actual_receipts(self):
        result,events,commands,queries,p=fixture()
        self.assertEqual(len(commands),50);self.assertEqual(queries,50);self.assertEqual(p.session.version,2)
        self.assertEqual(result['outcome']['deadline_loss'],50)
        for e in events:
            if e['kind']=='WINDOW_FEEDBACK':
                previous=events[e['payload']['sequence']-1]
                self.assertEqual(previous['kind'],'WINDOW_RESULT');self.assertEqual(previous['payload']['at_calls'],e['payload']['at_calls'])

    def test_early_success_before_boundary_keeps_assignment_and_no_filter(self):
        result,events,commands,queries,p=fixture(stop=5)
        self.assertEqual(len(commands),5);self.assertEqual(queries,5);self.assertIsNone(p.session)
        self.assertFalse(any(e['kind']=='WINDOW_DECISION' for e in events));self.assertEqual(result['outcome']['deadline_loss'],5)

    def test_terminal_short_window_saves_label_without_filter_update(self):
        result,events,commands,_,p=fixture(stop=19,success=False)
        m=next(e['payload']['measurement'] for e in events if e['kind']=='WINDOW_RESULT')
        self.assertEqual(m['actual_steps'],3);self.assertEqual(p.session.version,0);self.assertTrue(p.session.closed)
        self.assertEqual(result['outcome']['deadline_loss'],500);self.assertEqual(len(commands),19)

    def test_validate8_is_actual_task_steps_with_carried_memory(self):
        result,events,commands,queries,p=fixture(action='VALIDATE8')
        phases=[x['phase'] for x in commands];self.assertEqual(phases.count('VALIDATION_TASK'),8)
        first=next(e['payload'] for e in events if e['kind']=='WINDOW_QUERY')
        self.assertEqual(first['at_calls'],24);self.assertEqual(len(first['value']['history']),24)
        self.assertNotEqual(first['value']['integral_xy'],[0.,0.]);self.assertEqual(queries,50)
        self.assertEqual(result['outcome']['measurement_steps'],8)

    def test_movement_is_real_callback_cost_and_can_end_before_selection(self):
        result,events,commands,queries,p=fixture(stop=20,action='MOVE_MEASURE')
        self.assertEqual(len(commands),20);self.assertEqual(queries,16);self.assertIsNone(p.session)
        self.assertEqual(result['outcome']['movement_steps'],4);self.assertEqual(result['outcome']['deadline_loss'],20)

    def test_tampered_acknowledgement_cannot_execute(self):
        def change(kind,value):
            if kind=='COMMAND':value['command'][0]=.75
        with self.assertRaises(ValueError):fixture(mutate=change)

    def test_saved_query_contains_only_past_rows_and_public_memory(self):
        _,events,_,_,_=fixture()
        for e in events:
            if e['kind']=='WINDOW_QUERY':
                q=e['payload']['value'];self.assertEqual(len(q['history']),q['completed_steps']);features(q,8)
                bad=deepcopy(q);bad['history'].append(q['history'][-1])
                with self.assertRaises(ValueError):features(bad,8)

    def test_bank_change_or_extra_private_input_rejected(self):
        p=actor.OccamProvider(actor.constructed_bank(1));p.bank['prior']['mean'][0]=1.
        with self.assertRaises(ValueError):p.declare({})
        _,events,_,_,_=fixture();q=deepcopy(next(e['payload']['value'] for e in events if e['kind']=='WINDOW_QUERY'))
        q['seed']=164000
        with self.assertRaises(ValueError):actor.OccamProvider(actor.constructed_bank(1)).declare(q)

    def test_population_pairing_caps_and_shared_noise(self):
        specs=allocation.population();self.assertEqual(len(specs),36)
        for a,b in zip(specs[::2],specs[1::2]):
            np.testing.assert_array_equal(allocation.noise(a),allocation.noise(b));self.assertFalse(allocation.noise(a).flags.writeable)
            self.assertEqual(allocation.destination(a),allocation.destination(b))
        self.assertEqual(allocation.limits()['all_resets'],36*51)
        with self.assertRaises(ValueError):allocation.validate_spec({**specs[0],'seed':1})


class WindowHostTests(unittest.TestCase):
    def test_record_host_runs_all_three_actual_acquisition_interfaces(self):
        from tests.test_learned_acquisition_native_v1 import FakeSession
        from src.analysis.occam_window_host_v1 import run_live
        for group in range(3):
            spec=next(s for s in allocation.population() if s['group']==group);session=FakeSession(end=120);labels=[]
            result=run_live(spec,session,labels.append,lambda:None)
            self.assertEqual(result['total_steps'],session.completed);self.assertEqual(session.ledger.counts['simulation_frames_completed'],5*session.completed)
            self.assertEqual(result['policy_queries'],session.policy_queries);self.assertIn('FIRST_RATE_PRE',labels)

    def test_host_rejects_midtask_reset_at_gain_change(self):
        from tests.test_learned_acquisition_native_v1 import FakeSession
        from src.analysis.occam_window_host_v1 import run_live
        session=FakeSession(end=40)
        def witness(name):
            if name=='FIRST_RATE_PRE':session.ledger.counts['reset_attempts']+=1
        with self.assertRaisesRegex(ValueError,'noise/reset changed'):run_live(allocation.population()[0],session,witness,lambda:None)

    def test_host_rejects_noise_tape_replacement(self):
        from tests.test_learned_acquisition_native_v1 import FakeSession
        from src.analysis.occam_window_host_v1 import run_live
        session=FakeSession(end=40)
        def witness(name):
            if name=='FIRST_RATE_PRE':session.ctx['noise_rows']=session.ctx['noise_rows'].copy()
        with self.assertRaisesRegex(ValueError,'noise/reset changed'):run_live(allocation.population()[0],session,witness,lambda:None)

    def test_host_rejects_clock_rewind_at_gain_change(self):
        from tests.test_learned_acquisition_native_v1 import FakeSession
        from src.analysis.occam_window_host_v1 import run_live
        session=FakeSession(end=40)
        def witness(name):
            if name=='FIRST_RATE_PRE':session.data.time=0.
        with self.assertRaisesRegex(ValueError,'clock/restoration violation'):run_live(allocation.population()[0],session,witness,lambda:None)

    def test_host_rejects_fictional_step_cursor(self):
        from tests.test_learned_acquisition_native_v1 import FakeSession
        from src.analysis.occam_window_host_v1 import run_live
        session=FakeSession(end=40);original=session._agent_step
        def wrong(saved):
            out=original(saved);session.ctx['calls']+=1;return out
        session._agent_step=wrong
        with self.assertRaisesRegex(ValueError,'cursor continuity'):run_live(allocation.population()[0],session,lambda n:None,lambda:None)

    def test_host_rejects_changed_world_at_gain_change(self):
        from tests.test_learned_acquisition_native_v1 import FakeSession
        from src.analysis.occam_window_host_v1 import run_live
        session=FakeSession(end=40)
        def witness(name):
            if name=='FIRST_RATE_PRE':session.model._address=7
        with self.assertRaisesRegex(ValueError,'world replaced'):run_live(allocation.population()[0],session,witness,lambda:None)


if __name__=='__main__':unittest.main()
