"""Fixed software fixtures in owned Windows processes, never native collection."""
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess,sys,time,traceback,uuid
from pathlib import Path
from src.analysis import occam_resource_observation_v1 as resources

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'outputs/occam_resource_qualification_v2'
WORKER=ROOT/'scripts/occam_resource_fixture_v2.py'
RUNTIME_LOCK=ROOT/'outputs/response_action/validation_v1/runtime_lock.json'
SOURCES=('src/analysis/occam_resource_observation_v1.py','src/analysis/occam_resource_process_v2.py',
    'scripts/occam_resource_fixture_v2.py','src/analysis/release_learning_guard_v1.py',
    'src/analysis/response_action_io_v1.py','src/analysis/command_contrast_io_v1.py')
MIB=1024**2
PROFILE=dict(minimum_commit_bytes=512*MIB,minimum_disk_bytes=64*MIB,maximum_private_bytes=1024*MIB)
JOBS=(('RETURN',4096,10,'RETURNED'),('RETURN',8192,10,'RETURNED'),
    ('RAISE_NESTED',0,10,'WORKER_EXCEPTION'),('EXIT',0,10,'UNRECEIPTED_EXIT'),
    ('HANG',0,1,'TIMEOUT_TERMINATED'),('TAMPER',0,10,'INVALID_RECEIPT'),
    ('IMPORT_RUNTIME',0,90,'RETURNED'),('RETURN',65536,10,'RETURNED'))


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024**2),b''):h.update(data)
    return h.hexdigest()


def utc():return datetime.now(timezone.utc).isoformat()


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))


