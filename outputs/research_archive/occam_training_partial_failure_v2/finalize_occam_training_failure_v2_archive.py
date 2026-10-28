from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();out=ROOT/'outputs/research_archive/occam_training_partial_failure_v2'
remote=io.read(out/'remote_receipt.json');local=io.read(out/'local_receipt.json');source=local['source_local_commit']
assert source=='3759e0e425ddb49e3d199abee1e2c95a494c91e0' and remote['integrity']==local['integrity']=='PASSED'
assert remote['remote_after']==local['archive_commit']=='7b9cd18ec23bcf204475c30fd2af30beb9a80125'
assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
for name in ('build_occam_training_failure_v2_archive.py','finalize_occam_training_failure_v2_archive.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name);compile((out/name).read_bytes(),name,'exec')
for head,label in ((source,'result_committed_bytes.json'),('eb0bffc847f4240452448af9cc58cb9d2836eb1f','diagnostic_freeze_committed_bytes.json')):
    proof=Path(__file__).parent/('occam_core_postcommit_'+head[:12]+'.json')
    assert io.read(proof)['integrity']=='PASSED' and io.read(proof)['commit']==head
    shutil.copyfile(proof,out/label)
recovery=Path(__file__).parent/'occam_training_failure_v2_actual_git_recovery.json'
assert io.read(recovery)['integrity']=='PASSED' and io.read(recovery)['commit']==source
shutil.copyfile(recovery,out/'actual_git_record_recovery.json')
catalog=io.read(out/'catalog.json');changed=io.git('diff','--name-only','be387b8f073beea835acc85e7b8f98a4b50aec7f',source).splitlines()
rows=[r for r in catalog['files'] if r['path'] in changed]
assert len(rows)==len(changed)==110 and all(r['published'] for r in rows)
io.write(out/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,objects=110,published=110,omitted=0,files=rows,
    new_TRAIN_parts_published=19,all_historical_and_new_streams_recovered=7,all_record_parts_recovered=28,
    new_physics_during_archival=0,online_LLM_API_calls=0,no_training_or_task_qualification_claim=True))
report=ROOT/'reports/occam_reference_training_partial_failure_v2_zh.md'
with report.open('a',encoding='utf8',newline='\n') as file:
    file.write('\n交付本地3759e0e，完整新阶段110项已发布并核对远端快照\n7b9cd18ec23bcf204475c30fd2af30beb9a80125。归档独立从Git恢复本轮及历史\n共7流/28分片，逐行扫描全部解压字节；本轮TRAIN为其中2流/19分片。\n源提交之后本段仅补充归档回执，不改变科学数据、源码、门或结论。\n')
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}|{report.relative_to(ROOT).as_posix()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
    p=out/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' in data:continue
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');actual=check()
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,actual_index_basic_extra_scan=True))
io.write(out/'complete.json',dict(integrity='PASSED_ARCHIVAL_NOT_SCIENTIFIC_MODEL_QUALIFICATION',source_local_commit=source,remote_archive_commit=remote['remote_after'],
    phase_objects=110,phase_published=110,phase_omitted=0,new_TRAIN_parts_published=19,source_record_parts_recovered=28,
    original_history_raw_files_and_restorations_preserved=True,new_physics_during_archival=0,online_LLM_API_calls=0,
    scientific_sources_and_results_unchanged=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',objects=len(names),remote=remote['remote_after'],phase_published=110),flush=True)
