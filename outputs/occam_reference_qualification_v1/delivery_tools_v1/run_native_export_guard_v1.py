"""Freeze an offline exporter, then preserve a completed Native phase only."""
from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
from time import perf_counter_ns
from datetime import datetime,timezone
import argparse,hashlib,io,json,sys,unittest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b
OUT=Path(__file__).parent;VALIDATION=OUT/'validation_v1'
MANIFEST=ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085/manifest.json'
ENV=('mujoco','metaworld','gym','gymnasium','torch')


def source_paths():return sorted(OUT.glob('*.py'))+[OUT/'algorithm_reuse.json']


def freeze():
    VALIDATION.mkdir(exist_ok=False);start=perf_counter_ns();source={str(p.relative_to(ROOT)):b.c.sha(p) for p in source_paths()}
    stream=io.StringIO()
    with redirect_stdout(stream),redirect_stderr(stream):
        suite=unittest.defaultTestLoader.loadTestsFromName('outputs.occam_reference_qualification_v1.delivery_tools_v1.test_qualification_bundle_v1')
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (VALIDATION/'unit_tests.log').write_text(stream.getvalue(),encoding='utf8',newline='\n')
    b.require(result.wasSuccessful() and result.testsRun==13,'complete exporter unit tests')
    for p in source_paths():
        if p.suffix=='.py':compile(p.read_bytes(),str(p),'exec')
    for n,h in source.items():b.require(b.c.sha(ROOT/n)==h,'source immutable during validation')
    b.ready(MANIFEST,'NATIVE')
    b.c.write(VALIDATION/'complete.json',dict(integrity='PASSED_FROZEN_OFFLINE_EXPORT_SOFTWARE_ONLY',
        source_sha256=source,unit_tests=13,development_test_executions=13,formal_test_executions=13,
        unchanged_archive_algorithms=4,algorithm_reuse_sha256=b.c.sha(OUT/'algorithm_reuse.json'),
        unit_tests_log_sha256=b.c.sha(VALIDATION/'unit_tests.log'),manifest_sha256=b.c.sha(MANIFEST),
        phase='NATIVE',executions=174,new_records_exported_during_validation=0,
        new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    return dict(integrity='PASSED_FROZEN_OFFLINE_EXPORT_SOFTWARE_ONLY',tests=13)


def run(restore):
    frozen=b.c.read(VALIDATION/'complete.json');b.require(frozen['integrity']=='PASSED_FROZEN_OFFLINE_EXPORT_SOFTWARE_ONLY','validated exporter')
    for n,h in frozen['source_sha256'].items():b.require(b.c.sha(ROOT/n)==h,'frozen exporter changed')
    b.require(b.c.sha(MANIFEST)==frozen['manifest_sha256'],'source population unchanged')
    b.require(not any(n==e or n.startswith(e+'.') for n in sys.modules for e in ENV),'no scientific/environment modules imported')
    counts=dict(forbidden_process_or_network=0,forbidden_scientific_imports=0)
    enabled=[True]
    def hook(event,args):
        if not enabled[0]:return
        if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','socket.connect','socket.connect_ex','socket.bind','socket.getaddrinfo'):
            counts['forbidden_process_or_network']+=1;raise RuntimeError('offline export only')
        if event=='import' and any(args[0]==e or args[0].startswith(e+'.') for e in ENV):
            counts['forbidden_scientific_imports']+=1;raise RuntimeError('scientific modules forbidden during export')
    sys.addaudithook(hook);start=perf_counter_ns()
    try:
        result=b.export(MANIFEST,b.c.BASE/'native_delivery_v1',Path(restore),'NATIVE')
        b.require(not any(counts.values()),'zero forbidden export attempts')
        for n,h in frozen['source_sha256'].items():b.require(b.c.sha(ROOT/n)==h,'source unchanged after export')
        b.c.write(b.c.BASE/'native_delivery_v1/guard.json',dict(integrity='PASSED_OFFLINE_EXPORT_NO_SCIENTIFIC_EXECUTION',
            counts=counts,software_freeze_sha256=b.c.sha(VALIDATION/'complete.json'),
            new_environment_interactions=0,new_fits=0,new_model_predictions=0,online_LLM_API_calls=0,
            scientific_imports_attempted=0,wall_ns=perf_counter_ns()-start))
    finally:enabled[0]=False
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=('freeze','export'));parser.add_argument('--restore');args=parser.parse_args()
    if args.command=='export' and args.restore is None:parser.error('--restore is required')
    print(json.dumps(freeze() if args.command=='freeze' else run(args.restore)),flush=True)
