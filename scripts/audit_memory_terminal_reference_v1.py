"""Independent finite-model audit with main numerical routines disabled."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.analyze_acquisition_support_v1 import guarded
from src.analysis.memory_terminal_audit_v1 import audit
from src.analysis.response_qualification_io_v1 import write


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args()
    with ExitStack() as stack:
        for name in ('src.analysis.two_stage_terminal_dr_v1.estimate','src.analysis.memory_terminal_world_v1.atoms',
            'src.analysis.memory_terminal_world_v1.true_q1','src.analysis.memory_terminal_world_v1.true_q2','src.analysis.memory_terminal_world_v1.target_truth'):
            stack.enter_context(patch(name,side_effect=RuntimeError('Independent audit called a main numerical routine')))
        result,guard=guarded(lambda:audit(a.manifest))
    guard['main_numeric_functions_disabled']=True;write(a.manifest.parent/'audit_interaction_guard.json',guard)
    print({k:result[k] for k in ('integrity','exact_rational_identities','estimate_rows','fields_checked')},flush=True)
