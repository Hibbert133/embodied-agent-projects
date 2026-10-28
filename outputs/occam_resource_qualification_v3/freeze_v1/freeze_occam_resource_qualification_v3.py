from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import shutil,subprocess,sys,unittest
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_qualification_v3 as q
from src.analysis import occam_resource_process_v3 as p
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();out=q.FREEZE.parent;out.mkdir(parents=True,exist_ok=False)
parent='b0f0e5586140852fd771c31700131af1e619dd3f';assert io.git('rev-parse','HEAD')==parent
assert not io.git('status','--porcelain','--untracked-files=no')
old_folder=ROOT/'outputs/occam_resource_qualification_v2/freeze_v1';old=p.read(old_folder/'complete.json');reuse=p.read(old_folder/'source_reuse.json')
assert old['integrity']=='PASSED_SOFTWARE_IMPLEMENTATION_ONLY' and old['unique_test_total']==2621 and p.sha(old_folder/'source_reuse.json')==old['source_reuse_sha256']
prior={**reuse['source_sha256'],**old['source_sha256']}
for n,h in prior.items():assert p.sha(ROOT/n)==h,n
source={n:p.sha(ROOT/n) for n in q.OWN};p.write(out/'source_before_tests.json',source)
guard={}
with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard),patch('subprocess.Popen',side_effect=AssertionError('real process forbidden in software tests')):
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_resources_v3'))
p.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,regression_reexecutions=35,new_unique_tests=8,real_workers=0,guard=guard))
assert result.wasSuccessful() and result.testsRun==43
def run(name,args):
    t=perf_counter_ns();v=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    p.write(out/name,dict(args=args,returncode=v.returncode,stdout=v.stdout,stderr=v.stderr,wall_ns=perf_counter_ns()-t));assert v.returncode==0,name
run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
run('main_dependencies.json',[sys.executable,'-m','pip','check'])
run('training_dependencies.json',[r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-history-training-cpu22/Scripts/python.exe','-m','pip','check'])
p.write(out/'source_reuse.json',dict(integrity='PASSED',source_sha256=prior,reused_unique_tests=2621,new_unique_tests=8,unique_tests=2629,
    source_receipt=(old_folder/'complete.json').relative_to(ROOT).as_posix(),source_receipt_sha256=p.sha(old_folder/'complete.json'),
    separately_reexecuted_software_contract_tests=35,old_scientific_or_optimizer_checks_repeated=False))
inputs=dict(old['input_sha256']);inputs['.python310/Lib/platform.py']=p.bootstrap.module_sha256()
for name in ('outputs/occam_resource_qualification_v2/freeze_v1/complete.json','outputs/occam_resource_qualification_v2/freeze_v1/source_reuse.json',
    'outputs/occam_resource_qualification_v2/qualification_v1/complete.json','outputs/occam_resource_qualification_v2/qualification_v1/CLOSED_UNEXPECTED_IMPORT_FAILURE.json',
    'outputs/occam_resource_qualification_v2/failure_delivery_v1/complete.json'):
    inputs[name]=p.sha(ROOT/name)
p.write(out/'input_sha256.json',inputs)
archive=ROOT/'outputs/research_archive/resource_stage_log_v1';remote=p.read(archive/'remote_receipt.json');catalog=p.read(archive/'catalog.json')
assert remote['integrity']=='PASSED' and remote['remote_after']=='7e27e365896bbc4b3eda7333476fc8fdc5e2d9fb'
changed=io.git('diff-tree','--no-commit-id','--name-only','-r',parent).splitlines()
rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==19 and all(r['published'] for r in rows)
for name in ('build_resource_stage_log_archive_v1.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,archive/name)
proof=Path(__file__).parent/'occam_core_postcommit_b0f0e5586140.json';assert p.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,archive/'source_committed_bytes.json')
p.write(archive/'phase_selection.json',dict(integrity='PASSED',source_local_commit=parent,published=19,omitted=0,files=rows,remote_archive_commit=remote['remote_after']))
p.write(archive/'complete.json',dict(integrity='PASSED_DOCUMENTATION_PUBLICATION',source_local_commit=parent,remote_archive_commit=remote['remote_after'],
    append_only_log_in_remote=True,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0))
p.write(out/'tracked_secret_scan_chain.json',dict(integrity='PASSED',full_tracked_scan_at='c55d0940384e645dc7aa98f95cc93a19ffa639dd',
    previous_index_proof='outputs/research_archive/occam_resource_software_failure_v2/index_disk_proof.json',previous_proof_sha256=p.sha(ROOT/'outputs/research_archive/occam_resource_software_failure_v2/index_disk_proof.json'),
    all_changed_objects_previously_scanned=True,this_stage_actual_index_basic_extra_scan=True,unchanged_large_objects_not_allocated_again=True))
for name in ('create_occam_resource_qualification_v3.py','freeze_occam_resource_qualification_v3.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name)
names={n for n in q.OWN if n not in prior}|{n.relative_to(ROOT).as_posix() for n in archive.iterdir() if n.is_file()}
def stage(label):
    global names
    names|={n.relative_to(ROOT).as_posix() for n in out.iterdir() if n.is_file()}
    file=out/(label+'.nul');names.add(file.relative_to(ROOT).as_posix());file.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+file.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');proof=check();p.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_index_basic_extra_scan=True))
for n,h in {**source,**inputs,**prior}.items():assert p.sha(ROOT/n)==h,n
p.write(out/'complete.json',dict(integrity='PASSED_SOFTWARE_IMPLEMENTATION_ONLY',source_sha256=source,input_sha256=inputs,
    source_reuse_sha256=p.sha(out/'source_reuse.json'),unique_test_total=2629,new_unique_tests=8,reused_unique_tests=2621,
    actual_test_executions=43,reexecuted_software_contract_tests=35,guard=guard,real_workers=0,new_environment_operations=0,new_fits=0,
    online_LLM_API_calls=0,science_collection_opened=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED_SOFTWARE_IMPLEMENTATION_ONLY',owned_files=len(names),unique_tests=2629,actual_tests=43),flush=True)
