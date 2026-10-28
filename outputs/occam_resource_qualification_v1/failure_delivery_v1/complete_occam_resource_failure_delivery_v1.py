from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_resource_process_v1 as p
from src.analysis import occam_resource_qualification_v1 as q
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();out=p.OUTPUT/'failure_delivery_v1';run=q.RUN
assert not (out/'complete.json').exists()
audit=p.read(out/'audit.json');assert audit['integrity']=='PASSED_FAILURE_CLOSURE_ONLY_NOT_SOFTWARE_QUALIFICATION'
for n,h in audit['original_artifact_sha256'].items():assert p.sha(ROOT/n)==h,n
for n,h in p.read(q.FREEZE)['source_sha256'].items():assert p.sha(ROOT/n)==h,n
failures={}
for j in (3,7):
    name='outputs/occam_resource_qualification_v1/qualification_v1/job%02d/stderr.log'%j
    index=__import__('subprocess').check_output(['git','show',':'+name],cwd=ROOT);original=(ROOT/name).read_bytes()
    assert index==original.replace(b'\r\n',b'\n') and index!=original
    failures[name]=dict(original_disk_sha256=p.sha(ROOT/name),normalized_index_sha256=__import__('hashlib').sha256(index).hexdigest())
p.write(out/'delivery_index_failure.json',dict(status='CAUGHT_AUTOMATIC_TEXT_NORMALIZATION_BEFORE_COMMIT',files=failures,
    fix='scoped -text attributes; original stderr bytes never altered',new_workers_started=0))
shutil.copyfile(Path(__file__),out/Path(__file__).name)
names={n.relative_to(ROOT).as_posix() for n in run.rglob('*') if n.is_file()}|{'reports/occam_resource_qualification_v1_zh.md','.gitattributes'}
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
stage('owned_checked_repaired');proof=check();p.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_staged_basic_extra_scan=True))
p.write(out/'complete.json',dict(integrity='PASSED_FAILURE_DELIVERY_NOT_QUALIFICATION',launched=7,expected_prefix=6,unexpected=1,not_started=1,
    source_sha256=p.read(q.FREEZE)['source_sha256'],original_qualification_artifacts_sha256=audit['original_artifact_sha256'],
    new_environment_operations=0,new_fits=0,online_LLM_API_calls=0,science_collection_opened=False,publication_goal_complete=False,
    original_stderr_preserved_in_git_without_text_conversion=True,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED_FAILURE_DELIVERY_NOT_QUALIFICATION',owned_files=len(names),launched=7,not_started=1),flush=True)
