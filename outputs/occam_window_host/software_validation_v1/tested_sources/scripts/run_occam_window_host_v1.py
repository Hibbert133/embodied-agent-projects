"""Prepare, collect or independently audit the frozen one-shot native contract."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','collect','audit'));p.add_argument('--manifest');v=p.parse_args()
    if v.command=='prepare':
        from src.analysis.occam_window_io_v1 import prepare
        result=str(prepare())
    else:
        if v.manifest is None:p.error('--manifest required')
        if v.command=='collect':
            from src.analysis.occam_window_collect_v1 import collect
            result=str(collect(v.manifest))
        else:
            from src.analysis.occam_window_audit_v1 import audit
            result=audit(v.manifest)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
