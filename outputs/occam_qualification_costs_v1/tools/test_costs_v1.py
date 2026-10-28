"""Pure cumulative ledgers and constructed metadata only."""
from copy import deepcopy
import unittest
import costs_engine_v1 as e
import costs_audit_v1 as a


def ledger(cases,control):
    if cases==control==0:return dict(counts={},by_phase={})
    def numbers(resets,sim,frames):
        return dict(reset_attempts=resets,reset_completed=resets,simulation_attempts=sim,simulation_completed=sim,
                    simulation_frames_attempted=frames,simulation_frames_completed=frames)
    return dict(counts=numbers(51*cases,5100*cases+control,25500*cases+5*control),by_phase={
        'GOAL_GENERATION':numbers(50*cases,5000*cases,25000*cases),
        'CONTROLLED_RESET':numbers(cases,100*cases,500*cases),
        'CONTROL':dict(simulation_attempts=control,simulation_completed=control,simulation_frames_attempted=5*control,simulation_frames_completed=5*control)})


def case(program='META_ADAPT__CONTINUE',n=50,w=3,u=2,*,prior_cases=0,prior_steps=0,success=True):
    spec=dict(cohort='CONSTRUCTED',group=0,program=program)
    fits=2 if program in e.LEGACY else 0
    c=dict(**spec,completed=True,environment_closed=True,error=None,close_error=None,
        ledger_before=ledger(prior_cases,prior_steps),ledger_after_close=ledger(prior_cases+1,prior_steps+n),
        total_steps=n,success=success,deadline_loss=n if success else 500,policy_queries=max(0,n-8) if fits else n,
        performance_windows=w,filter_update_attempts=u,full_feedback_windows=u,
        c4_c8_fit_attempts=fits,c4_c8_optimizer_nfev=fits,legacy_fit_accounting=dict(fit_intents=fits,optimizer_nfev=fits),
        online_LLM_API_calls=0,wall_ns=1000)
    return c,spec


def historical():
    return dict(trained_performance_banks=dict(control_steps=85789,all_resets=34884,physical_frames=17870945,
            actual_joint_AdamW_updates=9000,per_method_standalone_AdamW_updates=5000),
        C8_complete_source_study_including_training_not_additive=dict(control_steps=3840,all_resets=24480,physical_frames=12259200),
        C8_nominal_training=dict(control_steps=3072))


