"""One software qualification and a separate literal, read-only record auditor."""
from pathlib import Path
import hashlib,json,subprocess,time,traceback
from src.analysis import occam_resource_process_v1 as p
from src.analysis import occam_resource_observation_v1 as r

ROOT=p.ROOT
FREEZE=p.OUTPUT/'freeze_v1/complete.json'
RUN=p.OUTPUT/'qualification_v1'
OWN=(*p.SOURCES[:3],'src/analysis/occam_resource_qualification_v1.py','scripts/qualify_occam_resources_v1.py',
    'tests/test_occam_resources_v1.py','docs/protocols/occam_resource_software_qualification_v1_zh.md')
SCIENCE_FLOOR=dict(minimum_commit_bytes=4*1024**3,minimum_disk_bytes=4*1024**3)


def git(*args):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT).decode('utf8').strip()


def verify_freeze():
    value=p.read(FREEZE)
    if value['integrity']!='PASSED_SOFTWARE_IMPLEMENTATION_ONLY' or value['reused_unique_tests']!=2586:raise ValueError('software freeze required')
    for name,h in {**value['source_sha256'],**value['input_sha256']}.items():
        if p.sha(ROOT/name)!=h:raise ValueError('frozen source/input changed: '+name)
    reuse=p.read(FREEZE.parent/'source_reuse.json')
    if p.sha(FREEZE.parent/'source_reuse.json')!=value['source_reuse_sha256']:raise ValueError('source reuse receipt changed')
    for name,h in reuse['source_sha256'].items():
        if p.sha(ROOT/name)!=h:raise ValueError('reused source changed: '+name)
    if git('status','--porcelain','--untracked-files=no'):raise ValueError('clean committed software freeze required')
    for name,h in value['source_sha256'].items():
        blob=subprocess.check_output(['git','show','HEAD:'+name],cwd=ROOT)
        if hashlib.sha256(blob).hexdigest()!=h:raise ValueError('source not committed: '+name)
    return value


def qualify():
    frozen=verify_freeze();RUN.mkdir(exist_ok=False);started=time.perf_counter_ns()
    p.write(RUN/'manifest.json',dict(schema='OCCAM_RESOURCE_QUALIFICATION_V1',source_local_commit=git('rev-parse','HEAD'),
        freeze_sha256=p.sha(FREEZE),source_sha256=frozen['source_sha256'],timestamp_UTC=p.utc(),
        jobs=[dict(job_id=i+1,kind=a,bytes=b,timeout_seconds=c,expected_status=d) for i,(a,b,c,d) in enumerate(p.JOBS)],
        software_profile=p.PROFILE,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0))
    outcomes=[];stopped=False
    for j in range(1,9):
        if stopped:outcomes.append(dict(job_id=j,state='NOT_STARTED',task_metrics=None));continue
        try:
            result=p.attempt(RUN/('job%02d'%j),p.spec(j))
            outcomes.append(dict(job_id=j,state=result['status'],result_sha256=p.sha(RUN/('job%02d'%j)/'result.json')))
            stopped=not result['expected_contract_observed']
        except Exception:
            outcomes.append(dict(job_id=j,state='ORCHESTRATION_EXCEPTION',traceback=traceback.format_exc(),task_metrics=None))
            stopped=True
    preflight={}
    try:
        sample=r.snapshot(ROOT);preflight=dict(sample=sample,decision=r.gate(sample,**SCIENCE_FLOOR),observed_once=True)
    except Exception as error:preflight=dict(error=repr(error),decision=dict(allowed=False,reasons=['UNKNOWN_RESOURCE']),observed_once=True)
    result=dict(integrity='UNEXPECTED_FAILURE' if stopped else 'COMPLETED_AWAITING_INDEPENDENT_AUDIT',
        outcomes=outcomes,launches=sum(p.read(RUN/('job%02d'%x['job_id'])/'result.json')['launches'] for x in outcomes if x['state'] not in ('NOT_STARTED','ORCHESTRATION_EXCEPTION')),
        unresolved_attempts=[x['job_id'] for x in outcomes if x['state']=='ORCHESTRATION_EXCEPTION'],
        science_preflight=preflight,science_collection_opened=False,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,
        wall_ns=time.perf_counter_ns()-started)
    p.write(RUN/'complete.json',result);return result


def _require(value,message):
    if not value:raise ValueError(message)


