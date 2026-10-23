"""One frozen 18-case native run, full failure records and physical accounting."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import gzip,json,os,shutil
from src.analysis import native_command_witness_io_v1 as a,native_command_witness_host_v1 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger
io=a.io


def collect(path):
    path=Path(path).resolve();m=a.checked(path);io.require(io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('status','--porcelain','--untracked-files=no'),'frozen clean native execution')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.VALIDATION/'runtime_lock.json'))
    out=path.parent/'native';out.mkdir(exist_ok=False);identity={k:m[k] for k in a.IDENTITY};limits=a.config()['limits'];start=perf_counter_ns()
    budget={'completed':0,'maximum':limits['control_steps']};key={};last={};completed=[];failure=failed=None;network={};fit_guard={}
    with gzip.open(out/'events.jsonl.gz','xt',encoding='utf-8',newline='\n') as ef,gzip.open(out/'cases.jsonl.gz','xt',encoding='utf-8',newline='\n') as cf,\
        gzip.open(out/'private_targets.jsonl.gz','xt',encoding='utf-8',newline='\n') as pf,gzip.open(out/'public_trajectories.jsonl.gz','xt',encoding='utf-8',newline='\n') as xf:
        journal=JsonJournal(ef,identity);private_journal=JsonJournal(pf,identity)
        def emit(kind,payload):
            nonlocal last
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'case ownership')
            if kind=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts['reset_attempts']<=limits['all_resets'],'whole native reset cap')
            value=journal.emit(kind,{**key,**payload});last={k:value[k] for k in ('sequence','saved_ns')};return value
        def private(kind,payload):return private_journal.emit(kind,{**key,**payload})
        def sync():
            for f in (ef,pf):f.flush();os.fsync(f.fileno())
        ledger=LifecycleLedger(emit,limits['physical_frames'])
        try:
            with io.forbid_online_calls(network),a.forbid_fitting(fit_guard):
                import metaworld
                from metaworld.sawyer_xyz_env import SawyerXYZEnv
                from gymnasium.envs.mujoco import MujocoEnv
                with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                    for spec in a.population():
                        io.require(shutil.disk_usage(io.ROOT).free>=512*1024**2,'emergency disk reserve');key=dict(spec);first=journal.sequence
                        emit('CASE_ALLOCATION',{'assignment':'FIXED_NATIVE_COLLECTOR_NOT_TRAINING','no_online_method_selection':True})
                        result,public=host.execute_case(spec,emit,private,ledger,budget,lambda:deepcopy(last),sync)
                        result={**identity,**result,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence,'public_trajectory_sha256':io.digest(public)}
                        cf.write(json.dumps(result,allow_nan=False,separators=(',',':'))+'\n');cf.flush()
                        xf.write(json.dumps(public,allow_nan=False,separators=(',',':'))+'\n');xf.flush()
                        emit('CASE_COMPLETE',{'case_record_sha256':io.digest(result)});completed.append({k:result[k] for k in (*a.KEYS,'total_steps','success','deadline_loss','complete_warm_window','warm_probe_steps','stop_reason')})
                        io.write(out/'status.json',{'status':'RUNNING','completed':len(completed),'control_steps':budget['completed'],'ledger':ledger.snapshot()},exclusive=False)
                        print({'completed':len(completed),'allocated':18,'steps':budget['completed']},flush=True)
        except BaseException as error:
            failure={'type':type(error).__name__,'message':str(error)}
            if isinstance(error,host.CaseFailure):failed={**identity,**error.record};io.write(out/'failed_case.json',failed)
        for f in (ef,cf,pf,xf):f.flush();os.fsync(f.fileno())
    result={**identity,'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL','executions':len(completed),'rows':completed,
        'control_steps':budget['completed'],'lifecycle':ledger.snapshot(),'events':journal.sequence,'private_target_records':private_journal.sequence,
        'failure':failure,'network_guard':network,'fitting_guard':fit_guard,'wall_ns':perf_counter_ns()-start,'new_model_fits':0,'online_LLM_API_calls':0,'publication_goal_complete':False}
    io.write(out/'summary.json',result);io.write(out/'status.json',{k:v for k,v in result.items() if k!='rows'},exclusive=False)
    io.write(out/'completion.json',{'status':result['status'],'manifest_id':m['manifest_id'],'artifact_sha256':{p.name:io.sha(p) for p in out.iterdir() if p.is_file()}})
    a.checked(path)
    if failure is not None:raise RuntimeError('Native one-shot failure preserved '+str(failure))
    return result
