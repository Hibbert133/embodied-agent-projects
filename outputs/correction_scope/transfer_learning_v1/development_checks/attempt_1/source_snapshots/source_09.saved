"""Synthetic learning checks, source-bound reuse and real-index freeze proof."""
from pathlib import Path
from time import perf_counter_ns
import io as stdio,shutil,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import correction_transfer_learning_v1 as m
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=m.io;BASE=m.BASE


def sources():return {name:io.sha(ROOT/name) for name in m.SOURCES}


def development():
    parent=BASE/'development_checks';parent.mkdir(exist_ok=True);i=1
    while (parent/('attempt_'+str(i))).exists():i+=1
    out=parent/('attempt_'+str(i));out.mkdir(exist_ok=False);guard={};start=perf_counter_ns();stream=stdio.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_correction_transfer_learning_v1.py')
    with read_only(guard):result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    ledger=sys.modules['test_correction_transfer_learning_v1'].SYNTHETIC_LEDGER
    payload=dict(integrity='PASSED' if result.wasSuccessful() else 'FAILED',tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        log=stream.getvalue(),guard=guard,synthetic_neural_ledger=ledger,source_sha256=sources(),wall_ns=perf_counter_ns()-start,
        new_physics=0,new_scientific_model_fits=0,online_LLM_API_calls=0)
    snapshots=out/'source_snapshots';snapshots.mkdir();index={}
    for j,(name,digest) in enumerate(payload['source_sha256'].items()):
        p=snapshots/('source_%02d.saved'%j);shutil.copyfile(ROOT/name,p);index[p.name]=dict(original=name,sha256=digest)
    io.write(snapshots/'index.json',index);io.write(out/'tests.json',payload);print({k:payload[k] for k in ('integrity','tests_run','failures','errors')})
    if not result.wasSuccessful():print(stream.getvalue())
    io.require(result.wasSuccessful(),'retained transfer synthetic test failure')


def freeze():
    out=BASE/'freeze_validation';out.mkdir(exist_ok=False);start=perf_counter_ns()
    latest=max((BASE/'development_checks').glob('attempt_*/tests.json'),key=lambda p:int(p.parent.name.split('_')[1]));dev=io.read(latest)
    io.require(dev['integrity']=='PASSED' and dev['source_sha256']==sources(),'just-passed unchanged synthetic learning checks')
    old=ROOT/'outputs/correction_scope/state_coupled_design_v1/freeze_validation'
    maps=[io.read(old/name)['source_sha256'] for name in ('complete.json','source_reuse.json')]
    io.require(io.read(old/'complete.json')['unique_test_total']==2115,'source-bound prior unique count')
    for mapping in maps:
        for name,digest in mapping.items():io.require(io.sha(ROOT/name)==digest,'unchanged reused2115 source '+name)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    io.write(out/'source_reuse.json',dict(integrity='PASSED',old_unique_tests_reused=2115,old_six_tensor_groups_separate=True,
        source_sha256={k:v for mapping in maps for k,v in mapping.items()},old_simulation_tests_repeated=False,
        latest_new_tests_sha256=io.sha(latest),new_unique_array_tests=dev['tests_run']))
    names=set(m.SOURCES)|{p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()}
        p.write_bytes(b'\0'.join(name.encode() for name in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def command(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,'learning freeze check '+name)
    def verify(selected):
        actual=index_bytes(selected)
        for name in actual:
            data=(ROOT/name).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'extra staged secret '+label+' '+name)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'complete scoped diffs');return actual
    io.require(not io.git('diff','--cached','--name-only'),'empty index before learning freeze');names=stage(names,'owned_initial')
    command('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
    command('dependencies.json',[sys.executable,'-m','pip','check'])
    command('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    command('ordinary_diff.json',['git','diff','--check']);command('staged_diff.json',['git','diff','--cached','--check'])
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_scan');actual=verify(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,extra_patterns='PASSED'))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=sources(),new_unique_tests=dev['tests_run'],old_unique_tests_reused=2115,
        unique_test_total=2115+dev['tests_run'],synthetic_neural_ledger=dev['synthetic_neural_ledger'],new_scientific_model_fits=0,
        new_physics=0,new_policy_queries=0,online_LLM_API_calls=0,TRAIN_only_learning_not_independent_robot_qualification=True,
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');verify(names)
    print(dict(integrity='PASSED',new_unique_tests=dev['tests_run'],unique_tests=2115+dev['tests_run'],new_physics=0))

if __name__=='__main__':{'dev':development,'freeze':freeze}[sys.argv[1]]()
