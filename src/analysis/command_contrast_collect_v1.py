"""One-shot native software or independent qualification, with complete raw journals."""
from copy import deepcopy
import gzip
import json
import os
import shutil
from pathlib import Path
from time import perf_counter_ns
from src.analysis import command_contrast_io_v1 as allocation
from src.analysis import command_contrast_host_v1 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger


def collect(path,cohort):
    path=Path(path).resolve(); io=allocation.io; manifest=allocation.phase_gate(path,cohort)
    specs=manifest['config']['native_software_population' if cohort=='SOFTWARE_NATIVE' else 'population']
    limits=manifest['config']['native_software_limits' if cohort=='SOFTWARE_NATIVE' else 'limits']
    folder=path.parent/('software_native' if cohort=='SOFTWARE_NATIVE' else 'collection')
    io.require(not folder.exists(),'one-shot phase already started; preserve failed/complete records')
    folder.mkdir(); identity={k:manifest[k] for k in ('experiment_run_id','manifest_id','source_git_commit')}
    models,nominal,_=allocation.source_models(); budget={'completed':0,'maximum':limits['control_steps']}
    started=perf_counter_ns(); key={}; last={}; compact=[]; failure=failed=None; reference=None; unit=None
    network={}; journal=private=ledger=None
    with gzip.open(folder/'events.jsonl.gz','xt',encoding='utf-8') as ef,\
         gzip.open(folder/'cases.jsonl.gz','xt',encoding='utf-8') as cf,\
         gzip.open(folder/'witnesses.jsonl.gz','xt',encoding='utf-8') as wf:
        journal=JsonJournal(ef,identity); private=JsonJournal(wf,identity)
        def wrapped_emit(target,event,payload):
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'case ownership override')
            return target.emit(event,{**key,**payload})
        def emit(event,payload):
            nonlocal last
            if event=='LIFECYCLE_RESET_INTENT': io.require(ledger.counts.get('reset_attempts',0)<=limits['all_resets'],'all-reset budget exhausted')
            value=wrapped_emit(journal,event,payload); last={k:value[k] for k in ('sequence','saved_ns')}; return value
        def emit_private(event,payload): return wrapped_emit(private,event,payload)
        def sync():
            for handle in (ef,cf,wf): handle.flush(); os.fsync(handle.fileno())
        ledger=LifecycleLedger(emit,limits['physical_frames'])
        try:
            with io.forbid_online_calls(network):
                import metaworld
                from metaworld.sawyer_xyz_env import SawyerXYZEnv
                from gymnasium.envs.mujoco import MujocoEnv
                with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                    for spec in specs:
                        io.require(shutil.disk_usage(allocation.ROOT).free>=512*1024**2,'emergency disk reserve exhausted; keep partial records')
                        key={k:spec[k] for k in ('cohort','case_id','unit_id','group','task','seed','context','measurement_program','target','action_id')}
                        if spec['unit_id']!=unit:
                            io.require(spec['action_id']=='BASELINE','first actual branch must save every prediction before query outcomes')
                            unit=spec['unit_id']; reference=None
                        start_sequence=journal.sequence
                        result,produced=host.execute_case(spec,nominal[spec['task']],models[spec['task']],emit,emit_private,
                            ledger,budget,lambda:deepcopy(last),sync,reference)
                        if spec['action_id']=='BASELINE': reference=produced
                        result={**identity,**result,'event_start_sequence':start_sequence,'event_end_sequence_exclusive':journal.sequence}
                        cf.write(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n'); cf.flush()
                        emit('CASE_COMPLETE',{'case_record_sha256':io.digest(result),'total_steps':result['total_steps'],
                             'query_available':result['query_available'],'missing_reason':result['missing_reason']})
                        compact.append({k:result[k] for k in ('case_id','unit_id','group','task','context','measurement_program','target','action_id',
                            'total_steps','query_available','missing_reason','c4_c8_fit_attempts','c4_c8_fit_results','c4_c8_optimizer_nfev')})
                        io.write(folder/'status.json',{**identity,'status':'RUNNING','cohort':cohort,'completed_executions':len(compact),
                            'control_steps':budget['completed'],'lifecycle':ledger.snapshot()},exclusive=False)
                        print(json.dumps({'cohort':cohort,'completed':len(compact),'allocated':len(specs),'steps':budget['completed']}),flush=True)
                io.require(len(compact)==len(specs),'incomplete allocated cohort')
        except BaseException as error:
            failure={'type':type(error).__name__,'message':str(error)}
            if isinstance(error,host.CaseFailure):
                failed={**identity,**error.record}; io.write(folder/'failed_execution.json',failed)
        sync()
    counts=ledger.snapshot(); fit_attempts=sum(r['c4_c8_fit_attempts'] for r in compact)+(0 if failed is None else failed['c4_c8_fit_attempts'])
    io.require(fit_attempts<=limits.get('online_c4_c8_fit_attempts',limits.get('c4_c8_fit_attempts',0)),'actuator-fit budget exceeded')
    summary={**identity,'cohort':cohort,'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL',
        'allocated_executions':len(specs),'executions':len(compact),'rows':compact,'control_steps':budget['completed'],
        'control_step_attempts':sum(r['total_steps'] for r in compact)+(0 if failed is None else failed.get('host_attempts',0)),
        'lifecycle':counts,'events':journal.sequence,'private_records':private.sequence,'failure':failure,'wall_ns':perf_counter_ns()-started,
        'online_c4_c8_fit_attempts':fit_attempts,'new_response_predictor_training':0,'new_policy_training':0,
        'new_api_calls':0,'network_guard':network,'execution_git_head':io.git('rev-parse','HEAD'),
        'physical_qualification':False,'task_benefit':False}
    io.write(folder/'summary.json',summary)
    io.write(folder/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(folder/'completion.json',{**identity,'cohort':cohort,'status':summary['status'],
        'artifact_sha256':{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()},'closed_ns':perf_counter_ns()})
    allocation.load_manifest(path)
    if failure is not None: raise RuntimeError('one-shot collection stopped; failed/partial records retained: '+str(failure))
    return folder
