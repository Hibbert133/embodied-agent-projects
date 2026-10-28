"""One-shot independently frozen reference deployment and read-only audits."""
from pathlib import Path
from contextlib import ExitStack,contextmanager,redirect_stdout,redirect_stderr
from time import perf_counter_ns
from unittest.mock import patch
import argparse,json,secrets,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def dispatch(command,manifest,phase):
    from src.analysis import occam_reference_qualification_io_v1 as a
    if command=='prepare':return str(a.prepare())
    if command=='collect':
        from src.analysis.occam_reference_qualification_collect_v1 import collect
        return str(collect(manifest,phase))
    if command=='process-audit':
        from src.analysis.occam_qualification_process_audit_v1 import audit_cohort
        result=audit_cohort(manifest,phase);a.io.write(Path(manifest).parent/phase.lower()/'process_audit.json',result);return result
    if command=='audit':
        from src.analysis.occam_reference_qualification_audit_v1 import audit
        a.io.require(a.io.read(Path(manifest).parent/phase.lower()/'process_audit.json')['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY','process audit before dynamics/model audit')
        return audit(manifest,phase)
    if command=='statistics':
        from src.analysis.occam_qualification_statistics_v1 import compute
        return compute(manifest)
    if command=='statistics-audit':
        from src.analysis.occam_qualification_statistics_audit_v1 import audit
        return audit(manifest)
    raise ValueError('unregistered command')


def run_entry(command,manifest=None,phase=None):
    from src.analysis import occam_qualification_case_io_v1 as c
    from src.analysis.occam_platform_bootstrap_v1 import in_process_queries,module_sha256
    if command=='prepare':folder=c.BASE/'preparation_attempts_v1'/('attempt_'+str(perf_counter_ns())+'_'+secrets.token_hex(6))
    else:
        path=Path(manifest).resolve();c.require(path.name=='manifest.json' and path.parent.parent==c.OUTPUT.resolve(),'exact manifest directory')
        if command in ('collect','process-audit','audit'):c.require(phase in ('NATIVE','QUAL'),'actual registered phase')
        folder=path.parent/'entry_attempts_v1'/(command+'_'+str(phase)+'_attempt01')
    folder.mkdir(parents=True,exist_ok=False);start=perf_counter_ns();failure=None;guard={};platform={};result=None
    c.write(folder/'request.json',dict(command=command,manifest=manifest,phase=phase,started_ns=start,one_shot=True))
    try:
        with (folder/'stdout.log').open('x',encoding='utf8') as out,(folder/'stderr.log').open('x',encoding='utf8') as err,\
            redirect_stdout(out),redirect_stderr(err),in_process_queries(module_sha256()) as platform,ExitStack() as stack:
            if command in ('audit','statistics','statistics-audit'):
                from src.analysis import release_learning_guard_v1 as guards
                original=guards.read_only
                @contextmanager
                def persistent(receipt,**kwargs):
                    try:
                        with original(receipt,**kwargs):yield
                    finally:guard.update(receipt);c.write(folder/'guard.json',receipt)
                stack.enter_context(patch.object(guards,'read_only',persistent))
            result=dispatch(command,manifest,phase)
    except BaseException as error:
        failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
        if command=='collect':c.close_failed_allocation(manifest,phase,dict(**failure,source='ONE_SHOT_COLLECTION'))
    final=dict(integrity='PASSED' if failure is None else 'FAILED',command=command,result=result,failure=failure,guard=guard,
        platform_query=platform,stdout_sha256=c.sha(folder/'stdout.log'),stderr_sha256=c.sha(folder/'stderr.log'),
        wall_ns=perf_counter_ns()-start,online_LLM_API_calls=0)
    c.write(folder/'complete.json',final)
    if failure is not None:raise RuntimeError('one-shot entry failed, retained '+str(folder/'complete.json'))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','collect','process-audit','audit','statistics','statistics-audit'))
    p.add_argument('--manifest');p.add_argument('--phase',choices=('NATIVE','QUAL'));x=p.parse_args()
    print(json.dumps(run_entry(x.command,x.manifest,x.phase),ensure_ascii=False),flush=True)
