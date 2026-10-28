from pathlib import Path
from time import perf_counter_ns
import base64,hashlib,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_qualification_v1 as q
from src.analysis import occam_resource_process_v1 as p
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();out=q.FREEZE.parent
assert not q.FREEZE.exists() and io.git('rev-parse','HEAD')=='c55d0940384e645dc7aa98f95cc93a19ffa639dd'
source=io.read(out/'source_before_tests.json');prior=io.read(out/'source_reuse.json')['source_sha256'];inputs=io.read(out/'input_sha256.json')
for n,h in {**source,**prior,**inputs}.items():assert io.sha(ROOT/n)==h,n
tests=io.read(out/'tests.json');assert tests['success'] and tests['tests']==33
for name in ('compile.json','main_dependencies.json','training_dependencies.json'):assert io.read(out/name)['returncode']==0
path=p.OUTPUT/'development_v1/attempt01.json';before=path.read_bytes();after=before.replace(b'\r\n',b'\n')
assert before!=after and io.read(path)['real_worker_launches']==0
path.write_bytes(after)
io.write(out/'initial_freeze_failure.json',dict(status='INDEX_DISK_CRLF_MISMATCH_CAUGHT_BEFORE_FREEZE',path=path.relative_to(ROOT).as_posix(),
    original_bytes_base64=base64.b64encode(before).decode('ascii'),original_sha256=hashlib.sha256(before).hexdigest(),
    normalized_sha256=io.sha(path),only_CRLF_to_LF=True,implementation_sources_unchanged=True,tests_not_repeated=True,real_workers_started=0))
shutil.copyfile(Path(__file__),out/Path(__file__).name)
names=set(q.OWN)|{n.relative_to(ROOT).as_posix() for n in (p.OUTPUT/'development_v1').rglob('*') if n.is_file()}
names|={n.relative_to(ROOT).as_posix() for n in (ROOT/'outputs/research_archive/research_log_initial_v1').iterdir() if n.is_file()}
def stage(label):
    global names
    names|={n.relative_to(ROOT).as_posix() for n in out.iterdir() if n.is_file()}
    file=out/(label+'.nul');names.add(file.relative_to(ROOT).as_posix());file.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+file.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    assert all(line.startswith('A\t') for line in io.git('diff','--cached','--name-status').splitlines())
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked_repaired');proof=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_staged_basic_extra_scan=True))
for n,h in {**source,**inputs,**prior}.items():assert io.sha(ROOT/n)==h,n
io.write(out/'complete.json',dict(integrity='PASSED_SOFTWARE_IMPLEMENTATION_ONLY',source_sha256=source,input_sha256=inputs,
    source_reuse_sha256=io.sha(out/'source_reuse.json'),unique_test_total=2619,new_unique_tests=33,reused_unique_tests=2586,guard=tests['guard'],
    new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,real_software_workers=0,
    source_and_seeds_of_closed_scientific_allocation_unchanged=True,science_collection_opened=False,publication_goal_complete=False,
    freeze_completion_after_metadata_newline_repair=True,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED_SOFTWARE_IMPLEMENTATION_ONLY',owned_objects=len(names),new_unique_tests=33,unique_tests=2619),flush=True)
