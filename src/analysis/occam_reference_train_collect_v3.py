"""One frozen population, one owned process per complete logical case."""
from pathlib import Path
from time import perf_counter_ns
import gzip,json,shutil,traceback
from src.analysis import occam_reference_train_io_v3 as a
from src.analysis import occam_native_case_io_v1 as contract
from src.analysis import occam_native_case_process_v1 as processes
from src.analysis.occam_native_case_audit_v1 import check_case
io=a.io


def progress_prefix(folder):
    """Read a durable prefix even when a killed worker left a gzip without EOF."""
    file=Path(folder)/'accounting_progress.jsonl.gz'
    if not file.exists():return None
    latest=None;rows=0;error=None
    try:
        with gzip.open(file,'rt',encoding='utf8') as stream:
            for line in stream:
                row=json.loads(line);contract.check_ledger(row['ledger'])
                io.require(type(row['control_steps']) is int and row['control_steps']>=0,'prefix control count')
                latest=row;rows+=1
    except (EOFError,OSError,ValueError) as exc:error=dict(type=type(exc).__name__,message=str(exc))
    return dict(complete_rows=rows,last_reported=latest,read_error=error,
        semantics='LAST_REPORTED_PREFIX_NOT_FINAL_PHYSICAL_COST; ATTEMPTS_MAY_BE_UNRESOLVED')


def _collect(path,phase):
    path=Path(path).resolve();m=a.phase_gate(path,phase);root=path.parent/phase.lower();root.mkdir(exist_ok=False)
    specs=a.population(phase);caps=a.limits(phase);started=perf_counter_ns();wall_limit=a.execution()['phase_wall_seconds_max'][phase]
    previous=dict(ledger=dict(counts={},by_phase={}),control_steps=0,cursors=dict(events=0,private=0,last_event_ns=-1,last_private_ns=-1))
    compact=[];outcomes=[];members=[];failure=None;attempted=0;process_count=0;unknown_cost=False
    with (root/'events.jsonl.gz').open('xb') as joined_events,(root/'witnesses.jsonl.gz').open('xb') as joined_private,\
        gzip.open(root/'cases.jsonl.gz','xt',encoding='utf8') as cases:
        for index,spec in enumerate(specs,1):
            if failure is not None:outcomes.append(dict(case_index=index,case=spec,status='NOT_STARTED',task_metrics=None));continue
            folder=root/('case_%04d'%index);attempted=index;dispatch_started=False
            try:
                io.require((perf_counter_ns()-started)/1e9+210<=wall_limit,'registered phase active wall cap')
                request=contract.request(path,phase,index,previous['ledger'],previous['control_steps'],previous['cursors'])
                dispatch_started=True;process=processes.attempt(folder,request);process_count+=process['launches']
                io.require(process['status']=='RETURNED','native process failed: '+process['status'])
                next_state,checked=check_case(folder,m,phase,index,previous);case=checked['case']
                member=dict(case_index=index,files={})
                for name,target in (('events.jsonl.gz',joined_events),('witnesses.jsonl.gz',joined_private)):
                    member['files'][name]=dict(offset=target.tell(),bytes=(folder/name).stat().st_size,sha256=contract.sha(folder/name))
                    with (folder/name).open('rb') as source:shutil.copyfileobj(source,target,length=1024**2)
                    target.flush()
                members.append(member)
                cases.write(json.dumps(case,separators=(',',':'),allow_nan=False)+'\n');cases.flush();previous=next_state
                compact.append({k:case[k] for k in (*a.KEYS,'total_steps','deadline_loss','success','policy_queries','performance_windows','full_feedback_windows','boundary_applied')})
                outcomes.append(dict(case_index=index,case=spec,status='COMPLETE',task_metrics={k:case[k] for k in ('success','deadline_loss','total_steps')},process_result_sha256=contract.sha(folder/'result.json')))
                io.write(root/'status.json',dict(status='RUNNING',completed=len(compact),launched_processes=process_count,control_steps=previous['control_steps']),exclusive=False)
                print(dict(phase=phase,completed=len(compact),allocated=len(specs),control_steps=previous['control_steps']),flush=True)
            except BaseException as error:
                failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc(),case_index=index,case=spec)
                # Preserve exact completed accounting where present. Otherwise the
                # registered cap is an upper bound, never fabricate zero physics.
                partial=None
                if (folder/'accounting.json').exists():
                    partial=contract.read(folder/'accounting.json');failure['available_accounting']=partial
                launch=0 if not dispatch_started else contract.read(folder/'result.json')['launches'] if (folder/'result.json').exists() else None
                unknown_cost=partial is None and launch!=0
                failure.update(physical_cost_unknown=unknown_cost,unresolved_case_registered_upper_bound=dict(control_steps=500,all_resets=51,physical_frames=28000) if unknown_cost else None)
                if unknown_cost:failure['known_accounting_prefix']=progress_prefix(folder)
                outcomes.append(dict(case_index=index,case=spec,status='FAILED_TECHNICAL',task_metrics=None,process_launches=launch,physical_cost_unknown=unknown_cost))
                io.write(path.parent/'CLOSED_TECHNICAL_FAILURE.json',dict(status='CLOSED_NO_RESUME_NO_RETRY',manifest_id=m['manifest_id'],phase=phase,failure=failure))
        for stream in (joined_events,joined_private,cases):stream.flush();__import__('os').fsync(stream.fileno())
    costs=dict(completed_case_ledger=previous['ledger'],completed_case_control_steps=previous['control_steps'],unresolved_case_cost=unknown_cost)
    if failure is not None and failure.get('available_accounting') is not None:
        costs['last_attempt_ledger']=failure['available_accounting']['ledger_after'];costs['last_attempt_control_steps']=failure['available_accounting']['control_steps_after']
    io.write(root/'member_index.json',dict(schema='OCCAM_VERBATIM_GZIP_MEMBERS_V1',manifest_id=m['manifest_id'],phase=phase,members=members))
    summary={**{k:m[k] for k in a.IDENTITY},'status':'COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL',
        'allocated_executions':len(specs),'executions':len(compact),'rows':compact,'control_steps':previous['control_steps'],'lifecycle':previous['ledger'],
        'events':previous['cursors']['events'],'private_records':previous['cursors']['private'],'failure':failure,'outcomes':outcomes,'cost_accounting':costs,
        'logical_attempts':attempted,'owned_native_process_launches_known':process_count,'unresolved_process_launches':[x['case_index'] for x in outcomes if x['status']=='FAILED_TECHNICAL' and x['process_launches'] is None],
        'unstarted':sum(x['status']=='NOT_STARTED' for x in outcomes),
        'online_LLM_API_calls':0,'scientific_model_training':0,'training_behavior_data_not_task_qualification':True,
        'collection_active_wall_limit_seconds':wall_limit,'wall_ns':perf_counter_ns()-started,'publication_goal_complete':False}
    io.write(root/'summary.json',summary);io.write(root/'status.json',{k:v for k,v in summary.items() if k not in ('rows','outcomes')},exclusive=False)
    io.write(root/'completion.json',dict(status=summary['status'],manifest_id=m['manifest_id'],artifact_sha256={p.name:io.sha(p) for p in root.iterdir() if p.is_file()}))
    a.checked(path)
    if failure is not None:raise RuntimeError('isolated population stopped; do not resume or replace missing cases')
    return root


def collect(path,phase):
    try:return _collect(path,phase)
    except BaseException as error:
        contract.close_failed_allocation(path,phase,dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc(),
            source='COLLECTION_ENTRY_INCLUDING_PHASE_GATE; EXISTING_FIRST_CAUSE_RETAINED'))
        raise
