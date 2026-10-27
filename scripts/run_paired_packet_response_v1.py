"""Versioned one-shot collector/qualification entry point; zero online LLM."""
from pathlib import Path
import argparse,sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import paired_packet_io_v1 as io,paired_packet_collect_v1 as collector,paired_packet_record_audit_v1 as records
from src.analysis import paired_packet_training_v1 as training,paired_packet_evaluation_v1 as evaluation,paired_packet_statistics_audit_v1 as statistics

OWN=tuple(sorted([p.relative_to(ROOT).as_posix() for pattern in ('src/probe/paired_packet*_v1.py','src/analysis/paired_packet*_v1.py','scripts/*paired_packet*_v1.py','tests/test_paired_packet*_v1.py') for p in ROOT.glob(pattern)]))
DOCS=('configs/movement_task/paired_packet_response_v1.json','docs/protocols/paired_packet_response_v1_zh.md','docs/protocols/paired_packet_seeds_v1.json','docs/research/paired_packet_response_decision_v1_zh.md')
def sources():
    import subprocess
    tracked=subprocess.check_output(['git','ls-files','src/*.py','scripts/*.py','tests/*.py'],cwd=ROOT,text=True).splitlines()
    return tuple(sorted(set(tracked)|set(OWN)|set(DOCS)))

def audit_records(path,split):
    from src.probe import paired_packet_model_v1
    from src.analysis import paired_packet_host_v1
    def denied(*a,**kw):raise RuntimeError('production predictor disabled in independent record audit')
    with patch.object(paired_packet_model_v1,'predict',denied),patch.object(paired_packet_host_v1,'predict',denied):return records.audit(path,split)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','collect','audit','train','audit-training','evaluate','audit-statistics','lock'));p.add_argument('--manifest');p.add_argument('--split',choices=io.SPLITS);args=p.parse_args()
    if args.phase=='prepare':result=io.prepare(sources())
    elif args.phase=='collect':result=collector.collect(args.manifest,args.split)
    elif args.phase=='audit':
        result=audit_records(args.manifest,args.split)
    elif args.phase=='train':result=training.train(args.manifest)
    elif args.phase=='audit-training':result=training.audit_training(args.manifest)
    elif args.phase=='evaluate':result=evaluation.evaluate_split(args.manifest,args.split)
    elif args.phase=='audit-statistics':result=statistics.audit(args.manifest,args.split)
    else:result=evaluation.lock(args.manifest)
    print(result)
