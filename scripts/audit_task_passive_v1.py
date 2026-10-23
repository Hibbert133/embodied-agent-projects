"""Read-only independent task-passive journal audit."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis.task_passive_audit_v1 import audit


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--manifest',type=Path,required=True); p.add_argument('--cohort',choices=('SOFTWARE_NATIVE','DEV','QUAL'),required=True)
    a=p.parse_args(); print(json.dumps(audit(a.manifest,a.cohort),ensure_ascii=False))
