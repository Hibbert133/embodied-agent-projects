"""Read-only independent audits; never create, reset or advance an environment."""
import argparse
from pathlib import Path
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import response_qualification_audit_v1 as audit


def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=("TRAIN","CAL","QUAL","models","calibration","numeric"));p.add_argument("--manifest",required=True,type=Path);a=p.parse_args()
    path=a.manifest.resolve()
    value=audit.audit_split(path,a.mode) if a.mode in ("TRAIN","CAL","QUAL") else getattr(audit,"audit_"+a.mode)(path)
    print(json.dumps(value,ensure_ascii=False))


if __name__=="__main__":main()