def audit_sample(s,*,observer=None,measured=None):
    """Literal units/identity checks; does not call the telemetry decoder/gate."""
    keys=('system_commit_total_pages','system_commit_limit_pages','system_commit_peak_pages','page_size_bytes',
        'system_commit_total_bytes','system_commit_limit_bytes','system_commit_available_bytes','system_commit_peak_bytes',
        'current_process_available_commit_bytes','physical_total_bytes','physical_available_bytes',
        'process_private_commit_bytes','process_peak_private_commit_bytes','process_working_set_bytes','process_peak_working_set_bytes',
        'observer_available_address_space_bytes','disk_free_bytes','sample_started_ns','sample_completed_ns','observer_pid','measured_process_pid')
    _require(s.get('schema')=='OCCAM_RESOURCE_SAMPLE_V1' and s.get('pointer_bits')==64,'resource schema/architecture')
    _require(all(type(s.get(k)) is int and s[k]>=0 for k in keys),'unknown/invalid resource value')
    page=s['page_size_bytes'];total=s['system_commit_total_pages'];limit=s['system_commit_limit_pages']
    _require(page>0 and limit>=total,'commit pages')
    for name,value in (('total',total*page),('limit',limit*page),('available',(limit-total)*page),('peak',s['system_commit_peak_pages']*page)):
        _require(s['system_commit_'+name+'_bytes']==value,'commit page/byte arithmetic')
    _require(s['physical_available_bytes']<=s['physical_total_bytes'] and s['sample_started_ns']<=s['sample_completed_ns'],'resource ordering')
    if observer is not None:_require(s['observer_pid']==observer,'observer PID')
    if measured is not None:_require(s['measured_process_pid']==measured,'owned handle PID')
    # Different OS APIs are not atomic; do not infer reserved future memory.
    return min(s['system_commit_available_bytes'],s['current_process_available_commit_bytes'])


