from pathlib import Path
import argparse,sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import packet_structure_sources_v1 as source,packet_structure_diagnosis_v1 as main,packet_structure_independent_v1 as independent
from scripts.run_paired_packet_response_v1 import sources as prior_sources
OWN=tuple(sorted(p.relative_to(ROOT).as_posix() for pattern in ('src/analysis/packet_structure*_v1.py','scripts/*packet_structure*_v1.py','tests/test_packet_structure*_v1.py') for p in ROOT.glob(pattern)))
DOCS=('configs/autoresearch/packet_structure_diagnosis_v1.json','docs/protocols/packet_structure_diagnosis_v1_zh.md','docs/research/packet_structure_decision_v1_zh.md')
SOURCES=tuple(sorted(set(prior_sources())|set(OWN)|set(DOCS)))


def execute(phase,path):
    from src.probe import paired_packet_model_v1
    from src.analysis import paired_packet_host_v1
    def denied(*args,**kw):raise RuntimeError('No model prediction permitted during descriptive diagnosis')
    with patch.object(paired_packet_model_v1,'predict',denied),patch.object(paired_packet_host_v1,'predict',denied):return (main.run if phase=='analyze' else independent.audit)(path)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','analyze','audit'));p.add_argument('--manifest');args=p.parse_args()
    print(source.prepare(SOURCES) if args.phase=='prepare' else execute(args.phase,args.manifest))
