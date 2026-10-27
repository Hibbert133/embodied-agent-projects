from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
started=perf_counter_ns();out=ROOT/'outputs/research_archive/occam_reference_training_failure_v1';remote=io.read(out/'remote_receipt.json');local=io.read(out/'local_receipt.json');source=local['source_local_commit']
assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit'] and io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
for name in ('build_occam_reference_training_failure_archive_v1.py','finalize_occam_reference_training_failure_archive_v1.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name);compile((out/name).read_bytes(),name,'exec')
proof=Path(__file__).parent/('occam_core_postcommit_'+source[:12]+'.json');assert io.read(proof)['integrity']=='PASSED' and io.read(proof)['commit']==source;shutil.copyfile(proof,out/'failure_committed_bytes.json')
catalog=io.read(out/'catalog.json');changed=io.git('diff','--name-only','f77e36ba63d1335d2256482f9039fb7096efe1d0',source).splitlines();rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==35 and all(r['published'] for r in rows)
io.write(out/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,objects=35,published=35,omitted=0,files=rows,
    control_steps=0,physical_frames=0,factory_attempts=1,reset_attempts=1,completed_resets=0,scientific_model_training=0,online_LLM_API_calls=0,
    original_experiment_closed_technical_failure=True,no_task_success_or_loss_estimate=True))
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()};q=out/(label+'.nul');names.add(q.relative_to(ROOT).as_posix());q.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+q.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_scan=True,object_sha256=actual))
io.write(out/'complete.json',dict(integrity='PASSED_ARCHIVAL_NOT_EXPERIMENT_QUALIFICATION',source_local_commit=source,remote_archive_commit=remote['remote_after'],phase_objects=35,phase_published=35,phase_omitted=0,
    new_physics_during_archival=0,online_LLM_API_calls=0,original_experiment_closed_technical_failure=True,scientific_sources_unchanged=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-started))
stage('owned_final');check();print(dict(integrity='PASSED',objects=len(names),remote=remote['remote_after'],phase_published=35),flush=True)
