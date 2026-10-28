"""One separately frozen reader attempt; never calls a physical collector."""
from pathlib import Path
from contextlib import contextmanager,redirect_stdout,redirect_stderr
from time import perf_counter_ns
from unittest.mock import patch
import argparse,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_reader_extension_v3 as e,release_learning_guard_v1 as guards
from src.analysis.occam_reference_train_audit_v3 import audit


def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',required=True,choices=e.a.PHASES);v=p.parse_args()
    e.verify();attempt=e.BASE/(v.phase.lower()+'_attempt01');attempt.mkdir(exist_ok=False)
    original=guards.read_only;guard={};started=perf_counter_ns();failure=None;result=None
    @contextmanager
    def persistent(receipt,**kw):
        try:
            with original(receipt,**kw):yield
        finally:guard.update(receipt);e.io.write(attempt/'guard.json',receipt,exclusive=False)
    try:
        with (attempt/'stdout.log').open('x',encoding='utf8',newline='\n') as log,(attempt/'stderr.log').open('x',encoding='utf8',newline='\n') as err,redirect_stdout(log),redirect_stderr(err),patch.object(guards,'read_only',persistent):
            result=audit(e.TARGET,v.phase)
        if v.phase=='NATIVE':
            raw=e.TARGET.parent/'native';r=e.io.read(raw/'audit_repair_v3/audit.json')
            meta=dict(reader_version=3,extension_freeze_sha256=e.io.sha(e.VALIDATION/'complete.json'),
                repaired_audit_path='native/audit_repair_v3/audit.json',repaired_audit_sha256=e.io.sha(raw/'audit_repair_v3/audit.json'),
                original_failed_attempt_sha256=e.io.sha(raw/'audit_attempt01/complete.json'))
            e.io.write(raw/'audit.json',{**r,'reader_repair':meta});e.native_authorization()
    except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
    e.io.write(attempt/'complete.json',dict(integrity='PASSED' if failure is None else 'FAILED',result=result,failure=failure,
        guard=guard,source_manifest_id=e.io.read(e.TARGET)['manifest_id'],extension_freeze_sha256=e.io.sha(e.VALIDATION/'complete.json'),wall_ns=perf_counter_ns()-started))
    if failure is not None:raise RuntimeError('One-shot V3 reader stopped; preserve '+str(failure))
    print(dict(integrity='PASSED',phase=v.phase,counts=result['counts']),flush=True)


if __name__=='__main__':main()
