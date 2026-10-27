"""Bounded pure-array checks, source reuse, complete frozen ownership and index QA."""
from pathlib import Path
from time import perf_counter_ns
import gzip,subprocess,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_window_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=a.io;ROOT=a.ROOT
OWN=('src/probe/occam_window_cost_v1.py','src/probe/occam_window_program_v1.py',
    'src/analysis/occam_window_io_v1.py','src/analysis/occam_window_host_v1.py','src/analysis/occam_window_collect_v1.py',
    'src/analysis/occam_window_audit_v1.py','scripts/run_occam_window_host_v1.py','scripts/validate_occam_window_host_v1.py',
    'tests/test_occam_window_host_v1.py','docs/protocols/occam_window_host_v1_zh.md',
    'docs/research/occam_window_decision_v1_zh.md','configs/movement_task/occam_window_host_v1.json','docs/protocols/occam_window_host_seeds_v1.json')


def main():
    start=perf_counter_ns();out=a.VALIDATION;out.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'old sources unchanged, empty index')
    io.require(io.read(a.CONFIG)==a.config() and io.read(a.SEEDS)==a.registry(),'exact native config')
    previous=ROOT/'outputs/occam_performance_core/software_validation_v1';q=io.read(previous/'complete.json');reuse=io.read(previous/'source_reuse.json')
    io.require(q['integrity']==reuse['integrity']=='PASSED' and q['unique_test_total']==2487,'source-bound prior tests')
    prior={**reuse['source_sha256'],**q['source_sha256']}
    for n,h in prior.items():io.require(io.sha(ROOT/n)==h,'old checked source changed '+n)
    source={n:io.sha(ROOT/n) for n in OWN};io.write(out/'source_before_tests.json',source)
    snapshot=out/'tested_sources';snapshot.mkdir()
    for n in OWN:
        target=snapshot/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    guard={};ids=[]
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard,max_solve=2000):
        suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_window_host_v1')
        def collect(s):
            for t in s:
                if isinstance(t,unittest.TestSuite):collect(t)
                else:ids.append(t.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,ids=ids,guard=guard))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==27,'27 unique pure checks')
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    io.write(out/'source_reuse.json',dict(integrity='PASSED',reused_unique_tests=2487,new_unique_tests=27,unique_tests=2514,
        source_sha256=prior,prior_receipt_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in (previous/'complete.json',previous/'source_reuse.json')},old_physics_tests_repeated=False))
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.RUNTIME));io.write(out/'runtime_lock_source.json',dict(path=a.RUNTIME.relative_to(ROOT).as_posix(),sha256=io.sha(a.RUNTIME),integrity='PASSED'))
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check'])
    names=set(OWN)|{p.relative_to(ROOT).as_posix() for p in (a.BASE/'development_validation_v1').rglob('*') if p.is_file()}
    names|={p.relative_to(ROOT).as_posix() for p in a.QUERY.iterdir() if p.is_file()}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
        path=out/(label+'.nul');names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.gz'):data=gzip.decompress(data)
            if b'\0' in data:continue
            text=data.decode('utf8',errors='replace');io.require(find_secret_rule(text) is None,'staged basic secret '+n)
            for label,p in EXTRA.items():io.require(p.search(text) is None,'staged extra secret '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged diff');return actual
    stage('owned_initial');run('full_tracked_secrets.json',[sys.executable,'scripts/check_tracked_secrets.py'])
    run('staged_secrets.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_scan=True,object_sha256=actual))
    for n,h in source.items():io.require(io.sha(ROOT/n)==h,'tested source changed '+n)
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=source,unique_test_total=2514,new_unique_tests=27,reused_unique_tests=2487,
        guard=guard,development_tests=27,formal_tests=27,actual_test_executions=54,development01_guard_not_instrumented_disclosed=True,
        new_robot_interactions=0,scientific_model_training=0,online_LLM_API_calls=0,synthetic_Adam_steps=0,
        native_population_not_executed_yet=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',new_unique_tests=27,unique_test_total=2514,objects=len(names)),flush=True)


if __name__=='__main__':main()
