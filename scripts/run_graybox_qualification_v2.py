"""Explicit dependency binding for unchanged scientific collector and auditors."""
from pathlib import Path
from contextlib import ExitStack,contextmanager
from unittest.mock import patch
import argparse,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import graybox_qualification_io_v2 as io
from scripts import run_graybox_response_v1 as prior
from src.analysis import graybox_response_host_v1 as host,graybox_response_training_v1 as training
_BOUND=False
OWN=('src/analysis/graybox_qualification_io_v2.py','scripts/run_graybox_qualification_v2.py','scripts/run_graybox_qualification_pipeline_v2.py',
    'scripts/validate_graybox_qualification_freeze_v2.py','tests/test_graybox_qualification_v2.py')
DOCS=('AGENTS.md','configs/movement_task/graybox_qualification_v2.json','docs/protocols/graybox_qualification_v2_zh.md','docs/protocols/graybox_qualification_seeds_v2.json')
MODULES=(prior.collector,host,prior.records,training,prior.evaluation,prior.statistics)

def sources():
    import subprocess
    tracked=subprocess.check_output(['git','ls-files','src/*.py','scripts/*.py','tests/*.py'],cwd=ROOT,text=True).splitlines()
    return tuple(sorted(set(tracked)|set(OWN)|set(DOCS)))

@contextmanager
def binding():
    global _BOUND
    io.io.require(not _BOUND and all(m.a is io.prior for m in MODULES),'one explicit nonnested supplement binding')
    _BOUND=True
    try:
        with ExitStack() as stack:
            for module in MODULES:stack.enter_context(patch.object(module,'a',io))
            yield
    finally:_BOUND=False

def collect(path,split):
    io.population(split)
    with binding():return prior.collector.collect(path,split)
def audit_records(path,split):
    io.population(split)
    with binding():return prior.audit_records(path,split)
def evaluate(path,split):
    io.population(split)
    with binding():return prior.evaluation.evaluate_split(path,split)
def audit_statistics(path,split):
    io.population(split)
    with binding():return prior.audit_statistics(path,split)
def lock(path):
    with binding():return prior.evaluation.lock(path)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','collect','audit','evaluate','audit-statistics','lock'))
    p.add_argument('--manifest');p.add_argument('--split',choices=io.SPLITS);args=p.parse_args()
    if args.phase=='prepare':result=io.prepare(sources())
    elif args.phase=='collect':result=collect(args.manifest,args.split)
    elif args.phase=='audit':result=audit_records(args.manifest,args.split)
    elif args.phase=='evaluate':result=evaluate(args.manifest,args.split)
    elif args.phase=='audit-statistics':result=audit_statistics(args.manifest,args.split)
    else:result=lock(args.manifest)
    print(result)
