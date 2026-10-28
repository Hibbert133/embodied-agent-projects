from pathlib import Path
from time import perf_counter_ns
import gzip,subprocess,sys,unittest
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_training_failure_v2 as d
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=d.io;start=perf_counter_ns();out=d.FREEZE;out.mkdir(exist_ok=False)
assert not io.git('status','--porcelain','--untracked-files=no')
old=io.read(d.extension.VALIDATION/'complete.json');reuse=io.read(d.extension.VALIDATION/'source_reuse.json')
assert old['integrity']=='PASSED' and old['unique_test_total']==2578
prior={**reuse['source_sha256'],**old['source_sha256']}
for n,h in prior.items():assert io.sha(ROOT/n)==h,n
source={n:io.sha(ROOT/n) for n in d.OWN};io.write(out/'source_before_tests.json',source)
input_paths=[d.extension.TARGET,d.extension.TARGET.parent/'CLOSED_TECHNICAL_FAILURE.json',d.BASE/'resource_observation.json',d.BASE/'resource_event_2004.raw_local_only.xml']
for folder in (d.extension.TARGET.parent/'train',d.extension.TARGET.parent/'native',d.a.BASE/'pipeline_reader_v3'):
    input_paths.extend(p for p in folder.rglob('*') if p.is_file())
inputs={p.relative_to(ROOT).as_posix():io.sha(p) for p in input_paths};io.write(out/'input_sha256.json',inputs)
guard={}
with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard):
    r=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_training_failure_v2'))
io.write(out/'tests.json',dict(success=r.wasSuccessful(),tests=r.testsRun,guard=guard));assert r.wasSuccessful() and r.testsRun==8
def run(name,args):
    t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));assert p.returncode==0,name
run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
run('main_dependencies.json',[sys.executable,'-m','pip','check']);run('training_dependencies.json',[str(d.a.TRAIN_PYTHON),'-m','pip','check']);d.a.verify_training_runtime()
io.write(out/'source_reuse.json',dict(integrity='PASSED',reused_unique_tests=2578,new_unique_tests=8,unique_tests=2586,source_sha256=prior,old_physics_or_optimizer_checks_repeated=False))
(out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
names=set(d.OWN)|{p.relative_to(ROOT).as_posix() for folder in (d.BASE/'development_validation_v1',d.BASE/'array_stream_fixtures_v1') for p in folder.rglob('*') if p.is_file()}
names|={(d.BASE/'resource_observation.json').relative_to(ROOT).as_posix(),(d.extension.TARGET.parent/'CLOSED_TECHNICAL_FAILURE.json').relative_to(ROOT).as_posix()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
    path=out/(label+'.nul');names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if n.endswith('.gz'):data=gzip.decompress(data)
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_initial');run('tracked_secret_script.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
stage('owned_checked');proof=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_index_basic_extra_decoded_scan=True))
for n,h in {**source,**inputs,**prior}.items():assert io.sha(ROOT/n)==h,n
io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=source,input_sha256=inputs,source_reuse_sha256=io.sha(out/'source_reuse.json'),
    unique_test_total=2586,new_unique_tests=8,reused_unique_tests=2578,guard=guard,policy_queries=0,new_physics=0,new_fits=0,
    online_LLM_API_calls=0,no_complete_TRAIN_or_model_qualification=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),new_unique_tests=8,new_physics=0),flush=True)
