"""Population, independent arithmetic, real TinyEnv collector and failure tests.

Native fixtures use software-only seeds and stub estimators/policy. They do not
execute any MetaWorld task, registered study seed, API call or optimizer fit.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import mujoco
import numpy as np
from scripts import run_short_probe_reference_v1 as collector
from scripts import short_probe_reference_pipeline_v1 as pipeline
from src.analysis import short_probe_study_io_v1 as study_io
from src.analysis import short_probe_study_v1 as study
from src.analysis import short_probe_study_audit_v1 as audit
from src.analysis import short_probe_numeric_audit_v1 as numeric
from src.analysis import short_probe_public_audit_v1 as public
from src.analysis import short_probe_journal_audit_v1 as journal
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe import short_probe_execution_reference_v1 as actor
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.short_probe_design_reference_v1 import design_four
from tests.test_paired_probe_host_v1 import TinyEnv, TinyPolicy
from tests.test_short_joint_reference_v1 import model
from tests.test_short_probe_execution_reference_v1 import fit

FIXTURE_RECEIPTS = []


def synthetic_summary(phase):
    rows = []
    for stream in study.population(phase):
        for case in stream['cases']:
            for j,method in enumerate(study.METHODS):
                success = (stream['stream']*3+case['episode']+j)%11 != 0
                stopped = not success and j != 0
                steps = 10+(stream['stream']*7+case['episode']*13+j*17)%450
                probe = 0 if j == 0 else 8 if j in (1,4,5) else 4
                row = {'study_phase':phase,'stream':stream['stream'],'episode':case['episode'],'task':case['task'],
                    'seed':case['seed'],'method':method,'family_oracle':stream['family_oracle'],'schedule_oracle':stream['schedule_oracle'],
                    'success':success,'stopped':stopped,'end_reason':'SUCCESS' if success else 'STOP_INVALID_FIT' if stopped else 'TRUNCATED',
                    'deadline_loss':steps if success else 500,'total_steps':steps,'fixed_probe_steps':probe,
                    'policy_steps':steps-probe,'policy_queries':steps-probe,'applied_fitted_controller':j != 0,
                    'online_parameter_fits':int(j != 0),'optimizer_nfev':int(j != 0)*3,'design_verification_candidates':144 if j >= 3 else 0}
                rows.append(row)
    return {'phase':phase,'rows':rows,'lifecycle':{'counts':{},'by_phase':{}},'wall_ns':12345}


class ShortStudyNumbersTest(unittest.TestCase):
    def test_population_independent_allocation_and_disjoint_reservations(self):
        main = study.population('MAIN');smoke = study.population('SMOKE')
        self.assertEqual(main,audit.population('MAIN'));self.assertEqual(smoke,audit.population('SMOKE'))
        self.assertEqual({c['seed'] for s in main for c in s['cases']},set(range(20200,20848)))
        self.assertEqual({c['seed'] for s in smoke for c in s['cases']},set(range(21200,21209)))
        self.assertEqual(len(main),54)
        for family in study.FAMILIES:
            for schedule in study.SCHEDULES:
                self.assertEqual(sum(s['family_oracle'] == family and s['schedule_oracle'] == schedule for s in main),6)
        for stream in main:
            self.assertEqual([sum(c['task'] == t for c in stream['cases']) for t in study.TASKS],[4,4,4])

    def test_independent_statistics_costs_and_bootstrap_agree_with_nonconstant_failures(self):
        for phase in ('SMOKE','MAIN'):
            with self.subTest(phase=phase):
                summary = synthetic_summary(phase);expected_stats,expected_cost = numeric.reconstruct(summary)
                result = numeric.compare({'statistics':study.statistics(summary['rows'],phase),'costs':study.costs(summary)},
                                         {'statistics':expected_stats,'costs':expected_cost})
                self.assertLess(result['maximum_absolute_difference'],1e-9)

    def test_failures_stops_population_and_strict_types_cannot_disappear(self):
        base = synthetic_summary('SMOKE')['rows']
        for mutation in ('drop','duplicate','foreign_seed','failure_loss','float_loss','bool_steps','ending','stopped_success'):
            rows = deepcopy(base)
            if mutation == 'drop':rows.pop()
            elif mutation == 'duplicate':rows[1] = deepcopy(rows[0])
            elif mutation == 'foreign_seed':rows[0]['seed'] += 1
            elif mutation == 'failure_loss':rows[0]['deadline_loss'] = rows[0]['total_steps']
            elif mutation == 'float_loss':rows[0]['deadline_loss'] = 500.
            elif mutation == 'bool_steps':rows[0]['total_steps'] = True
            elif mutation == 'ending':rows[0]['end_reason'] = 'SUCCESS'
            else:rows[1]['stopped'] = True
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):study.statistics(rows,'SMOKE')

    def test_cost_denominator_is_units_not_method_executions(self):
        summary = synthetic_summary('MAIN');fees = study.costs(summary)
        self.assertEqual(fees['methods']['DOPT4_UPDATE']['prior_source_steps_per_unit'],3840/648)
        self.assertEqual(fees['methods']['NO_PROBE']['prior_source_steps_per_unit'],0)
        self.assertEqual(fees['shared_historical_nominal_source_paid_once']['all_reset_calls'],24480)

    def test_audit_rejects_changed_interval_cost_and_missing_field(self):
        summary = synthetic_summary('MAIN');expected = study.statistics(summary['rows'],'MAIN')
        for mutation in ('interval','count','group','missing','nonfinite'):
            changed = deepcopy(expected)
            if mutation == 'interval':changed['contrasts'][0]['ci95'][0] += .01
            elif mutation == 'count':changed['methods']['NO_PROBE']['cases'] -= 1
            elif mutation == 'group':changed['descriptive_groups'][0]['methods']['NO_PROBE']['mean_deadline_loss'] += 1
            elif mutation == 'missing':del changed['algorithm_promotion_claim']
            else:changed['contrasts'][0]['mean_loss_difference'] = float('nan')
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):numeric.compare(changed,expected)

    def test_smoke_has_no_population_interval(self):
        value = study.statistics(synthetic_summary('SMOKE')['rows'],'SMOKE')
        self.assertEqual(value['bootstrap_samples'],0)
        self.assertTrue(all(v['ci95'] is None for v in value['contrasts']))


@contextmanager
def native_fixture(ledger, *, fail_step=False, fail_close=False):
    original_simulation = TinyEnv.do_simulation;original_step = TinyEnv.step
    original_policy = TinyPolicy.get_action;frames = queries = 0
    def simulation(env,ctrl,n_frames):
        def counted(env,ctrl,n_frames):
            nonlocal frames
            result = original_simulation(env,ctrl,n_frames);frames += n_frames;return result
        return ledger.simulation_call(counted,env,ctrl,n_frames)
    def reset_body(env, **kwargs):
        mujoco.mj_resetData(env.model,env.data);env.calls = 0
        for _ in range(100):env.do_simulation([0.],5)
        return np.zeros(39),{}
    def reset(env, **kwargs):return ledger.reset_call(reset_body,env,**kwargs)
    def factory(task,seed):
        env = TinyEnv()
        with ledger.scope('GOAL_GENERATION'):
            for _ in range(50):env.reset()
        return env
    def step(env,command):
        result = original_step(env,command)
        if fail_step:raise RuntimeError('software fixture failure after actual simulation')
        return result
    def close(env):
        if fail_close:raise RuntimeError('software close failure')
    def policy_query(policy,observation):
        nonlocal queries
        queries += 1;return original_policy(policy,observation)
    with ExitStack() as stack:
        for target,name,value in ((TinyEnv,'do_simulation',simulation),(TinyEnv,'reset',reset),(TinyEnv,'step',step),
                (TinyEnv,'close',close),(TinyPolicy,'get_action',policy_query),(collector,'create_task_environment',factory)):
            stack.enter_context(patch.object(target,name,value))
        stack.enter_context(patch.object(collector,'create_task_policy',return_value=TinyPolicy()))
        stack.enter_context(patch.object(actor,'infer_four',return_value=fit()))
        stack.enter_context(patch.object(actor,'infer_operator',return_value=fit((-.1,.04),nfev=2)))
        try:yield
        finally:FIXTURE_RECEIPTS.append({'actual_native_requested_frames':frames,'actual_tiny_policy_queries':queries,
            'ledger':ledger.snapshot(),'scientific_tasks_executed':0,'actual_optimizer_fits':0})


class ShortStudyCollectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = model();cls.design = design_four(cls.model);cls.events = [];cls.records = [];cls.current = {}
        cls.identity = {'experiment_run_id':'SOFTWARE_COLLECTOR_ONLY','manifest_id':'SOFTWARE_ONLY','source_git_commit':'SOFTWARE_ONLY'}
        writer = JsonJournal(io.StringIO(),cls.identity)
        def emit(event,payload):
            row = writer.emit(event,{**cls.current,**payload});cls.events.append(row);return row
        cls.ledger = LifecycleLedger(emit,1800000);cls.budget = {'completed':0,'maximum':31500}
        fault = {'matrix_xy':[[1.,0.],[0.,1.]],'bias_xy':[.1,-.06],'deadzone_xy':[0.,0.]}
        cls.specs = [{'stream':0,'family_oracle':'BIAS','schedule_oracle':'SMOKE_ABRUPT','cases':[
            {'episode':i,'seed':700100+i,'task':'push-v3','fault_oracle':fault} for i in range(9)]}]
        with native_fixture(cls.ledger):
            for case in cls.specs[0]['cases']:
                for method in study.METHODS:
                    cls.current = {'study_phase':'SMOKE','stream':0,'episode':case['episode'],'task':case['task'],'seed':case['seed'],'method':method}
                    key = {**cls.identity,**cls.current,'family_oracle':'BIAS','schedule_oracle':'SMOKE_ABRUPT'}
                    cls.records.append(collector.execute_one(key,fault,None if method == 'NO_PROBE' else cls.model,
                        cls.design if method.startswith('DOPT') else None,emit,cls.ledger,cls.budget))
        cls.summary = {**cls.identity,'phase':'SMOKE','status':'COLLECTED_FOR_INDEPENDENT_AUDIT','failure':None,
            'computation_counters_complete':True,'completed_executions':63,'wall_ns':1,
            'new_api_calls':0,'new_nominal_training':0,'new_selector_fits':0,'policy_updates':0,
            'rows':[study.compact(r) for r in cls.records],'controlled_steps':cls.budget['completed'],'lifecycle':cls.ledger.snapshot()}
        cls.manifest = {**cls.identity,'population_oracle':{'SMOKE':cls.specs},'config':{'smoke':{
            'maximum_environment_steps':31500,'maximum_controlled_resets':63,'maximum_simulation_frames':1800000}}}

    def check(self, **changes):
        args = {'manifest':self.manifest,'summary':self.summary,'records':self.records,'events':self.events,**changes}
        with patch.object(audit,'population',return_value=self.specs),patch.object(journal,'create_task_policy',return_value=TinyPolicy()), \
                patch.object(public,'infer_four',return_value=fit()),patch.object(public,'infer_operator',return_value=fit((-.1,.04),nfev=2)):
            return audit.audit_records(phase='SMOKE',models={'push-v3':self.model},designs={'push-v3':self.design},**args)

    def test_complete_collector_to_independent_record_audit_chain(self):
        with patch.object(collector,'execute_one',side_effect=AssertionError('collector forbidden during audit')), \
                patch.object(TinyEnv,'step',side_effect=AssertionError('physical audit replay forbidden')):
            result = self.check()
        self.assertEqual(result['executions_checked'],63)
        self.assertEqual(result['actual_lifecycle']['counts']['reset_completed'],3213)
        self.assertEqual(result['online_computation']['total_steps'],756)
        self.assertEqual(result['actual_lifecycle']['counts']['simulation_frames_completed'],1610280)
        self.assertEqual(len(result['four_step_policy_chains']),36)
        self.assertEqual(len(result['matched_units']),9)
        self.assertTrue(all(v['complete_prefix_pairs'] == 4 for v in result['matched_units']))

    def test_population_owner_order_and_summary_cannot_be_substituted(self):
        for mutation in ('seed','fault','order','summary','missing','closed','before'):
            rows = deepcopy(self.records);summary = deepcopy(self.summary)
            if mutation == 'seed':rows[0]['seed'] += 1
            elif mutation == 'fault':rows[0]['fault_oracle']['bias_xy'][0] += .01
            elif mutation == 'order':rows[0],rows[1] = rows[1],rows[0]
            elif mutation == 'summary':summary['rows'][0]['deadline_loss'] += 1
            elif mutation == 'missing':rows.pop(0)
            elif mutation == 'closed':rows[0]['environment_closed'] = False
            else:rows[0]['lifecycle_before']['counts']['reset_completed'] = 0
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.check(records=rows,summary=summary)

    def test_extra_execution_and_forged_phase_are_rejected(self):
        with self.assertRaises(ValueError):self.check(records=self.records+[self.records[0]])
        events = deepcopy(self.events);events[0]['study_phase'] = 'MAIN'
        with self.assertRaises(ValueError):self.check(events=events)

    def test_collector_failure_retains_completed_frames_and_does_not_substitute(self):
        for fail_step,fail_close in ((True,False),(False,True)):
            writer = JsonJournal(io.StringIO(),self.identity);ledger = LifecycleLedger(writer.emit,100000)
            budget = {'completed':0,'maximum':500};key = {**self.identity,**self.current,'method':'NO_PROBE'}
            with self.subTest(fail_step=fail_step),native_fixture(ledger,fail_step=fail_step,fail_close=fail_close), \
                    self.assertRaises(collector.CollectionFailure) as caught:
                collector.execute_one(key,self.specs[0]['cases'][0]['fault_oracle'],None,None,writer.emit,ledger,budget)
            row = caught.exception.record
            self.assertFalse(row['completed']);self.assertEqual(row['lifecycle_after_close']['counts']['reset_completed'],51)
            if fail_step:
                self.assertTrue(row['environment_closed']);self.assertEqual(row['partial_host']['unreturned_step_attempts'],1)
                self.assertEqual(row['lifecycle_after_close']['counts']['simulation_frames_completed'],25505)
                self.assertEqual(row['partial_host']['optimizer_calls_and_nfev'],'UNKNOWN_IF_NO_COMPLETED_PUBLIC_RECORD')
            else:
                self.assertIsNotNone(row['close_error']);self.assertEqual(row['public']['outcome']['total_steps'],12)
                self.assertFalse(row['environment_closed'])


class ShortStudyPipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory();self.root = Path(self.temp.name);self.folder = self.root/'run';self.folder.mkdir()
        self.path = self.folder/'manifest.json';self.identity = {
            'experiment_run_id':'SOFTWARE_PIPELINE_TEST','manifest_id':'SOFTWARE_ONLY','source_git_commit':'SOFTWARE_ONLY'}
        self.summary = {**self.identity,**synthetic_summary('SMOKE')}
        self.summary['controlled_steps'] = sum(r['total_steps'] for r in self.summary['rows'])
        self.summary['lifecycle']['counts'] = {'reset_completed':3213,
            'simulation_frames_attempted':1606500+5*self.summary['controlled_steps']}
        (self.folder/'smoke').mkdir();study_io.write(self.folder/'smoke/summary.json',self.summary)
        self.record = {**self.identity,'phase':'SMOKE','integrity':'PASSED','required_four_step_policy_chain':True,
            'summary_sha256':study_io.sha(self.folder/'smoke/summary.json'),'four_step_policy_chains':[{'software_fixture':True}],
            'matched_units':[],'audit_recomputation':{'software_fixture':True}}
        study_io.write(self.folder/'smoke_record_audit.json',self.record)
        self.patches = ExitStack()
        self.patches.enter_context(patch.object(study_io,'load',return_value=(self.identity,{},{})))
        self.patches.enter_context(patch.object(pipeline,'ROOT',self.root))
        self.patches.enter_context(patch.object(collector,'ROOT',self.root))
        (self.root/'reports').mkdir()

    def tearDown(self):
        self.patches.close();self.temp.cleanup()

    def complete(self):
        pipeline.analyze(self.path,'SMOKE');pipeline.numeric(self.path,'SMOKE');pipeline.report(self.path,'SMOKE')
        logs = self.folder/'smoke_pipeline';logs.mkdir();steps = []
        for stage in ('collect','record_audit','analyze','numeric_audit','report'):
            (logs/(stage+'.txt')).write_text('software fixture process output',encoding='utf-8')
            steps.append({'stage':stage,'returncode':0,'log_sha256':study_io.sha(logs/(stage+'.txt'))})
        study_io.write(self.folder/'smoke_pipeline_completion.json',{**self.identity,'status':'COMPLETED_FOR_REVIEW',
            'failure':None,'steps':steps})

    def test_analysis_numeric_report_and_main_gate_bind_all_failures_and_costs(self):
        self.complete();collector.require_smoke(self.path,self.identity)
        checked = study_io.read(self.folder/'smoke_numeric_audit.json')
        self.assertEqual(checked['integrity'],'PASSED')
        report = (self.root/'reports/short_probe_reference/smoke_v1.md').read_text(encoding='utf-8')
        self.assertIn('API 调用为零',report);self.assertIn('全部失败',report)
        self.assertIn('单流预检不估计总体区间',report)
        self.assertIn('1e',str(checked['absolute_tolerance']))

    def test_wrong_numeric_values_fail_after_receipt_rehashed(self):
        pipeline.analyze(self.path,'SMOKE');out = self.folder/'smoke_analysis'
        fees = study_io.read(out/'costs.json');fees['methods']['DOPT4_UPDATE']['prior_source_steps_per_unit'] /= 7
        study_io.write(out/'costs.json',fees,exclusive=False)
        receipt = study_io.read(out/'analysis_completion.json');receipt['artifact_sha256']['costs.json'] = study_io.sha(out/'costs.json')
        study_io.write(out/'analysis_completion.json',receipt,exclusive=False)
        with self.assertRaises(ValueError):pipeline.numeric(self.path,'SMOKE')
        self.assertFalse((self.folder/'smoke_numeric_audit.json').exists())

    def test_missing_failure_csv_row_fails_after_receipt_rehashed(self):
        pipeline.analyze(self.path,'SMOKE');out = self.folder/'smoke_analysis';csv = out/'all_failures.csv'
        lines = csv.read_bytes().splitlines(keepends=True);self.assertGreater(len(lines),2)
        csv.write_bytes(b''.join(lines[:-1]))
        receipt = study_io.read(out/'analysis_completion.json');receipt['artifact_sha256']['all_failures.csv'] = study_io.sha(csv)
        study_io.write(out/'analysis_completion.json',receipt,exclusive=False)
        with self.assertRaises(ValueError):pipeline.numeric(self.path,'SMOKE')

    def test_main_gate_rejects_wrong_stage_order_and_changed_process_log(self):
        self.complete();path = self.folder/'smoke_pipeline_completion.json';original = study_io.read(path)
        wrong = deepcopy(original);wrong['steps'][0],wrong['steps'][1] = wrong['steps'][1],wrong['steps'][0]
        study_io.write(path,wrong,exclusive=False)
        with self.assertRaises(ValueError):collector.require_smoke(self.path,self.identity)
        study_io.write(path,original,exclusive=False)
        (self.folder/'smoke_pipeline/collect.txt').write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):collector.require_smoke(self.path,self.identity)

    def test_main_gate_requires_actual_four_step_chain(self):
        self.complete();path = self.folder/'smoke_record_audit.json';record = study_io.read(path)
        record['required_four_step_policy_chain'] = False;study_io.write(path,record,exclusive=False)
        with self.assertRaises(ValueError):collector.require_smoke(self.path,self.identity)

    def test_failed_pipeline_stops_and_cannot_restart_same_folder(self):
        def failed(args,**kwargs):
            kwargs['stdout'].write(b'preserved software child failure\n');return SimpleNamespace(returncode=7)
        with patch.object(study_io,'clean'),patch.object(study_io,'git',return_value='SOFTWARE_ONLY'), \
                patch.object(pipeline.subprocess,'run',side_effect=failed) as run:
            with self.assertRaises(RuntimeError):pipeline.pipeline(self.path,'SMOKE')
            self.assertEqual(run.call_count,1)
            with self.assertRaises(FileExistsError):pipeline.pipeline(self.path,'SMOKE')
            self.assertEqual(run.call_count,1)
        receipt = study_io.read(self.folder/'smoke_pipeline_completion.json')
        self.assertEqual(receipt['status'],'FAILED_PARTIAL');self.assertEqual(receipt['steps'][0]['returncode'],7)
        self.assertEqual(study_io.read(self.folder/'smoke_pipeline_status.json'),receipt)

    def test_untracked_new_source_blocks_freeze(self):
        with patch.object(study_io,'git',side_effect=['','src/analysis/not_yet_committed.py']):
            with self.assertRaises(ValueError):study_io.clean()
