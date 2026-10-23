"""Pure arrays and finite algebra; no environment construction, fitting or API."""
from dataclasses import replace,asdict
from copy import deepcopy
import unittest
import numpy as np
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe.task_memory_option_v1 import TaskMemory,TaskMemoryMachine
from src.probe.task_passive_pi_v1 import PIQuery,PIPlan
from src.analysis import two_stage_terminal_dr_v1 as d
from src.analysis import memory_terminal_world_v1 as w


def obs(x=0.,*,success=False):return StepObservation((x,)+tuple(0. for _ in range(38)),False,False,success)
def machine(task='push-v3'):return TaskMemoryMachine(replace(TaskMemory.initial(task,obs()),integral_xy=(.2,-.1)))


class MemoryTests(unittest.TestCase):
    def test_task_plan_matches_original_PI_exactly_for_all_tasks(self):
        for task in ('push-v3','reach-v3','door-open-v3'):
            m=machine(task);raw=np.array([.1,-.2,.3,1],np.float32);q=PIQuery.create(task,0,m.memory.current,raw,m.memory.base(),m.memory.integral_xy,.5)
            saved=m.plan(raw);self.assertEqual(saved['pi_plan'],PIPlan(q).to_dict())
            after=m.commit(saved,StepReceipt(obs(.01),1));self.assertEqual(list(after.integral_xy),PIPlan(q).numbers()['integral_after_receipt'])
    def test_move_resume_preserves_memory_and_uses_new_actual_state(self):
        m=machine();before=m.memory;token=m.suspend();after=m.resume(token,[StepReceipt(obs(.1),1),StepReceipt(obs(.2),2)])
        self.assertEqual(after.integral_xy,before.integral_xy);self.assertEqual(after.saved_controller,before.saved_controller)
        self.assertEqual(after.completed_steps,2);self.assertEqual(after.current,obs(.2))
    def test_task_validation_steps_commit_integral_instead_of_freezing_it(self):
        m=machine();before=m.memory.integral_xy
        for i in (1,2):saved=m.plan(np.array([.1,.1,0,0],np.float32));m.commit(saved,StepReceipt(obs(.01*i),i))
        self.assertNotEqual(m.memory.integral_xy,before)
    def test_zero_length_resume_and_token_single_use(self):
        m=machine();token=m.suspend();before=m.memory;m.resume(token,[]);self.assertEqual(m.memory,before)
        with self.assertRaises(ValueError):m.resume(token,[])
    def test_jump_after_end_and_budget_receipts_rejected(self):
        m=machine();token=m.suspend()
        with self.assertRaises(ValueError):m.resume(token,[StepReceipt(obs(),2)])
        with self.assertRaises(ValueError):m.resume(token,[StepReceipt(obs(success=True),1),StepReceipt(obs(),2)])
        m=TaskMemoryMachine(replace(machine().memory,completed_steps=499));token=m.suspend()
        with self.assertRaises(ValueError):m.resume(token,[StepReceipt(obs(),500),StepReceipt(obs(),501)])
    def test_rate_change_carries_or_explicitly_resets_and_changes_send(self):
        old=machine();carry=machine();reset=machine();raw=np.array([.1,.1,0,0],np.float32)
        old_send=old.plan(raw)['pi_plan']['numbers']['sent_command'];event=carry.set_rate(.125,memory_mode='CARRY')
        self.assertEqual(carry.memory.integral_xy,(.2,-.1));self.assertFalse(event['bumpless_transfer_established'])
        self.assertNotEqual(carry.plan(raw)['pi_plan']['numbers']['sent_command'],old_send)
        reset.set_rate(.125,memory_mode='EXPLICIT_RESET');self.assertEqual(reset.memory.integral_xy,(0.,0.))
        self.assertNotEqual(reset.plan(raw)['pi_plan']['numbers']['sent_command'],old_send)
    def test_private_future_or_oracle_controller_memory_fields_rejected(self):
        state=machine().memory.to_dict();state['future_success']=True
        with self.assertRaises(ValueError):TaskMemory.from_dict(state)
        state=machine().memory.to_dict();state['controller']['source']='ORACLE'
        with self.assertRaises(ValueError):TaskMemory.from_dict(state)
    def test_modified_command_and_stale_memory_rejected(self):
        m=machine();saved=m.plan(np.array([.1,0,0,0],np.float32));bad=deepcopy(saved);bad['pi_plan']['numbers']['sent_command'][0]+=.1
        with self.assertRaises(ValueError):m.commit(bad,StepReceipt(obs(),1))
        m.commit(saved,StepReceipt(obs(),1))
        with self.assertRaises(ValueError):m.commit(saved,StepReceipt(obs(),2))


