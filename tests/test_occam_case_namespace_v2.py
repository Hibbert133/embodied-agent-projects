"""Actual collector + Journal + LifecycleLedger, with array-only delegates.

Fixture reset/simulation callbacks are ordinary Python functions, never Env
methods. These records cannot pass a real manifest gate or train a model.
"""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import io as streams,json,uuid
import numpy as np
from src.analysis import occam_reference_train_io_v2 as a
from src.analysis import occam_reference_train_collect_v2 as collector
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.analysis.occam_case_events_v2 import emit_owned


def integration(*,legacy_header=False,foreign=None,callback_error=False):
    root=a.BASE/'array_integration_fixtures_v1'/uuid.uuid4().hex;root.mkdir(parents=True,exist_ok=False)
    path=root/'array_metadata.json';identity=dict(experiment_run_id='ARRAY_FIXTURE_NOT_RESEARCH',manifest_id='array',source_git_commit='array')
    path.write_text(json.dumps(identity),encoding='utf8',newline='\n')
    spec={**a.population('NATIVE')[0],'seed':42}
    if legacy_header:spec['phase']=spec.pop('cohort')
    calls=dict(reset_callbacks=0,simulation_callbacks=0,executions=0)
    class ResetCallback:
        def reset(self):
            calls['reset_callbacks']+=1
            if callback_error:raise RuntimeError('synthetic callback failure')
            return np.zeros(39),{}
    class SimulationCallback:
        def do_simulation(self,ctrl,n_frames):calls['simulation_callbacks']+=1
    factory=SimpleNamespace(_make_tasks=lambda:ResetCallback().reset())
    def execute(spec,emit,private,ledger,budget,position,sync):
        calls['executions']+=1
        if foreign is not None:emit('BEFORE_FACTORY',foreign)
        emit('FACTORY_INTENT',dict(ledger=ledger.snapshot()))
        with ledger.scope('FACTORY_SETUP'):factory._make_tasks()
        emit('FACTORY_COMPLETE',dict(ledger=ledger.snapshot()))
        with ledger.scope('CONTROLLED_RESET'):ResetCallback().reset()
        phases=('PREFIX_TASK','VALIDATION_TASK','REPOSITION','WARM_PROBE','TAIL_TASK')
        for index,phase in enumerate(phases):
            emit('STEP_INTENT',dict(phase=phase,logical_step=index,command=[0.,0.,0.,0.]))
            with ledger.scope('CONTROL'):SimulationCallback().do_simulation(np.zeros(4),5)
            budget['completed']+=1;emit('STEP_COMPLETE',dict(phase=phase,logical_step=index))
        private('ARRAY_PRIVATE_EVENT',dict(phase='CONTROL',logical_step=5))
        return {**spec,'array_fixture':True,'total_steps':5,'deadline_loss':500,'success':False,'policy_queries':0,'performance_windows':0,'full_feedback_windows':0,'boundary_applied':False}
    caps={**a.limits('NATIVE'),'executions':1};error=None
    with ExitStack() as st:
        st.enter_context(patch.object(a,'phase_gate',lambda *v:identity));st.enter_context(patch.object(a,'checked',lambda *v:identity))
        st.enter_context(patch.object(a,'population',lambda *v:[spec]));st.enter_context(patch.object(a,'limits',lambda *v:caps))
        st.enter_context(patch.object(collector,'native_dependencies',lambda:(ResetCallback,SimulationCallback,factory)))
        st.enter_context(patch.object(collector.host,'execute_case',execute))
        st.enter_context(patch('src.analysis.response_action_io_v1.verify_runtime',lambda *v:None))
        try:collector.collect(path,'NATIVE')
        except RuntimeError as ex:error=str(ex)
    summary=a.io.read(root/'native/summary.json');events=list(a.io.rows(root/'native/events.jsonl.gz'));private=list(a.io.rows(root/'native/witnesses.jsonl.gz'))
    return calls,summary,events,private,error


