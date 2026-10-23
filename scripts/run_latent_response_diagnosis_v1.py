"""One-shot zero-fit diagnosis phases with independent-operation guards."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from time import perf_counter_ns
import argparse,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import latent_response_diagnosis_io_v1 as a
from scripts.run_latent_response_v1 import readonly_guard


def run(phase,path):
    if phase=='prepare':return str(a.prepare())
    a.checked(path);guard={}
    try:
        with readonly_guard(guard):
            if phase=='analyze':
                from src.analysis.latent_response_diagnosis_v1 import run as analyze
                return analyze(path)
            if phase=='audit':
                from src.analysis.latent_response_diagnosis_audit_v1 import audit
                from src.analysis import latent_response_diagnosis_v1 as main,latent_response_diagnosis_math_v1 as math
                def deny(*args,**kwargs):raise RuntimeError('New main diagnosis and aggregators disabled during independent audit')
                with ExitStack() as stack:
                    for name in ('run','main_windows','components','entry_features','prefix_signature','menu_summary'):stack.enter_context(patch.object(main,name,deny))
                    for name in ('metrics','means','trajectory_rows','grouped','training_objectives','menu_unit'):stack.enter_context(patch.object(math,name,deny))
                    return audit(path)
            if phase=='report':
                from scripts.report_latent_response_diagnosis_v1 import report
                return str(report(path))
            raise ValueError('registered diagnosis phase')
    finally:a.io.write(path.parent/(phase+'_guard.json'),guard)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','analyze','audit','report'));p.add_argument('--manifest',type=Path);v=p.parse_args();start=perf_counter_ns();failure=None;result=None
    try:result=run(v.phase,v.manifest.resolve() if v.manifest else None)
    except BaseException as error:failure={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
    receipt={'phase':v.phase,'status':'PASSED' if failure is None else 'FAILED_PARTIAL_RETAINED','wall_ns':perf_counter_ns()-start,'failure':failure,
        'new_environment_steps':0,'new_model_fits':0,'new_optimizer_updates':0,'online_LLM_API_calls':0}
    if v.manifest:
        a.io.write(v.manifest.parent/(v.phase+'_process_receipt.json'),receipt)
        if failure is not None:a.io.write(v.manifest.parent/(v.phase+'_failure_artifacts.json'),{p.relative_to(v.manifest.parent).as_posix():a.io.sha(p) for p in v.manifest.parent.rglob('*') if p.is_file()})
    print(result if v.phase=='prepare' and failure is None else receipt,flush=True)
    if failure is not None:raise SystemExit(1)