def audit_job(request,result,start,receipt,*,request_hash,artifact_hashes):
    """Independent of runner classify/spec/gate/decoder; pure saved dictionaries."""
    j=request['job_id'];_require(type(j) is int and 1<=j<=8,'job id')
    # Repeat the protocol literally; don't derive expected outcomes from records.
    expected=('RETURNED','RETURNED','WORKER_EXCEPTION','UNRECEIPTED_EXIT','TIMEOUT_TERMINATED','INVALID_RECEIPT','RETURNED','RETURNED')[j-1]
    kinds=('RETURN','RETURN','RAISE_NESTED','EXIT','HANG','TAMPER','IMPORT_RUNTIME','RETURN')
    sizes=(4096,8192,0,0,0,0,0,65536)
    _require(request['kind']==kinds[j-1] and request['bytes']==sizes[j-1],'fixed fixture identity')
    _require(request['timeout_seconds']==(1 if j==5 else 90 if j==7 else 10),'fixed timeout')
    _require(request['profile']==dict(minimum_commit_bytes=512*1024**2,minimum_disk_bytes=64*1024**2,maximum_private_bytes=1024**3),'software profile')
    _require(result['job_id']==j and result['spec_sha256']==request_hash and result['nonce']==request['nonce'],'result binding')
    _require(result['artifact_sha256']==artifact_hashes,'all child artifact hashes')
    _require(result['status']==expected==result['expected_status'] and result['expected_contract_observed'],'expected outcome')
    _require(result['launches']==1 and type(result['pid']) is int and result['pid']>0 and result['returncode'] is not None,'one terminal owned process')
    _require(result['parent_error'] is None and request['created_ns']<=result['started_ns']<=result['completed_ns'],'parent ordering/error')
    _require(all(result[k]==0 for k in ('new_environment_operations','new_fits','online_LLM_API_calls')),'no scientific interaction')
    identities=dict(pid=result['pid'],ppid=result['parent_pid'],job_id=j,kind=request['kind'],nonce=request['nonce'],
        spec_sha256=request_hash,source_sha256=request['source_sha256'],runtime_lock_sha256=request['runtime_lock_sha256'],
        direct_executable_sha256=request['direct_executable_sha256'])
    _require(start is not None and all(start.get(k)==v for k,v in identities.items()),'child start identity')
    _require(result['started_ns']<=start['started_ns']<=result['completed_ns'],'start precedes exit')
    audit_sample(start['resource'],observer=result['pid'],measured=result['pid'])
    samples=result['samples'];_require(samples and samples[0]['phase']=='PREFLIGHT','pre-spawn resource observation')
    commits=[];peaks=[start['resource']['process_peak_private_commit_bytes']]
    for item in samples:
        measured=result['parent_pid'] if item['phase']=='PREFLIGHT' else result['pid']
        _require(item['phase'] in ('PREFLIGHT','OWNED_CHILD'),'known observation phase')
        commits.append(audit_sample(item['sample'],observer=result['parent_pid'],measured=measured))
        if item['phase']=='OWNED_CHILD':peaks.append(item['sample']['process_peak_private_commit_bytes'])
    _require(commits[0]>=512*1024**2 and samples[0]['sample']['disk_free_bytes']>=64*1024**2
        and samples[0]['sample']['process_private_commit_bytes']<=1024**3,'admission resource floor')
    events=result['events'];names=[x['kind'] for x in events]
    _require(names.count('SPAWNED')==1 and names.count('EXIT_OBSERVED')==1 and names[0]=='ADMISSION','event inventory')
    admission=events[0]['decision'];_require(admission['allowed'] and admission['reasons']==[],'admission before spawn')
    _require(names.index('ADMISSION')<names.index('SPAWNED')<names.index('EXIT_OBSERVED'),'decision/process order')
    times=[x['clock_ns'] for x in events];_require(times==sorted(times) and result['started_ns']<=min(times)<=max(times)<=result['completed_ns'],'event clocks')
    admission_time=events[0]['clock_ns'];spawn_time=events[names.index('SPAWNED')]['clock_ns'];exit_time=events[names.index('EXIT_OBSERVED')]['clock_ns']
    _require(samples[0]['sample']['sample_started_ns']>=result['started_ns'] and samples[0]['sample']['sample_completed_ns']<=admission_time,'admission uses past observation')
    _require(start['started_ns']>=admission_time and start['resource']['sample_started_ns']>=start['started_ns']
        and start['resource']['sample_completed_ns']<=exit_time,'child start resource timing')
    for item in samples[1:]:_require(spawn_time<=item['sample']['sample_started_ns']<=item['sample']['sample_completed_ns']<=exit_time,'live sample time')
    if j in (4,5):
        _require(receipt is None,'negative fixture cannot use fallback receipt')
        if j==4:_require(result['returncode']==17 and result['termination'] is None,'fixed no-receipt exit')
        else:
            _require(result['termination']=='TIMEOUT' and names.count('TERMINATE_OWNED_HANDLE')==1 and result['returncode']!=0,'owned timeout termination')
            stop=events[names.index('TERMINATE_OWNED_HANDLE')]
            _require(stop['pid']==result['pid'] and stop['clock_ns']-result['started_ns']>=10**9,'timeout PID/deadline')
        return dict(job_id=j,status=expected,parent_minimum_available_commit_bytes=min(commits),peak_private_commit_bytes=max(peaks))
    _require(receipt is not None and receipt['started_ns']==start['started_ns'],'saved receipt start binding')
    for k,v in identities.items():
        _require(receipt.get(k)==('0'*32 if j==6 and k=='nonce' else v),'receipt identity/tamper contract')
    _require(start['started_ns']<=receipt['completed_ns']<=result['completed_ns'],'receipt before result')
    audit_sample(receipt['resource_at_finish'],observer=result['pid'],measured=result['pid'])
    _require(start['started_ns']<=receipt['resource_at_finish']['sample_started_ns']<=receipt['resource_at_finish']['sample_completed_ns']<=receipt['completed_ns'],'receipt resource time')
    peaks.append(receipt['resource_at_finish']['process_peak_private_commit_bytes'])
    if j==3:
        _require(result['returncode']==1 and receipt['state']=='ERROR' and receipt['error']['constructed_fixture'],'synthetic nested exception')
        trace=receipt['error']['traceback']
        _require(all(x in trace for x in ('Traceback (most recent call last)','_nested_failure','ValueError: constructed inner fixture cause',
            'direct cause','RuntimeError: constructed outer fixture failure')),'complete nested traceback')
    else:
        _require(result['returncode']==0 and receipt['state']=='RETURNED' and receipt['error'] is None,'successful child receipt')
        if j in (1,2,8):
            _require(receipt['payload']==dict(bytes=sizes[j-1],sha256=hashlib.sha256(bytes(sizes[j-1])).hexdigest()),'real bounded payload')
        if j==7:
            payload=receipt['payload'];_require(payload['runtime_verified'] and payload['dependency_import_only'],'import-only qualification')
            guard=payload['guard'];counts=guard['operation_counts']
            _require(set(counts)=={'environment_creations','resets','simulation','solve_attempts','lstsq_attempts','cold_fit_attempts',
                'cold_estimator_entries','cold_linear_solve_attempts','cold_linear_lstsq_attempts'} and all(type(v) is int and v==0 for v in counts.values())
                and guard['network']['attempted_network_calls']==0 and guard['online_LLM_API_calls']==0
                and guard['zero_new_physical_interactions'] is True,'guard zero operations')
    _require(result['termination'] is None and 'TERMINATE_OWNED_HANDLE' not in names,'no extra termination')
    return dict(job_id=j,status=expected,parent_minimum_available_commit_bytes=min(commits),peak_private_commit_bytes=max(peaks))


