"""Float32 plan and immutable selection tests; no robot, network or model fit."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import unittest
import numpy as np
from src.probe import command_contrast_v1 as core
from src.probe.linear_command_preflight_v1 import LinearCommandModel,DIMENSIONS,COMMAND_SLICES,make_query


def models(task='push-v3'):
    result={}
    for source in ('FEEDBACK8','BALANCED8'):
        for feature in ('H10','F20','F43'):
            n=DIMENSIONS[feature]; coefficients=np.zeros((n+1,2)); start=COMMAND_SLICES[feature].start
            coefficients[start+1,0]=.002; coefficients[start+2,1]=.003; coefficients[0]=[.01,.02]
            key=f'{source}/{task}/LINEAR_{feature}'
            result[key]=(LinearCommandModel(task,feature,np.zeros(n),np.ones(n),coefficients),hashlib.sha256(key.encode()).hexdigest())
    return result


def query(step=5,baseline=(.12345679,-.7654321,.3,-1.)):
    history=np.arange(117,dtype=float).reshape(3,39)/1000
    return core.PhysicalQuery.create('push-v3',step,history,core.sent32(baseline))


class PhysicalPlanTests(unittest.TestCase):
    def test_float32_rounding_is_applied_before_predicting(self):
        q=query(); ideal=make_query(q.task,q.decision_step,q.observations,q.baseline_command)
        actual=dict(q.candidates)['X_PLUS']; unrounded=ideal.candidates[0].command
        self.assertNotEqual(actual,unrounded)
        self.assertEqual(core.sent32(actual),actual)
        plan=core.SavedPlan.build(q,models()); row=plan.to_dict()['models']['FEEDBACK8/push-v3/LINEAR_F20']['predictions_m']
        self.assertAlmostEqual(row[1][0]-row[0][0],.002*(actual[0]-q.baseline_command[0]),15)
        self.assertNotEqual(row[1][0]-row[0][0],.002*(unrounded[0]-q.baseline_command[0]))

    def test_unquantized_baseline_and_ideal_candidates_rejected(self):
        q=query()
        with self.assertRaises(ValueError): core.PhysicalQuery.create(q.task,5,q.observations,(.1,0.,0.,0.))
        invalid=list(q.candidates); invalid[1]=('X_PLUS',make_query(q.task,5,q.observations,q.baseline_command).candidates[0].command)
        with self.assertRaises(ValueError): replace(q,candidates=invalid)

    def test_all_five_candidates_and_two_frozen_source_banks(self):
        q=query(); plan=core.SavedPlan.build(q,models())
        self.assertEqual([x[0] for x in q.candidates],list(core.BRANCHES)); self.assertEqual(len(plan.predictions),6)
        incomplete=models(); incomplete.pop(next(iter(incomplete)))
        with self.assertRaises(ValueError): core.SavedPlan.build(q,incomplete)
        wrong=models(); key='FEEDBACK8/push-v3/LINEAR_F20'; wrong[key]=wrong['FEEDBACK8/push-v3/LINEAR_H10']
        with self.assertRaises(ValueError): core.SavedPlan.build(q,wrong)

    def test_public_query_and_plan_reject_nested_oracle_fields(self):
        q=query(); plan=core.SavedPlan.build(q,models())
        for field in ('seed','actual_noise','true_operator','future_result','private_state'):
            raw=q.to_dict(); raw[field]=0
            with self.assertRaises(ValueError): core.PhysicalQuery.from_dict(raw)
            raw=q.to_dict(); raw['candidates'][0][field]=0
            with self.assertRaises(ValueError): core.PhysicalQuery.from_dict(raw)
            raw=plan.to_dict(); raw['models'][next(iter(raw['models']))][field]=0
            with self.assertRaises(ValueError): core.SavedPlan.from_dict(raw)

    def test_real_history_and_time_stamps_required(self):
        q=query()
        with self.assertRaises(ValueError): replace(q,observation_steps=(3,4,6))
        with self.assertRaises(ValueError): replace(q,observations=q.observations[1:])
        with self.assertRaises(ValueError): replace(q,decision_step=1)

    def test_plan_roundtrip_and_copied_dictionary_cannot_mutate_saved_commands(self):
        plan=core.SavedPlan.build(query(),models()); digest=plan.digest(); raw=plan.to_dict()
        self.assertEqual(core.SavedPlan.from_dict(raw),plan)
        raw['query']['candidates'][1]['sent_command'][0]=-1.
        self.assertEqual(plan.digest(),digest)

    def test_saved_selection_changes_the_command_and_synthetic_response(self):
        q=query(); plan=core.SavedPlan.build(q,models()); responses=[]
        for action_id in ('X_PLUS','X_MINUS'):
            selected=core.PlanConsumer(plan).consume(q,action_id,1)
            observed=np.asarray(selected['sent_command'],np.float32)[:2]*.002
            responses.append(observed)
            self.assertEqual(tuple(selected['sent_command']),dict(q.candidates)[action_id])
        self.assertNotEqual(responses[0][0],responses[1][0])

    def test_plan_is_bound_to_the_actual_current_observations(self):
        q=query(); plan=core.SavedPlan.build(q,models()); changed=np.asarray(q.observations)+.1
        with self.assertRaises(ValueError): core.PlanConsumer(plan).consume(replace(q,observations=changed),'BASELINE',1)

    def test_invalid_action_budget_and_repeated_consumption_rejected(self):
        q=query(); consumer=core.PlanConsumer(core.SavedPlan.build(q,models()))
        for budget in (0,-1,True):
            with self.assertRaises(ValueError): consumer.consume(q,'BASELINE',budget)
        with self.assertRaises(ValueError): consumer.consume(q,'OTHER',1)
        consumer.consume(q,'BASELINE',1)
        with self.assertRaises(ValueError): consumer.consume(q,'BASELINE',1)

    def test_saturated_labels_remain_in_the_denominator(self):
        q=query(baseline=(1.,-1.,0.,-1.)); plan=core.SavedPlan.build(q,models()); sent=dict(q.candidates)
        self.assertEqual(sent['BASELINE'],sent['X_PLUS']); self.assertEqual(sent['BASELINE'],sent['Y_MINUS'])
        self.assertEqual(len(sent),5)
        for _,_,values in plan.predictions:
            self.assertEqual(values[0],values[1]); self.assertEqual(values[0],values[4])

    def test_no_plan_can_claim_physical_or_task_qualification(self):
        raw=core.SavedPlan.build(query(),models()).to_dict()
        self.assertFalse(raw['physical_qualification']); self.assertFalse(raw['task_benefit'])
        raw['physical_qualification']=True
        with self.assertRaises(ValueError): core.SavedPlan.from_dict(raw)

    def test_prescribed_intervention_stage_selection(self):
        self.assertTrue(core.reaches_target('COLD_STEP2',{'at_calls':2,'phase':'FIXED_PROBE'}))
        self.assertFalse(core.reaches_target('COLD_STEP2',{'at_calls':3,'phase':'FIXED_PROBE'}))
        self.assertTrue(core.reaches_target('POST_MOVE_MEAS0',{'at_calls':32,'phase':'MEASURE_BALANCED'}))
        self.assertTrue(core.reaches_target('POST_MEASURE_TASK0',{'at_calls':40,'phase':'TASK_AFTER_MEASUREMENT'}))


if __name__=='__main__': unittest.main()
