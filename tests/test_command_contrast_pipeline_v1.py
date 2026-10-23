"""Pure arrays/synthetic saved journals; never construct/reset/advance a world."""
from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from src.analysis import command_contrast_io_v1 as allocation
from src.analysis import command_contrast_audit_v1 as audit
from src.analysis import command_contrast_statistics_v1 as stats
from src.analysis import command_contrast_host_v1 as host
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation
from src.analysis.capsule_record_json_v2 import normalize
from src.probe import observable_history_behavior_v1 as behavior
from tests.test_command_contrast_host_v1 import ArraySession,ArrayJournal,selected,live
from tests.test_command_contrast_v1 import models


def raw_bank():
    return {key:({'task':model.task,'feature':model.feature,'stats':{'input_mean':list(model.mean),'input_scale':list(model.scale)},
                  'coefficient':[list(v) for v in model.coefficient]},sha) for key,(model,sha) in models().items()}


def saved_numeric_case(spec,reference=None,success_at=None):
    """A fully synthetic journal fixture with no environment or reset methods."""
    journal=ArrayJournal(); private=ArrayJournal(); session=ArraySession(spec,journal,success_at=success_at)
    ledger={'counts':{},'by_phase':{}}; initial=normalize(asdict(session.public())); refs=[]
    journal.emit('FACTORY_INTENT',{'ledger':deepcopy(ledger)})
    for phase,count in (('GOAL_GENERATION',50),('CONTROLLED_RESET',1)):
        for _ in range(count):
            intent=journal.emit('LIFECYCLE_RESET_INTENT',{'phase':phase,'before':deepcopy(ledger)})
            ledger=ledger_add(ledger,phase,'reset_attempts',1); ledger=simulation(ledger,phase,100,500)
            ledger=ledger_add(ledger,phase,'reset_completed',1)
            journal.emit('LIFECYCLE_RESET_COMPLETE',{'phase':phase,'intent_sequence':intent['sequence'],'after':deepcopy(ledger)})
        if phase=='GOAL_GENERATION': journal.emit('FACTORY_COMPLETE',{'ledger':deepcopy(ledger)})
    journal.emit('CONTROLLED_INITIAL',{'task':spec['task'],'observation':initial['observation'],'ledger':deepcopy(ledger),'simulation_time':0.})
    journal.emit('NOISE_COMMITMENT',{'at_calls':0,'noise_namespace_oracle':spec['noise_namespace'],
        'tape_sha256_oracle':allocation.io.digest(session.ctx['noise_rows'].tolist())})
    def take(label):
        anchor=journal.rows[-1]; source=session.witness(); n=session.ctx['calls']
        witness={'native_sha256':source['native_sha256'],'comparison_python_sha256':source['python_semantic_sha256']}
        stamp=perf_counter_ns(); p=private.emit('STATE_WITNESS',{'label':label,'logical_step':n,
            'source_anchor_sequence':anchor['sequence'],'source_anchor_saved_ns':anchor['saved_ns'],'started_ns':stamp,'completed_ns':stamp,
            'ledger_before':deepcopy(ledger),'ledger_after':deepcopy(ledger),'source_witness':source,'witness':witness})
        refs.append({'label':label,'sequence':p['sequence'],**witness,'logical_step':n})
        return (source['native_sha256'],source['python_semantic_sha256'],source['noise_past_sha256'],source['simulation_time'])
    original=session._agent_step
    def numeric_response(saved):
        nonlocal ledger
        before=deepcopy(ledger); value=original(saved); intent=next(e for e in reversed(journal.rows) if e['event']=='STEP_INTENT')
        intent.update(global_command_sequence=session._map[saved['sequence']],ledger_before=before)
        complete=next(e for e in reversed(journal.rows) if e['event']=='STEP_COMPLETE'); ledger=simulation(ledger,'CONTROL',1,5)
        extra={'global_command_sequence':intent['global_command_sequence'],'completed_ns':complete['saved_ns'],
               'ledger_before':before,'ledger_after':deepcopy(ledger),'info':{'success':value.success},'reward':0.}
        complete.update(extra); session.last_rows[-1].update(extra); return value
    session._agent_step=numeric_response; take('INITIAL')
    with patch.object(behavior,'validate_model'):
        outcome,ref=host.run_live_prefix(spec,{'task':spec['task']},models(),session,take,lambda:None,reference)
    case={**spec,**outcome,'initial':initial,'final':normalize(asdict(session.public())),
        'fault_oracle':allocation.fault(spec),'completed':True,'environment_closed':True,'error':None,'close_error':None,
        'ledger_before':{'counts':{},'by_phase':{}},'ledger_before_close':deepcopy(ledger),'ledger_after_close':deepcopy(ledger),
        'captures':0,'restores':0,'physical_rows_count':len(session.last_rows),'host_attempts':session.attempts,
        'host_returned':session.completed,'policy_queries':session.policy_queries,'state_witness_refs':refs}
    return case,journal.rows,private.rows,ref


