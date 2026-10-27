"""Pure-array regression checks, source-bound reuse and exact-index proof."""
from pathlib import Path
from time import perf_counter_ns
import io as stdio,shutil,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts import run_correction_effect_horizon_v1 as command
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=command.main;BASE=main.BASE;io=main.io
def sources():return {n:io.sha(ROOT/n) for n in command.SOURCES}
def development():
    parent=BASE/'development_checks';parent.mkdir(exist_ok=True);i=1
    while (parent/('attempt_'+str(i))).exists():i+=1
    out=parent/('attempt_'+str(i));out.mkdir();guard={};start=perf_counter_ns();stream=stdio.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_correction_effect_horizon_v1.py')
    with read_only(guard,max_solve=0,max_lstsq=0):result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    io.write(out/'tests.json',dict(integrity='PASSED' if result.wasSuccessful() else 'FAILED',tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        log=stream.getvalue(),guard=guard,source_sha256=sources(),wall_ns=perf_counter_ns()-start,new_physics=0,new_fits=0,online_LLM_API_calls=0))
    snapshots=out/'source_snapshots';snapshots.mkdir();index={}
    for j,n in enumerate(command.OWN):
        target=snapshots/('source_%02d.saved'%j);shutil.copyfile(ROOT/n,target);index[target.name]=dict(original=n,sha256=io.sha(target))
    io.write(snapshots/'index.json',index)
    print(dict(integrity='PASSED' if result.wasSuccessful() else 'FAILED',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors)),flush=True)
    if not result.wasSuccessful():print(stream.getvalue())
    io.require(result.wasSuccessful(),'retained horizon regression failure')
def freeze():
    out=BASE/'freeze_validation';out.mkdir(exist_ok=False);start=perf_counter_ns()
    latest=max((BASE/'development_checks').glob('attempt_*/tests.json'),key=lambda p:int(p.parent.name.split('_')[1]));dev=io.read(latest)
    io.require(dev['integrity']=='PASSED' and dev['source_sha256']==sources(),'unchanged just-passed horizon source')
    previous=ROOT/'outputs/correction_scope/effect_learning_v1/result_validation/source_reuse.json';reuse=io.read(previous)
    io.require(reuse['unique_tests']==2216,'source-bound prior2216')
    for n,h in reuse['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged reused source '+n)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    io.write(out/'source_reuse.json',dict(integrity='PASSED',prior_unique_tests=2216,prior_source_reuse_sha256=io.sha(previous),source_sha256=reuse['source_sha256'],
        old_simulation_tests_repeated=False,old_six_tensor_groups_separate=True))
    io.require(not io.git('diff','--cached','--name-only'),'empty index before horizon freeze')
    names=set(command.SOURCES)|{p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,'horizon freeze '+name)
    def verify(selected):
        actual=index_bytes(selected)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'extra staged secret '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'horizon diff checks');return actual
    names=stage(names,'owned_initial')
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check'])
    run('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_scan');actual=verify(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,extra_secret_patterns='PASSED'))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=sources(),new_unique_tests=dev['tests_run'],old_unique_tests_reused=2216,
        unique_test_total=2216+dev['tests_run'],receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},wall_ns=perf_counter_ns()-start,
        new_physics=0,new_fits=0,online_LLM_API_calls=0,post_hoc_only=True,original_native_qualification='FAILED_RETAINED',publication_goal_complete=False))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');verify(names)
    print(dict(integrity='PASSED',unique_tests=2216+dev['tests_run'],new_physics=0),flush=True)
if __name__=='__main__':{'dev':development,'freeze':freeze}[sys.argv[1]]()