class TerminalValueTests(unittest.TestCase):
    def test_complete_finite_model_has_44_atoms_and_unit_probability(self):
        atoms=w.atoms();self.assertEqual(len(atoms),44);self.assertAlmostEqual(sum(a['probability_under_true_behavior'] for a in atoms),1,places=14)
        self.assertTrue(all(a['synthetic_finite_model_atom'] for a in atoms))
    def test_all_40_stagewise_correct_mean_identities(self):
        for first in w.FIRST_POLICIES:
            for tail in w.TAIL_POLICIES:
                for mode in w.MODES[:-1]:
                    mean=0.
                    for atom in w.atoms():
                        r=d.LoggedTerminal.from_dict(atom['record']);mean+=atom['probability_under_true_behavior']*d.estimate(r,**w.inputs(r.before,r.after,mode,first,tail))['whole_DR']
                    self.assertAlmostEqual(mean,w.target_truth(first,tail),places=10)
    def test_both_wrong_bias_is_retained_not_silently_passed(self):
        first='ONLY_CONTINUE';tail='KEEP_ONLY';mean=0.
        for atom in w.atoms():
            r=d.LoggedTerminal.from_dict(atom['record']);mean+=atom['probability_under_true_behavior']*d.estimate(r,**w.inputs(r.before,r.after,'BOTH_WRONG',first,tail))['whole_DR']
        self.assertGreater(abs(mean-w.target_truth(first,tail)),1)
    def test_behavior_marginal_is_not_the_poststate_adoption_policy_value(self):
        before=w.pre(1);truth=before.completed_steps+w.true_q1(before,'POSTSTATE_ADAPTIVE')[2]
        direct=before.completed_steps+w.true_q1(before,'POSTSTATE_ADAPTIVE')[0]
        selected=[a for a in w.atoms() if a['record']['before']['observed_code']==1 and a['record']['action']=='MOVE_VALIDATE']
        marginal=sum(a['probability_under_true_behavior']*a['record']['full_deadline_loss'] for a in selected)/sum(a['probability_under_true_behavior'] for a in selected)
        self.assertLess(truth,direct);self.assertGreater(marginal,direct)
    def test_terminal_option_has_no_fake_tail_action_or_probability(self):
        atom=next(a for a in w.atoms() if a['record']['option_ended']=='SUCCESS');row=d.LoggedTerminal.from_dict(atom['record'])
        inputs=w.inputs(row.before,row.after,'P_TRUE_Q_WRONG','MIXED','KEEP_ONLY');self.assertIsNone(inputs['behavior2'])
        inputs['behavior2']=[.5,.5]
        with self.assertRaises(ValueError):d.estimate(row,**inputs)
    def test_failure_penalty_and_actual_cost_are_distinct(self):
        r=next(d.LoggedTerminal.from_dict(a['record']) for a in w.atoms() if a['record']['option_ended']=='FAILURE')
        self.assertEqual(r.full_deadline_loss,500);self.assertLess(r.before.completed_steps+r.option_actual_steps,500)
        result=d.estimate(r,**w.inputs(r.before,r.after,'P_TRUE_Q_ZERO','MIXED','KEEP_ONLY'))
        self.assertEqual(result['observed_terminal_remaining_loss'],500-r.before.completed_steps-r.option_actual_steps)
    def test_unsupported_target_and_zero_chosen_probability_rejected(self):
        r=d.LoggedTerminal.from_dict(w.atoms()[0]['record']);params=w.inputs(r.before,r.after,'P_TRUE_Q_ZERO','ONLY_MOVE','KEEP_ONLY');params['behavior1']=[1.,0.,0.]
        with self.assertRaisesRegex(ValueError,'unsupported'):d.estimate(r,**params)
    def test_invalid_nonfinite_and_incomplete_probabilities_rejected(self):
        for p in ([.3,.3,float('nan')],[.3,.3,.3],[True,0,0]):
            with self.assertRaises(ValueError):d.probabilities(p,3)
    def test_private_future_query_fields_rejected(self):
        pre=w.pre(0).to_dict();pre['seed']=7
        with self.assertRaises(ValueError):d.History1.from_dict(pre)
        post=w.post(w.pre(0),'VALIDATE','NEAR').to_dict();post['true_validity']=True
        with self.assertRaises(ValueError):d.History2.from_dict(post)
    def test_wrong_parent_and_future_clock_cannot_form_a_branch(self):
        r=next(d.LoggedTerminal.from_dict(a['record']) for a in w.atoms() if a['record']['option_ended']=='NONE')
        with self.assertRaises(ValueError):replace(r,after=replace(r.after,prehistory_sha256='0'*64))
        with self.assertRaises(ValueError):replace(r,after=replace(r.after,completed_steps=r.after.completed_steps+1))
    def test_predictions_do_not_take_the_future_tail_result(self):
        atoms=[a for a in w.atoms() if a['record']['option_ended']=='NONE'];left=d.LoggedTerminal.from_dict(atoms[0]['record']);right=d.LoggedTerminal.from_dict(atoms[1]['record'])
        self.assertNotEqual(left.full_deadline_loss,right.full_deadline_loss)
        self.assertEqual(w.inputs(left.before,left.after,'P_WRONG_Q_TRUE','MIXED','POSTSTATE_ADAPTIVE'),w.inputs(right.before,right.after,'P_WRONG_Q_TRUE','MIXED','POSTSTATE_ADAPTIVE'))
    def test_DR_values_outside_loss_range_are_not_clipped(self):
        values=[]
        for a in w.atoms():
            r=d.LoggedTerminal.from_dict(a['record']);v=d.estimate(r,**w.inputs(r.before,r.after,'P_TRUE_Q_WRONG','ONLY_VALIDATE','KEEP_ONLY'))
            self.assertFalse(v['estimate_clipped']);values.append(v['whole_DR'])
        self.assertTrue(min(values)<0 or max(values)>500)


if __name__=='__main__':unittest.main()
