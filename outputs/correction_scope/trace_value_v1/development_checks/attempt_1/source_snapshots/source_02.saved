from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import correction_trace_value_v1 as main
from src.analysis import correction_trace_value_independent_v1 as audit

def run():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=('prepare','train','audit-models','replay','audit-replay'));parser.add_argument('manifest',nargs='?')
    args=parser.parse_args()
    if args.phase=='prepare':
        if args.manifest is not None:parser.error('prepare takes no existing manifest')
        print(main.prepare());return
    if args.manifest is None:parser.error('frozen manifest required')
    result={'train':main.train,'audit-models':audit.audit_models,'replay':main.evaluate,'audit-replay':audit.audit_replay}[args.phase](args.manifest)
    print({k:v for k,v in result.items() if k in ('integrity','actual_fits','independent_refits','offline_replays','new_physics','online_LLM_API_calls')})

if __name__=='__main__':run()
