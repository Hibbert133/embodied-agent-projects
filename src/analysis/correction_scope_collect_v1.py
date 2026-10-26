"""One-shot actual A1 cohorts. No online LLM, fitting or restoring trajectories."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import gzip,json,os,shutil
from src.analysis import correction_scope_io_v1 as a
from src.analysis import correction_scope_host_v1 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger
io=a.io


def collect(path,cohort):
    path=Path(path).resolve();m=a.phase_gate(path,cohort);out=path.parent/cohort.lower();out.mkdir(exist_ok=False)
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.VALIDATION/'runtime_lock.json'))
    bank=None if cohort in ('NATIVE','TRAIN') else io.read(path.parent/'learning/bank.json')
    identity={k:m[k] for k in a.IDENTITY};caps=a.limits(cohort);budget=dict(completed=0,maximum=caps['control_steps'])
    start=perf_counter_ns();key={};last={};compact=[];failed=failure=None;network={}
    with gzip.open(out/'events.jsonl.gz','xt',encoding='utf-8') as ef,gzip.open(out/'cases.jsonl.gz','xt',encoding='utf-8') as cf,gzip.open(out/'witnesses.jsonl.gz','xt',encoding='utf-8') as wf:
        journal=JsonJournal(ef,identity);private=JsonJournal(wf,identity)
        def wrapped(target,name,payload):
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'case ownership override')
            return target.emit(name,{**key,**payload})
        def emit(name,payload):
            nonlocal last
            if name=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts.get('reset_attempts',0)<=caps['all_resets'],'reset cap')
            v=wrapped(journal,name,payload);last={k:v[k] for k in ('sequence','saved_ns')};return v
        def emit_private(name,payload):return wrapped(private,name,payload)
        def sync():ef.flush();os.fsync(ef.fileno())
        ledger=LifecycleLedger(emit,caps['physical_frames'])
        try:
            with io.forbid_online_calls(network):
                import metaworld
                from metaworld.sawyer_xyz_env import SawyerXYZEnv
                from gymnasium.envs.mujoco import MujocoEnv
                with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                    for spec in a.population(cohort):
                        io.require(shutil.disk_usage(io.ROOT).free>=512*1024**2,'emergency disk reserve')
                        key=dict(spec);first=journal.sequence;emit('CASE_ALLOCATION',dict(assignment='FROZEN_FACTUAL_FORECAST_ARM'))
                        result=host.execute_case(spec,emit,emit_private,ledger,budget,lambda:deepcopy(last),sync,bank)
                        result={**identity,**result,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence}
                        cf.write(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n');cf.flush()
                        emit('CASE_COMPLETE',dict(case_record_sha256=io.digest(result),total_steps=result['total_steps'],deadline_loss=result['deadline_loss']))
                        compact.append({k:result[k] for k in (*a.KEYS,'total_steps','deadline_loss','success','policy_queries','movement_steps','measurement_steps','stop_reason','boundary_applied')})
                        io.write(out/'status.json',dict(status='RUNNING',cohort=cohort,completed=len(compact),steps=budget['completed'],lifecycle=ledger.snapshot()),exclusive=False)
                        print(dict(cohort=cohort,completed=len(compact),allocated=caps['executions'],steps=budget['completed']),flush=True)
        except BaseException as error:
            failure=dict(type=type(error).__name__,message=str(error))
            if isinstance(error,host.CaseFailure):failed={**identity,**error.record};io.write(out/'failed_execution.json',failed)
        for stream in (ef,cf,wf):stream.flush();os.fsync(stream.fileno())
    summary={**identity,'cohort':cohort,'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL',
        'allocated_executions':caps['executions'],'executions':len(compact),'rows':compact,'control_steps':budget['completed'],'lifecycle':ledger.snapshot(),
        'events':journal.sequence,'private_records':private.sequence,'failure':failure,'wall_ns':perf_counter_ns()-start,
        'network_guard':network,'online_LLM_API_calls':0,'new_model_fits':0,'new_policy_training':0,'prediction_only_not_method_selection':True,
        'execution_git_head':io.git('rev-parse','HEAD'),'publication_goal_complete':False}
    io.write(out/'summary.json',summary);io.write(out/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(out/'completion.json',dict(status=summary['status'],manifest_id=m['manifest_id'],artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()}))
    a.checked(path)
    if failure is not None:raise RuntimeError('One-shot A1 phase stopped; partial preserved '+str(failure))
    return out
