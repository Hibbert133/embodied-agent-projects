"""One-shot fixed source collection; forecasters never select physical controls."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns,time_ns
import gzip,json,os,shutil
from src.analysis import latent_response_io_v1 as a,latent_response_host_v1 as host
from src.analysis.native_command_witness_io_v1 import forbid_fitting
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.lifecycle_ledger import LifecycleLedger
io=a.io


def collect(path,split):
    path=Path(path).resolve();m=a.phase_gate(path,split);io.require(io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('status','--porcelain','--untracked-files=no'),'frozen clean collection')
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.VALIDATION/'runtime_lock.json'));out=path.parent/split.lower();out.mkdir(exist_ok=False)
    bank=model_sha=None
    if split in ('CAL','QUAL'):
        model_path=path.parent/'training/models.json';model_sha=io.sha(model_path);bank=io.read(model_path)['by_task']
    identity={k:m[k] for k in a.IDENTITY};limits=a.limits(split);budget={'completed':0,'maximum':limits['control_steps']};start=perf_counter_ns();started_unix=time_ns()
    key={};last={};rows=[];failure=None;network={};fit_guard={}
    with gzip.open(out/'events.jsonl.gz','xt',encoding='utf-8',newline='\n') as ef,gzip.open(out/'cases.jsonl.gz','xt',encoding='utf-8',newline='\n') as cf,\
        gzip.open(out/'private_targets.jsonl.gz','xt',encoding='utf-8',newline='\n') as pf,gzip.open(out/'public_trajectories.jsonl.gz','xt',encoding='utf-8',newline='\n') as xf,\
        gzip.open(out/'public_packet_metadata.jsonl.gz','xt',encoding='utf-8',newline='\n') as mf:
        journal=JsonJournal(ef,identity);private_journal=JsonJournal(pf,identity)
        def emit(kind,payload):
            nonlocal last
            io.require(all(k not in payload or payload[k]==v for k,v in key.items()),'immutable case ownership')
            if kind=='LIFECYCLE_RESET_INTENT':io.require(ledger.counts['reset_attempts']<=limits['all_resets'],'whole phase reset cap')
            e=journal.emit(kind,{**key,**payload});last={k:e[k] for k in ('sequence','saved_ns')};return e
        def private(kind,payload):return private_journal.emit(kind,{**key,**payload})
        def sync():
            for f in (ef,pf):f.flush();os.fsync(f.fileno())
        ledger=LifecycleLedger(emit,limits['physical_frames'])
        try:
            with io.forbid_online_calls(network),forbid_fitting(fit_guard):
                import metaworld
                from metaworld.sawyer_xyz_env import SawyerXYZEnv
                from gymnasium.envs.mujoco import MujocoEnv
                with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                    for spec in a.population(split):
                        io.require(shutil.disk_usage(io.ROOT).free>=512*1024**2,'emergency storage reserve');key=dict(spec);first=journal.sequence
                        emit('CASE_ALLOCATION',{'assignment':'FROZEN_KNOWN_PACKET_RESPONSE_DATA','preallocated_packet':a.packet(spec),'model_sha256':model_sha})
                        c,public=host.execute_case(spec,emit,private,ledger,budget,lambda:deepcopy(last),sync,bank,model_sha)
                        c={**identity,**c,'event_start_sequence':first,'event_end_sequence_exclusive':journal.sequence,'public_trajectory_sha256':io.digest(public)}
                        cf.write(json.dumps(c,allow_nan=False,separators=(',',':'))+'\n');cf.flush();xf.write(json.dumps(public,allow_nan=False,separators=(',',':'))+'\n');xf.flush()
                        meta={'schema':'PUBLIC_PACKET_METADATA_V1','entry_at_calls':c['entry_at_calls'],'packet_commands':c['preallocated_packet'],'reason':c['reason']}
                        mf.write(json.dumps(meta,allow_nan=False,separators=(',',':'))+'\n');mf.flush()
                        emit('CASE_COMPLETE',{'case_record_sha256':io.digest(c)})
                        rows.append({k:c[k] for k in (*a.KEYS,'total_steps','entry_at_calls','packet_steps','complete_first_eight','complete_packet','reason','success_at_response_horizon')})
                        io.write(out/'status.json',{'status':'RUNNING','split':split,'executions':len(rows),'control_steps':budget['completed'],'lifecycle':ledger.snapshot()},exclusive=False)
                        print({'split':split,'completed':len(rows),'allocated':len(a.population(split)),'steps':budget['completed']},flush=True)
        except BaseException as error:
            failure={'type':type(error).__name__,'message':str(error)}
            if isinstance(error,host.CaseFailure):io.write(out/'failed_case.json',{**identity,**error.record})
        for f in (ef,cf,pf,xf,mf):f.flush();os.fsync(f.fileno())
    summary={**identity,'split':split,'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL','executions':len(rows),'rows':rows,
        'control_steps':budget['completed'],'events':journal.sequence,'private_target_records':private_journal.sequence,'lifecycle':ledger.snapshot(),
        'failure':failure,'network_guard':network,'fitting_guard':fit_guard,'model_sha256':model_sha,'started_unix_ns':started_unix,
        'wall_ns':perf_counter_ns()-start,'new_model_fits':0,'online_LLM_API_calls':0,'full_task_tail_evaluated':False}
    io.write(out/'summary.json',summary);io.write(out/'status.json',{k:v for k,v in summary.items() if k!='rows'},exclusive=False)
    io.write(out/'completion.json',{'status':summary['status'],'manifest_id':m['manifest_id'],'artifact_sha256':{p.name:io.sha(p) for p in out.iterdir() if p.is_file()}})
    a.checked(path)
    if failure is not None:raise RuntimeError('One-shot response collection failed; all partial records preserved '+str(failure))
    return summary
