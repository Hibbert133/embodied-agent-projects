"""Read-only process/cursor/accounting audit; no actor or process classifier."""
from pathlib import Path
from collections import Counter
from contextlib import ExitStack
from unittest.mock import patch
import gzip,hashlib,json,random
from src.analysis import occam_native_case_io_v1 as c
from src.analysis.occam_resource_qualification_v3 import audit_sample


def require(value,message):
    if not value:raise ValueError(message)


def ledger(value):
    require(set(value)=={'counts','by_phase'},'ledger structure');total=Counter()
    for counts in value['by_phase'].values():
        require(type(counts) is dict and all(type(v) is int and v>=0 for v in counts.values()),'integer phase counts');total.update(counts)
    root=value['counts'];require(all(type(v) is int and v>=0 and total[k]==v for k,v in root.items()) and all(root.get(k,0)==v for k,v in total.items()),'literal ledger sum')
    return root


def check_case(folder,m,phase,index,previous):
    """Returns next ledger/control/cursors after literal validation of saved data."""
    folder=Path(folder);request=c.read(folder/'request.json');result=c.read(folder/'result.json');start=c.read(folder/'start.json');receipt=c.read(folder/'receipt.json')
    require(request['schema']=='OCCAM_NATIVE_CASE_REQUEST_V1' and result['schema']=='OCCAM_NATIVE_CASE_PROCESS_RESULT_V1','native request/result schema')
    require(request['cohort']==phase and request['case_index']==index and request['case']==m['config']['populations'][phase][index-1],'registered case/order')
    require(request['ledger_start']==previous['ledger'] and request['control_steps_start']==previous['control_steps'] and request['cursors_start']==previous['cursors'],'requested prior state')
    require(request['native_runtime_bindings']==m['native_runtime_bindings'] and request['timeout_seconds']==210,'native runtime/timeout')
    require(result['status']=='RETURNED' and result['expected_status']=='RETURNED' and result['expected_contract_observed'] is True
        and result['returncode']==0 and result['launches']==1 and result['termination'] is None and result['parent_error'] is None,'one successful native process')
    require(type(result['pid']) is int and result['pid']>0 and result['nonce']==request['nonce'] and result['request_sha256']==c.sha(folder/'request.json'),'result request/PID')
    expected=dict(pid=result['pid'],ppid=result['parent_pid'],nonce=request['nonce'],request_sha256=result['request_sha256'],cohort=phase,case_index=index,
        manifest_sha256=request['manifest_sha256'],native_runtime_bindings=request['native_runtime_bindings'])
    require(all(start.get(k)==receipt.get(k)==v for k,v in expected.items()),'child identity binding')
    require(request['created_ns']<=result['started_ns']<=start['started_ns']==receipt['started_ns']<=receipt['completed_ns']<=result['completed_ns'],'causal process timestamps')
    require(receipt['state']=='RETURNED' and receipt['error'] is None,'native worker receipt')
    actual={n.name:c.sha(n) for n in folder.iterdir() if n.is_file() and n.name not in ('request.json','result.json')}
    require(result['artifact_sha256']==actual,'every original case artifact byte hash')
    needed={'start.json','receipt.json','stdout.log','stderr.log','case.json','events.jsonl.gz','witnesses.jsonl.gz','accounting.json','accounting_progress.jsonl.gz','rng_initialization.json','bootstrap.json'}
    require(set(actual)==needed,'complete known successful artifacts')
    for item in result['samples']:
        require(item['phase'] in ('PREFLIGHT','OWNED_CHILD'),'known resource sampling phase')
        audit_sample(item['sample'],observer=result['parent_pid'],measured=result['parent_pid'] if item['phase']=='PREFLIGHT' else result['pid'])
    require(result['samples'] and result['samples'][0]['phase']=='PREFLIGHT','pre-admission sample')
    first=result['samples'][0]['sample'];require(min(first['system_commit_available_bytes'],first['current_process_available_commit_bytes'])>=4*1024**3 and first['disk_free_bytes']>=2*1024**3,'four GiB before spawn')
    records=result['events'];names=[x['kind'] for x in records]
    require([n for n in names if n!='RESOURCE_QUERY_ERROR']==['ADMISSION','SPAWNED','EXIT_OBSERVED'],'single direct native launch/exit; no retry')
    require(all(x['terminal_returncode']==0 for x in records if x['kind']=='RESOURCE_QUERY_ERROR'),'only documented terminal query race allowed')
    require(records[0]['decision']['allowed'] and records[0]['decision']['reasons']==[],'admission decision')
    stamps=[x['clock_ns'] for x in records];require(stamps==sorted(stamps) and max(stamps)<=result['completed_ns'],'process event order')
    admission=records[0]['clock_ns'];spawn=next(x['clock_ns'] for x in records if x['kind']=='SPAWNED');exit_stamp=records[-1]['clock_ns']
    require(result['started_ns']<=first['sample_started_ns']<=first['sample_completed_ns']<=admission<=start['started_ns'],'past admission sample')
    for item in result['samples'][1:]:require(spawn<=item['sample']['sample_started_ns']<=item['sample']['sample_completed_ns']<=exit_stamp,'live resource chronology')
    audit_sample(start['resource'],observer=result['pid'],measured=result['pid']);audit_sample(receipt['resource_at_finish'],observer=result['pid'],measured=result['pid'])
    require(start['started_ns']<=start['resource']['sample_started_ns']<=start['resource']['sample_completed_ns']<=receipt['completed_ns']
        and receipt['resource_at_finish']['sample_completed_ns']<=receipt['completed_ns']<=exit_stamp,'child resource chronology')
    accounting=c.read(folder/'accounting.json');case=c.read(folder/'case.json');boot=c.read(folder/'bootstrap.json')
    require(accounting['status']=='COMPLETE' and accounting['failure'] is None and accounting['ledger_start']==previous['ledger'],'complete case accounting')
    require(accounting['cohort']==phase and accounting['case_index']==index and accounting['cursors_start']==previous['cursors'],'accounting identity/cursors')
    require(case['completed'] and case['environment_closed'] and case['error'] is None and case['close_error'] is None,'actual environment close')
    require(all(case[k]==m[k] for k in c.IDENTITY) and {k:case[k] for k in c.FIELDS}==request['case'],'native case identity')
    require(receipt['payload']==dict(accounting_sha256=c.sha(folder/'accounting.json'),case_sha256=c.sha(folder/'case.json'),status='COMPLETE'),'receipt binds real case/cost')
    require(boot['runtime_verified'] is True and boot['before_native_factory'] is True and start['started_ns']<=boot['completed_ns']<receipt['completed_ns'],'bootstrap before native work')
    guard=boot['dependency_guard'];expected_guards={'environment_creations','resets','simulation','solve_attempts','lstsq_attempts','cold_fit_attempts',
        'cold_estimator_entries','cold_linear_solve_attempts','cold_linear_lstsq_attempts'}
    require(guard['zero_new_physical_interactions'] is True and set(guard['operation_counts'])==expected_guards
        and all(type(v) is int and v==0 for v in guard['operation_counts'].values()) and guard['network']['attempted_network_calls']==0
        and guard['online_LLM_API_calls']==0,'dependency import guard; not a zero-native-cost claim')
    info=boot['platform_query'];require(info['schema']=='OCCAM_PLATFORM_BOOTSTRAP_V1' and info['platform_module_sha256']==request['native_runtime_bindings']['platform_module_sha256']
        and info['optional_shell_probe_disabled'] is True and info['original_function_restored'] is True
        and type(info['optional_command_calls_suppressed']) is int and info['optional_command_calls_suppressed']>=1
        and len(info['native_windows_version'])==3 and all(type(v) is int and v>=0 for v in info['native_windows_version']),'registered cold-start platform path')
    rng=c.read(folder/'rng_initialization.json');registered=m['config']['process_global_rng']
    require(all(rng[k]==v for k,v in registered.items()) and rng['scope']=='BEFORE_FACTORY_ONLY_NO_WITHIN_CASE_RESEED','only declared initialization')
    import numpy as np
    state=np.random.RandomState(registered['global_rng_seed_numpy']).get_state();py=random.Random(registered['global_rng_seed_python']).getstate()
    expected_np=dict(algorithm=state[0],vector_sha256=hashlib.sha256(state[1].tobytes()).hexdigest(),position=state[2],has_gaussian=state[3],cached_gaussian=state[4])
    require(rng['numpy_initial']==expected_np and rng['python_initial_sha256']==c.digest(py),'literal independently initialized RNG state')
    live=case['live_global_rng_guard'];require(set(live['attempts'])=={'numpy_seed','numpy_set_state','python_seed','python_setstate'} and not any(live['attempts'].values())
        and live['scope']=='LIVE_TASK_ONLY_AFTER_INITIAL_RESET' and live['draws_not_rewound'] is True,'no live global RNG reseeding')
    before=ledger(previous['ledger']);after=ledger(accounting['ledger_after']);delta={k:after.get(k,0)-before.get(k,0) for k in set(before)|set(after)}
    require(all(v>=0 for v in delta.values()) and delta.get('reset_attempts',0)<=51 and delta.get('simulation_frames_attempted',0)<=28000,'one case exact cost caps')
    require(all(after.get(k,0)==0 for k in ('reset_errors','simulation_errors','uncertain_simulation_frames','frame_budget_rejections')),'no hidden lifecycle error')
    paid=accounting['control_steps_after'];require(accounting['control_steps_start']==previous['control_steps'] and 0<=paid-previous['control_steps']==case['total_steps']<=500,'actual control-step delta')
    require(case['ledger_before']==previous['ledger'] and case['ledger_after_close']==accounting['ledger_after'],'host and process ledger continuity')
    require(accounting['within_case_global_rng_reseeds']==0 and accounting['network_guard']['attempted_network_calls']==0 and accounting['online_LLM_API_calls']==0,'no undeclared reseed/network')
    cursors=accounting['cursors_after'];lasts={};counts={}
    for stream,name,cursor,last_key in (('events.jsonl.gz','events',previous['cursors']['events'],'last_event_ns'),('witnesses.jsonl.gz','private',previous['cursors']['private'],'last_private_ns')):
        stamp=previous['cursors'][last_key];first_row=None;last_row=None;n=0
        with gzip.open(folder/stream,'rt',encoding='utf8') as f:
            for line in f:
                row=json.loads(line);require(row['sequence']==cursor and row['saved_ns']>stamp,'unmodified global stream sequence/time')
                require(all(row[k]==m[k] for k in c.IDENTITY) and {k:row[k] for k in c.FIELDS}==request['case'],'stream case owner')
                if first_row is None:first_row=row
                last_row=row;cursor+=1;n+=1;stamp=row['saved_ns']
        require(cursor==cursors[name] and stamp==cursors[last_key],'next stream cursor');counts[name]=n;lasts[name]=stamp
        if name=='events':
            require(first_row['event']=='CASE_ALLOCATION' and last_row['event']=='CASE_COMPLETE' and boot['completed_ns']<first_row['saved_ns'],'complete native event bracket')
            require(case['event_start_sequence']==first_row['sequence'] and case['event_end_sequence_exclusive']==last_row['sequence']
                and last_row['case_record_sha256']==c.digest(case),'native case closure hash')
    return dict(ledger=accounting['ledger_after'],control_steps=paid,cursors=cursors),dict(case=case,counts=counts,peak_private_commit_bytes=max(
        [start['resource']['process_peak_private_commit_bytes'],receipt['resource_at_finish']['process_peak_private_commit_bytes']]
        +[s['sample']['process_peak_private_commit_bytes'] for s in result['samples'] if s['phase']=='OWNED_CHILD']))