def _audit_records():
    started=time.perf_counter_ns();manifest=p.read(RUN/'manifest.json');complete=p.read(RUN/'complete.json')
    _require(manifest['freeze_sha256']==p.sha(FREEZE),'immutable software freeze')
    for name,h in manifest['source_sha256'].items():_require(p.sha(ROOT/name)==h,'qualification source unchanged')
    _require(complete['integrity']=='COMPLETED_AWAITING_INDEPENDENT_AUDIT' and len(complete['outcomes'])==8,'complete software population')
    rows=[];pids=[]
    for i,row in enumerate(complete['outcomes'],1):
        _require(row['job_id']==i and row['state']!='NOT_STARTED','all fixed jobs retained')
        folder=RUN/('job%02d'%i);result=p.read(folder/'result.json');request=p.read(folder/'spec.json')
        _require(row['result_sha256']==p.sha(folder/'result.json'),'saved result binding')
        _require(request['source_sha256']=={n:manifest['source_sha256'][n] for n in p.SOURCES[:3]}|{n:p.sha(ROOT/n) for n in p.SOURCES[3:]},'worker source manifest')
        artifact_hashes={n:p.sha(folder/n) for n in ('start.json','receipt.json','stdout.log','stderr.log') if (folder/n).exists()}
        rows.append(audit_job(request,result,p.read(folder/'start.json') if (folder/'start.json').exists() else None,
            p.read(folder/'receipt.json') if (folder/'receipt.json').exists() else None,request_hash=p.sha(folder/'spec.json'),artifact_hashes=artifact_hashes))
        pids.append(result['pid'])
    _require(complete['launches']==8,'eight owned process launches; no retries')
    preflight=complete['science_preflight'];decision=preflight['decision']
    if 'sample' in preflight:
        sample=preflight['sample'];available=audit_sample(sample)
        reasons=[]
        if available<4*1024**3:reasons.append('AVAILABLE_COMMIT_BELOW_FLOOR')
        if sample['disk_free_bytes']<4*1024**3:reasons.append('DISK_BELOW_FLOOR')
        _require(decision['allowed']==(not reasons) and decision['reasons']==reasons,'literal future-science floor')
    else:_require(not decision['allowed'] and decision['reasons']==['UNKNOWN_RESOURCE'],'unknown future resource rejected')
    _require(not complete['science_collection_opened'] and all(complete[k]==0 for k in ('new_environment_operations','new_fits','online_LLM_API_calls')),'science remains closed')
    result=dict(integrity='PASSED_SOFTWARE_CONTRACT_ONLY',rows=rows,owned_process_launches=8,distinct_pid_values=len(set(pids)),source_local_commit=manifest['source_local_commit'],
        complete_sha256=p.sha(RUN/'complete.json'),manifest_sha256=p.sha(RUN/'manifest.json'),new_environment_operations=0,new_fits=0,
        online_LLM_API_calls=0,science_collection_opened=False,science_preflight=preflight,synthetic_error_not_original_failure_reproduction=True,
        native_peak_or_state_continuity_not_qualified=True,publication_goal_complete=False,wall_ns=time.perf_counter_ns()-started)
    result['disabled_during_independent_audit']=['runner/classify/spec/validate_spec','telemetry snapshot/decode/gate','subprocess.Popen']
    p.write(RUN/'audit.json',result);return result


def audit():
    from contextlib import ExitStack
    from unittest.mock import patch
    def denied(*args,**kwargs):raise RuntimeError('main runner, resource calculation and processes disabled in independent audit')
    with ExitStack() as stack:
        for obj,names in ((p,('attempt','classify','spec','validate_spec')),(r,('snapshot','decode','gate')),(subprocess,('Popen',))):
            for name in names:stack.enter_context(patch.object(obj,name,denied))
        return _audit_records()
