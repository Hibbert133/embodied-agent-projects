"""One native allocation; immutable weights, no online fitting/API/restarts."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import gzip,json,os,shutil
from src.analysis import learned_acquisition_native_io_v1 as a
from src.analysis import learned_acquisition_native_host_v1 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.frozen_risk_client_v1 import FrozenRiskClient
from src.probe.lifecycle_ledger import LifecycleLedger
io=a.io


def collect(path):
    path=Path(path).resolve();m=a.checked(path)
    io.require(io.git('rev-parse','HEAD')==m['source_git_commit'],'freeze remains current at one-shot execution')
    io.require(io.read(path.parent/'training_signal/audit.json')['integrity']=='PASSED','checked read-only signal diagnosis before native execution')
    out=path.parent/'native';out.mkdir(exist_ok=False)
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(io.ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    client=FrozenRiskClient(a.ASSETS/'bundle.json',maximum_calls=36);caps=a.limits();identity={k:m[k] for k in a.IDENTITY}
    budget=dict(completed=0,maximum=caps['control_steps']);start=perf_counter_ns();key={};last={};compact=[];failure=failed=None;network={};fits={'attempts':0}
    def no_fit(*args,**kwargs):fits['attempts']+=1;raise RuntimeError('Fitting forbidden during frozen native integration')
    with gzip.open(out/'events.jsonl.gz','xt',encoding='utf8') as ef,gzip.open(out/'cases.jsonl.gz','xt',encoding='utf8') as cf,gzip.open(out/'witnesses.jsonl.gz','xt',encoding='utf8') as wf:
        journal=JsonJournal(ef,identity);private=JsonJournal(wf,identity)
        def wrapped(target,name,payload):
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'native case ownership')
            return target.emit(name,{**key,**payload})
        def emit(name,payload):
            nonlocal last
            if name=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts.get('reset_attempts',0)<=caps['all_resets'],'all-reset cap')
            value=wrapped(journal,name,payload);last={k:value[k] for k in ('sequence','saved_ns')};return value
        def emit_private(name,payload):return wrapped(private,name,payload)
        def sync():ef.flush();os.fsync(ef.fileno())
        ledger=LifecycleLedger(emit,caps['physical_frames'])
        try:
            with io.forbid_online_calls(network),ExitStack() as stack:
                import metaworld,scipy.optimize
                from metaworld.sawyer_xyz_env import SawyerXYZEnv
                from gymnasium.envs.mujoco import MujocoEnv
                from src.analysis import transfer_risk_math_v1,correction_scope_risk_reference_v1
                from src.probe import correction_scope_model_v1,task_passive_program_v1
                for obj,name in ((transfer_risk_math_v1,'fit'),(correction_scope_risk_reference_v1,'fit_model'),
                    (correction_scope_model_v1,'fit'),(task_passive_program_v1,'infer_four'),(task_passive_program_v1,'infer_operator'),(scipy.optimize,'least_squares')):
                    stack.enter_context(patch.object(obj,name,no_fit))
                with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                    for spec in a.population():
                        io.require(shutil.disk_usage(io.ROOT).free>=2*1024**3,'2GiB free-space prerequisite')
                        key=dict(spec);first=journal.sequence;before_calls=client.calls;emit('CASE_ALLOCATION',dict(assignment='FROZEN_NATIVE_INTEGRATION_PROGRAM'))
                        result=host.execute_case(spec,emit,emit_private,ledger,budget,lambda:deepcopy(last),sync,client)
                        result={**identity,**result,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence,'live_model_calls':client.calls-before_calls}
                        cf.write(json.dumps(result,separators=(',',':'),allow_nan=False)+'\n');cf.flush()
                        emit('CASE_COMPLETE',dict(case_record_sha256=io.digest(result),total_steps=result['total_steps'],deadline_loss=result['deadline_loss']))
                        compact.append({k:result[k] for k in (*a.KEYS,'total_steps','deadline_loss','success','policy_queries','movement_steps','measurement_steps','selected_action','selected_rate','live_model_calls','stop_reason')})
                        io.write(out/'status.json',dict(status='RUNNING',completed=len(compact),steps=budget['completed'],lifecycle=ledger.snapshot(),live_model_calls=client.calls),exclusive=False)
                        print(dict(completed=len(compact),allocated=54,steps=budget['completed'],live_model_calls=client.calls),flush=True)
        except BaseException as error:
            failure=dict(type=type(error).__name__,message=str(error))
            if isinstance(error,host.CaseFailure):failed={**identity,**error.record};io.write(out/'failed_execution.json',failed)
        for stream in (ef,cf,wf):stream.flush();os.fsync(stream.fileno())
    summary={**identity,'classification':m['classification'],'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL',
        'allocated_executions':54,'executions':len(compact),'rows':compact,'control_steps':budget['completed'],'lifecycle':ledger.snapshot(),
        'events':journal.sequence,'private_records':private.sequence,'failure':failure,'live_model_calls':client.calls,'forbidden_fit_guard':fits,
        'network_guard':network,'new_model_fits':0,'online_LLM_API_calls':0,'new_policy_training':0,'source_models_immutable':True,
        'wall_ns':perf_counter_ns()-start,'execution_git_head':io.git('rev-parse','HEAD'),'task_gain_qualification':False,'publication_goal_complete':False}
    io.write(out/'summary.json',summary);io.write(out/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(out/'completion.json',dict(status=summary['status'],manifest_id=m['manifest_id'],artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()}))
    a.checked(path)
    io.require(failure is None,'One-shot native allocation stopped; partial preserved '+str(failure))
    return out
