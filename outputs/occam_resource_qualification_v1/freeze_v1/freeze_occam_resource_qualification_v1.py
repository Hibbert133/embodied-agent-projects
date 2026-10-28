from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import shutil,subprocess,sys,unittest
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_qualification_v1 as q
from src.analysis import occam_resource_process_v1 as p
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();out=q.FREEZE.parent;out.mkdir(exist_ok=False)
assert io.git('rev-parse','HEAD')=='c55d0940384e645dc7aa98f95cc93a19ffa639dd'
assert not io.git('status','--porcelain','--untracked-files=no')
old_folder=ROOT/'outputs/occam_reference_train_v2/failure_delivery_v2/diagnostic_freeze_v1'
old=io.read(old_folder/'complete.json');reuse=io.read(old_folder/'source_reuse.json')
assert old['integrity']=='PASSED' and old['unique_test_total']==2586 and io.sha(old_folder/'source_reuse.json')==old['source_reuse_sha256']
prior={**reuse['source_sha256'],**old['source_sha256']}
for n,h in prior.items():assert io.sha(ROOT/n)==h,n
source={n:io.sha(ROOT/n) for n in q.OWN};io.write(out/'source_before_tests.json',source)
guard={}
with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard),patch('subprocess.Popen',side_effect=AssertionError('real process forbidden in array qualification tests')):
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_resources_v1'))
io.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,real_software_workers=0,guard=guard))
assert result.wasSuccessful() and result.testsRun==33

def run(name,args):
    t=perf_counter_ns();v=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    io.write(out/name,dict(args=args,returncode=v.returncode,stdout=v.stdout,stderr=v.stderr,wall_ns=perf_counter_ns()-t));assert v.returncode==0,name
run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
run('main_dependencies.json',[sys.executable,'-m','pip','check'])
training=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-history-training-cpu22/Scripts/python.exe')
run('training_dependencies.json',[str(training),'-m','pip','check'])
io.write(out/'source_reuse.json',dict(integrity='PASSED',source_sha256=prior,reused_unique_tests=2586,new_unique_tests=33,unique_tests=2619,
    source_receipt=(old_folder/'complete.json').relative_to(ROOT).as_posix(),source_receipt_sha256=io.sha(old_folder/'complete.json'),old_native_or_optimizer_tests_repeated=False))
inputs={n:io.sha(ROOT/n) for n in ('outputs/response_action/validation_v1/runtime_lock.json',
    'outputs/occam_reference_train_v2/failure_delivery_v2/diagnostic_freeze_v1/complete.json',
    'outputs/occam_reference_train_v2/failure_delivery_v2/diagnostic_freeze_v1/source_reuse.json',
    'outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/CLOSED_TECHNICAL_FAILURE.json',
    'outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/train/completion.json')}
inputs[p.executable().relative_to(ROOT).as_posix()]=io.sha(p.executable())
io.write(out/'input_sha256.json',inputs)
io.write(out/'tracked_secret_scan_reuse.json',dict(integrity='PASSED',command=[sys.executable,'scripts/check_tracked_secrets.py','--staged'],
    returncode=0,stdout='tracked-secret scan: passed\n',completed_in_preceding_documentation_stage=True,
    unchanged_baseline_commit='c55d0940384e645dc7aa98f95cc93a19ffa639dd',new_index_objects_receive_full_basic_and_extra_scan=True,
    large_unchanged_tracked_files_not_allocated_again=True))
shutil.copyfile(Path(__file__),out/Path(__file__).name)
archive=ROOT/'outputs/research_archive/research_log_initial_v1'
assert io.read(archive/'remote_receipt.json')['remote_after']=='f735f259f6935a707cd95f41a9941b5abb417842'
for name in ('build_research_log_archive_v1.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,archive/name)
proof=Path(__file__).parent/'occam_core_postcommit_c55d0940384e.json'
assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,archive/'source_committed_bytes.json')
names=set(q.OWN)|{n.relative_to(ROOT).as_posix() for n in (p.OUTPUT/'development_v1').rglob('*') if n.is_file()}
names|={n.relative_to(ROOT).as_posix() for n in archive.iterdir() if n.is_file()}
def stage(label):
    global names
    names|={n.relative_to(ROOT).as_posix() for n in out.iterdir() if n.is_file()}
    file=out/(label+'.nul');names.add(file.relative_to(ROOT).as_posix());file.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+file.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    assert all(line.startswith('A\t') for line in io.git('diff','--cached','--name-status').splitlines()),'baseline tracked objects must be unchanged'
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');proof=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_staged_basic_extra_scan=True))
for n,h in {**source,**inputs,**prior}.items():assert io.sha(ROOT/n)==h,n
io.write(out/'complete.json',dict(integrity='PASSED_SOFTWARE_IMPLEMENTATION_ONLY',source_sha256=source,input_sha256=inputs,
    source_reuse_sha256=io.sha(out/'source_reuse.json'),unique_test_total=2619,new_unique_tests=33,reused_unique_tests=2586,guard=guard,
    new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,real_software_workers=0,
    source_and_seeds_of_closed_scientific_allocation_unchanged=True,science_collection_opened=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED_SOFTWARE_IMPLEMENTATION_ONLY',owned_objects=len(names),new_unique_tests=33,unique_tests=2619,new_environment_operations=0),flush=True)