def _audit_cohort_records(manifest,phase):
    """Re-read all immutable cases and verify member concatenation, no workers."""
    path=Path(manifest);m=c.check_manifest(path);root=path.parent/phase.lower();summary=c.read(root/'summary.json')
    require(summary['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial cannot gain data qualification')
    previous=dict(ledger=dict(counts={},by_phase={}),control_steps=0,cursors=dict(events=0,private=0,last_event_ns=-1,last_private_ns=-1));rows=[]
    for index in range(1,len(m['config']['populations'][phase])+1):
        previous,row=check_case(root/('case_%04d'%index),m,phase,index,previous);rows.append(row)
    members=c.read(root/'member_index.json');require(members['schema']=='OCCAM_VERBATIM_GZIP_MEMBERS_V1' and members['manifest_id']==m['manifest_id']
        and members['phase']==phase and len(members['members'])==len(rows),'all gzip member locations preserved')
    for name in ('events.jsonl.gz','witnesses.jsonl.gz'):
        joined=hashlib.sha256();offset=0
        for index in range(1,len(rows)+1):
            part=root/('case_%04d'%index)/name;entry=members['members'][index-1]
            require(entry['case_index']==index and entry['files'][name]==dict(offset=offset,bytes=part.stat().st_size,sha256=c.sha(part)),'literal member offset/length/hash')
            offset+=part.stat().st_size
            with part.open('rb') as f:
                for data in iter(lambda:f.read(1024**2),b''):joined.update(data)
        require(offset==(root/name).stat().st_size and joined.hexdigest()==c.sha(root/name),'aggregate is verbatim compressed member concatenation')
    require(previous['ledger']==summary['lifecycle'] and previous['control_steps']==summary['control_steps']
        and previous['cursors']['events']==summary['events'] and previous['cursors']['private']==summary['private_records'],'complete cohort accounting')
    return dict(integrity='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY',executions=len(rows),control_steps=previous['control_steps'],ledger=previous['ledger'],
        peak_private_commit_bytes=max(r['peak_private_commit_bytes'] for r in rows),raw_files_not_rewritten=True,new_physics_during_audit=0,online_LLM_API_calls=0,
        dynamics_and_full_witness_audit_required=True)


def audit_cohort(manifest,phase):
    """Literal reader cannot call the executor, classifier, gates or telemetry."""
    from src.analysis import occam_native_case_process_v1 as process
    def denied(*args,**kwargs):raise AssertionError('execution or primary decision function forbidden in independent process audit')
    with ExitStack() as stack:
        for obj,name in ((process,'attempt'),(process,'classify'),(c,'validate_request'),(c,'check_ledger'),
            (process.resources,'gate'),(process.resources,'snapshot'),(process.subprocess,'Popen')):
            stack.enter_context(patch.object(obj,name,denied))
        return _audit_cohort_records(manifest,phase)
