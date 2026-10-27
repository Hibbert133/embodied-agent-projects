"""Freeze the new collector and independent checks before any native sampling."""
from pathlib import Path
from contextlib import ExitStack
from time import perf_counter_ns
from unittest.mock import patch
import subprocess,sys,unittest,gzip,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_graybox_response_v1 as command
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
a=command.io;io=a.io

def freeze():
    start=perf_counter_ns();out=a.VALIDATION;out.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'unchanged tracked sources and empty owned index')
    io.require(io.read(a.CONFIG)==a.config() and io.read(a.SEEDS)==a.registry(),'exact executable configuration and seed registry')
    reuse_path=ROOT/'outputs/graybox_observer/array_implementation_v1/source_reuse.json';reuse=io.read(reuse_path)
    array_path=reuse_path.parent/'complete.json';array=io.read(array_path)
    io.require(reuse['integrity']==array['integrity']=='PASSED' and reuse['unique_tests']==array['unique_test_total']==2376,'2376 source-bound prior unique checks')
    prior={**reuse['source_sha256'],**array['source_sha256']}
    for n,h in prior.items():io.require(io.sha(ROOT/n)==h,'unchanged source-reused checks '+n)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    before={n:io.sha(ROOT/n) for n in command.sources()};io.write(out/'source_before_tests.json',before)
    guard={};counts={};ids=[]
    def counted(obj,name,label):
        fn=getattr(obj,name)
        def call(*args,**kw):
            counts[label]=counts.get(label,0)+1;io.require(counts[label]<=1000000,'constructed numerical operation budget '+label);return fn(*args,**kw)
        return patch.object(obj,name,call)
    from src.probe import graybox_observer_v1 as model
    from src.analysis import graybox_observer_independent_v1 as scalar
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard,max_solve=12,max_lstsq=9),ExitStack() as stack:
        for obj,name,label in ((model,'advance','main_axis_predict_attempts'),(model,'observe','main_axis_observe_attempts'),(model,'moments','main_gaussian_moments'),
            (model,'fit_nominal_grid','constructed_nominal_task_grid_fits'),(scalar,'predict','independent_axis_predictions'),(scalar,'update','independent_axis_updates'),
            (scalar,'quad','independent_quadrature_calls')):stack.enter_context(counted(obj,name,label))
        suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_graybox_response_v1')
        def collect(s):
            for test in s:
                if isinstance(test,unittest.TestSuite):collect(test)
                else:ids.append(test.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'test_receipt.json',dict(tests=result.testsRun,unique_test_ids=ids,success=result.wasSuccessful(),guard=guard,constructed_numerical_counts=counts,source_sha256=before))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==32,'all32 new no-physics contracts')
    io.require(guard['operation_counts']['solve_attempts']==12 and guard['operation_counts']['lstsq_attempts']==9 and counts['constructed_nominal_task_grid_fits']==3,'exact constructed fit accounting')
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2408,new_unique_tests=32,reused_unique_tests=2376,source_sha256=prior,
        prior_receipt_sha256={str(p.relative_to(ROOT)):io.sha(p) for p in (reuse_path,array_path)},old_simulation_tests_repeated=False))
    scope=a.seed_scope();io.write(out/'seed_scope.json',scope)
    # Large census kept byte-exact locally and in a deterministic compressed object.
    with (out/'seed_scope.json').open('rb') as source,(out/'seed_scope.json.gz').open('xb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as dest:
        while True:
            chunk=source.read(1048576)
            if not chunk:break
            dest.write(chunk)
    io.write(out/'seed_scope_index.json',dict(raw_local='seed_scope.json',raw_sha256=io.sha(out/'seed_scope.json'),raw_bytes=(out/'seed_scope.json').stat().st_size,
        committed_gzip='seed_scope.json.gz',compressed_sha256=io.sha(out/'seed_scope.json.gz'),compressed_bytes=(out/'seed_scope.json.gz').stat().st_size,
        integrity='PASSED',exact_self_registration_exclusions=scope['exact_self_registration_exclusions']))
    io.require(gzip.decompress((out/'seed_scope.json.gz').read_bytes())==(out/'seed_scope.json').read_bytes(),'actual census compression restoration')
    for n,h in before.items():io.require(io.sha(ROOT/n)==h,'source unchanged while validating '+n)
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    development=ROOT/'outputs/graybox_observer/collector_development_v1'
    names=(set(command.OWN)|set(command.DOCS)|{p.relative_to(ROOT).as_posix() for p in development.iterdir() if p.is_file()})-{'AGENTS.md'}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file() and p.name!='seed_scope.json'}
        spec=out/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,regex in EXTRA.items():io.require(regex.search(data.decode('utf8',errors='replace')) is None,'actual indexed extra secret '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged differences');return actual
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check'])
    stage('owned_initial');run('full_tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py'])
    stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_actual_index_secret_scan=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=before,seed_scope_index_sha256=io.sha(out/'seed_scope_index.json'),
        unique_test_total=2408,new_unique_tests=32,reused_unique_tests=2376,constructed_numerical_counts=counts,array_guard=guard,
        prefreeze_attempts_separately_retained=True,scientific_collection_started=False,new_physics=0,new_scientific_model_fits=0,online_LLM_API_calls=0,
        scientific_collection_protocol_frozen_after_commit=True,full_task_benefit_established=False,publication_goal_complete=False,
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file() and p.name!='seed_scope.json'},wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',new_unique_checks=32,reused_unique_checks=2376,owned_objects=len(names),science='NOT_STARTED'),flush=True)

if __name__=='__main__':freeze()
