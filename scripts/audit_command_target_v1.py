"""Disable the main arithmetic and reductions during the independent audit."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import command_target_sources_v1 as source,command_target_diagnostic_v1 as main
from src.analysis.command_target_audit_v1 import audit
from scripts.analyze_acquisition_support_v1 import guarded

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);v=p.parse_args()
    def deny(*args,**kwargs):raise RuntimeError('Main diagnostic disabled during independent audit')
    with ExitStack() as stack:
        for name in ('trace','arithmetic','grouped','stats','target_update','applied'):stack.enter_context(patch.object(main,name,deny))
        result,guard=guarded(lambda:audit(v.manifest))
    source.io.write(v.manifest.parent/'audit_interaction_guard.json',guard)
    print({k:result[k] for k in ('integrity','executions','saved_steps','independently_checked_fields','wall_ns')},flush=True)
