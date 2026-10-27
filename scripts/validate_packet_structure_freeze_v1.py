"""Source-bound arrays/records plus complete real-index checks before diagnosis."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys,unittest,shutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_packet_structure_v1 as command
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
a=command.source;io=a.io


def freeze():
    start=perf_counter_ns();out=a.VALIDATION;out.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only'),'clean tracked checkout and index')
    io.require(io.read(a.CONFIG)==a.config(),'frozen diagnostic config');old=ROOT/'outputs/paired_packet_response/result_validation_v1/source_reuse.json';reuse=io.read(old);same=io.require
    same(reuse['unique_tests']==2265,'prior unique checks')
    for n,h in reuse['source_sha256'].items():same(io.sha(ROOT/n)==h,'unchanged prior checked source '+n)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'));inputs=a.inputs();before={n:io.sha(ROOT/n) for n in command.SOURCES}
    io.write(out/'source_before_tests.json',before);io.write(out/'source_input_hashes.json',inputs)
    external=Path(r'C:\Users\Administrator\Documents\ChatGPT\robotic agent')
    for p in external.glob('packet_structure_array_checks_attempt*.log'):shutil.copyfile(p,out/p.name)
    suite=unittest.defaultTestLoader.discover('tests',pattern='test_packet_structure_v1.py');ids=[]
    def collect(s):
        for test in s:
            if isinstance(test,unittest.TestSuite):collect(test)
            else:ids.append(test.id())
    collect(suite);guard={}
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard):r=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'test_receipt.json',dict(tests=r.testsRun,unique_test_ids=ids,success=r.wasSuccessful(),guard=guard,source_sha256=before))
    same(r.wasSuccessful() and len(set(ids))==r.testsRun==21,'all21 new pure-array/record checks')
    for n,h in before.items():same(io.sha(ROOT/n)==h,'sources unchanged while tests ran')
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2286,new_unique_tests=21,reused_unique_tests=2265,source_sha256=reuse['source_sha256'],prior_receipt_sha256=io.sha(old),old_simulation_tests_repeated=False))
    names=set(command.OWN)|set(command.DOCS)|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def check(selected):
        result=index_bytes(selected)
        for name in result:
            data=(ROOT/name).read_bytes()
            if b'\0' not in data:
                for label,p in EXTRA.items():same(p.search(data.decode('utf8',errors='replace')) is None,'extra index secret '+label+' '+name)
        same(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged differences');return result
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace');io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));same(p.returncode==0,'freeze '+name)
    names=stage(names,'owned_initial');run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check']);run('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_checked');actual=check(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_index_secret_scan=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=before,source_input_sha256=inputs,unique_test_total=2286,new_unique_tests=21,old_unique_tests_reused=2265,
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},all_new_test_operation_counts=guard['operation_counts'],scientific_analysis_started=False,
        new_physics=0,new_model_fits=0,new_predictions=0,online_LLM_API_calls=0,source_qualification='CLOSED_NEGATIVE_RETAINED',wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');check(names);print(dict(integrity='PASSED',new_checks=21,reused_checks=2265,analysis='NOT_STARTED'),flush=True)


if __name__=='__main__':freeze()
