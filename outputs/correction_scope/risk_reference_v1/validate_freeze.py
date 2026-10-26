"""Scoped freeze checks; old physics tests are reused only with source hashes."""
from pathlib import Path
from time import perf_counter_ns
import io as stdio,subprocess,sys,unittest,shutil
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA

BASE=ROOT/'outputs/correction_scope/risk_reference_v1'
OWNED=('src/analysis/correction_scope_risk_reference_v1.py','src/analysis/correction_scope_risk_reference_independent_v1.py',
    'scripts/run_correction_scope_risk_reference_v1.py','tests/test_correction_scope_risk_reference_v1.py',
    'configs/movement_task/correction_scope_risk_reference_v1.json','docs/protocols/correction_scope_risk_reference_v1_zh.md',
    'docs/research/correction_scope_reference_decision_v1_zh.md','outputs/correction_scope/risk_reference_v1/validate_freeze.py',
    'outputs/correction_scope/risk_reference_v1/run_pipeline.py')

def sources():return {n:io.sha(ROOT/n) for n in OWNED}

def development():
    parent=BASE/'development_checks';parent.mkdir(exist_ok=True)
    i=1
    while (parent/('attempt_'+str(i))).exists():i+=1
    out=parent/('attempt_'+str(i));out.mkdir(exist_ok=False);guard={};started=perf_counter_ns()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_correction_scope_risk_reference_v1.py')
    stream=stdio.StringIO()
    with read_only(guard,max_solve=11,max_lstsq=8):result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    payload=dict(integrity='PASSED' if result.wasSuccessful() else 'FAILED',tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        log=stream.getvalue(),guard=guard,source_sha256=sources(),wall_ns=perf_counter_ns()-started,
        synthetic_numerical_solves_separate=True,new_real_model_fits=0,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0)
    snapshots=out/'source_snapshots';snapshots.mkdir();index={}
    for i,(n,h) in enumerate(payload['source_sha256'].items()):
        name='source_%02d.saved'%i;shutil.copyfile(ROOT/n,snapshots/name);index[name]=dict(original=n,sha256=h)
    io.write(snapshots/'index.json',index)
    io.write(out/'tests.json',payload);print({k:payload[k] for k in ('integrity','tests_run','failures','errors')})
    io.require(result.wasSuccessful(),'retained development test failures')

def freeze():
    out=BASE/'freeze_validation';out.mkdir(exist_ok=False);started=perf_counter_ns()
    latest=max((BASE/'development_checks').glob('attempt_*/tests.json'),key=lambda p:int(p.parent.name.split('_')[1]));dev=io.read(latest)
    io.require(dev['integrity']=='PASSED' and dev['source_sha256']==sources(),'reuse just-passed unchanged arrays, no repeat')
    old=ROOT/'outputs/correction_scope/freeze_validation_v1'
    maps=[io.read(old/n)['source_sha256'] for n in ('complete.json','source_reuse.json')]
    for mapping in maps:
        for n,h in mapping.items():io.require(io.sha(ROOT/n)==h,'source-bound2045 reuse '+n)
    verify_runtime(io.read(old/'runtime_lock.json'))
    io.write(out/'source_reuse.json',dict(integrity='PASSED',old_unique_tests_reused=2045,old_six_tensor_groups_separate=True,
        source_sha256={k:v for mapping in maps for k,v in mapping.items()},old_simulation_tests_repeated=False,
        latest_new_tests_sha256=io.sha(latest),new_unique_array_tests=dev['tests_run'],synthetic_solves=dev['guard']['operation_counts']['solve_attempts']))
    names=set(OWNED)|{p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def command(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,'freeze check '+name)
    io.require(not io.git('diff','--cached','--name-only'),'empty index before new owned freeze')
    names=stage(names,'owned_initial')
    command('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
    command('dependencies.json',[sys.executable,'-m','pip','check'])
    command('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    command('ordinary_diff.json',['git','diff','--check']);command('staged_diff.json',['git','diff','--cached','--check'])
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_scan')
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,p in EXTRA.items():io.require(p.search(data.decode('utf8',errors='replace')) is None,'extra staged credential pattern '+label+' '+n)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,extra_patterns='PASSED'))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=sources(),new_unique_tests=dev['tests_run'],old_unique_tests_reused=2045,
        unique_test_total=2045+dev['tests_run'],scientific_fits_before_freeze=0,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0,
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},wall_ns=perf_counter_ns()-started,publication_goal_complete=False))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final')
    index_bytes(names);io.require(not io.git('diff','--cached','--check'),'final frozen diff')
    print(dict(integrity='PASSED',new_unique_tests=dev['tests_run'],unique_tests=2045+dev['tests_run']))

if __name__=='__main__':{'dev':development,'freeze':freeze}[sys.argv[1]]()
