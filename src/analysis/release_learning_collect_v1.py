"""One-shot real cohorts; every arm starts once and never rewinds acquisition."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import gzip,json,os,shutil
from src.analysis import release_learning_io_v1 as a
from src.analysis import release_learning_host_v1 as host
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.release_learning_programs_v1 import calibrated_prefix
io=a.io


def runtime_for(path,cohort):
    root=Path(path).parent;runtime=dict(receiver=None,pre_bank=None,policy=None);files={}
    if cohort in ('GATE_TRAIN','CAL','DEV','QUAL'):files['receiver']='receiver_freeze.json'
    if cohort=='CAL':files['pre_bank']='pre_bank.json'
    if cohort in ('DEV','QUAL'):files['policy']='policy_lock.json'
    hashes={}
    for role,name in files.items():
        p=root/'models'/name;runtime[role]=io.read(p);hashes[p.relative_to(io.ROOT).as_posix()]=io.sha(p)
    return runtime,hashes


def collect(path,cohort):
    path=Path(path).resolve();m=a.phase_gate(path,cohort);out=path.parent/cohort.lower();out.mkdir(exist_ok=False)
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.VALIDATION/'runtime_lock.json'));nominal,_=a.source_models();runtime,model_hashes=runtime_for(path,cohort)
    identity={k:m[k] for k in a.IDENTITY};limits=a.limits(cohort);budget={'completed':0,'maximum':limits['control_steps']}
    start=perf_counter_ns();key={};last={};compact=[];failed=failure=None;network={}
    io.write(out/'model_commitment.json',dict(**identity,model_artifact_sha256=model_hashes,no_model_updates_during_cohort=True))
    with gzip.open(out/'events.jsonl.gz','xt',encoding='utf-8') as ef,gzip.open(out/'cases.jsonl.gz','xt',encoding='utf-8') as cf,gzip.open(out/'witnesses.jsonl.gz','xt',encoding='utf-8') as wf:
        journal=JsonJournal(ef,identity);private=JsonJournal(wf,identity)
        def wrapped(target,name,payload):
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'case ownership override');return target.emit(name,{**key,**payload})
        def emit(name,payload):
            nonlocal last
            if name=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts.get('reset_attempts',0)<=limits['all_resets'],'all-reset cap')
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
                        for n,h in model_hashes.items():io.require(io.sha(io.ROOT/n)==h,'model changed during actual deployment')
                        key={k:spec[k] for k in a.KEYS};first=journal.sequence
                        emit('CASE_ALLOCATION',dict(assignment='FIXED_COMPLETE_PROCEDURE_WITH_REGISTERED_INTERNAL_DECISION',
                            no_online_method_selection=spec['program'] not in ('LEARNED_EFFECT','DIRECT_RISK','EFFECT_DISABLED','RELEASE_ALWAYS','FORCE_MASKED')))
                        result=host.execute_case(spec,nominal[spec['task']] if calibrated_prefix(spec['program']) else None,
                            emit,emit_private,ledger,budget,lambda:deepcopy(last),sync,runtime)
                        result={**identity,**result,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence}
                        cf.write(json.dumps(result,allow_nan=False,separators=(',',':'))+'\n');cf.flush()
                        emit('CASE_COMPLETE',dict(case_record_sha256=io.digest(result),total_steps=result['total_steps'],deadline_loss=result['deadline_loss']))
                        fields=(*a.KEYS,'total_steps','deadline_loss','success','policy_queries','option_reason','movement_steps','warm_probe_steps',
                            'stop_reason','c4_c8_fit_attempts','c4_c8_fit_results','c4_c8_optimizer_nfev','exposure_draws','receiver_version','rate_transition_applied','reference_update_applied')
                        compact.append({k:result[k] for k in fields})
                        io.write(out/'status.json',dict(status='RUNNING',cohort=cohort,completed=len(compact),steps=budget['completed'],lifecycle=ledger.snapshot()),exclusive=False)
                        print(dict(cohort=cohort,completed=len(compact),allocated=limits['executions'],steps=budget['completed']),flush=True)
        except BaseException as error:
            failure=dict(type=type(error).__name__,message=str(error))
            if isinstance(error,host.CaseFailure):failed={**identity,**error.record};io.write(out/'failed_execution.json',failed)
        for stream in (ef,cf,wf):stream.flush();os.fsync(stream.fileno())
    fits=sum(r['c4_c8_fit_attempts'] for r in compact)+(0 if failed is None else failed.get('c4_c8_fit_attempts',0))
    io.require(fits<=limits['c4_c8_fit_attempts'],'initial C4/C8 cap')
    summary=dict(**identity,cohort=cohort,status='COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL',
        allocated_executions=limits['executions'],executions=len(compact),rows=compact,control_steps=budget['completed'],lifecycle=ledger.snapshot(),
        events=journal.sequence,private_records=private.sequence,c4_c8_fit_attempts=fits,failure=failure,wall_ns=perf_counter_ns()-start,
        new_response_training=0,new_low_level_policy_training=0,online_LLM_API_calls=0,network_guard=network,
        execution_git_head=io.git('rev-parse','HEAD'),model_artifact_sha256=model_hashes,publication_goal_complete=False)
    io.write(out/'summary.json',summary);io.write(out/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(out/'completion.json',dict(status=summary['status'],manifest_id=m['manifest_id'],artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()}))
    a.checked(path)
    if failure is not None:raise RuntimeError('one-shot cohort stopped; partial data retained '+str(failure))
    return out
