"""Pure allocation/statistics/record checks, no robot construction or fitting."""
import unittest
from copy import deepcopy
from unittest.mock import patch
from contextlib import ExitStack
import numpy as np
from src.analysis import response_action_io_v1 as allocation
from src.analysis import response_action_statistics_v1 as stats


def synthetic_cases(cohort='DEV',weight=None):
    rows=[]
    for spec in allocation.population(cohort,weight):
        loss=20 if spec['style']=='F20_RANK' else 40
        rows.append({**spec,'completed':True,'error':None,'close_error':None,'success':True,'total_steps':loss,'deadline_loss':loss,
            'rank_steps':0,'pi_steps':0,'movement_steps':0,'response_model_forward_evaluations':0,'kinematic_proxy_evaluations':0})
    return rows


class RankAllocationTests(unittest.TestCase):
    def test_full_cohorts_and_all_old_strong_references(self):
        for cohort,n in (('SOFTWARE_NATIVE',36),('DEV',432),('QUAL',540)):
            specs=allocation.population(cohort,.1 if cohort=='QUAL' else None);self.assertEqual(len(specs),n)
            self.assertEqual(len({s['style'] for s in specs}),10)
            self.assertTrue(all(s['maximum_steps']==500 for s in specs))
        self.assertEqual(allocation.limits('QUAL')['all_resets'],27540)
        self.assertEqual(sum(allocation.limits(c)['physical_frames'] for c in allocation.COHORTS),28224000)
    def test_distinct_phase_seeds_reserved_ranges_and_noise_domains(self):
        sets=[{s['seed'] for s in allocation.population(c,.1 if c=='QUAL' else None)} for c in allocation.COHORTS]
        for i in range(3):
            for j in range(i):self.assertFalse(sets[i]&sets[j])
        a=allocation.noise(64000,130002);self.assertFalse(a.flags.writeable);np.testing.assert_array_equal(a,allocation.noise(64000,130002))
        self.assertFalse(np.array_equal(a,allocation.noise(64000,130004)))
    def test_illegal_spec_extra_or_reserved_seed_rejected(self):
        s=allocation.population('DEV')[0];allocation.validate_spec(s)
        for key,value in (('seed',64018),('oracle',{}),('maximum_steps',501)):
            x=dict(s);x[key]=value
            with self.assertRaises(ValueError):allocation.validate_spec(x)
    def test_one_global_weight_ties_largest_no_task_selection(self):
        result=stats.choose(synthetic_cases());self.assertEqual(result['selected_F20_weight'],10.);self.assertTrue(result['development_gate_passed'])
    def test_strong_raw_pi_and_kinematic_each_can_block_development(self):
        for style in ('RAW_TASK_PI','KINEMATIC_RANK'):
            cases=synthetic_cases()
            for c in cases:
                if c['style']==style:c['total_steps']=c['deadline_loss']=10
            self.assertFalse(stats.choose(cases)['development_gate_passed'])
    def test_no_missing_failures_or_success_loss_substitution(self):
        c=synthetic_cases();c[0]['success']=False;c[0]['deadline_loss']=500
        self.assertEqual(stats.summary_rows(c,'DEV')[0]['all_failure_ids'],[c[0]['case_id']])
        with self.assertRaises(ValueError):stats.choose(c[:-1])
        c[0]['deadline_loss']=c[0]['total_steps']
        with self.assertRaises(ValueError):stats.choose(c)
    def test_four_primary_contrasts_and_whole_group_unit(self):
        v=stats.summarize(synthetic_cases('QUAL',1.),'QUAL',1.,'F20_RANK_W1.0')
        self.assertEqual(len(v['primary_comparisons']),4);self.assertEqual(v['qualification_gate'],'PASSED_ENGINEERING_CONTROL_REFERENCE_ONLY')
        self.assertEqual(len(v['complete_task_context_cells']),60)
        r=stats.bootstrap({g:1. for g in range(9)},'QUAL');self.assertEqual((r['mean'],r['lower95'],r['upper95']),(1.,1.,1.))
    def test_original_sources_and_models_load_without_refit(self):
        nominal,models,hashes=allocation.source_models();self.assertEqual(set(nominal),set(allocation.GAINS));self.assertEqual(len(models),3)
        self.assertGreaterEqual(len(hashes),21)
    def test_independent_matrix_statistics_match_all_fields(self):
        from src.analysis.response_action_statistics_audit_v1 import independent_summary,compare
        for cohort,weight in (('DEV',None),('QUAL',1.)):
            cases=synthetic_cases(cohort,weight);primary='F20_RANK_W'+('10.0' if weight is None else '1.0')
            self.assertGreater(compare(stats.summarize(cases,cohort,weight,primary),independent_summary(cases,cohort,weight,primary)),1000)
    def test_independent_statistics_detects_wrong_loss_or_omitted_group(self):
        from src.analysis.response_action_statistics_audit_v1 import independent_summary,compare
        cases=synthetic_cases('QUAL',1.);expected=independent_summary(cases,'QUAL',1.,'F20_RANK_W1.0');actual=stats.summarize(cases,'QUAL',1.,'F20_RANK_W1.0')
        actual['programs'][0]['mean_deadline_loss']+=1
        with self.assertRaises(ValueError):compare(actual,expected)
        with self.assertRaises(ValueError):independent_summary(cases[:-1],'QUAL',1.,'F20_RANK_W1.0')


