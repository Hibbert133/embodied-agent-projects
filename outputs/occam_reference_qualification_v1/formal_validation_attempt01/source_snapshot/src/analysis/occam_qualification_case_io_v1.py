"""Standard-library-only isolated native-case contract, never a simulator."""
from collections import Counter
from pathlib import Path
import hashlib,json,re,secrets,time
from src.analysis import occam_resource_process_v3 as software
from src.analysis import occam_resource_observation_v1 as resources
from src.analysis import occam_platform_bootstrap_v1 as bootstrap

ROOT=software.ROOT
BASE=ROOT/'outputs/occam_reference_qualification_v1'
OUTPUT=BASE/'qualification_v1'
FREEZE=BASE/'freeze_validation_v1/complete.json'
CONFIG=ROOT/'configs/movement_task/occam_reference_qualification_v1.json'
WORKER=ROOT/'scripts/occam_qualification_case_worker_v1.py'
PROFILE_ADMIT=dict(minimum_commit_bytes=4*1024**3,minimum_disk_bytes=2*1024**3)
PROFILE_LIVE=dict(minimum_commit_bytes=512*1024**2,minimum_disk_bytes=512*1024**2,maximum_private_bytes=2*1024**3)
FIELDS=('cohort','group','task','seed','context','planned_boundary','program')
IDENTITY=('experiment_run_id','manifest_id','source_git_commit')
COUNTS={'reset_attempts','reset_errors','reset_completed','simulation_attempts','simulation_errors','simulation_completed',
    'simulation_frames_attempted','simulation_frames_completed','uncertain_simulation_frames','frame_budget_rejections'}
PHASES={'FACTORY_SETUP','GOAL_GENERATION','CONTROLLED_RESET','CONTROL'}
read=software.read;sha=software.sha;write=software.write


def require(ok,message):
    if not ok:raise ValueError(message)


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def runtime_bindings():
    return dict(runtime_lock_sha256=sha(software.RUNTIME_LOCK),direct_executable_sha256=sha(software.executable()),platform_module_sha256=bootstrap.module_sha256())


def require_science_resources(*,initial):
    sample=resources.snapshot(ROOT);decision=resources.gate(sample,minimum_commit_bytes=4*1024**3,minimum_disk_bytes=(4 if initial else 2)*1024**3)
    require(decision['allowed'],'scientific resource admission rejected: '+','.join(decision['reasons']))
    return sample


def check_manifest(path):
    path=Path(path).resolve();require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve(),'exact new v3 manifest directory')
    require(not (path.parent/'CLOSED_TECHNICAL_FAILURE.json').exists(),'closed v3 allocation cannot resume')
    m=read(path);require(type(m.get('experiment_run_id')) is str and m['experiment_run_id'].startswith('occam_reference_qualification_v1_'),'registered native study run id; array fixtures forbidden')
    copy=dict(m);mid=copy.pop('manifest_id');require(digest(copy)==mid,'manifest digest')
    require(m['config']==read(CONFIG) and m['config']['protocol']=='OCCAM_REFERENCE_QUALIFICATION_V1','frozen independent deployment config')
    frozen=read(FREEZE);require(frozen['integrity']=='PASSED','implementation freeze required')
    require(all(m['source_sha256'].get(n)==h==sha(ROOT/n) for n,h in frozen['source_sha256'].items()),'tested committed source binding')
    require(m['native_runtime_bindings']==runtime_bindings(),'locked worker runtime')
    require(type(m['source_git_commit']) is str and re.fullmatch('[0-9a-f]{40}',m['source_git_commit']),'source commit identity')
    return m


def check_ledger(value):
    require(type(value) is dict and set(value)=={'counts','by_phase'},'ledger shape')
    require(type(value['counts']) is dict and type(value['by_phase']) is dict and set(value['by_phase'])<=PHASES,'registered ledger phases')
    total=Counter()
    for entry in (value['counts'],*value['by_phase'].values()):
        require(type(entry) is dict and set(entry)<=COUNTS and all(type(v) is int and v>=0 for v in entry.values()),'nonnegative integer ledger')
    for counts in value['by_phase'].values():total.update(counts)
    require(all(total[k]==value['counts'].get(k,0) for k in set(total)|set(value['counts'])),'phase counts sum')
    c=value['counts']
    require(c.get('reset_completed',0)<=c.get('reset_attempts',0) and c.get('simulation_completed',0)<=c.get('simulation_attempts',0)
        and c.get('simulation_frames_completed',0)<=c.get('simulation_frames_attempted',0),'ledger completion order')
    return c


