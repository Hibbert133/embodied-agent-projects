"""One read-only closed-allocation diagnosis; no collector or training entry."""
from pathlib import Path
from contextlib import contextmanager,redirect_stdout,redirect_stderr
from time import perf_counter_ns
from unittest.mock import patch
import json,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_training_failure_v2 as d,release_learning_guard_v1 as guards
if __name__=='__main__':
    attempt=d.BASE/'diagnostic_attempt01';attempt.mkdir(exist_ok=False);start=perf_counter_ns();original=guards.read_only;guard={};failure=None;result=None
    @contextmanager
    def persistent(receipt,**kw):
        try:
            with original(receipt,**kw):yield
        finally:guard.update(receipt);d.io.write(attempt/'guard.json',receipt,exclusive=False)
    try:
        with (attempt/'stdout.log').open('x',encoding='utf8',newline='\n') as log,(attempt/'stderr.log').open('x',encoding='utf8',newline='\n') as err,redirect_stdout(log),redirect_stderr(err),patch.object(guards,'read_only',persistent):result=d.diagnose()
    except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
    d.io.write(attempt/'complete.json',dict(integrity='PASSED' if failure is None else 'FAILED',failure=failure,guard=guard,wall_ns=perf_counter_ns()-start))
    if failure is not None:raise RuntimeError('One-shot read-only diagnostic stopped; retained '+str(failure))
    print(json.dumps({k:result[k] for k in ('integrity','completed_TRAIN','partial_TRAIN','not_started_TRAIN','whole_allocation_actual_cost','online_LLM_API_calls')},ensure_ascii=False),flush=True)
