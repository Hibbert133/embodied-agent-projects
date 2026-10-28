from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
source=(ROOT/'src/analysis/occam_resource_process_v3.py').read_text(encoding='utf8')
start=source.index('def attempt(');stop=source.index('def _nested_failure',start);body=source[start:stop]
body=body.replace('    validate_spec(request);directory=Path(directory).resolve()\n    if not directory.is_relative_to(OUTPUT.resolve()):raise ValueError(\'owned software output directory required\')',
    '    directory=Path(directory).resolve();contract.validate_request(request,directory)')
body=body.replace("'spec.json'","'request.json'").replace("'--spec'","'--request'")
body=body.replace('resources.gate(preflight,**PROFILE)','resources.gate(preflight,**contract.PROFILE_ADMIT)')
body=body.replace('resources.gate(sample,**PROFILE)','resources.gate(sample,**contract.PROFILE_LIVE)')
body=body.replace('sleep(.05)','sleep(.25)')
body=body.replace('    for name in (\'stdout.log\',\'stderr.log\'):',"    for name in ('stdout.log','stderr.log','case.json','events.jsonl.gz','witnesses.jsonl.gz','accounting.json','accounting_progress.jsonl.gz','failed_execution.json','execution_error.json','rng_initialization.json','bootstrap.json'):")
i=body.index("    result=dict(schema=");j=body.index("    write(directory/'result.json',result);return result",i)
body=body[:i]+'''    result=dict(schema='OCCAM_NATIVE_CASE_PROCESS_RESULT_V1',cohort=request['cohort'],case_index=request['case_index'],nonce=request['nonce'],request_sha256=request_hash,
        status=status,expected_status='RETURNED',expected_contract_observed=status=='RETURNED',
        pid=None if p is None else p.pid,parent_pid=os.getpid(),returncode=returncode,launches=int(p is not None),
        termination=termination,parent_error=parent_error,started_ns=started,completed_ns=clock(),samples=samples,events=events,
        artifact_sha256=artifacts,new_scientific_training=0,online_LLM_API_calls=0,physical_cost_claim='READ_ACCOUNTING_AND_NATIVE_JOURNALS_NOT_ASSUMED_ZERO')
'''+body[j:]
body=body.replace("write(directory/'result.json',result)","write_compact(directory/'result.json',result)")
header='''"""Own one complete native case process; no simulator imports in the parent."""
from pathlib import Path
import json,os,subprocess,sys,time,traceback
from src.analysis import occam_native_case_io_v1 as contract
from src.analysis import occam_resource_observation_v1 as resources
from src.analysis import occam_resource_process_v3 as software
ROOT=contract.ROOT;WORKER=contract.WORKER;read=contract.read;sha=contract.sha;write=contract.write;executable=software.executable


def write_compact(path,value):
    with Path(path).open('x',encoding='utf8',newline='\\n') as f:json.dump(value,f,ensure_ascii=False,allow_nan=False,separators=(',',':'));f.write('\\n')


def _same_identity(receipt,request,request_hash,pid):
    expected=contract.child_identity(request,request_hash,pid,os.getpid())
    return all(receipt.get(k)==v for k,v in expected.items())


def classify(request,request_hash,pid,returncode,start,receipt,termination):
    if start is None or not _same_identity(start,request,request_hash,pid) or not request['created_ns']<=start.get('started_ns',-1):return 'INVALID_START'
    if termination:return termination+'_TERMINATED' if returncode is not None else 'PROCESS_NOT_CONFIRMED_TERMINAL'
    if receipt is None:return 'UNRECEIPTED_EXIT'
    if not _same_identity(receipt,request,request_hash,pid) or receipt.get('started_ns')!=start['started_ns'] or receipt.get('completed_ns',-1)<start['started_ns']:return 'INVALID_RECEIPT'
    if returncode==0 and receipt.get('state')=='RETURNED' and receipt.get('error') is None:return 'RETURNED'
    if returncode==1 and receipt.get('state')=='ERROR' and receipt.get('error',{}).get('traceback'):return 'WORKER_EXCEPTION'
    return 'EXIT_RECEIPT_DISAGREEMENT'


'''
footer='''def worker(request_path):
    request_path=Path(request_path).resolve();value=read(request_path);contract.validate_request(value,request_path.parent)
    if request_path.name!='request.json':raise ValueError('exact native request file required')
    sys.addaudithook(software._worker_audit);started=time.perf_counter_ns()
    identity=contract.child_identity(value,sha(request_path),os.getpid(),os.getppid())
    write(request_path.parent/'start.json',dict(**identity,started_ns=started,resource=resources.snapshot(ROOT)))
    state='RETURNED';error=None;code=0;payload={}
    try:
        from src.analysis.occam_platform_bootstrap_v1 import in_process_queries
        sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'));guard={}
        with in_process_queries(value['native_runtime_bindings']['platform_module_sha256']) as platform_query:
            from src.analysis.release_learning_guard_v1 import read_only
            with read_only(guard):
                from src.analysis.response_action_io_v1 import verify_runtime
                verify_runtime(read(software.RUNTIME_LOCK))
                from src.analysis.occam_reference_train_case_v3 import run_case
        bootstrap=dict(runtime_verified=True,dependency_guard=guard,platform_query=platform_query,completed_ns=time.perf_counter_ns(),before_native_factory=True)
        write(request_path.parent/'bootstrap.json',bootstrap)
        accounting=run_case(value,request_path.parent)
        payload=dict(accounting_sha256=sha(request_path.parent/'accounting.json'),case_sha256=sha(request_path.parent/'case.json'),status=accounting['status'])
    except BaseException:
        state='ERROR';code=1;error=dict(type=sys.exc_info()[0].__name__,message=str(sys.exc_info()[1]),traceback=traceback.format_exc())
        traceback.print_exc()
    finish_resource=resources.snapshot(ROOT)
    write(request_path.parent/'receipt.json',dict(**identity,started_ns=started,completed_ns=time.perf_counter_ns(),state=state,error=error,payload=payload,
        resource_at_finish=finish_resource))
    return code
'''
text=header+body+footer
compile(text,'occam_native_case_process_v1.py','exec')
with (ROOT/'src/analysis/occam_native_case_process_v1.py').open('x',encoding='utf8',newline='\n') as f:f.write(text)
print('native-case owned process and guarded worker entry created')
