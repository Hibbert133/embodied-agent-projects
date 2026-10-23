"""Freeze-gated preparation, one-shot collection and pre-QUAL weight lock."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import response_action_io_v1 as allocation


def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','software-native','dev','select','evaluate-dev','qual','evaluate-qual'));p.add_argument('--manifest',type=Path)
    a=p.parse_args()
    if a.phase=='prepare':
        if a.manifest is not None:p.error('prepare takes no existing manifest')
        print(allocation.prepare());return
    if a.manifest is None:p.error('--manifest required')
    if a.phase=='select':
        from src.analysis.response_action_statistics_v1 import select
        v=select(a.manifest);print(json.dumps({k:v[k] for k in ('selected_F20_weight','primary_program','development_gate')}));return
    if a.phase.startswith('evaluate-'):
        from src.analysis.response_action_statistics_v1 import evaluate
        v=evaluate(a.manifest,'DEV' if a.phase=='evaluate-dev' else 'QUAL');print(json.dumps({k:v[k] for k in ('cohort','qualification_gate','primary_program')}));return
    from src.analysis.response_action_collect_v1 import collect
    print(collect(a.manifest,{'software-native':'SOFTWARE_NATIVE','dev':'DEV','qual':'QUAL'}[a.phase]))


if __name__=='__main__':main()
