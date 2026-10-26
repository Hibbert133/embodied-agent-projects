"""Only saved-branch analysis: no environment collection command exists."""
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import correction_scope_risk_reference_v1 as reference
from src.analysis import correction_scope_risk_reference_independent_v1 as audit

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=('prepare','train','audit-models','replay','audit-replay'));parser.add_argument('manifest',nargs='?')
    args=parser.parse_args()
    if args.phase=='prepare':
        if args.manifest is not None:parser.error('prepare has no existing manifest')
        print(reference.prepare());return
    if args.manifest is None:parser.error('a saved frozen manifest is required')
    method={'train':reference.train,'audit-models':audit.audit_models,'replay':reference.evaluate,'audit-replay':audit.audit_replay}[args.phase]
    result=method(args.manifest)
    print({k:v for k,v in result.items() if k in ('integrity','actual_model_fits','independent_refits','offline_replays','new_physics','online_LLM_API_calls')})

if __name__=='__main__':main()