class CostTests(unittest.TestCase):
    def checked(self,*args,**kwargs):
        c,s=case(*args,**kwargs);r=e.case_cost(c,s);a.verify_case(c,s,r);return r
    def test_case_increments_not_cumulative_endpoints(self):
        r=self.checked(prior_cases=17,prior_steps=4000);self.assertEqual(r['all_resets'],51);self.assertEqual(r['physical_frames'],25750)
    def test_factory_reset_frames_are_charged(self):self.assertEqual(self.checked()['setup_frames'],25500)
    def test_failure_penalty_has_no_extra_physics(self):
        r=self.checked(success=False);self.assertEqual(r['unexecuted_failure_penalty_steps'],450);self.assertEqual(r['control_frames'],250)
    def test_only_trained_provider_windows_are_predictions(self):
        r=self.checked('PI_0500__CONTINUE',35,2,0);self.assertEqual(r['all_provider_windows'],2);self.assertEqual(r['candidate_predictions'],0)
    def test_four_candidates_and_covariance_checks_reconstructed(self):
        r=self.checked();self.assertEqual(r['candidate_predictions'],12);self.assertEqual(r['model_core_eigendecompositions_reconstructed'],45)
    def test_frozen_observations_do_not_update(self):
        r=self.checked('META_FROZEN__CONTINUE',50,3,0);self.assertEqual(r['model_core_eigendecompositions_reconstructed'],39)
    def test_early_success_no_model_session(self):self.assertEqual(self.checked('META_ADAPT__CONTINUE',10,0,0)['model_session_initializations'],0)
    def test_legacy_invalid_fit_stop_still_has_full_penalty(self):
        r=self.checked('DIRECT_C8',8,0,0,success=False);self.assertEqual(r['cutoff_loss'],500);self.assertEqual(r['C4_C8_fit_attempts'],2)
    def test_global_alias_not_a_new_execution(self):
        with self.assertRaises(ValueError):e.classify('GLOBAL_PI_0500')
    def test_missing_or_decreasing_cumulative_count_rejected(self):
        c,s=case();c['ledger_after_close']['counts']['reset_attempts']=0
        with self.assertRaises(ValueError):e.case_cost(c,s)
    def test_misplaced_control_frames_rejected(self):
        c,s=case();c['ledger_after_close']['by_phase']['CONTROL']['simulation_frames_completed']+=1
        with self.assertRaises(ValueError):e.case_cost(c,s)
    def test_fixed_model_update_rejected(self):
        with self.assertRaises(ValueError):self.checked('PI_0500__CONTINUE',50,3,1)
    def test_frozen_model_update_rejected(self):
        with self.assertRaises(ValueError):self.checked('ERM_FROZEN__CONTINUE',50,3,1)
    def test_unknown_method_rejected(self):
        with self.assertRaises(ValueError):e.classify('UNKNOWN')
    def test_api_latency_is_missing_when_there_are_no_calls(self):self.assertIsNone(self.checked()['mean_API_call_latency_ns'])
    def test_standalone_training_is_not_joint_cost_times_program_count(self):
        rows=[self.checked(),self.checked('ERM_ADAPT__CONTINUE')];table=e.program_table(rows,historical());a.verify_programs(rows,historical(),table)
        self.assertEqual(table[0]['hypothetical_standalone_source']['actual_joint_AdamW_updates'],9000)
    def test_C8_training_subset_not_added_to_full_study(self):
        rows=[self.checked('DIRECT_C8',50,0,0)];table=e.program_table(rows,historical());a.verify_programs(rows,historical(),table)
        self.assertEqual(table[0]['hypothetical_standalone_source']['source_controls'],3840)
    def test_fixed_no_specific_calibration_does_not_mean_no_shared_prior_cost(self):
        p=e.standalone_source('GLOBAL_PI_0125',historical());self.assertTrue(p['shared_handwritten_policy_and_prior_development_cost_not_asserted_zero'])
    def test_independent_program_table_detects_wrong_observed_cost(self):
        rows=[self.checked()];table=e.program_table(rows,historical());table[0]['observed']['physical_frames']+=5
        with self.assertRaises(ValueError):a.verify_programs(rows,historical(),table)
    def test_independent_program_table_keeps_all_methods(self):
        rows=[self.checked(),self.checked('ERM_ADAPT__CONTINUE')];table=e.program_table(rows,historical())
        with self.assertRaises(ValueError):a.verify_programs(rows,historical(),table[:1])
    def test_independent_detects_tampering(self):
        c,s=case();r=e.case_cost(c,s);r['physical_frames']+=1
        with self.assertRaises(ValueError):a.verify_case(c,s,r)
    def test_independent_does_not_call_main_projection(self):
        from unittest.mock import patch
        c,s=case();r=e.case_cost(c,s)
        with patch.object(e,'case_cost',None),patch.object(e,'increment',None):a.verify_case(c,s,r)
    def phase(self):
        rows=[self.checked(),self.checked('PI_0500__CONTINUE',35,2,0,prior_cases=1,prior_steps=50)]
        summary=dict(status='COLLECTED_FOR_INDEPENDENT_AUDIT',executions=2,control_steps=85,lifecycle=ledger(2,85))
        audit=dict(integrity='PASSED',counts=dict(executions=2,control_steps=85,audit_fixed_policy_queries=85,observed_windows=5,
            audit_filter_updates=2,independent_batch_solves=1,actual_c4_c8_fit_attempts=0,actual_c4_c8_optimizer_nfev=0),
            guard=dict(operation_counts=dict(solve_attempts=3,cold_fit_attempts=0)))
        return rows,summary,audit
    def test_whole_phase_costs_agree_with_source_audit(self):
        rows,s,audit=self.phase();saved=e.check_phase(rows,s,audit);a.verify_phase(rows,s,audit,saved)
        self.assertEqual(saved['totals']['trained_model_declarations'],3);self.assertEqual(saved['totals']['all_provider_windows'],5)
    def test_missing_audited_window_is_rejected(self):
        rows,s,audit=self.phase();audit['counts']['observed_windows']+=1
        with self.assertRaises(ValueError):e.check_phase(rows,s,audit)
    def test_actor_and_independent_batch_solves_not_conflated(self):
        rows,s,audit=self.phase();audit['guard']['operation_counts']['solve_attempts']=2
        with self.assertRaises(ValueError):e.check_phase(rows,s,audit)


if __name__=='__main__':unittest.main()
