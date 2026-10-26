from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import correction_program_support_v1 as m

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=('prepare','analyze','audit'));parser.add_argument('--manifest')
    args=parser.parse_args()
    if args.phase=='prepare':print(m.prepare())
    elif args.phase=='analyze':
        result=m.analyze(args.manifest);print(dict(integrity=result['integrity'],source_units=len(result['units']),new_physics=0,new_fits=0))
    else:
        from src.analysis.correction_program_support_independent_v1 import audit
        result=audit(args.manifest);print({k:result[k] for k in ('integrity','checked_fields','source_cases','source_units','new_physics','new_model_fits')})
