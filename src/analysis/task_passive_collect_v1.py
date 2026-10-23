"""One-shot native, development or locked qualification; retain every record."""
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import shutil
from time import perf_counter_ns
from src.analysis import task_passive_io_v1 as allocation
from src.analysis import task_passive_host_v1 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger


def collect(path,cohort):
    path=Path(path).resolve(); io=allocation.io; m=allocation.phase_gate(path,cohort)
    selected=io.read(path.parent/'selection.json')['selected_time_constants_s'] if cohort=='QUAL' else None
    specs=allocation.population(cohort,selected); limits=allocation.limits(cohort)
    folder=path.parent/cohort.lower(); io.require(not folder.exists(),'one-shot phase already started; preserve partial/complete records')
    folder.mkdir(); identity={k:m[k] for k in io.IDENTITY}; nominal,_=allocation.source_models()
    budget={'completed':0,'maximum':limits['control_steps']}; started=perf_counter_ns(); key={}; last={}; compact=[]
    failure=failed=None; network={}; journal=private=ledger=None
    with gzip.open(folder/'events.jsonl.gz','xt',encoding='utf-8') as ef,\
         gzip.open(folder/'cases.jsonl.gz','xt',encoding='utf-8') as cf,\
         gzip.open(folder/'witnesses.jsonl.gz','xt',encoding='utf-8') as wf:
        journal=JsonJournal(ef,identity); private=JsonJournal(wf,identity)
        def wrapped(target,event,payload):
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'case ownership override')
            return target.emit(event,{**key,**payload})
        def emit(event,payload):
            nonlocal last
            if event=='LIFECYCLE_RESET_INTENT': io.require(ledger.counts.get('reset_attempts',0)<=limits['all_resets'],'reset budget exhausted')
            v=wrapped(journal,event,payload); last={k:v[k] for k in ('sequence','saved_ns')}; return v
        def private_emit(event,payload): return wrapped(private,event,payload)
        def sync(): ef.flush(); os.fsync(ef.fileno())
        ledger=LifecycleLedger(emit,limits['physical_frames'])
        try:
            with io.forbid_online_calls(network):
                import metaworld
                from metaworld.sawyer_xyz_env import SawyerXYZEnv
                from gymnasium.envs.mujoco import MujocoEnv
                with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                    for spec in specs:
                        io.require(shutil.disk_usage(allocation.ROOT).free>=512*1024**2,'emergency storage reserve exhausted; keep partial results')
                        key={k:spec[k] for k in allocation.KEYS}; start=journal.sequence
                        result=host.execute_case(spec,nominal[spec['task']],emit,private_emit,ledger,budget,lambda:deepcopy(last),sync)
                        result={**identity,**result,'event_start_sequence':start,'event_end_sequence_exclusive':journal.sequence}
                        cf.write(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n'); cf.flush()
                        emit('CASE_COMPLETE',{'case_record_sha256':io.digest(result),'total_steps':result['total_steps'],'deadline_loss':result['deadline_loss']})
                        compact.append({k:result[k] for k in (*allocation.KEYS,'total_steps','deadline_loss','success','stop_reason','pi_steps',
                            'boundary_applied','boundary_missing_reason','movement_steps','c4_c8_fit_attempts','c4_c8_fit_results','c4_c8_optimizer_nfev')})
                        io.write(folder/'status.json',{**identity,'cohort':cohort,'status':'RUNNING','completed_executions':len(compact),
                            'control_steps':budget['completed'],'lifecycle':ledger.snapshot()},exclusive=False)
                        print(json.dumps({'cohort':cohort,'completed':len(compact),'allocated':len(specs),'steps':budget['completed']}),flush=True)
                io.require(len(compact)==len(specs),'incomplete allocated population')
        except BaseException as error:
            failure={'type':type(error).__name__,'message':str(error)}
            if isinstance(error,host.CaseFailure): failed={**identity,**error.record}; io.write(folder/'failed_execution.json',failed)
        for h in (ef,cf,wf): h.flush(); os.fsync(h.fileno())
    fits=sum(r['c4_c8_fit_attempts'] for r in compact)+(0 if failed is None else failed['c4_c8_fit_attempts'])
    io.require(fits<=limits['online_c4_c8_fit_attempts'],'actuator-fit budget exceeded')
    summary={**identity,'cohort':cohort,'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL',
        'allocated_executions':len(specs),'executions':len(compact),'rows':compact,'control_steps':budget['completed'],
        'control_step_attempts':sum(r['total_steps'] for r in compact)+(0 if failed is None else failed.get('host_attempts',0)),
        'lifecycle':ledger.snapshot(),'events':journal.sequence,'private_records':private.sequence,'failure':failure,
        'wall_ns':perf_counter_ns()-started,'online_c4_c8_fit_attempts':fits,'new_response_predictor_training':0,
        'new_policy_training':0,'new_api_calls':0,'network_guard':network,'execution_git_head':io.git('rev-parse','HEAD'),
        'selection_sha256':io.sha(path.parent/'selection.json') if cohort=='QUAL' else None,'safety_guarantee':False,'novel_algorithm':False}
    io.write(folder/'summary.json',summary); io.write(folder/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(folder/'completion.json',{**identity,'cohort':cohort,'status':summary['status'],
        'artifact_sha256':{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()},'closed_ns':perf_counter_ns()})
    allocation.load_manifest(path)
    if failure is not None: raise RuntimeError('one-shot collection stopped; partial records retained: '+str(failure))
    return folder
