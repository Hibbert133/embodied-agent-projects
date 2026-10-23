"""Prepare, collect or audit exactly one native measurement qualification."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from time import perf_counter_ns
import argparse,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import native_command_witness_io_v1 as a

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','collect','audit'));p.add_argument('--manifest',type=Path);v=p.parse_args()
    if v.phase=='prepare':print(a.prepare(),flush=True)
    else:
        a.io.require(v.manifest is not None,'native manifest required');a.checked(v.manifest);start=perf_counter_ns();failure=None;result=None
        try:
            if v.phase=='collect':
                from src.analysis.native_command_witness_collect_v1 import collect
                result=collect(v.manifest)
            else:
                from src.analysis.native_command_witness_audit_v1 import audit
                from src.analysis import native_command_witness_host_v1 as host
                from src.probe import nominal_command_target_v1 as nominal
                from scripts.analyze_acquisition_support_v1 import guarded
                def deny(*args,**kwargs):raise RuntimeError('Main native observation/public-summary computation disabled in audit')
                with ExitStack() as stack:
                    for obj,name in ((host,'native_values'),(host,'run_live'),(host,'public_prefix'),(nominal,'target_update')):stack.enter_context(patch.object(obj,name,deny))
                    result,guard=guarded(lambda:audit(v.manifest))
                a.io.write(v.manifest.parent/'native/audit_guard.json',guard)
        except BaseException as error:failure={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
        receipt={'phase':v.phase,'status':'PASSED' if failure is None else 'FAILED','manifest_id':a.io.read(v.manifest)['manifest_id'],
            'wall_ns':perf_counter_ns()-start,'failure':failure,'new_model_fits':0,'online_LLM_API_calls':0}
        a.io.write(v.manifest.parent/(v.phase+'_process_receipt.json'),receipt);print(receipt,flush=True)
        if failure is not None:raise SystemExit(1)
