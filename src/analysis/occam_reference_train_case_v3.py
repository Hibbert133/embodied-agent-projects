"""Execute one complete native case; raw scientific rows retain their schema."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import gzip,json,os,traceback
from src.analysis import occam_reference_train_io_v3 as a
from src.analysis import occam_reference_train_host_v3 as host
from src.analysis import occam_native_case_io_v1 as contract
from src.analysis.capsule_record_json_v2 import JsonJournal,normalize
from src.analysis.occam_case_events_v2 import emit_owned
from src.probe.lifecycle_ledger import LifecycleLedger
io=a.io


def native_dependencies():
    import metaworld
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    return SawyerXYZEnv,MujocoEnv,metaworld


def initialize_global_rng(registry):
    import random
    import numpy as np
    np.random.seed(registry['global_rng_seed_numpy']);random.seed(registry['global_rng_seed_python'])
    n=np.random.get_state();p=random.getstate()
    return dict(global_rng_seed_numpy=registry['global_rng_seed_numpy'],global_rng_seed_python=registry['global_rng_seed_python'],
        numpy_initial=dict(algorithm=n[0],vector_sha256=__import__('hashlib').sha256(n[1].tobytes()).hexdigest(),position=n[2],has_gaussian=n[3],cached_gaussian=n[4]),
        python_initial_sha256=contract.digest(p),scope='BEFORE_FACTORY_ONLY_NO_WITHIN_CASE_RESEED')


def run_case(value,directory,*,dependencies=None,execute=None):
    directory=Path(directory).resolve();m=contract.validate_request(value,directory);spec=value['case'];caps=a.limits(value['cohort'])
    a.checked(value['manifest_path']);a.validate_spec(spec);base=value['ledger_start'];contract.check_ledger(base)
    initial_frames=base['counts'].get('simulation_frames_attempted',0);initial_resets=base['counts'].get('reset_attempts',0)
    budget=dict(completed=value['control_steps_start'],maximum=value['control_steps_start']+500)
    identity={k:m[k] for k in a.IDENTITY};cur=value['cursors_start'];last={};failure=None;case=None;network={};started=perf_counter_ns()
    rng=initialize_global_rng(a.registry());contract.write(directory/'rng_initialization.json',rng);live_reseed_attempts=0
    dependencies=native_dependencies if dependencies is None else dependencies;execute=host.execute_case if execute is None else execute
    with gzip.open(directory/'events.jsonl.gz','xt',encoding='utf8') as events,gzip.open(directory/'witnesses.jsonl.gz','xt',encoding='utf8') as witnesses,\
        gzip.open(directory/'accounting_progress.jsonl.gz','xt',encoding='utf8') as progress:
        journal=JsonJournal(events,identity);private=JsonJournal(witnesses,identity);journal.sequence=cur['events'];private.sequence=cur['private']
        last_event_ns=cur['last_event_ns'];last_private_ns=cur['last_private_ns']
        def emit(kind,payload):
            nonlocal last,last_event_ns
            if kind=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts['reset_attempts']-initial_resets<=51 and ledger.counts['reset_attempts']<=caps['all_resets'],'per-case/all reset cap')
            row=emit_owned(journal,spec,kind,payload);io.require(row['saved_ns']>last_event_ns,'cross-process public clock reversed')
            last_event_ns=row['saved_ns'];last={k:row[k] for k in ('sequence','saved_ns')}
            if kind in ('LIFECYCLE_RESET_INTENT','LIFECYCLE_RESET_COMPLETE','STEP_INTENT','STEP_COMPLETE','CASE_COMPLETE'):
                progress.write(json.dumps(dict(public_sequence=row['sequence'],saved_ns=row['saved_ns'],event=kind,ledger=ledger.snapshot(),control_steps=budget['completed']),separators=(',',':'))+'\n');progress.flush()
            return row
        def emit_private(kind,payload):
            nonlocal last_private_ns
            row=emit_owned(private,spec,kind,payload);io.require(row['saved_ns']>last_private_ns,'cross-process private clock reversed');last_private_ns=row['saved_ns'];return row
        def sync():events.flush();os.fsync(events.fileno())
        ledger=LifecycleLedger(emit,min(caps['physical_frames'],initial_frames+28000));ledger.counts=Counter(base['counts']);ledger.by_phase={k:Counter(v) for k,v in base['by_phase'].items()}
        try:
            with io.forbid_online_calls(network):
                reset_class,simulation_class,factory=dependencies()
                with ledger.instrument(reset_class,simulation_class,factory):
                    first=journal.sequence;emit('CASE_ALLOCATION',dict(assignment='FROZEN_RANDOM_OR_BLOCK_TRAIN_BEHAVIOR'))
                    result=execute(spec,emit,emit_private,ledger,budget,lambda:deepcopy(last),sync)
                    case=normalize({**identity,**result,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence})
                    contract.write(directory/'case.json',case)
                    emit('CASE_COMPLETE',dict(case_record_sha256=io.digest(case),total_steps=case['total_steps'],deadline_loss=case['deadline_loss']))
        except BaseException as error:
            failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
            if isinstance(error,host.CaseFailure):contract.write(directory/'failed_execution.json',normalize({**identity,**error.record}))
            if isinstance(error,host.CaseFailure):live_reseed_attempts=sum(error.record.get('live_global_rng_guard',{}).get('attempts',{}).values())
            contract.write(directory/'execution_error.json',failure)
        for stream in (events,witnesses,progress):stream.flush();os.fsync(stream.fileno())
    accounting=dict(status='COMPLETE' if failure is None else 'FAILED_PARTIAL',cohort=value['cohort'],case_index=value['case_index'],
        ledger_start=base,ledger_after=ledger.snapshot(),control_steps_start=value['control_steps_start'],control_steps_after=budget['completed'],
        cursors_start=cur,cursors_after=dict(events=journal.sequence,private=private.sequence,last_event_ns=last_event_ns,last_private_ns=last_private_ns),
        failure=failure,network_guard=network,within_case_global_rng_reseeds=live_reseed_attempts,
        reseed_counter_semantics='ATTEMPTS_IN_LIVE_GUARD_INCLUDING_REJECTED_CALLS',online_LLM_API_calls=0,scientific_model_training=0,wall_ns=perf_counter_ns()-started)
    contract.write(directory/'accounting.json',accounting)
    if failure is not None:raise RuntimeError('isolated complete-case attempt failed; all partial files retained')
    io.require(case['total_steps']==budget['completed']-value['control_steps_start']<=500,'one actual task budget')
    return accounting
