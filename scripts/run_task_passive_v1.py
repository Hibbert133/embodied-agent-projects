"""Freeze-gated one-shot task-passive phases and pre-qualification selection."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import task_passive_io_v1 as allocation


def main():
    p=argparse.ArgumentParser(); p.add_argument('phase',choices=('prepare','software-native','dev','select','qual')); p.add_argument('--manifest',type=Path)
    a=p.parse_args()
    if a.phase=='prepare':
        if a.manifest is not None: p.error('prepare takes no existing manifest')
        print(allocation.prepare()); return 0
    if a.manifest is None: p.error('--manifest required')
    if a.phase=='select':
        from src.analysis.task_passive_statistics_v1 import select
        v=select(a.manifest); print(json.dumps({k:v[k] for k in ('selected_time_constants_s','primary_program','development_gate')},ensure_ascii=False)); return 0
    from src.analysis.task_passive_collect_v1 import collect
    print(collect(a.manifest,{'software-native':'SOFTWARE_NATIVE','dev':'DEV','qual':'QUAL'}[a.phase])); return 0


if __name__=='__main__': raise SystemExit(main())
