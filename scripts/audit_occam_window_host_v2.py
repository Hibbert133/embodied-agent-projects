"""One read-only repair audit; persist guards and failures as well as success."""
from pathlib import Path
from contextlib import contextmanager,redirect_stdout,redirect_stderr
from unittest.mock import patch
from time import perf_counter_ns
import argparse,traceback,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_window_io_v1 as a
from src.analysis import release_learning_guard_v1 as guards
io=a.io


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);arg=parser.parse_args()
    manifest=a.checked(arg.manifest);base=a.BASE/'audit_repair_v2';freeze=io.read(base/'freeze_complete.json')
    io.require(freeze['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'committed reader repair')
    for n,h in freeze['source_sha256'].items():io.require(io.sha(a.ROOT/n)==h,'reader source changed')
    out=base/'attempt01';out.mkdir(exist_ok=False);start=perf_counter_ns();guard={};original=guards.read_only
    @contextmanager
    def persistent(receipt,**kw):
        try:
            with original(receipt,**kw):yield
        finally:
            guard.update(receipt);io.write(out/'guard.json',receipt,exclusive=False)
    failure=None;result=None
    try:
        with (out/'stdout.log').open('x',encoding='utf8') as log,(out/'stderr.log').open('x',encoding='utf8') as err,redirect_stdout(log),redirect_stderr(err),patch.object(guards,'read_only',persistent):
            from src.analysis.occam_window_audit_v2 import audit
            result=audit(arg.manifest)
    except BaseException as error:
        failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
    if result is not None:
        counts=result['counts'];io.require(counts['audit_fixed_policy_queries']<=18000 and counts['audit_filter_updates']<=1116 and counts['independent_batch_solves']<=36,'repair CPU budget')
    receipt=dict(integrity='PASSED' if failure is None else 'FAILED',manifest_id=manifest['manifest_id'],source_git_commit=io.git('rev-parse','HEAD'),
        source_sha256=freeze['source_sha256'],result=result,failure=failure,guard=guard,wall_ns=perf_counter_ns()-start,
        new_environment_interactions=0,scientific_model_training=0,online_LLM_API_calls=0,original_native_records_unchanged=True)
    io.write(out/'complete.json',receipt);a.checked(arg.manifest)
    if failure is not None:raise RuntimeError('Read-only repair failed; preserved, no automatic retry '+str(failure))
    print({k:v for k,v in receipt.items() if k in ('integrity','wall_ns','new_environment_interactions','online_LLM_API_calls')},flush=True)


if __name__=='__main__':main()
