"""One native allocation. All errors stop; no replaced/restarted experiment."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import gzip,json,os,shutil
from src.analysis import occam_reference_train_io_v2 as a
from src.analysis import occam_reference_train_host_v2 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger
from src.analysis.occam_case_events_v2 import emit_owned
io=a.io


def native_dependencies():
    import metaworld
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco import MujocoEnv
    return SawyerXYZEnv,MujocoEnv,metaworld


def collect(path,phase):
    path=Path(path).resolve();m=a.phase_gate(path,phase);out=path.parent/phase.lower();out.mkdir(exist_ok=False)
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.RUNTIME));identity={k:m[k] for k in a.IDENTITY};caps=a.limits(phase);budget=dict(completed=0,maximum=caps['control_steps'])
    start=perf_counter_ns();key={};last={};compact=[];failure=None;network={}
    with gzip.open(out/'events.jsonl.gz','xt',encoding='utf8') as ef,gzip.open(out/'cases.jsonl.gz','xt',encoding='utf8') as cf,gzip.open(out/'witnesses.jsonl.gz','xt',encoding='utf8') as wf:
        journal=JsonJournal(ef,identity);private=JsonJournal(wf,identity)
        def wrapped(target,name,payload):
            return emit_owned(target,key,name,payload)
        def emit(name,payload):
            nonlocal last
            if name=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts.get('reset_attempts',0)<=caps['all_resets'],'reset cap')
            v=wrapped(journal,name,payload);last={k:v[k] for k in ('sequence','saved_ns')};return v
        def emit_private(name,payload):return wrapped(private,name,payload)
        def sync():ef.flush();os.fsync(ef.fileno())
        ledger=LifecycleLedger(emit,caps['physical_frames'])
        try:
            with io.forbid_online_calls(network):
                reset_class,simulation_class,factory_module=native_dependencies()
                with ledger.instrument(reset_class,simulation_class,factory_module):
                    for spec in a.population(phase):
                        io.require(shutil.disk_usage(io.ROOT).free>=512*1024**2,'emergency disk reserve')
                        key=dict(spec);first=journal.sequence;emit('CASE_ALLOCATION',dict(assignment='FROZEN_RANDOM_OR_BLOCK_TRAIN_BEHAVIOR'))
                        result=host.execute_case(spec,emit,emit_private,ledger,budget,lambda:deepcopy(last),sync)
                        result={**identity,**result,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence}
                        cf.write(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n');cf.flush()
                        emit('CASE_COMPLETE',dict(case_record_sha256=io.digest(result),total_steps=result['total_steps'],deadline_loss=result['deadline_loss']))
                        compact.append({k:result[k] for k in (*a.KEYS,'total_steps','deadline_loss','success','policy_queries','performance_windows','full_feedback_windows','boundary_applied')})
                        io.write(out/'status.json',dict(status='RUNNING',completed=len(compact),control_steps=budget['completed']),exclusive=False)
                        print(dict(completed=len(compact),allocated=caps['executions'],control_steps=budget['completed']),flush=True)
        except BaseException as error:
            failure=dict(type=type(error).__name__,message=str(error))
            if isinstance(error,host.CaseFailure):io.write(out/'failed_execution.json',{**identity,**error.record})
        for stream in (ef,cf,wf):stream.flush();os.fsync(stream.fileno())
    summary={**identity,'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL',
        'allocated_executions':caps['executions'],'executions':len(compact),'rows':compact,'control_steps':budget['completed'],'lifecycle':ledger.snapshot(),
        'events':journal.sequence,'private_records':private.sequence,'failure':failure,'wall_ns':perf_counter_ns()-start,
        'network_guard':network,'online_LLM_API_calls':0,'scientific_model_training':0,'training_behavior_data_not_task_qualification':True,
        'execution_git_head':io.git('rev-parse','HEAD'),'publication_goal_complete':False}
    io.write(out/'summary.json',summary);io.write(out/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(out/'completion.json',dict(status=summary['status'],manifest_id=m['manifest_id'],artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()}))
    a.checked(path)
    if failure is not None:raise RuntimeError('One-shot native stopped; preserve partial '+str(failure))
    return out
