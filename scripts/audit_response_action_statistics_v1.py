"""Read-only numeric reconstruction of complete full-task cohort statistics."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.response_action_statistics_audit_v1 import audit
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--cohort',choices=('DEV','QUAL'),required=True);a=p.parse_args()
    print(audit(a.manifest,a.cohort))
