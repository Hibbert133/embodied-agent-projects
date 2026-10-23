"""Synthetic callback traces only; fixed policy queried once per task command."""
from copy import deepcopy
from unittest.mock import patch
import unittest
import numpy as np
from src.probe import response_action_program_v1 as actor
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.analysis.response_action_io_v1 import io
from tests.test_response_action_rank_v1 import fixture


def run_synthetic(sign=1.,success_at=13,invalid=False,tamper=False,old_style=False):
    q,model,_=fixture(sign);current=q.current;n=0;events=[];commands=[];queries=[]
    nominal=io.read(io.ROOT/io.C8)['joint']['push-v3']
    fit={'valid':not invalid,'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'nfev':0}
    def emit(kind,payload):
        v={'sequence':len(events),'saved_ns':len(events)+1,**deepcopy(payload)}
        if tamper and kind=='RANK_PLAN':v['plan']['numbers']['selected_action_id']='BASELINE'
        events.append({'kind':kind,'payload':deepcopy(v)});return v
    def policy(o):queries.append(o.copy());return np.array([.5,0.,0.,0.],np.float32)
    def step(saved):
        nonlocal current,n
        commands.append(deepcopy(saved));n+=1;o=np.asarray(current.observation).copy();o[:3]+=.001*np.asarray(saved['command'])[:3]
        current=StepObservation(o.tolist(),terminated=False,truncated=False,success=n>=success_at);return StepReceipt(current,n)
    program=actor.Program('DIRECT_C8') if old_style else actor.Program('F20_RANK',regularization_weight=.1)
    with patch.object(actor.old,'infer_four',return_value=fit),patch.object(actor.old,'infer_operator',return_value=fit):
        result=actor.run('push-v3',q.current,nominal,16,program,policy,step,emit,None if old_style else model)
    return result,events,commands,queries


class RankProgramTests(unittest.TestCase):
    def test_saved_plan_drives_each_actual_command_and_once_policy(self):
        result,events,commands,queries=run_synthetic()
        self.assertEqual(result['outcome']['total_steps'],13);self.assertEqual(result['outcome']['rank_steps'],5)
        self.assertEqual(result['outcome']['response_model_forward_evaluations'],50);self.assertEqual(len(queries),5)
        plans={e['payload']['plan_sha256']:e['payload']['plan'] for e in events if e['kind']=='RANK_PLAN'}
        for cmd in commands[8:]:
            p=plans[cmd['rank_plan_sha256']];self.assertEqual(cmd['command'],p['numbers']['selected_command'])
            self.assertEqual(cmd['raw_policy'],p['query']['raw_policy'])
        self.assertEqual([e['payload']['plan']['query']['observation_steps'] for e in events if e['kind']=='RANK_PLAN'][0],[6,7,8])
    def test_different_legal_model_choices_change_executed_task_commands(self):
        _,_,a,_=run_synthetic(sign=1.);_,_,b,_=run_synthetic(sign=-1.)
        self.assertEqual([c['command'] for c in a[:8]],[c['command'] for c in b[:8]])
        self.assertNotEqual(a[8]['command'],b[8]['command'])
    def test_early_success_does_not_force_fit_or_rank(self):
        result,events,commands,queries=run_synthetic(success_at=3)
        self.assertTrue(result['outcome']['success']);self.assertEqual(result['outcome']['rank_steps'],0);self.assertEqual(len(queries),0)
        self.assertFalse(any(e['kind']=='FIT_INTENT' for e in events))
    def test_invalid_fit_kept_at_loss500_without_substitution(self):
        result,events,commands,queries=run_synthetic(invalid=True)
        self.assertEqual(result['outcome']['stop_reason'],'INVALID_FOUR');self.assertEqual(result['outcome']['deadline_loss'],500)
        self.assertEqual(len(commands),4);self.assertEqual(len(queries),0)
    def test_changed_acknowledgement_rejected_before_task_execution(self):
        with self.assertRaises(ValueError):run_synthetic(tamper=True)
    def test_old_direct_program_has_no_response_predictor_or_rank(self):
        result,events,commands,queries=run_synthetic(old_style=True)
        self.assertEqual(result['outcome']['rank_steps'],0);self.assertEqual(result['outcome']['response_model_forward_evaluations'],0)
        self.assertFalse(any(e['kind'].startswith('RANK') for e in events));self.assertEqual(len(queries),5)
    def test_old_pi_parameters_are_locked_and_rank_weight_not_time_constant(self):
        for s,ti in actor.LOCKED_PI.items():
            self.assertEqual(actor.Program(s,ti).time_constant_s,ti)
            with self.assertRaises(ValueError):actor.Program(s,8.)
        with self.assertRaises(ValueError):actor.Program('F20_RANK',time_constant_s=.1)
        with self.assertRaises(ValueError):actor.Program('KINEMATIC_RANK',regularization_weight=.1)


if __name__=='__main__':unittest.main()
