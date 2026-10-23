"""Independent read-only audit with main diagnostic routines disabled."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.analyze_acquisition_support_v1 import guarded
from src.analysis.acquisition_anchor_diagnosis_audit_v1 import audit
from src.analysis.response_qualification_io_v1 import write
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args()
    with ExitStack() as stack:
        for name in ('case_analysis','gates','chain','balance_reference','paired_cost'):
            stack.enter_context(patch('src.analysis.acquisition_anchor_diagnosis_v1.'+name,side_effect=RuntimeError('Main diagnostic function called by independent audit')))
        result,guard=guarded(lambda:audit(v.manifest))
    guard['main_diagnostic_functions_disabled']=True;write(v.manifest.parent/'audit_interaction_guard.json',guard)
    print({k:result[k] for k in ('integrity','fields_checked','source_executions','source_steps')},flush=True)
