from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','collect','audit','prepare-learning','model-audit'));p.add_argument('--manifest');p.add_argument('--phase',choices=('NATIVE','TRAIN'));v=p.parse_args()
    if v.command=='prepare':
        from src.analysis.occam_reference_train_io_v2 import prepare
        r=str(prepare())
    else:
        if v.manifest is None:p.error('--manifest required')
        if v.command in ('collect','audit') and v.phase is None:p.error('--phase required')
        if v.command=='collect':
            from src.analysis.occam_reference_train_collect_v2 import collect
            r=str(collect(v.manifest,v.phase))
        elif v.command=='audit':
            from src.analysis.occam_reference_train_audit_v2 import audit
            from src.analysis import occam_reference_train_io_v2 as a,release_learning_guard_v1 as guards
            from contextlib import contextmanager,redirect_stdout,redirect_stderr
            from unittest.mock import patch
            from time import perf_counter_ns
            import traceback
            attempt=Path(v.manifest).parent/v.phase.lower()/'audit_attempt01';attempt.mkdir(exist_ok=False)
            original=guards.read_only;guard={};started=perf_counter_ns();failure=None;r=None
            @contextmanager
            def persistent(receipt,**kw):
                try:
                    with original(receipt,**kw):yield
                finally:guard.update(receipt);a.io.write(attempt/'guard.json',receipt,exclusive=False)
            try:
                with (attempt/'stdout.log').open('x',encoding='utf8',newline='\n') as log,(attempt/'stderr.log').open('x',encoding='utf8',newline='\n') as err,redirect_stdout(log),redirect_stderr(err),patch.object(guards,'read_only',persistent):r=audit(v.manifest,v.phase)
            except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
            a.io.write(attempt/'complete.json',dict(integrity='PASSED' if failure is None else 'FAILED',result=r,failure=failure,guard=guard,wall_ns=perf_counter_ns()-started))
            if failure is not None:raise RuntimeError('One-shot reader failed; retained '+str(failure))
        else:
            from src.analysis.occam_reference_learning_io_v2 import prepare_learning,audit_learning
            r=str(prepare_learning(v.manifest)) if v.command=='prepare-learning' else audit_learning(v.manifest)
    print(json.dumps(r,ensure_ascii=False))


if __name__=='__main__':main()
