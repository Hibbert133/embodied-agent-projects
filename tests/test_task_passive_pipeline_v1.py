"""Synthetic arrays and journal rows only. No Env or online API calls."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
import unittest
from unittest.mock import patch
import numpy as np
from src.analysis import task_passive_io_v1 as allocation
from src.analysis import task_passive_audit_v1 as audit
from src.analysis import task_passive_statistics_v1 as stats
from src.analysis.short_probe_journal_audit_v1 import ledger_add,simulation
from tests.test_task_passive_host_v1 import ArrayJournal,ArithmeticLedger,ArraySession,NumericPolicy,spec,fit_patches


def cases(losses=None):
    result=[]; losses=losses or {}
    for s in allocation.population('DEV'):
        key=(s['style'],s['time_constant_s']); loss=losses.get(key,100)
        result.append({**s,'completed':True,'error':None,'close_error':None,'success':loss<500,'total_steps':loss,
            'deadline_loss':loss,'movement_steps':0,'pi_steps':0,'boundary_applied':loss>16,
            'boundary_missing_reason':None if loss>16 else 'EARLY_SUCCESS','stop_reason':'SUCCESS' if loss<500 else 'DEADLINE'})
    return result


def synthetic_record(s=None,success_at=25):
    s=s or spec(); journal=ArrayJournal(); private=ArrayJournal(); ledger=ArithmeticLedger()
    journal.emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
    for phase,count in (('GOAL_GENERATION',50),('CONTROLLED_RESET',1)):
        if phase=='CONTROLLED_RESET': journal.emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
        for _ in range(count):
            before=ledger.snapshot(); ledger.value=ledger_add(ledger.value,phase,'reset_attempts',1)
            intent=journal.emit('LIFECYCLE_RESET_INTENT',{'phase':phase,'before':before})
            ledger.value=simulation(ledger.value,phase,100,500); ledger.value=ledger_add(ledger.value,phase,'reset_completed',1)
            journal.emit('LIFECYCLE_RESET_COMPLETE',{'phase':phase,'intent_sequence':intent['sequence'],'after':ledger.snapshot()})
    session=ArraySession(s,journal,success_at=success_at,ledger=ledger); initial=asdict(session.public())
    journal.emit('CONTROLLED_INITIAL',{'task':s['task'],'observation':initial['observation'],'simulation_time':0.,'ledger':ledger.snapshot()})
    journal.emit('NOISE_COMMITMENT',{'at_calls':0,'noise_namespace_oracle':s['noise_namespace'],'tape_sha256_oracle':allocation.io.digest(session.ctx['noise_rows'].tolist())})
    refs=[]
    def witness(label):
        expected=session.witness(); anchor=journal.rows[-1]; start=perf_counter_ns(); w={'native_sha256':expected['native_sha256'],'comparison_python_sha256':expected['python_semantic_sha256']}
        saved=private.emit('STATE_WITNESS',{'label':label,'logical_step':session.ctx['calls'],'source_anchor_sequence':anchor['sequence'],
            'source_anchor_saved_ns':anchor['saved_ns'],'started_ns':start,'completed_ns':perf_counter_ns(),
            'ledger_before':ledger.snapshot(),'ledger_after':ledger.snapshot(),'source_witness':expected,'witness':w})
        refs.append({'label':label,'sequence':saved['sequence'],'logical_step':session.ctx['calls'],**w})
        return (w['native_sha256'],w['comparison_python_sha256'],expected['noise_past_sha256'],expected['simulation_time'])
    witness('INITIAL')
    from src.analysis.task_passive_host_v1 import run_live
    with fit_patches(): outcome=run_live(s,{'task':s['task']},session,witness,lambda:None)
    case={**s,**outcome,'completed':True,'error':None,'close_error':None,'environment_closed':True,'ledger_before':{'counts':{},'by_phase':{}},
        'initial_fault_oracle':allocation.initial_fault(),'destination_oracle':allocation.destination(s),
        'initial':initial,'final':asdict(session.public()),'captures':0,'restores':0,'physical_rows_count':session.completed,
        'host_attempts':session.completed,'host_returned':session.completed,'ledger_before_close':ledger.snapshot(),'ledger_after_close':ledger.snapshot(),
        'state_witness_refs':refs}
    return s,case,journal.rows,private.rows


def audit_numeric(record):
    from contextlib import ExitStack
    with ExitStack() as stack:
        stack.enter_context(fit_patches()); stack.enter_context(patch('src.rollout.task_registry.create_task_policy',return_value=NumericPolicy()))
        stack.enter_context(patch('src.analysis.continuous_state_witness_v1.verify_witness'))
        stack.enter_context(patch('src.analysis.continuous_state_witness_v1.compare_witnesses',side_effect=lambda a,b:{'comparison_equal':a==b}))
        s,c,e,p=record
        return audit.audit_case(s,c,e,p,{'task':s['task']},{'counts':{},'by_phase':{}})


class TaskAllocationTests(unittest.TestCase):
    def test_full_registered_populations_and_independent_seed_ranges(self):
        pop=[allocation.population(c,{s:2. for s in allocation.PI_STYLES} if c=='QUAL' else None) for c in allocation.COHORTS]
        self.assertEqual(list(map(len,pop)),[36,720,432]); seeds=[{s['seed'] for s in p} for p in pop]
        self.assertFalse(any(seeds[i]&seeds[j] for i in range(3) for j in range(i)))
        for p in pop: self.assertEqual(len({s['case_id'] for s in p}),len(p))
    def test_full_cost_ceiling_counts_all_factory_resets_and_frames(self):
        x=allocation.expected_config()['combined_limits']
        self.assertEqual((x['executions'],x['control_steps'],x['all_resets'],x['physical_frames'],x['online_c4_c8_fit_attempts']),
            (1188,594000,60588,33264000,1782))
    def test_noise_is_initial_immutable_and_common_only_inside_allocated_unit(self):
        s=spec(); a=allocation.noise(s['seed'],s['noise_namespace']); self.assertFalse(a.flags.writeable)
        np.testing.assert_array_equal(a,allocation.noise(s['seed'],s['noise_namespace']))
        self.assertFalse(np.array_equal(a,allocation.noise(s['seed'],120004)))
    def test_exact_specs_reject_unregistered_seed_parameter_and_budget(self):
        for k,v in (('seed',63018),('time_constant_s',.3),('maximum_steps',501)):
            s=spec(); s[k]=v
            with self.assertRaises(ValueError): allocation.validate_spec(s)
    def test_selection_uses_full_loss_and_prespecified_ties(self):
        c=cases(); v=stats.choose(c)
        self.assertTrue(all(t==8. for t in v['selected_time_constants_s'].values())); self.assertEqual(v['primary_style'],'RAW_TASK_PI')
        self.assertFalse(v['development_gate_passed'])
        v=stats.choose(cases({('DIRECT_TASK_PI',.5):20}))
        self.assertEqual(v['primary_program'],'DIRECT_TASK_PI_T0.5'); self.assertTrue(v['development_gate_passed'])
    def test_missing_failures_or_reordered_cases_cannot_select(self):
        c=cases(); c[0]['success']=False; c[0]['deadline_loss']=0
        with self.assertRaises(ValueError): stats.choose(c)
        for v in (cases()[:-1],list(reversed(cases()))):
            with self.assertRaises(ValueError): stats.choose(v)
    def test_all_secondary_pairs_and_task_context_cells_retained(self):
        v=stats.summarize(cases(),'DEV',primary='RAW_TASK_PI_T8.0')
        self.assertEqual(len(v['all_paired_secondary_comparisons']),190); self.assertEqual(len(v['complete_task_context_cells']),120)
    def test_bootstrap_clusters_whole_groups_and_known_constant_difference(self):
        v=stats.bootstrap({g:7. for g in range(9)},'QUAL'); self.assertEqual((v['mean'],v['lower95'],v['upper95']),(7.,7.,7.))
        with self.assertRaises(ValueError): stats.bootstrap({0:0.},'QUAL')


class TaskRecordTests(unittest.TestCase):
    def test_synthetic_full_lifecycle_continuous_task_and_pi_arithmetic(self):
        record=synthetic_record(); ledger,result=audit_numeric(record)
        self.assertEqual(ledger['counts']['reset_completed'],51); self.assertEqual(ledger['counts']['simulation_frames_completed'],51*500+25*5)
        self.assertEqual(result['costs']['pi_plans'],17); self.assertEqual(result['costs']['independent_c4_c8_refits'],2)
    def test_early_success_before_boundary_and_before_fit_remains_observed(self):
        r=synthetic_record(success_at=2); _,v=audit_numeric(r)
        self.assertFalse(r[1]['boundary_applied']); self.assertEqual(r[1]['deadline_loss'],2)
        self.assertEqual(v['costs'].get('pi_plans',0),0)
    def test_all_move_variants_audit_actual_post_movement_without_reset(self):
        for style in ('MOVE_KEEP_C8','MOVE_INTEGRAL','MOVE_KEEP_TASK_PI','MOVE_INTEGRAL_TASK_PI'):
            r=synthetic_record(spec(style,None if style in allocation.CONTROLS else .5),success_at=110); _,v=audit_numeric(r)
            self.assertIsNotNone(v['movement_end']); self.assertEqual(r[1]['total_steps'],110)
    def test_wrong_noise_cursor_or_final_execution_order_is_rejected(self):
        r=synthetic_record(); row=next(e for e in r[2] if e['event']=='STEP_COMPLETE'); row['noise_cursor_after']+=1
        with self.assertRaisesRegex(ValueError,'cursor'): audit_numeric(r)
        r=synthetic_record(); row=next(e for e in r[2] if e['event']=='STEP_COMPLETE'); row['executed_action_oracle'][0]+=.01
        with self.assertRaisesRegex(ValueError,'transform/noise'): audit_numeric(r)
    def test_duplicate_boundary_clock_rewind_and_hidden_reset_rejected(self):
        for kind in ('boundary','clock','reset'):
            r=synthetic_record()
            if kind=='boundary':
                at=next(i for i,e in enumerate(r[2]) if e['event']=='FAULT_BOUNDARY'); r[2].insert(at+1,deepcopy(r[2][at]))
            elif kind=='clock': next(e for e in r[2] if e['event']=='STEP_COMPLETE')['simulation_time_after']-=1
            else:
                at=next(i for i,e in enumerate(r[2]) if e['event']=='STEP_COMPLETE'); r[2].insert(at,{'event':'LIFECYCLE_RESET_INTENT','phase':'CONTROLLED_RESET'})
            with self.assertRaises(ValueError): audit_numeric(r)
    def test_plan_saved_after_action_and_future_policy_data_rejected(self):
        r=synthetic_record(); command=next(e for e in r[2] if e['event']=='AGENT_EVENT' and e['agent_event']=='COMMAND'); command['saved_ns']=10**25
        with self.assertRaisesRegex(ValueError,'saved after'): audit_numeric(r)
        r=synthetic_record(); raw=next(e for e in r[2] if e['event']=='AGENT_EVENT' and e['agent_event']=='PI_PLAN')['public_payload']['plan']['query']['raw_policy']; raw[0]+=.1
        with self.assertRaises(ValueError): audit_numeric(r)
    def test_changed_saved_arithmetic_and_virtual_integral_commit_rejected(self):
        for key in ('integral_proposed','integral_after_receipt'):
            r=synthetic_record(); plan=next(e for e in r[2] if e['event']=='AGENT_EVENT' and e['agent_event']=='PI_PLAN')['public_payload']['plan']; plan['numbers'][key][0]+=.01
            with self.assertRaises(ValueError): audit_numeric(r)
    def test_source_numeric_mapping_cannot_be_swapped_for_fault_oracle(self):
        r=synthetic_record(); plan=next(e for e in r[2] if e['event']=='AGENT_EVENT' and e['agent_event']=='PI_PLAN')['public_payload']['plan']
        plan['query']['controller']['source']='ORACLE_EVALUATOR'
        with self.assertRaises(ValueError): audit_numeric(r)


if __name__=='__main__': unittest.main()
