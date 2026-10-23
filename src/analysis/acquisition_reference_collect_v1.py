"""One native cohort then one independent QUAL allocation; never retry or append."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import gzip,json,os,shutil
from src.analysis import acquisition_reference_io_v1 as a
from src.analysis import acquisition_reference_host_v1 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.acquisition_reference_program_v1 import is_legacy
io=a.io


def collect(path,cohort):
    path=Path(path).resolve();m=a.phase_gate(path,cohort);out=path.parent/cohort.lower();out.mkdir(exist_ok=False)
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.VALIDATION/'runtime_lock.json'));nominal,_=a.source_models()
    identity={k:m[k] for k in a.IDENTITY};limits=a.limits(cohort);budget={'completed':0,'maximum':limits['control_steps']}
    start=perf_counter_ns();key={};last={};compact=[];failed=failure=None;network={}
    with gzip.open(out/'events.jsonl.gz','xt',encoding='utf-8') as ef,gzip.open(out/'cases.jsonl.gz','xt',encoding='utf-8') as cf,gzip.open(out/'witnesses.jsonl.gz','xt',encoding='utf-8') as wf:
        journal=JsonJournal(ef,identity);private=JsonJournal(wf,identity)
        def wrapped(target,name,payload):
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'case ownership override')
            return target.emit(name,{**key,**payload})
        def emit(name,payload):
            nonlocal last
            if name=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts.get('reset_attempts',0)<=limits['all_resets'],'reset cap')
            v=wrapped(journal,name,payload);last={k:v[k] for k in ('sequence','saved_ns')};return v
        def emit_private(name,payload):return wrapped(private,name,payload)
        def sync():ef.flush();os.fsync(ef.fileno())
        ledger=LifecycleLedger(emit,limits['physical_frames'])
        try:
            with io.forbid_online_calls(network):
                import metaworld
                from metaworld.sawyer_xyz_env import SawyerXYZEnv
                from gymnasium.envs.mujoco import MujocoEnv
                with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                    for spec in a.population(cohort):
                        io.require(shutil.disk_usage(io.ROOT).free>=512*1024**2,'emergency storage reserve')
                        key={k:spec[k] for k in a.KEYS};first=journal.sequence
                        emit('CASE_ALLOCATION',{'assignment':'FIXED_STANDARD_COMPLETE_PROGRAM','no_online_method_selection':True})
                        result=host.execute_case(spec,nominal[spec['task']] if is_legacy(spec['program']) else None,emit,emit_private,ledger,budget,lambda:deepcopy(last),sync)
                        result={**identity,**result,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence}
                        cf.write(json.dumps(result,allow_nan=False,separators=(',',':'))+'\n');cf.flush()
                        emit('CASE_COMPLETE',{'case_record_sha256':io.digest(result),'total_steps':result['total_steps'],'deadline_loss':result['deadline_loss']})
                        compact.append({k:result[k] for k in (*a.KEYS,'total_steps','deadline_loss','success','policy_queries','option_reason','movement_steps','warm_probe_steps',
                            'complete_warm_window','stop_reason','reference_update_applied','reference_update_mode','reference_admission_reason','acquisition_entered',
                            'c4_c8_fit_attempts','c4_c8_fit_results','c4_c8_optimizer_nfev')})
                        io.write(out/'status.json',{'status':'RUNNING','cohort':cohort,'completed':len(compact),'steps':budget['completed'],'lifecycle':ledger.snapshot()},exclusive=False)
                        print({'cohort':cohort,'completed':len(compact),'allocated':limits['executions'],'steps':budget['completed']},flush=True)
        except BaseException as error:
            failure={'type':type(error).__name__,'message':str(error)}
            if isinstance(error,host.CaseFailure):failed={**identity,**error.record};io.write(out/'failed_execution.json',failed)
        for stream in (ef,cf,wf):stream.flush();os.fsync(stream.fileno())
    fits=sum(r['c4_c8_fit_attempts'] for r in compact)+(0 if failed is None else failed.get('c4_c8_fit_attempts',0))
    io.require(fits<=limits['c4_c8_fit_attempts'],'initial fitting cap')
    summary={**identity,'cohort':cohort,'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL','allocated_executions':limits['executions'],
        'executions':len(compact),'rows':compact,'control_steps':budget['completed'],'lifecycle':ledger.snapshot(),'events':journal.sequence,'private_records':private.sequence,
        'c4_c8_fit_attempts':fits,'failure':failure,'wall_ns':perf_counter_ns()-start,'new_response_training':0,'new_policy_training':0,'online_LLM_API_calls':0,
        'network_guard':network,'execution_git_head':io.git('rev-parse','HEAD'),'standard_reference_not_new_algorithm':True,'publication_goal_complete':False}
    io.write(out/'summary.json',summary);io.write(out/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(out/'completion.json',{'status':summary['status'],'manifest_id':m['manifest_id'],'artifact_sha256':{p.name:io.sha(p) for p in out.iterdir() if p.is_file()}})
    a.checked(path)
    if failure is not None:raise RuntimeError('one-shot phase stopped with partial records preserved '+str(failure))
    return out