class PipelineTests(unittest.TestCase):
    def test_full_population_and_budgets_are_arithmetically_reconstructed(self):
        cases=allocation.population(); cfg=allocation.expected_config(); units={s['unit_id'] for s in cases}
        self.assertEqual(len(cases),540); self.assertEqual(len(units),108); self.assertEqual(sum(s['maximum_steps'] for s in cases),38820)
        self.assertEqual(51*len(cases),27540); self.assertEqual(500*27540+5*38820,13964100)
        native=allocation.software_population(); self.assertEqual(len(native),15)
        self.assertEqual(500*51*15+5*sum(s['maximum_steps'] for s in native),382725)
        self.assertEqual(cfg['limits']['online_c4_c8_fit_attempts'],2*sum(s['target']!='COLD_STEP2' for s in cases))
        self.assertTrue(set(s['seed'] for s in cases).isdisjoint(s['seed'] for s in native))

    def test_registered_spec_cannot_add_hidden_fields_or_unassigned_seeds(self):
        for change in ({'seed':61999},{'maximum_steps':500},{'oracle':True}):
            with self.assertRaises(ValueError): allocation.validate_spec({**selected(),**change})

    def test_noise_is_initial_readonly_and_new_namespace_is_distinct(self):
        a=allocation.noise(61000); b=allocation.noise(61000)
        np.testing.assert_array_equal(a,b); self.assertFalse(a.flags.writeable)
        self.assertFalse(np.array_equal(a,allocation.noise(61000,110012)))
        with self.assertRaises(ValueError): allocation.noise(61000,57001)

    def test_storage_gate_precedes_collector_native_imports(self):
        from src.analysis.command_contrast_collect_v1 import collect
        with patch.object(allocation,'phase_gate',side_effect=ValueError('NEEDS_STORAGE')),\
             patch('src.rollout.task_registry.create_task_environment',side_effect=AssertionError('world forbidden')):
            with self.assertRaisesRegex(ValueError,'NEEDS_STORAGE'): collect('not_a_manifest','QUAL')

    def test_fixed_raw_coefficients_match_saved_physical_predictions(self):
        case,events,private,ref=saved_numeric_case(selected())
        history=[case['initial']['observation'],*[e['after']['observation'] for e in events if e['event']=='STEP_COMPLETE']][:-1]
        query=audit.audit_plan(ref.plan.to_dict(),selected(),history,ref.plan.query.baseline_command,raw_bank())
        self.assertEqual(query,ref.plan.query)

    def test_independent_plan_audit_detects_future_or_stale_observations(self):
        case,events,_,ref=saved_numeric_case(selected()); plan=ref.plan.to_dict()
        history=[case['initial']['observation'],*[e['after']['observation'] for e in events if e['event']=='STEP_COMPLETE']][:-1]
        for change in ('future','stale'):
            changed=deepcopy(plan)
            if change=='future': changed['query']['observation_steps'][-1]+=1
            else: changed['query']['observations'][-1][0]+=.001
            with self.assertRaises(ValueError): audit.audit_plan(changed,selected(),history,ref.plan.query.baseline_command,raw_bank())

    def test_wrong_output_units_or_model_prediction_is_detected(self):
        case,events,_,ref=saved_numeric_case(selected()); plan=ref.plan.to_dict()
        history=[case['initial']['observation'],*[e['after']['observation'] for e in events if e['event']=='STEP_COMPLETE']][:-1]
        for key in plan['models']: plan['models'][key]['predictions_m'][1][0]*=1000
        with self.assertRaisesRegex(ValueError,'prediction differs'): audit.audit_plan(plan,selected(),history,ref.plan.query.baseline_command,raw_bank())

    def test_synthetic_complete_saved_journal_passes_without_physics(self):
        case,events,private,ref=saved_numeric_case(selected())
        with patch('src.analysis.continuous_state_witness_v1.verify_witness'),patch.object(behavior,'validate_model'):
            ledger,result=audit.audit_case(selected(),case,events,private,{'task':'push-v3'},raw_bank(),case['ledger_before'])
        self.assertEqual(len(result['steps']),3); self.assertEqual(ledger['counts']['simulation_frames_completed'],25515)
        self.assertEqual(result['costs']['independent_c4_c8_refits'],0)

    def test_cursor_early_clip_late_plan_and_wrong_command_are_rejected(self):
        case,events,private,_=saved_numeric_case(selected()); last=next(e for e in reversed(events) if e['event']=='STEP_COMPLETE')
        changes=('cursor','clip','late_plan','command')
        for change in changes:
            changed=deepcopy(events); row=next(e for e in reversed(changed) if e['event']=='STEP_COMPLETE')
            if change=='cursor': row['noise_cursor_after']+=1
            elif change=='clip': row['executed_action_oracle'][0]+=.001
            elif change=='late_plan': next(e for e in changed if e['event']=='UNIT_PLAN_COMMITTED')['sequence']=row['sequence']+1
            else: row['command'][0]+=.1
            with patch('src.analysis.continuous_state_witness_v1.verify_witness'),patch.object(behavior,'validate_model'):
                with self.assertRaises(ValueError,msg=change): audit.audit_case(selected(),case,changed,private,{'task':'push-v3'},raw_bank(),case['ledger_before'])

    def test_early_success_is_missing_instead_of_zero_error(self):
        case,events,private,_=saved_numeric_case(selected(),success_at=1)
        with patch('src.analysis.continuous_state_witness_v1.verify_witness'),patch.object(behavior,'validate_model'):
            _,result=audit.audit_case(selected(),case,events,private,{'task':'push-v3'},raw_bank(),case['ledger_before'])
        self.assertFalse(case['query_available']); self.assertIsNone(result['plan']); self.assertEqual(case['missing_reason'],'EARLY_SUCCESS')

    def test_executor_order_has_observable_synthetic_counterexample(self):
        fault={'matrix_xy':[[2.,0.],[0.,1.]],'bias_xy':[0.,0.],'deadzone_xy':[0.,0.]}
        correct=applied([1.,0.,0.,0.],fault,np.array([-.5,0,0],np.float32))
        wrong=(np.clip(np.array([2.,0,0,0],np.float32),-1,1)+np.array([-.5,0,0,0],np.float32)).tolist()
        self.assertEqual(correct[0],1.); self.assertEqual(wrong[0],.5)

    def test_prefix_replay_has_three_real_stages_and_rejects_fit_or_command_changes(self):
        fit={'valid':True,'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[0.,0.],'nfev':0,'reason':'ARRAY_ONLY'}
        fixed=SimpleNamespace(get_action=lambda o:np.array([.2,-.1,0.,-1.],np.float32))
        for g in (0,3,6):
            spec=selected(g); journal=ArrayJournal(); result,ref,session=live(spec,journal)
            public=[e for e in journal.rows if e['event']=='AGENT_EVENT'][:result['prefix_event_count']]
            initial=normalize(asdict(ArraySession(spec,ArrayJournal()).public()))
            with patch.object(behavior,'validate_model'),patch.object(behavior,'infer_four',return_value=fit),\
                 patch.object(behavior,'infer_operator',return_value=fit),patch('src.rollout.task_registry.create_task_policy',return_value=fixed):
                target,_,cost=audit.replay_prefix(spec,initial,public,session.last_rows[:-1],{'task':'push-v3'})
                self.assertEqual(target['command'],list(ref.plan.query.baseline_command)); self.assertEqual(cost['independent_c4_c8_refits'],0 if g==0 else 2)
                changed=deepcopy(public); next(e for e in changed if e['agent_event']=='COMMAND')['public_payload']['command'][0]+=.01
                with self.assertRaises(ValueError): audit.replay_prefix(spec,initial,changed,session.last_rows[:-1],{'task':'push-v3'})

    def test_all_missing_population_keeps_540_denominator_and_nulls(self):
        cases=[{**s,'query_available':False,'missing_reason':'INVALID_FOUR','total_steps':4} for s in allocation.population()]
        result=stats.summarize(cases,{})
        self.assertEqual(result['executions'],540); self.assertEqual(result['eligible_units'],0)
        self.assertEqual(result['missing_reasons'],{'INVALID_FOUR':108}); self.assertEqual(result['fixed_F20_component_gate'],'NOT_QUALIFIED')
        self.assertIsNone(result['primary_and_secondary']['F20_MINUS_ZERO']); self.assertEqual(len(result['complete_source_transfer_tables']),72)

    def test_whole_group_bootstrap_does_not_inflate_step_sample_size(self):
        negative=stats.bootstrap_groups({g:-.5 for g in range(9)},100)
        self.assertEqual(negative['groups'],9); self.assertEqual(negative['lower95'],-.5); self.assertEqual(negative['upper95'],-.5)
        with self.assertRaises(ValueError): stats.bootstrap_groups({g:0 for g in range(8)},100)

    def test_complete_synthetic_effect_population_checks_positive_and_negative_gate(self):
        actual=np.array([[0,0],[.001,0],[-.001,0],[0,.001],[0,-.001]])
        cases=[]; plans={}
        for s in allocation.population():
            i=allocation.core.BRANCHES.index(s['action_id']); o=np.zeros(39); o[:2]=actual[i]
            cases.append({**s,'query_available':True,'missing_reason':None,'total_steps':3,'before_observation':[0.]*39,
                          'after_observation':o.tolist(),'plan_sha256':'SYNTHETIC_ARRAY_ONLY'})
            if s['action_id']=='BASELINE':
                plans[s['unit_id']]={'query':{'candidates':[{'action_id':name,'sent_command':[float(j),0,0,0]} for j,name in enumerate(allocation.core.BRANCHES)]},
                    'models':{f"{source}/{s['task']}/LINEAR_{f}":{'predictions_m':actual.tolist() if f=='F20' else np.zeros((5,2)).tolist()}
                              for source in allocation.PROGRAMS for f in ('H10','F20','F43')}}
        result=stats.summarize(cases,plans)
        self.assertEqual(result['eligible_units'],108); self.assertTrue(result['fixed_F20_component_gate'].startswith('PASSED'))
        self.assertAlmostEqual(result['primary_and_secondary']['F20_MINUS_ZERO']['mean'],-.0000005)
        self.assertEqual(result['matched_group_mean_mse_m2']['F20'],0.)
        for plan in plans.values():
            for model in plan['models'].values(): model['predictions_m']=np.zeros((5,2)).tolist()
        self.assertEqual(stats.summarize(cases,plans)['fixed_F20_component_gate'],'NOT_QUALIFIED')

    def test_common_seed_is_not_a_unique_independent_execution(self):
        self.assertEqual(len({s['seed'] for s in allocation.population()}),27)
        self.assertEqual(len({s['group'] for s in allocation.population()}),9)


if __name__=='__main__': unittest.main()
