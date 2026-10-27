"""Versioned one-shot collector/qualification entry point; zero online LLM."""
from pathlib import Path
import argparse,sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import history_response_io_v1 as io,history_response_collect_v1 as collector,history_response_record_audit_v1 as records
from src.analysis import history_response_training_v1 as training,history_response_evaluation_v1 as evaluation,history_response_statistics_audit_v1 as statistics

OWN=('src/probe/history_response_model_v1.py',*(f'src/analysis/history_response_{name}_v1.py' for name in
    ('io','host','collect','record_audit','training','independent_math','evaluation','statistics_audit')),
    'scripts/run_history_response_v1.py','scripts/run_history_response_pipeline_v1.py','scripts/validate_history_response_freeze_v1.py',
    'tests/test_history_response_v1.py')
DOCS=('AGENTS.md','configs/movement_task/history_response_v1.json','docs/protocols/history_response_v1_zh.md','docs/protocols/history_response_seeds_v1.json','docs/research/history_response_decision_v1_zh.md')
def sources():
    import subprocess
    tracked=subprocess.check_output(['git','ls-files','src/*.py','scripts/*.py','tests/*.py'],cwd=ROOT,text=True).splitlines()
    return tuple(sorted(set(tracked)|set(OWN)|set(DOCS)))

def audit_records(path,split):
    from src.probe import history_response_model_v1
    from src.analysis import history_response_host_v1
    def denied(*a,**kw):raise RuntimeError('production predictor disabled in independent record audit')
    with patch.object(history_response_model_v1,'predict',denied),patch.object(history_response_host_v1,'predict',denied):return records.audit(path,split)

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
