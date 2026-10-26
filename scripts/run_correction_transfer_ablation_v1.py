"""One frozen TRAIN-only matched supervision ablation."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import correction_transfer_ablation_v1 as main
from src.analysis import correction_transfer_ablation_independent_v1 as audit
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','fit','audit-models','evaluate','audit-replay'));p.add_argument('--manifest');a=p.parse_args()
    if a.phase=='prepare':print(main.prepare())
    else:
        assert a.manifest;print({'fit':main.fit,'audit-models':audit.audit_models,'evaluate':main.evaluate,'audit-replay':audit.audit_replay}[a.phase](a.manifest))
