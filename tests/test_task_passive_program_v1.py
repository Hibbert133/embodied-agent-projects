"""Pure numeric records plus legacy-reference comparisons; no Env methods."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import unittest
from unittest.mock import patch
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import task_passive_program_v1 as actor
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt,Start
from src.probe.operator_identification import identity_controller
from src.probe.movement_task_reference_v1 import run_movement_task


class ArrayJournal:
    def __init__(self): self.events=[]
    def __call__(self,kind,payload):
        saved=normalize({'sequence':len(self.events),'saved_ns':perf_counter_ns(),**payload})
        self.events.append({'kind':kind,'payload':deepcopy(saved)}); return deepcopy(saved)


class NumericSequence:
    """An arithmetic sequence, not an environment; has no reset or step API."""
    def __init__(self,success_at=80,initial=None,at=0):
        o=np.zeros(39); o[:3]=[0.,.6,.2]; o[4:7]=[.2,.65,.02]; o[-3:]=[.3,.8,.1]
        self.current=StepObservation(o,False,False,False) if initial is None else initial
        self.n=at; self.states=[self.current]; self.rows=[]; self.success_at=success_at; self.queries=0
    def policy(self,observation):
        np.testing.assert_array_equal(observation,self.current.observation)
        self.queries+=1; return np.array([.2,-.1,.05,-1.],np.float32)
    def respond(self,saved):
        before=self.current; obs=np.array(before.observation); command=np.array(saved['command'])
        obs[:3]+=.002*command[:3]+np.array([.0001,-.00005,0.])
        obs[3]=command[3]; self.n+=1
        self.current=StepObservation(obs,False,False,self.success_at is not None and self.n>=self.success_at)
        self.states.append(self.current); self.rows.append({'n':self.n,'command':command.tolist(),'phase':saved['phase'],'before':before,'after':self.current,'raw':saved['raw_policy']})
        return StepReceipt(self.current,self.n)


def numeric_run(style,time=None,success_at=80,invalid=False,journal=None):
    sequence=NumericSequence(success_at); journal=ArrayJournal() if journal is None else journal
    fit={'valid':not invalid,'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'nfev':1,'reason':'ARRAY_ONLY'}
    program=actor.Program(style,time)
    with patch.object(actor,'validate_model'),patch.object(actor,'infer_four',return_value=fit),patch.object(actor,'infer_operator',return_value=fit):
        result=actor.run('push-v3',sequence.current,{'task':'push-v3'} if program.uses_c8 else None,16,program,sequence.policy,sequence.respond,journal)
    return result,sequence,journal


class TaskProgramTests(unittest.TestCase):
    def test_raw_controls_have_no_cold_source_and_pi_starts_at_zero(self):
        result,seq,journal=numeric_run('RAW_TASK_PI',.5)
        self.assertEqual(result['outcome']['c4_c8_fit_attempts'],0); self.assertEqual(result['outcome']['pi_steps'],80)
        plans=[e['payload'] for e in journal.events if e['kind']=='PI_PLAN']
        self.assertEqual(plans[0]['at_calls'],0); self.assertEqual(seq.queries,80)
        with self.assertRaises(ValueError): actor.run('push-v3',NumericSequence().current,{'task':'push-v3'},16,actor.Program('NO_PROBE'),lambda _:None,lambda _:None,lambda *_:None)

    def test_no_probe_matches_bounded_original_policy_without_fits(self):
        result,seq,_=numeric_run('NO_PROBE')
        self.assertEqual(seq.n,seq.queries); self.assertEqual(result['outcome']['c4_c8_fit_attempts'],0)
        self.assertTrue(all(r['command']==np.array([.2,-.1,.05,-1.],np.float32).tolist() for r in seq.rows))

    def test_c8_pi_begins_after_eight_real_probes_and_policy_called_once(self):
        result,seq,journal=numeric_run('DIRECT_TASK_PI',.5)
        self.assertEqual(result['outcome']['c4_c8_fit_attempts'],2); self.assertEqual(result['outcome']['pi_steps'],72)
        self.assertEqual(seq.queries,72); self.assertEqual(next(e['payload']['at_calls'] for e in journal.events if e['kind']=='PI_PLAN'),8)
        self.assertEqual([r['command'] for r in seq.rows[:8]],actor.PROBE*2)

    def test_all_move_programs_keep_the_same_physical_movement(self):
        runs=[numeric_run(style,.5 if style in actor.PI_STYLES else None,success_at=130)
              for style in ('MOVE_KEEP_C8','MOVE_INTEGRAL','MOVE_KEEP_TASK_PI','MOVE_INTEGRAL_TASK_PI')]
        prefixes=[]
        for result,seq,journal in runs:
            end=next(e['payload']['at_calls'] for e in journal.events if e['kind']=='POST_MOVE_TASK_ENTRY')
            prefixes.append([(r['command'],r['after']) for r in seq.rows[:end]])
            pi=[e for e in journal.events if e['kind']=='PI_PLAN']
            if pi: self.assertEqual(pi[0]['payload']['at_calls'],end)
            self.assertGreater(result['outcome']['movement_steps'],0)
        self.assertTrue(all(p==prefixes[0] for p in prefixes[1:]))

    def test_three_original_programs_match_frozen_legacy_commands_and_outcomes(self):
        for style in ('DIRECT_C8','MOVE_KEEP_C8','MOVE_INTEGRAL'):
            result,seq,_=numeric_run(style,success_at=130)
            state=seq.states[16]; suffix=NumericSequence(130,state,16); journal=ArrayJournal()
            start=Start('push-v3',16,state,[[1.,0.],[0.,1.]],[0.,0.]); context=tuple(seq.states[14:17])
            legacy=run_movement_task(start,context,method=style,reference=None,policy=suffix.policy,step=suffix.respond,emit=journal)
            self.assertEqual([(r['command'],r['after']) for r in seq.rows[16:]],[(r['command'],r['after']) for r in suffix.rows],style)
            self.assertEqual(result['outcome']['deadline_loss'],legacy['outcome']['deadline_loss'])
            self.assertEqual(result['outcome']['movement_steps'],legacy['outcome']['reposition_steps'])

    def test_saved_plan_and_command_precede_receipt_and_integral_commit(self):
        _,_,journal=numeric_run('DIRECT_TASK_PI',.5,success_at=10)
        kinds=[e['kind'] for e in journal.events]
        for i,k in enumerate(kinds):
            if k=='PI_PLAN': self.assertEqual(kinds[i:i+4],['PI_PLAN','COMMAND','STEP_RESULT','PI_STATE_COMMIT'])
        for entry in journal.events:
            if entry['kind']=='PI_STATE_COMMIT': self.assertEqual(entry['payload']['at_calls'],journal.events[entry['payload']['plan_sequence']]['payload']['at_calls']+1)

    def test_changed_durable_acknowledgement_never_executes_tampered_plan(self):
        journal=ArrayJournal(); seq=NumericSequence()
        def changed(kind,payload):
            saved=journal(kind,payload)
            if kind=='PI_PLAN': saved['plan']['numbers']['sent_command'][0]=1.
            return saved
        with self.assertRaises(ValueError): actor.run('push-v3',seq.current,None,16,actor.Program('RAW_TASK_PI',.5),seq.policy,seq.respond,changed)
        self.assertEqual(seq.n,0)

    def test_failed_physical_receipt_cannot_commit_virtual_integral(self):
        journal=ArrayJournal(); seq=NumericSequence()
        def fail(saved): raise RuntimeError('synthetic physical failure')
        with self.assertRaises(RuntimeError): actor.run('push-v3',seq.current,None,16,actor.Program('RAW_TASK_PI',.5),seq.policy,fail,journal)
        self.assertFalse(any(e['kind']=='PI_STATE_COMMIT' for e in journal.events))

    def test_invalid_cold_fit_stops_without_fallback_and_keeps_500_loss(self):
        for style in ('DIRECT_C8','DIRECT_TASK_PI','MOVE_INTEGRAL_TASK_PI'):
            result,seq,journal=numeric_run(style,.5 if style in actor.PI_STYLES else None,invalid=True)
            self.assertEqual(seq.n,4); self.assertEqual(result['outcome']['deadline_loss'],500)
            self.assertEqual(result['outcome']['stop_reason'],'INVALID_FOUR')
            self.assertFalse(any(e['kind']=='PI_PLAN' for e in journal.events))

    def test_early_success_and_full_deadline_preserve_actual_denominator(self):
        result,seq,_=numeric_run('DIRECT_TASK_PI',.5,success_at=2)
        self.assertEqual(seq.n,2); self.assertEqual(result['outcome']['deadline_loss'],2); self.assertEqual(seq.queries,0)
        result,seq,_=numeric_run('RAW_TASK_PI',.5,success_at=None)
        self.assertEqual(seq.n,500); self.assertEqual(result['outcome']['deadline_loss'],500); self.assertEqual(result['outcome']['stop_reason'],'DEADLINE')


if __name__=='__main__': unittest.main()
