"""Frozen, TRAIN-only auxiliary-risk component development."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import correction_transfer_learning_v1 as main
from src.analysis import correction_transfer_independent_v1 as independent

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','fit','audit-models','evaluate','audit-replay'));p.add_argument('--manifest')
    args=p.parse_args()
    if args.phase=='prepare':print(main.prepare())
    else:
        assert args.manifest
        print({'fit':main.fit,'audit-models':independent.audit_models,'evaluate':main.evaluate,'audit-replay':independent.audit_replay}[args.phase](args.manifest))
