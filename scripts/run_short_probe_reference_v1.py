"""One-shot independent-environment comparison of seven frozen cold programs."""
import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
from src.analysis import short_probe_study_io_v1 as io
from src.analysis.capsule_record_json_v2 import JsonJournal, normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.short_probe_reference_host_v1 import execute_short_session
from src.analysis.short_probe_study_v1 import METHODS, population, compact
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout.task_registry import create_task_environment, create_task_policy


class CollectionFailure(RuntimeError):
    def __init__(self, record):
        super().__init__('physical execution failed; preserve partial record')
        self.record = record


def execute_one(key, fault, model, design, emit, ledger, budget):
    row = {**key, 'fault_oracle':normalize(fault), 'completed':False, 'error':None, 'close_error':None,
        'environment_closed':False, 'lifecycle_before':ledger.snapshot(), 'host':None, 'public':None}
    env = session = None;before_close = None
    try:
        emit('FACTORY_INTENT', {'ledger':ledger.snapshot()})
        with ledger.scope('FACTORY_SETUP'):
            env = create_task_environment(key['task'], key['seed'])
        emit('FACTORY_COMPLETE', {'ledger':ledger.snapshot()})
        before_reset = ledger.snapshot()
        with ledger.scope('CONTROLLED_RESET'):
            initial, _ = env.reset(seed=key['seed'])
        session = ProbeSession(env, create_task_policy(key['task']), initial, key['task'], key['seed'], fault, emit, ledger, budget)
        row['host'], row['public'] = execute_short_session(session, key['method'], model, before_reset, design=design)
        row['completed'] = True
    except BaseException as error:
        row['error'] = {'type':type(error).__name__, 'message':str(error)}
        if session is not None:
            row['partial_host'] = {'step_attempts':session.attempts, 'returned_steps':session.completed,
                'unreturned_step_attempts':session.attempts-session.completed, 'policy_query_attempts':session.policy_queries,
                'returned_physical_rows':normalize(session.last_rows), 'optimizer_calls_and_nfev':'UNKNOWN_IF_NO_COMPLETED_PUBLIC_RECORD'}
    finally:
        before_close = ledger.snapshot()
        if env is not None:
            try:
                env.close();row['environment_closed'] = True
            except BaseException as error:
                row['close_error'] = {'type':type(error).__name__, 'message':str(error)}
        row['lifecycle_after_close'] = ledger.snapshot()
        if row['lifecycle_after_close'] != before_close:
            row['close_error'] = {'type':'UnexpectedCloseInteraction', 'message':'environment close changed physical ledger'}
    if row['error'] is not None or row['close_error'] is not None or not row['completed'] or not row['environment_closed']:
        row['completed'] = False;raise CollectionFailure(normalize(row))
    return normalize(row)


def prepare():
    io.clean();c = io.read(io.CONFIG);io.validate(c);prior, _, _, _ = io.sources(c)
    parent = ROOT/c['output_root']
    if list(parent.glob('*/manifest.json')):
        raise FileExistsError('one frozen experiment already prepared')
    names = set(prior['input_sha256']) | set(io.git('ls-files', 'src', 'scripts', 'tests').splitlines()) | {
        io.CONFIG.relative_to(ROOT).as_posix(), io.PROTOCOL, 'AGENTS.md', '.gitattributes',
        'outputs/short_probe_reference/.gitattributes', 'reports/short_probe_reference/.gitattributes', 'configs/short_probe_reference/planning_v1.json',
        'docs/research/short_probe_task_comparison_draft_20261018_zh.md'}
    names |= {c[k] for k in ('source_manifest','source_completion','source_record_audit','source_numeric_audit','nominal_designs','nominal_models')}
    commit = io.git('rev-parse', 'HEAD');run_id = 'short_probe_reference_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+commit[:12]
    m = {'experiment_run_id':run_id, 'source_git_commit':commit, 'config':c, 'prior_manifest_id':prior['manifest_id'],
        'population_oracle':{p:population(p) for p in ('SMOKE','MAIN')}, 'input_sha256':{p:io.sha(ROOT/p) for p in sorted(names)},
        **{k:prior[k] for k in ('library_source_sha256','native_library_sha256','policy_sha256')}}
    m['manifest_id'] = digest(m);folder = parent/run_id;folder.mkdir(parents=True)
    io.write(folder/'manifest.json', m);print((folder/'manifest.json').relative_to(ROOT), flush=True)


