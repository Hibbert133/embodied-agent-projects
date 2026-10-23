"""Prepare, collect frozen cohort, or compute standard-reference statistics."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import acquisition_reference_io_v1 as a
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','collect','statistics'));p.add_argument('--manifest',type=Path);p.add_argument('--cohort',choices=('SOFTWARE_NATIVE','QUAL'));v=p.parse_args()
    if v.phase=='prepare':print(a.prepare(),flush=True)
    else:
        if v.manifest is None:p.error('manifest required')
        if v.phase=='collect':
            if v.cohort is None:p.error('cohort required')
            from src.analysis.acquisition_reference_collect_v1 import collect
            print(collect(v.manifest,v.cohort),flush=True)
        else:
            from scripts.analyze_acquisition_support_v1 import guarded
            from src.analysis.acquisition_reference_statistics_v1 import run
            result,guard=guarded(lambda:run(v.manifest));a.io.write(v.manifest.parent/'qual/statistics_guard.json',guard)
            print({k:result[k] for k in ('acquisition_status','reference_update_status','joint_component_gate_passed')},flush=True)
