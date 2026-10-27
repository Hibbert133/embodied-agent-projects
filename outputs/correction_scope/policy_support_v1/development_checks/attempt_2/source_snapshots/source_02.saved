"""One frozen zero-physics factual support analysis and independent audit."""
from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import correction_policy_support_v1 as main
from src.analysis import correction_policy_support_independent_v1 as independent
from scripts.run_learned_acquisition_native_v1 import SOURCES as native_sources
OWN=('src/analysis/correction_policy_support_v1.py','src/analysis/correction_policy_support_independent_v1.py',
    'scripts/run_correction_policy_support_v1.py','tests/test_correction_policy_support_v1.py',
    'configs/movement_task/correction_policy_support_v1.json','docs/protocols/correction_policy_support_v1_zh.md',
    'docs/research/correction_policy_support_decision_v1_zh.md','outputs/correction_scope/policy_support_v1/.gitattributes',
    'outputs/correction_scope/policy_support_v1/validate_freeze.py','outputs/correction_scope/policy_support_v1/run_pipeline.py')
DEPENDENCIES=tuple(dict.fromkeys((*native_sources,'src/analysis/learned_acquisition_native_audit_v2.py','tests/test_learned_native_audit_repair_v2.py')))
SOURCES=(*OWN,*DEPENDENCIES)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','analyze','audit'));p.add_argument('--manifest');args=p.parse_args()
    if args.phase=='prepare':print(main.prepare(SOURCES))
    else:
        assert args.manifest
        print({'analyze':main.analyze,'audit':independent.audit}[args.phase](args.manifest))