def require_smoke(path, m):
    folder = path.parent;summary = folder/'smoke/summary.json'
    record = io.read(folder/'smoke_record_audit.json');numeric = io.read(folder/'smoke_numeric_audit.json')
    report = io.read(folder/'smoke_analysis/report_receipt.json')
    pipeline = io.read(folder/'smoke_pipeline_completion.json')
    if any(v[k] != m[k] for v in (record,numeric,report,pipeline) for k in io.IDENTITY):
        raise ValueError('smoke identity differs')
    if record['integrity'] != 'PASSED' or not record['required_four_step_policy_chain'] or numeric['integrity'] != 'PASSED':
        raise ValueError('complete smoke record/numeric audits and actual four-step chain required')
    if record['summary_sha256'] != io.sha(summary) or numeric['summary_sha256'] != record['summary_sha256'] or numeric['statistics_sha256'] != io.sha(folder/'smoke_analysis/statistics.json'):
        raise ValueError('audited smoke bytes changed')
    if pipeline['status'] != 'COMPLETED_FOR_REVIEW' or pipeline['failure'] is not None or [v['stage'] for v in pipeline['steps']] != ['collect','record_audit','analyze','numeric_audit','report'] or any(type(v['returncode']) is not int or v['returncode'] != 0 for v in pipeline['steps']):
        raise ValueError('completed five-stage smoke pipeline required')
    if any(v['log_sha256'] != io.sha(folder/'smoke_pipeline'/(v['stage']+'.txt')) for v in pipeline['steps']):
        raise ValueError('smoke process logs changed')
    if numeric['costs_sha256'] != io.sha(folder/'smoke_analysis/costs.json') or numeric['record_audit_sha256'] != io.sha(folder/'smoke_record_audit.json'):
        raise ValueError('audited smoke costs changed')
    if report['report_sha256'] != io.sha(ROOT/report['report_path']) or report['record_audit_sha256'] != io.sha(folder/'smoke_record_audit.json') or report['numeric_audit_sha256'] != io.sha(folder/'smoke_numeric_audit.json'):
        raise ValueError('reviewable smoke report required')


def run(path, phase):
    io.clean();m, models, designs = io.load(path)
    if io.git('rev-parse', 'HEAD') != m['source_git_commit']:
        raise ValueError('execute only the frozen commit')
    if phase == 'MAIN':
        require_smoke(path, m)
    folder = path.parent/phase.lower();folder.mkdir()
    identity = {k:m[k] for k in io.IDENTITY};limits = m['config'][phase.lower()]
    budget = {'completed':0, 'maximum':limits['maximum_environment_steps']};rows = [];started = perf_counter_ns()
    status = {**identity, 'phase':phase, 'status':'RUNNING', 'completed_executions':0};current_key = {};failed = None
    io.write(folder/'status.json', status)
    with gzip.open(folder/'events.jsonl.gz', 'xt', encoding='utf-8') as handle:
        writer = JsonJournal(handle, identity)
        def emit(event, payload):
            return writer.emit(event, {**current_key, **payload})
        ledger = LifecycleLedger(emit, limits['maximum_simulation_frames'])
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
                for stream in m['population_oracle'][phase]:
                    with gzip.open(folder/f"cases_{stream['stream']:02}.jsonl.gz", 'xt', encoding='utf-8') as cases:
                        for spec in stream['cases']:
                            for method in METHODS:
                                current_key = {'study_phase':phase, 'stream':stream['stream'], 'episode':spec['episode'],
                                    'task':spec['task'], 'seed':spec['seed'], 'method':method}
                                key = {**identity, **current_key, **{k:stream[k] for k in ('family_oracle','schedule_oracle')}}
                                record = execute_one(key, spec['fault_oracle'], None if method == 'NO_PROBE' else models[spec['task']],
                                    designs[spec['task']] if method.startswith('DOPT') else None, emit, ledger, budget)
                                cases.write(json.dumps(record, ensure_ascii=False, allow_nan=False)+'\n');cases.flush()
                                rows.append(compact(record));status['completed_executions'] = len(rows)
                                status.update(controlled_steps=budget['completed'], lifecycle=ledger.snapshot())
                                io.write(folder/'status.json', status, exclusive=False)
                            print(f"{phase} units={len(rows)//7}/{limits['units']} executions={len(rows)} steps={budget['completed']}", flush=True)
            if len(rows) != limits['executions'] or ledger.counts['reset_completed'] != limits['executions']*51 or ledger.by_phase['CONTROLLED_RESET']['reset_completed'] != limits['maximum_controlled_resets']:
                raise ValueError('incomplete frozen population/reset accounting')
            status.update(status='COLLECTED_FOR_INDEPENDENT_AUDIT', wall_ns=perf_counter_ns()-started,
                rows=rows, lifecycle=ledger.snapshot(), controlled_steps=budget['completed'], failure=None,
                new_api_calls=0, new_nominal_training=0, new_selector_fits=0, policy_updates=0, computation_counters_complete=True)
        except BaseException as error:
            failed = error;status.update(status='FAILED_PARTIAL', failure={'type':type(error).__name__, 'message':str(error)},
                wall_ns=perf_counter_ns()-started, rows=rows, lifecycle=ledger.snapshot(), controlled_steps=budget['completed'],
                computation_counters_complete=False)
            if isinstance(error, CollectionFailure):
                io.write(folder/'failed_execution.json', error.record)
    io.write(folder/'summary.json', status);io.write(folder/'status.json', {k:v for k,v in status.items() if k != 'rows'}, exclusive=False)
    io.write(folder/'completion.json', {**identity, 'phase':phase, 'status':status['status'],
        'artifact_sha256':{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}})
    if failed is not None:
        raise failed
    print(json.dumps({k:status[k] for k in ('phase','status','completed_executions','controlled_steps','wall_ns')}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('command', choices=('prepare','run'));p.add_argument('--manifest', type=Path)
    p.add_argument('--phase', choices=('SMOKE','MAIN'));args = p.parse_args()
    if args.command == 'prepare':
        prepare()
    elif args.manifest is None or args.phase is None:
        p.error('--manifest and --phase required')
    else:
        run(args.manifest.resolve(), args.phase)
