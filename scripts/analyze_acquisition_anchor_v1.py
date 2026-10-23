"""Source-bound preparation and guarded read-only diagnosis."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import acquisition_anchor_diagnosis_io_v1 as a
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','analyze'));p.add_argument('--manifest',type=Path);v=p.parse_args()
    if v.phase=='prepare':print(a.prepare(),flush=True)
    else:
        if v.manifest is None:p.error('manifest required')
        from scripts.analyze_acquisition_support_v1 import guarded
        from src.analysis.acquisition_anchor_diagnosis_v1 import run
        result,guard=guarded(lambda:run(v.manifest));a.io.write(v.manifest.parent/'interaction_guard.json',guard)
        print({k:result[k] for k in ('source_executions','source_steps','actual_move_cases','full_windows','final_gate_mask_counts_among_actual_moves')},flush=True)
