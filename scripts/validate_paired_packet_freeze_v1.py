"""Tests and real index bytes must pass before the independent native allocation."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys,unittest,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_paired_packet_response_v1 as command
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
a=command.io;io=a.io


def freeze():
    out=a.VALIDATION;out.mkdir(parents=True,exist_ok=False);start=perf_counter_ns()
    io.require(io.read(a.CONFIG)==a.config() and io.read(a.SEEDS)==a.registry(),'executable registered plan')
    io.require(not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only'),'clean tracked work and index')
    old=ROOT/'outputs/correction_scope/selective_coverage_v1/result_validation/source_reuse.json';reuse=io.read(old)
    io.require(reuse['unique_tests']==2228,'old checked test population')
    for n,h in reuse['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged source-reused '+n)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    scope=a.seed_scope();io.write(out/'seed_scope.json',scope);sources=command.sources();before={n:io.sha(ROOT/n) for n in sources};io.write(out/'source_before_tests.json',before)
    external=Path(r'C:\Users\Administrator\Documents\ChatGPT\robotic agent')
    for p in sorted(external.glob('paired_packet_tests_attempt*.log*')):shutil.copyfile(p,out/p.name)
    guard={};suite=unittest.defaultTestLoader.discover('tests',pattern='test_paired_packet_response_v1.py');names=[]
    def enumerate_tests(s):
        for test in s:
            if isinstance(test,unittest.TestSuite):enumerate_tests(test)
            else:names.append(test.id())
    enumerate_tests(suite)
    with (out/'tests.log').open('x',encoding='utf8') as log,read_only(guard,max_solve=3,max_lstsq=1):result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'test_receipt.json',dict(tests_run=result.testsRun,unique_test_ids=names,success=result.wasSuccessful(),guard=guard,earlier_prefreeze_attempts_retained=True))
    io.require(result.wasSuccessful() and result.testsRun==len(set(names))==37,'new meaningful pure-array/mock-record tests')
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2228+len(names),new_unique_tests=len(names),reused_unique_tests=2228,
        source_sha256=reuse['source_sha256'],prior_receipt_sha256=io.sha(old),old_simulation_tests_repeated=False,old_six_tensor_groups_separate=True))
    for n,h in before.items():io.require(io.sha(ROOT/n)==h,'source changed during tests '+n)
    names=set(command.OWN)|set(command.DOCS)|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}|{p.relative_to(ROOT).as_posix() for p in (a.BASE/'freeze_validation_v1').iterdir() if p.is_file()}
    names.add((a.BASE/'precollection_review.json').relative_to(ROOT).as_posix())
    normalized=[]
    for p in out.iterdir():
        if p.is_file() and p.suffix in ('.log','.json'):
            data=p.read_bytes()
            if b'\r\n' in data:
                original=external/('paired_packet_freeze_v2_original_'+p.name)
                original.write_bytes(data);p.write_bytes(data.replace(b'\r\n',b'\n'));normalized.append(dict(name=p.name,original_external_path=str(original),original_sha256=io.sha(original),LF_sha256=io.sha(p)))
    io.write(out/'newline_receipt.json',dict(operation='CRLF_TO_LF_BEFORE_GIT_BYTE_PROOF',original_files_retained=True,files=normalized));names.add((out/'newline_receipt.json').relative_to(ROOT).as_posix())
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def check(selected):
        actual=index_bytes(selected)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'extra secret pattern '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary/staged whitespace checks');return actual
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,'freeze check '+name)
    names=stage(names,'owned_initial');run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check'])
    run('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_scanned');actual=check(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,extra_secret_patterns='PASSED'))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=before,unique_test_total=2265,new_unique_tests=37,old_unique_tests_reused=2228,
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},new_native_environment_steps=0,scientific_model_fits=0,online_LLM_API_calls=0,
        prefreeze_final_test_synthetic_solves=guard['operation_counts'],publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');check(names)
    print(dict(integrity='PASSED',new_unique_tests=37,source_reused_tests=2228,collection='NOT_STARTED'),flush=True)

if __name__=='__main__':freeze()
