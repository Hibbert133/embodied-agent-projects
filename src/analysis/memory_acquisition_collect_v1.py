"""One source-frozen native software allocation; keep partial failures, never retry."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import gzip,json,os,shutil
from src.analysis import memory_acquisition_io_v1 as allocation
from src.analysis import memory_acquisition_host_v1 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger
io=allocation.io


def collect(path):
    path=Path(path).resolve();m=allocation.checked(path);out=path.parent/'native';out.mkdir(exist_ok=False)
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(allocation.VALIDATION/'runtime_lock.json'))
    io.require(shutil.disk_usage(io.ROOT).free>=4*1024**3,'storage reserve before construction')
    identity={k:m[k] for k in allocation.IDENTITY};limits=allocation.limits();budget={'completed':0,'maximum':limits['control_steps']}
    begin=perf_counter_ns();key={};last={};compact=[];failed=failure=None;network={}
    with gzip.open(out/'events.jsonl.gz','xt',encoding='utf-8') as ef,gzip.open(out/'cases.jsonl.gz','xt',encoding='utf-8') as cf,gzip.open(out/'witnesses.jsonl.gz','xt',encoding='utf-8') as wf:
        journal=JsonJournal(ef,identity);private=JsonJournal(wf,identity)
        def wrapped(target,event,payload):
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'case ownership override')
            return target.emit(event,{**key,**payload})
        def emit(event,payload):
            nonlocal last
            if event=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts.get('reset_attempts',0)<=limits['all_resets'],'reset budget')
            v=wrapped(journal,event,payload);last={k:v[k] for k in ('sequence','saved_ns')};return v
        def emit_private(event,payload):return wrapped(private,event,payload)
        def sync():ef.flush();os.fsync(ef.fileno())
        ledger=LifecycleLedger(emit,limits['physical_frames'])
        try:
            with io.forbid_online_calls(network):
                import metaworld
                from metaworld.sawyer_xyz_env import SawyerXYZEnv
                from gymnasium.envs.mujoco import MujocoEnv
                with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                    for spec in allocation.population():
                        io.require(shutil.disk_usage(io.ROOT).free>=512*1024**2,'emergency storage reserve')
                        key={k:spec[k] for k in allocation.KEYS};first=journal.sequence
                        result=host.execute_case(spec,emit,emit_private,ledger,budget,lambda:deepcopy(last),sync)
                        result={**identity,**result,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence}
                        cf.write(json.dumps(result,allow_nan=False,separators=(',',':'))+'\n');cf.flush()
                        emit('CASE_COMPLETE',{'case_record_sha256':io.digest(result),'total_steps':result['total_steps'],'deadline_loss':result['deadline_loss']})
                        compact.append({k:result[k] for k in (*allocation.KEYS,'total_steps','deadline_loss','success','policy_queries','option_reason','option_steps','movement_steps','warm_probe_steps','complete_warm_window','boundary_reached','stop_reason')})
                        io.write(out/'status.json',{'status':'RUNNING','completed':len(compact),'steps':budget['completed'],'lifecycle':ledger.snapshot()},exclusive=False)
                        print({'completed':len(compact),'allocated':54,'control_steps':budget['completed']},flush=True)
        except BaseException as error:
            failure={'type':type(error).__name__,'message':str(error)}
            if isinstance(error,host.CaseFailure):failed={**identity,**error.record};io.write(out/'failed_execution.json',failed)
        for stream in (ef,cf,wf):stream.flush();os.fsync(stream.fileno())
    summary={**identity,'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL','allocated_executions':54,'executions':len(compact),
        'rows':compact,'control_steps':budget['completed'],'lifecycle':ledger.snapshot(),'events':journal.sequence,'private_records':private.sequence,
        'failure':failure,'wall_ns':perf_counter_ns()-begin,'new_parameter_fits':0,'new_response_training':0,'new_policy_training':0,'online_LLM_API_calls':0,'network_guard':network,
        'execution_git_head':io.git('rev-parse','HEAD'),'no_safety_or_task_gain_claim':True}
    io.write(out/'summary.json',summary);io.write(out/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(out/'completion.json',{'status':summary['status'],'manifest_id':m['manifest_id'],'artifact_sha256':{p.name:io.sha(p) for p in out.iterdir() if p.is_file()}})
    allocation.checked(path)
    if failure is not None:raise RuntimeError('one-shot native collection stopped; partial failure retained '+str(failure))
    return out