def audited_array_record(spec=None,mutate=None,success_at=25):
    from tests.response_action_array_fixtures_v1 import synthetic_record
    from tests.test_response_action_rank_v1 import fixture
    from tests.test_task_passive_host_v1 import fit_patches,NumericPolicy
    from src.analysis.response_action_audit_v1 import audit_case
    record=synthetic_record(spec,success_at)
    if mutate is not None:mutate(record)
    s,c,e,p=record;model=fixture()[1] if s['style']=='F20_RANK' else None
    with ExitStack() as stack:
        stack.enter_context(fit_patches());stack.enter_context(patch('src.rollout.task_registry.create_task_policy',return_value=NumericPolicy()))
        stack.enter_context(patch('src.analysis.continuous_state_witness_v1.verify_witness'))
        stack.enter_context(patch('src.analysis.continuous_state_witness_v1.compare_witnesses',side_effect=lambda a,b:{'comparison_equal':a==b}))
        return record,audit_case(s,c,e,p,{'task':s['task']},{'counts':{},'by_phase':{}},model)


class CompleteArrayJournalTests(unittest.TestCase):
    def test_rank_host_and_full_independent_journal_audit_no_environment(self):
        record,(ledger,result)=audited_array_record();self.assertEqual(record[1]['rank_steps'],17)
        self.assertEqual(result['costs']['independent_rank_raw_coefficient_forecasts'],85)
        self.assertEqual(ledger['counts']['simulation_frames_completed'],51*500+25*5)
    def test_all_twelve_programs_use_registered_continuous_contract(self):
        for p in allocation.programs('DEV'):
            s=next(s for s in allocation.population('DEV') if s['group']==0 and s['task']=='push-v3' and s['context']=='CHANGED'
                and s['style']==p.style and s['time_constant_s']==p.time_constant_s and s['regularization_weight']==p.regularization_weight)
            record,_=audited_array_record(s);self.assertEqual(record[1]['total_steps'],25)
    def test_early_success_and_no_rank_history_are_not_fabricated(self):
        record,(_,result)=audited_array_record(success_at=2);self.assertTrue(record[1]['success'])
        self.assertEqual(record[1]['rank_steps'],0);self.assertFalse(record[1]['boundary_applied'])
    def test_future_plan_and_noise_cursor_corruption_rejected(self):
        def future(r):
            p=next(e for e in r[2] if e['event']=='AGENT_EVENT' and e['agent_event']=='RANK_PLAN')['public_payload']['plan']
            p['query']['observation_steps'][-1]+=1
        with self.assertRaises(ValueError):audited_array_record(mutate=future)
        def noise(r):next(e for e in r[2] if e['event']=='STEP_COMPLETE')['noise_cursor_after']+=1
        with self.assertRaises(ValueError):audited_array_record(mutate=noise)


if __name__=='__main__':unittest.main()