class CaseNamespaceTests(TestCase):
    def test_real_collector_event_bridge_reaches_both_resets_and_all_command_phases(self):
        calls,summary,events,private,error=integration();self.assertIsNone(error)
        self.assertEqual(calls,dict(reset_callbacks=2,simulation_callbacks=5,executions=1));self.assertEqual(summary['executions'],1)
        self.assertTrue(all(e['cohort']=='NATIVE' and e['seed']==42 for e in events+private))
        reset=[e for e in events if e['event']=='LIFECYCLE_RESET_COMPLETE'];self.assertEqual([e['phase'] for e in reset],['GOAL_GENERATION','CONTROLLED_RESET'])
        self.assertEqual([e['phase'] for e in events if e['event']=='STEP_COMPLETE'],['PREFIX_TASK','VALIDATION_TASK','REPOSITION','WARM_PROBE','TAIL_TASK'])
        self.assertEqual(private[0]['phase'],'CONTROL')

    def test_legacy_header_rejected_before_any_factory_or_callback(self):
        calls,summary,events,private,error=integration(legacy_header=True)
        self.assertIsNotNone(error);self.assertEqual(calls['executions'],0);self.assertEqual(calls['reset_callbacks'],0);self.assertEqual(events,[])
        self.assertEqual(summary['status'],'FAILED_PARTIAL')

    def test_foreign_cohort_or_seed_still_fails_closed_without_reset(self):
        for bad in (dict(cohort='TRAIN'),dict(seed=7)):
            calls,summary,events,private,error=integration(foreign=bad);self.assertIsNotNone(error)
            self.assertEqual(calls['reset_callbacks'],0);self.assertEqual(summary['executions'],0)

    def test_callback_error_is_recorded_once_not_retried(self):
        calls,summary,events,private,error=integration(callback_error=True);self.assertIsNotNone(error)
        self.assertEqual(calls['reset_callbacks'],1);self.assertEqual(summary['lifecycle']['counts']['reset_errors'],1)
        self.assertEqual(summary['lifecycle']['counts'].get('reset_completed',0),0)

    def test_protected_journal_identity_cannot_be_overridden(self):
        j=JsonJournal(streams.StringIO(),dict(experiment_run_id='array'))
        with self.assertRaises(ValueError):emit_owned(j,dict(cohort='NATIVE'), 'X',dict(experiment_run_id='foreign'))

    def test_new_population_and_public_model_contract_keep_original_learning_rules(self):
        from src.analysis import occam_reference_train_io_v1 as old
        self.assertEqual(a.learning(),old.learning());self.assertEqual([len(a.population(c)) for c in a.PHASES],[36,648])
        self.assertEqual(set(a.population('NATIVE')[0]),set(a.KEYS));self.assertNotIn('phase',a.KEYS)
        self.assertEqual(a.config()['complete_limits'],old.config()['complete_limits'])
        self.assertTrue(all(s['cohort']=='TRAIN' for s in a.population('TRAIN')))

    def test_array_control_host_covers_new_cohort_schema_all_tasks_actions_rates(self):
        from tests.test_learned_acquisition_native_v1 import FakeSession
        from src.analysis.occam_reference_train_host_v2 import run_live
        specs=a.population('TRAIN')
        for group in range(3):
            for task in ('push-v3','reach-v3','door-open-v3'):
                for action in a.ACTIONS:
                    for behavior in a.BEHAVIORS:
                        spec=next(s for s in specs if s['group']==group and s['task']==task and s['acquisition_action']==action and s['behavior']==behavior)
                        session=FakeSession(end=120);r=run_live(spec,session,lambda name:None,lambda:None)
                        self.assertEqual(r['total_steps'],120);self.assertEqual(r['full_feedback_windows'],0)
                        self.assertEqual(r['policy_queries'],session.policy_queries)
