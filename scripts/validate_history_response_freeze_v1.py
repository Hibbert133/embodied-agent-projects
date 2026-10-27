"""Source-bound array/record contracts and real-index checks before sampling."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_history_response_v1 as command
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
a=command.io;io=a.io


def freeze():
    import numpy as np
    start=perf_counter_ns();out=a.VALIDATION;out.mkdir(parents=True,exist_ok=False)
    io.require(set(io.git('diff','--name-only').splitlines())<={'AGENTS.md'} and not io.git('diff','--cached','--name-only'),'only owned current overlay changed, empty index')
    io.require(io.read(a.CONFIG)==a.config() and io.read(a.SEEDS)==a.registry(),'exact executable config and seed register')
    prior_path=ROOT/'outputs/paired_packet_structure/validation_v1/complete.json';prior=io.read(prior_path)
    io.require(prior['integrity']=='PASSED' and prior['unique_test_total']==2286,'previous source-bound unique checks')
    for n,h in prior['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged reused science source '+n)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    before={n:io.sha(ROOT/n) for n in command.sources()};io.write(out/'source_before_tests.json',before)
    scope=a.seed_scope();io.write(out/'seed_scope.json',scope)
    io.write(out/'prefreeze_array_attempts.json',dict(attempts=[
        dict(attempt=1,tests=29,success=True,reported_unittest_seconds=2.278,full_terminal_log_saved=False,source_sha256_not_captured=True),
        dict(attempt=2,tests=30,success=True,reported_unittest_seconds=4.641,full_terminal_log_saved=False,source_sha256_not_captured=True)],
        accounting_per_attempt=dict(constructed_main_solves=50,constructed_augmented_lstsq=42,constructed_eigendecompositions=6),
        numerical_counts_basis='DETERMINISTIC_FIXTURE_FIT_LEDGER_AND_SOURCE_CONTROL_FLOW_NOT_OUTER_GUARD_MEASUREMENT',
        no_scientific_population_started=True,new_environment_interactions=0,online_LLM_API_calls=0))
    suite=unittest.defaultTestLoader.discover('tests',pattern='test_history_response_v1.py');ids=[]
    def collect(s):
        for test in s:
            if isinstance(test,unittest.TestSuite):collect(test)
            else:ids.append(test.id())
    collect(suite);guard={};eigen_count=0;original_eigh=np.linalg.eigh
    def counted_eigh(*args,**kw):
        nonlocal eigen_count
        eigen_count+=1;io.require(eigen_count<=6,'constructed eigen budget');return original_eigh(*args,**kw)
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard,max_solve=50,max_lstsq=42),patch.object(np.linalg,'eigh',counted_eigh):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'test_receipt.json',dict(tests=result.testsRun,unique_test_ids=ids,success=result.wasSuccessful(),guard=guard,constructed_eigendecompositions=eigen_count,
        deterministic_allocation_array_checks=dict(noise_tapes=3,noise_scalars=4500,known_packet_plans=3,physical_samples=0),source_sha256=before))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==32,'all32 new array/saved-record checks')
    io.require(guard['operation_counts']['solve_attempts']==50 and guard['operation_counts']['lstsq_attempts']==42 and eigen_count==6,'exact constructed numerical costs')
    for n,h in before.items():io.require(io.sha(ROOT/n)==h,'source unchanged while checking '+n)
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2318,new_unique_tests=32,reused_unique_tests=2286,
        source_sha256=prior['source_sha256'],prior_receipt_sha256=io.sha(prior_path),old_simulation_tests_repeated=False))
    names=set(command.OWN)|set(command.DOCS)|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def check(selected):
        actual=index_bytes(selected)
        for name in actual:
            data=(ROOT/name).read_bytes()
            if b'\0' not in data:
                for label,regex in EXTRA.items():io.require(regex.search(data.decode('utf8',errors='replace')) is None,'extra index secret '+label+' '+name)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged differences');return actual
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    names=stage(names,'owned_initial');run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
    run('dependencies.json',[sys.executable,'-m','pip','check']);run('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_checked');actual=check(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_index_secret_scan=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=before,seed_scope_sha256=io.sha(out/'seed_scope.json'),
        unique_test_total=2318,new_unique_tests=32,reused_unique_tests=2286,receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
        constructed_array_guard=guard,constructed_eigendecompositions=eigen_count,scientific_collection_started=False,new_scientific_model_fits=0,
        new_physics=0,online_LLM_API_calls=0,previous_FIR_qualification='CLOSED_NEGATIVE_RETAINED',publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');check(names)
    print(dict(integrity='PASSED',new_checks=32,reused_checks=2286,science='NOT_STARTED',owned_objects=len(names)),flush=True)


if __name__=='__main__':freeze()