def write(path,value):
    path=Path(path);temporary=path.with_suffix(path.suffix+'.tmp')
    with temporary.open('x',encoding='utf8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    if path.exists():raise ValueError('append-only output already exists: '+str(path))
    temporary.replace(path)


def source_hashes():return {n:sha(ROOT/n) for n in SOURCES}


def executable():
    # The venv redirector PID can differ from the actual worker PID on Windows.
    path=Path(sys._base_executable).resolve()
    if os.name!='nt' or path.suffix.lower()!='.exe' or not path.is_file():raise ValueError('direct Windows base interpreter required')
    return path


def spec(job_id,*,clock=time.perf_counter_ns):
    if type(job_id) is not int or not 1<=job_id<=len(JOBS):raise ValueError('fixed software job id required')
    kind,size,timeout,_=JOBS[job_id-1]
    return dict(schema='OCCAM_RESOURCE_SOFTWARE_SPEC_V2',job_id=job_id,kind=kind,bytes=size,nonce=uuid.uuid4().hex,
        created_UTC=utc(),created_ns=clock(),timeout_seconds=timeout,profile=dict(PROFILE),source_sha256=source_hashes(),
        runtime_lock_sha256=sha(RUNTIME_LOCK),direct_executable_sha256=sha(executable()))


def validate_spec(value):
    keys={'schema','job_id','kind','bytes','nonce','created_UTC','created_ns','timeout_seconds','profile',
        'source_sha256','runtime_lock_sha256','direct_executable_sha256'}
    if type(value) is not dict or set(value)!=keys:raise ValueError('exact software-only spec fields required')
    j=value['job_id']
    if type(j) is not int or not 1<=j<=len(JOBS):raise ValueError('unregistered job')
    kind,size,timeout,_=JOBS[j-1]
    if value['schema']!='OCCAM_RESOURCE_SOFTWARE_SPEC_V2' or (value['kind'],value['bytes'],value['timeout_seconds'])!=(kind,size,timeout):raise ValueError('fixed fixture changed')
    if type(value['bytes']) is not int or type(value['timeout_seconds']) is not int or value['profile']!=PROFILE or any(type(v) is not int for v in value['profile'].values()):raise ValueError('fixed payload or profile changed')
    if type(value['nonce']) is not str or not re.fullmatch('[0-9a-f]{32}',value['nonce']):raise ValueError('invalid nonce')
    if type(value['created_ns']) is not int or value['created_ns']<0:raise ValueError('invalid creation clock')
    if datetime.fromisoformat(value['created_UTC']).utcoffset().total_seconds()!=0:raise ValueError('UTC request required')
    if value['source_sha256']!=source_hashes() or value['runtime_lock_sha256']!=sha(RUNTIME_LOCK):raise ValueError('source or locked runtime changed')
    if value['direct_executable_sha256']!=sha(executable()):raise ValueError('direct interpreter changed')


def _same_identity(receipt,request,request_hash,pid):
    return all(receipt.get(k)==v for k,v in dict(pid=pid,ppid=os.getpid(),nonce=request['nonce'],
        job_id=request['job_id'],kind=request['kind'],spec_sha256=request_hash,source_sha256=request['source_sha256'],
        runtime_lock_sha256=request['runtime_lock_sha256'],direct_executable_sha256=request['direct_executable_sha256']).items())


def classify(request,request_hash,pid,returncode,start,receipt,termination):
    if start is None or not _same_identity(start,request,request_hash,pid):return 'INVALID_START'
    if not request['created_ns']<=start.get('started_ns',-1):return 'INVALID_START'
    if termination:
        if returncode is None:return 'PROCESS_NOT_CONFIRMED_TERMINAL'
        return termination+'_TERMINATED'
    if receipt is None:return 'UNRECEIPTED_EXIT'
    if not _same_identity(receipt,request,request_hash,pid) or receipt.get('started_ns')!=start['started_ns']:return 'INVALID_RECEIPT'
    if receipt.get('completed_ns',-1)<start['started_ns']:return 'INVALID_RECEIPT'
    if returncode==0 and receipt.get('state')=='RETURNED' and receipt.get('error') is None:return 'RETURNED'
    if returncode==1 and receipt.get('state')=='ERROR' and type(receipt.get('error')) is dict and receipt['error'].get('traceback'):return 'WORKER_EXCEPTION'
    return 'EXIT_RECEIPT_DISAGREEMENT'


def attempt(directory,request,*,spawn=None,observe=None,clock=time.perf_counter_ns,sleep=time.sleep):
    """Single launch only. Test injection never expands the production command."""
    spawn=subprocess.Popen if spawn is None else spawn
    observe=resources.snapshot if observe is None else observe
    validate_spec(request);directory=Path(directory).resolve()
    if not directory.is_relative_to(OUTPUT.resolve()):raise ValueError('owned software output directory required')
    directory.mkdir(parents=True,exist_ok=False);request_path=directory/'spec.json';write(request_path,request)
    request_hash=sha(request_path);samples=[];events=[];p=None;termination=None;parent_error=None
    started=clock();returncode=None;preflight=None
    def event(kind,**more):events.append(dict(kind=kind,clock_ns=clock(),**more))
    def stop(reason):
        nonlocal termination,returncode
        termination=reason;event('TERMINATE_OWNED_HANDLE',pid=p.pid,reason=reason)
        p.terminate()
        try:returncode=p.wait(timeout=5)
        except subprocess.TimeoutExpired:returncode=None
    try:
        preflight=observe(ROOT);samples.append(dict(phase='PREFLIGHT',sample=preflight))
        admission=resources.gate(preflight,**PROFILE);event('ADMISSION',decision=admission)
        if not admission['allowed']:termination='ADMISSION_REJECTED'
        else:
            command=[str(executable()),'-I','-S',str(WORKER),'--spec',str(request_path)]
            # Fixed files avoid pipe backpressure; only this Popen handle is owned.
            with (directory/'stdout.log').open('xb') as stdout,(directory/'stderr.log').open('xb') as stderr:
                p=spawn(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)
                event('SPAWNED',pid=p.pid);deadline=started+request['timeout_seconds']*10**9
                while p.poll() is None:
                    if clock()>=deadline:stop('TIMEOUT');break
                    try:
                        sample=observe(ROOT,process_handle=p._handle,process_id=p.pid);samples.append(dict(phase='OWNED_CHILD',sample=sample))
                        check=resources.gate(sample,**PROFILE)
                        if not check['allowed']:event('LIVE_RESOURCE_REJECTION',decision=check);stop('RESOURCE');break
                    except resources.ResourceObservationError:
                        # A live query may race a terminal exit. Record both facts.
                        event('RESOURCE_QUERY_ERROR',traceback=traceback.format_exc(),terminal_returncode=p.poll())
                        if p.poll() is None:stop('UNKNOWN_RESOURCE');break
                    sleep(.05)
                returncode=p.poll();event('EXIT_OBSERVED',pid=p.pid,returncode=returncode)
    except Exception:
        parent_error=traceback.format_exc();event('PARENT_ERROR',traceback=parent_error)
    finally:
        if p is not None and p.poll() is None and termination is None:
            try:stop('PARENT_ERROR')
            except Exception:parent_error=(parent_error or '')+'\n'+traceback.format_exc()
        if p is not None:returncode=p.poll()
    artifacts={};data={}
    for name in ('start.json','receipt.json'):
        path=directory/name
        if path.exists():
            artifacts[name]=sha(path)
            try:data[name]=read(path)
            except Exception:parent_error=(parent_error or '')+'\n'+traceback.format_exc()
    status=('ADMISSION_REJECTED' if termination=='ADMISSION_REJECTED' else 'PARENT_EXCEPTION') if p is None else classify(
        request,request_hash,p.pid,returncode,data.get('start.json'),data.get('receipt.json'),termination)
    if parent_error:status='PARENT_EXCEPTION'
    for name in ('stdout.log','stderr.log'):
        path=directory/name
        if path.exists():artifacts[name]=sha(path)
    result=dict(schema='OCCAM_RESOURCE_SOFTWARE_RESULT_V2',job_id=request['job_id'],nonce=request['nonce'],spec_sha256=request_hash,
        status=status,expected_status=JOBS[request['job_id']-1][3],expected_contract_observed=status==JOBS[request['job_id']-1][3],
        pid=None if p is None else p.pid,parent_pid=os.getpid(),returncode=returncode,launches=int(p is not None),
        termination=termination,parent_error=parent_error,started_ns=started,completed_ns=clock(),samples=samples,events=events,
        artifact_sha256=artifacts,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0)
    write(directory/'result.json',result);return result


def _nested_failure():
    try:raise ValueError('constructed inner fixture cause')
    except ValueError as cause:raise RuntimeError('constructed outer fixture failure') from cause


def _worker_audit(event,args):
    if event=='socket.gethostname' and args==():return
    if event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.posix_spawn','os.spawn'):
        raise RuntimeError('network or descendant creation forbidden in software worker')


def fixture(spec_path):
    path=Path(spec_path).resolve()
    if not path.is_relative_to(OUTPUT.resolve()) or path.name!='spec.json':raise ValueError('owned fixed software request required')
    request=read(path);validate_spec(request);sys.addaudithook(_worker_audit)
    started=time.perf_counter_ns();identity=dict(pid=os.getpid(),ppid=os.getppid(),job_id=request['job_id'],kind=request['kind'],
        nonce=request['nonce'],spec_sha256=sha(path),source_sha256=source_hashes(),runtime_lock_sha256=sha(RUNTIME_LOCK),
        direct_executable_sha256=sha(Path(sys.executable)),started_ns=started)
    write(path.parent/'start.json',dict(**identity,resource=resources.snapshot(ROOT)))
    payload={};error=None;code=0;state='RETURNED'
    try:
        kind=request['kind']
        if kind=='RETURN':
            data=bytes(request['bytes']);payload=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        elif kind=='RAISE_NESTED':_nested_failure()
        elif kind=='EXIT':os._exit(17)
        elif kind=='HANG':
            while True:time.sleep(.1)
        elif kind=='TAMPER':pass
        elif kind=='IMPORT_RUNTIME':
            # -I ignores PYTHONPATH/user site; -S skips site and .pth execution.
            # Add the frozen venv path directly, without site.addsitedir().
            sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
            from src.analysis.release_learning_guard_v1 import read_only
            guard={}
            with read_only(guard):
                from src.analysis.response_action_io_v1 import verify_runtime
                verify_runtime(read(RUNTIME_LOCK))
            payload=dict(runtime_verified=True,guard=guard,dependency_import_only=True)
        else:raise ValueError('unreachable unregistered software fixture')
    except Exception:
        state='ERROR';code=1;error=dict(type=sys.exc_info()[0].__name__,message=str(sys.exc_info()[1]),
            traceback=traceback.format_exc(),constructed_fixture=request['kind']=='RAISE_NESTED')
        traceback.print_exc()
    receipt=dict(**identity,state=state,payload=payload,error=error,resource_at_finish=resources.snapshot(ROOT),completed_ns=time.perf_counter_ns())
    if request['kind']=='TAMPER':receipt['nonce']='0'*32
    write(path.parent/'receipt.json',receipt)
    return code
