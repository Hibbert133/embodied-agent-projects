"""Frozen statistics and complete Chinese task-passive report."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import task_passive_statistics_v1 as stats


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('phase',choices=('DEV','QUAL','report')); p.add_argument('--manifest',type=Path,required=True)
    a=p.parse_args()
    if a.phase=='report': print(stats.report(a.manifest))
    else:
        v=stats.evaluate(a.manifest,a.phase); print(json.dumps({k:v[k] for k in ('cohort','executions','primary_program','qualification_gate')},ensure_ascii=False))
