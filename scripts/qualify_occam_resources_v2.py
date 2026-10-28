"""Run once or audit the fixed software fixtures, never start a robot task."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_resource_qualification_v2 as qualification

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('qualify','audit'))
    args=parser.parse_args()
    result=getattr(qualification,args.operation)()
    print(json.dumps({k:result[k] for k in ('integrity','new_environment_operations','new_fits','online_LLM_API_calls')},ensure_ascii=False))
