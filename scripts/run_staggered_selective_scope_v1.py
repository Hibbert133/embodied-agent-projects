from pathlib import Path
import argparse,sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import staggered_selective_scope_v1 as main
from src.analysis import staggered_selective_independent_v1 as independent
from scripts.run_correction_effect_horizon_v1 import SOURCES as previous_sources
OWN=('src/analysis/staggered_selective_scope_v1.py','src/analysis/staggered_selective_independent_v1.py','scripts/run_staggered_selective_scope_v1.py',
    'configs/autoresearch/staggered_selective_scope_v1.json','docs/protocols/staggered_selective_scope_v1_zh.md','docs/research/staggered_selective_decision_v1_zh.md',
    'outputs/correction_scope/selective_coverage_v1/run_pipeline.py','outputs/correction_scope/selective_coverage_v1/validate_freeze.py')
DEPENDENCIES=tuple(dict.fromkeys(previous_sources));SOURCES=(*OWN,*DEPENDENCIES)
def independent_run(path):
    main.checked(path)
    def denied(*a,**kw):raise RuntimeError('primary Fraction generator disabled in integer audit')
    with patch.object(main,'generate',denied):return independent.audit(path)
PHASES={'construct':main.run,'audit':independent_run}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare',*PHASES));p.add_argument('--manifest');a=p.parse_args()
    print(main.prepare(SOURCES) if a.phase=='prepare' else PHASES[a.phase](a.manifest))
