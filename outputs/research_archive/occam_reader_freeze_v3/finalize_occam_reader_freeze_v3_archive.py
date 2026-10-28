from pathlib import Path
from time import perf_counter_ns
import argparse,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');v=p.parse_args()
start=perf_counter_ns();out=ROOT/'outputs/research_archive/occam_reader_freeze_v3'
remote=io.read(out/'remote_receipt.json');local=io.read(out/'local_receipt.json');source=local['source_local_commit']
assert source=='be387b8f073beea835acc85e7b8f98a4b50aec7f' and remote['integrity']==local['integrity']=='PASSED'
assert remote['remote_after']==local['archive_commit']=='ee1162c775c3e54f94b78c9d595ced211c2a5c91'
assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
for name in ('build_occam_reader_freeze_v3_archive.py','finalize_occam_reader_freeze_v3_archive.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name);compile((out/name).read_bytes(),name,'exec')
proof=Path(__file__).parent/('occam_core_postcommit_'+source[:12]+'.json')
assert io.read(proof)['integrity']=='PASSED' and io.read(proof)['commit']==source
shutil.copyfile(proof,out/'freeze_committed_bytes.json')
recovery=Path(__file__).parent/'occam_reader_v3_actual_git_recovery.json'
assert io.read(recovery)['integrity']=='PASSED' and io.read(recovery)['commit']==source
shutil.copyfile(recovery,out/'actual_git_record_recovery.json')
catalog=io.read(out/'catalog.json')
changed=io.git('diff-tree','--no-commit-id','--name-only','-r',source).splitlines()
rows=[r for r in catalog['files'] if r['path'] in changed]
assert len(rows)==len(changed)==57 and all(r['published'] for r in rows)
io.write(out/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,objects=57,published=57,omitted=0,files=rows,
    native_stream_parts_published=4,new_physics_during_archival=0,online_LLM_API_calls=0,source_snapshot_is_reader_freeze_not_training_result=True),exclusive=False)
if v.prepare_only:
    names=[p for p in out.iterdir() if p.is_file()]
    for path in names:
        data=path.read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),path
    io.write(out/'prepared_for_local_receipt_commit.json',dict(integrity='PASSED_PREPARATION_ONLY',source_local_commit=source,
        remote_archive_commit=remote['remote_after'],phase_published=57,main_HEAD_and_index_unchanged=True,
        defer_receipt_commit_until_pipeline_terminal=True,new_physics=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start),exclusive=False)
    print(dict(integrity='PASSED_PREPARATION_ONLY',phase_published=57,remote=remote['remote_after'],main_index_unchanged=True),flush=True)
    raise SystemExit(0)
terminal=ROOT/'outputs/occam_reference_train_v2/pipeline_reader_v3/complete.json'
assert terminal.exists() and io.read(terminal)['integrity'] in ('PASSED','FAILED_PARTIAL'),'do not stage/commit receipts while physical/training pipeline is live'
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
    path=out/(label+'.nul');names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');actual=check()
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_scan=True,object_sha256=actual))
io.write(out/'complete.json',dict(integrity='PASSED_ARCHIVAL_NOT_EXPERIMENT_QUALIFICATION',source_local_commit=source,
    remote_archive_commit=remote['remote_after'],phase_objects=57,phase_published=57,phase_omitted=0,
    new_physics_during_archival=0,online_LLM_API_calls=0,scientific_sources_unchanged=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',objects=len(names),remote=remote['remote_after'],phase_published=57),flush=True)
