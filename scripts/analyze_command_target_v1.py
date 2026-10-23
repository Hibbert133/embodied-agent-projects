"""Freeze or run the guarded, read-only complete-source diagnostic."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import command_target_sources_v1 as source
from scripts.analyze_acquisition_support_v1 import guarded

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--manifest',type=Path);v=p.parse_args()
    if v.prepare:print(source.prepare(),flush=True)
    else:
        source.io.require(v.manifest is not None,'owned manifest required')
        from src.analysis.command_target_diagnostic_v1 import run
        result,guard=guarded(lambda:run(v.manifest));source.io.write(v.manifest.parent/'interaction_guard.json',guard)
        print({k:result[k] for k in ('integrity','executions','saved_steps','wall_ns')},flush=True)
