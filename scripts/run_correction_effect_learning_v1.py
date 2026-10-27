from pathlib import Path
import argparse,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import correction_effect_learning_v1 as main
from src.analysis import correction_effect_independent_v1 as independent
from scripts.run_correction_policy_support_v1 import SOURCES as previous_sources
OWN=('src/probe/correction_effect_model_v1.py','src/analysis/correction_effect_learning_v1.py','src/analysis/correction_effect_independent_v1.py',
    'scripts/run_correction_effect_learning_v1.py','tests/test_correction_effect_learning_v1.py','configs/movement_task/correction_effect_learning_v1.json',
    'docs/protocols/correction_effect_learning_v1_zh.md','docs/research/correction_effect_decision_v1_zh.md',
    'outputs/correction_scope/effect_learning_v1/run_pipeline.py','outputs/correction_scope/effect_learning_v1/validate_freeze.py')
DEPENDENCIES=tuple(dict.fromkeys(previous_sources));SOURCES=(*OWN,*DEPENDENCIES)
PHASES={'extract':main.extract,'audit-pairs':independent.audit_pairs,'fit':main.fit,'audit-models':independent.audit_models,'evaluate':main.evaluate,'audit-statistics':independent.audit_statistics}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare',*PHASES));p.add_argument('--manifest');args=p.parse_args()
    if args.phase=='prepare':print(main.prepare(SOURCES))
    else:
        assert args.manifest;print(PHASES[args.phase](args.manifest))
