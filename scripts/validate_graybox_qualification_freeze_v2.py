"""Freeze the one-shot unspent qualification entry; no physics or training."""
from pathlib import Path
from time import perf_counter_ns
from contextlib import ExitStack
from unittest.mock import patch
import gzip,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_graybox_qualification_v2 as command
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
a=command.io;io=a.io

def main():
    start=perf_counter_ns();out=a.VALIDATION;out.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'unchanged old tracked sources, empty index')
    io.require(io.read(a.CONFIG)==a.config() and io.read(a.SEEDS)==a.registry(),'exact supplementary design and existing reservation')
    old_path=ROOT/'outputs/graybox_response/result_validation_v1/source_reuse.json';old=io.read(old_path)
    repair_path=ROOT/'outputs/graybox_response/audit_repair_v2/complete.json';repair=io.read(repair_path)
    io.require(old['integrity']==repair['integrity']=='PASSED' and old['unique_tests']==2408 and repair['unique_tests']==2410,'2410 source-bound prior unique checks')
    prior={**old['source_sha256'],**repair['source_sha256']}
    for n,h in prior.items():io.require(io.sha(ROOT/n)==h,'unchanged reused source '+n)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    before={n:io.sha(ROOT/n) for n in command.sources()};io.write(out/'source_before_tests.json',before)
    guard={};ids=[];counts={}
    from src.probe import graybox_observer_v1 as observer,graybox_arx_reference_v1 as arx
    from src.analysis import graybox_observer_independent_v1 as scalar
    def counted(obj,name,label):
        fn=getattr(obj,name)
        def call(*args,**kw):
            counts[label]=counts.get(label,0)+1;io.require(counts[label]<=1000000,'constructed operation cap '+label);return fn(*args,**kw)
        return patch.object(obj,name,call)
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard,max_solve=4),ExitStack() as stack:
        for obj,name,label in ((observer,'advance','main_axis_predict_attempts'),(observer,'observe','main_axis_observe_attempts'),(observer,'moments','main_gaussian_moments'),
            (arx,'features','main_RLS_feature_rows'),(scalar,'predict','independent_axis_predictions'),(scalar,'update','independent_axis_updates'),(scalar,'quad','independent_quadrature_calls')):
            stack.enter_context(counted(obj,name,label))
        suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_graybox_qualification_v2')
        def collect(s):
            for t in s:
                if isinstance(t,unittest.TestSuite):collect(t)
                else:ids.append(t.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'test_receipt.json',dict(tests=result.testsRun,unique_test_ids=ids,success=result.wasSuccessful(),guard=guard,source_sha256=before,
        constructed_forecasts_from_fixed_bank_only=True,constructed_numerical_counts=counts,new_primary_fits=0))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==18 and guard['operation_counts']['solve_attempts']==4,'all18 no-physics entry checks and four independent constructed RLS replay solves')
    contract=a.source_contract();io.write(out/'existing_source_contract.json',contract);scope=a.seed_scope();io.write(out/'ownership_scope.json',scope)
    with (out/'ownership_scope.json').open('rb') as source,(out/'ownership_scope.json.gz').open('xb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as target:
        while True:
            chunk=source.read(1048576)
            if not chunk:break
            target.write(chunk)
    io.require(gzip.decompress((out/'ownership_scope.json.gz').read_bytes())==(out/'ownership_scope.json').read_bytes(),'actual complete census decompression')
    io.write(out/'ownership_scope_index.json',dict(integrity='PASSED',raw_local='ownership_scope.json',raw_bytes=(out/'ownership_scope.json').stat().st_size,
        raw_sha256=io.sha(out/'ownership_scope.json'),committed_gzip_sha256=io.sha(out/'ownership_scope.json.gz'),
        all_owner_sources_retained=True,exact_owner_exceptions=scope['exact_registered_owner_conflict_exceptions']))
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2428,new_unique_tests=18,reused_unique_tests=2410,source_sha256=prior,
        prior_receipt_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in (old_path,repair_path)},old_simulation_tests_repeated=False))
    for n,h in before.items():io.require(io.sha(ROOT/n)==h,'checked source unchanged '+n)
    development=a.BASE/'development_validation_v2';names=(set(command.OWN)|set(command.DOCS)|{p.relative_to(ROOT).as_posix() for p in development.iterdir() if p.is_file()})-{'AGENTS.md'}
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file() and p.name!='ownership_scope.json'}
        p=out/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,regex in EXTRA.items():io.require(regex.search(data.decode('utf8',errors='replace')) is None,'new indexed credential '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged differences');return actual
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check'])
    stage('owned_initial');run('full_tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py'])
    stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_actual_index_secret_scan=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=before,unique_test_total=2428,new_unique_tests=18,reused_unique_tests=2410,
        constructed_guard=guard,constructed_numerical_counts=counts,existing_source_contract_sha256=io.sha(out/'existing_source_contract.json'),ownership_scope_index_sha256=io.sha(out/'ownership_scope_index.json'),
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file() and p.name!='ownership_scope.json'},
        original_failed_pipeline_preserved=True,new_physics=0,new_primary_model_fits=0,new_episode_seed_allocations=0,online_LLM_API_calls=0,
        qualification_started=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),new_unique_checks=18,reused_unique_checks=2410,science='NOT_STARTED'),flush=True)

if __name__=='__main__':main()
