"""Frozen standard-reference stages. No online LLM and no implicit retry."""
from pathlib import Path
from contextlib import ExitStack,contextmanager
from unittest.mock import patch
import argparse,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import graybox_response_io_v1 as io,graybox_response_collect_v1 as collector,graybox_response_record_audit_v1 as records
from src.analysis import graybox_response_training_v1 as training,graybox_response_evaluation_v1 as evaluation,graybox_response_statistics_audit_v1 as statistics

OWN=(*(f'src/probe/{n}_v1.py' for n in ('graybox_packet_query','graybox_arx_reference','graybox_response_model','graybox_nominal_program')),
    *(f'src/analysis/graybox_response_{n}_v1.py' for n in ('io','host','collect','independent','record_audit','training','training_audit','evaluation','statistics_audit')),
    'scripts/run_graybox_response_v1.py','scripts/run_graybox_response_pipeline_v1.py','scripts/validate_graybox_response_freeze_v1.py','tests/test_graybox_response_v1.py')
DOCS=('AGENTS.md','configs/movement_task/graybox_response_v1.json','docs/protocols/graybox_response_v1_zh.md',
    'docs/protocols/graybox_response_seeds_v1.json','docs/research/graybox_arx_realization_v1_zh.md')

def sources():
    import subprocess
    tracked=subprocess.check_output(['git','ls-files','src/*.py','scripts/*.py','tests/*.py'],cwd=ROOT,text=True).splitlines()
    return tuple(sorted(set(tracked)|set(OWN)|set(DOCS)))

@contextmanager
def production_disabled():
    from src.probe import graybox_response_model_v1 as model,graybox_observer_v1 as observer,graybox_arx_reference_v1 as arx
    from src.analysis import graybox_response_host_v1 as host
    def denied(*args,**kw):raise RuntimeError('production predictor/fitter disabled in independent audit')
    with ExitStack() as stack:
        for module,name in ((model,'predict'),(host,'predict'),(observer,'advance'),(observer,'observe'),(observer,'fit_nominal_grid'),
            (arx,'forecast'),(arx,'fit'),(training,'nominal'),(training,'families'),(training,'fit_data')):
            stack.enter_context(patch.object(module,name,denied))
        yield

def audit_records(path,split):
    with production_disabled():return records.audit(path,split)

def audit_training(path):
    with production_disabled():return training.audit_training(path)

def audit_statistics(path,split):
    # Scoring must read the saved results, without main readers/scoring/selection.
    with production_disabled(),patch.object(evaluation,'scores',side_effect=RuntimeError('main scoring disabled')),\
        patch.object(evaluation,'choose_q',side_effect=RuntimeError('main choice disabled')):
        return statistics.audit(path,split)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','collect','audit','train','audit-training','evaluate','audit-statistics','lock'))
    p.add_argument('--manifest');p.add_argument('--split',choices=io.SPLITS);args=p.parse_args()
    if args.phase=='prepare':result=io.prepare(sources())
    elif args.phase=='collect':result=collector.collect(args.manifest,args.split)
    elif args.phase=='audit':result=audit_records(args.manifest,args.split)
    elif args.phase=='train':result=training.train(args.manifest)
    elif args.phase=='audit-training':result=audit_training(args.manifest)
    elif args.phase=='evaluate':result=evaluation.evaluate_split(args.manifest,args.split)
    elif args.phase=='audit-statistics':result=audit_statistics(args.manifest,args.split)
    else:result=evaluation.lock(args.manifest)
    print(result)