def request(manifest,cohort,index,ledger,control_steps,cursors):
    path=Path(manifest).resolve();m=check_manifest(path)
    require(cohort in ('NATIVE','QUAL') and type(index) is int and 1<=index<=len(m['config']['populations'][cohort]),'registered request ordinal')
    value=dict(schema='OCCAM_QUALIFICATION_CASE_REQUEST_V1',manifest_path=str(path),manifest_sha256=sha(path),cohort=cohort,case_index=index,
        case=m['config']['populations'][cohort][index-1],ledger_start=ledger,control_steps_start=control_steps,cursors_start=cursors,
        nonce=secrets.token_hex(16),created_ns=time.perf_counter_ns(),created_UTC=software.utc(),timeout_seconds=210,native_runtime_bindings=runtime_bindings())
    validate_request(value);return value


def validate_request(value,directory=None):
    keys={'schema','manifest_path','manifest_sha256','cohort','case_index','case','ledger_start','control_steps_start','cursors_start',
        'nonce','created_ns','created_UTC','timeout_seconds','native_runtime_bindings'}
    require(type(value) is dict and set(value)==keys and value['schema']=='OCCAM_QUALIFICATION_CASE_REQUEST_V1','exact native request fields')
    m=check_manifest(value['manifest_path']);require(sha(value['manifest_path'])==value['manifest_sha256'],'manifest bytes changed')
    phase=value['cohort'];index=value['case_index'];require(phase in ('NATIVE','QUAL') and type(index) is int and 1<=index<=len(m['config']['populations'][phase]),'registered case ordinal')
    require(value['case']==m['config']['populations'][phase][index-1] and set(value['case'])==set(FIELDS),'exact registered case')
    require(value['case']['cohort']==phase and value['native_runtime_bindings']==m['native_runtime_bindings']==runtime_bindings(),'cohort/runtime binding')
    require(type(value['timeout_seconds']) is int and value['timeout_seconds']==210,'fixed native timeout')
    require(type(value['nonce']) is str and re.fullmatch('[0-9a-f]{32}',value['nonce']),'native nonce')
    require(type(value['created_ns']) is int and value['created_ns']>=0,'native request clock')
    c=check_ledger(value['ledger_start']);limits=m['config']['limits'][phase];paid=value['control_steps_start']
    require(type(paid) is int and paid>=0 and paid+500<=limits['control_steps'],'reserve one full task budget')
    require(c.get('reset_attempts',0)+51<=limits['all_resets'] and c.get('simulation_frames_attempted',0)+28000<=limits['physical_frames'],'reserve all reset/frame costs')
    require(all(c.get(k,0)==0 for k in ('reset_errors','simulation_errors','uncertain_simulation_frames','frame_budget_rejections')),'cannot continue after uncertain lifecycle')
    cur=value['cursors_start'];require(type(cur) is dict and set(cur)=={'events','private','last_event_ns','last_private_ns'},'exact stream cursors')
    require(all(type(v) is int and v>=(-1 if k.startswith('last_') else 0) for k,v in cur.items()),'valid stream cursors')
    if phase=='QUAL':
        gate=Path(value['manifest_path']).parent/'native/audit.json'
        require(gate.is_file() and read(gate)['integrity']=='PASSED','native audit before TRAIN')
        process_gate=gate.with_name('process_audit.json')
        require(process_gate.is_file() and read(process_gate)['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY','native process audit before TRAIN')
    expected=Path(value['manifest_path']).parent/phase.lower()/('case_%04d'%index)
    if directory is not None:require(Path(directory).resolve()==expected.resolve(),'owned exact case directory')
    return m


def child_identity(value,request_hash,pid,ppid):
    return dict(pid=pid,ppid=ppid,nonce=value['nonce'],request_sha256=request_hash,cohort=value['cohort'],case_index=value['case_index'],
        manifest_sha256=value['manifest_sha256'],native_runtime_bindings=value['native_runtime_bindings'])


def close_failed_allocation(path,phase,failure):
    """Close only an explicitly owned allocated study; never overwrite a cause."""
    if path is None:return False
    path=Path(path).resolve()
    if path.name!='manifest.json' or path.parent.parent!=OUTPUT.resolve() or not path.is_file():return False
    m=read(path)
    if not str(m.get('experiment_run_id','')).startswith('occam_reference_qualification_v1_') or m.get('config',{}).get('protocol')!='OCCAM_REFERENCE_QUALIFICATION_V1':return False
    marker=path.parent/'CLOSED_TECHNICAL_FAILURE.json'
    if not marker.exists():write(marker,dict(status='CLOSED_NO_RESUME_NO_RETRY',manifest_id=m['manifest_id'],phase=phase,failure=failure))
    return True
