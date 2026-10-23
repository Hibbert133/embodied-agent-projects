"""Guarded independent saved-record action support audit."""
from pathlib import Path
import argparse
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.analyze_acquisition_support_v1 import guarded
from src.analysis.acquisition_support_audit_v1 import audit
from src.analysis.acquisition_support_sources_v1 import io


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args()
    result,guard=guarded(lambda:audit(a.manifest));io.write(a.manifest.parent/'audit_interaction_guard.json',guard)
    print({k:result[k] for k in ('integrity','source_cases','source_steps','fields_checked','all_rows')},flush=True)
