"""Verify result publication and retain archival receipts on the local branch."""
from pathlib import Path
from time import perf_counter_ns
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
out=ROOT/'outputs/research_archive/graybox_qualification_v2';start=perf_counter_ns();local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_receipt.json')
assert io.git('rev-parse','HEAD')==local['source_local_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
assert local['integrity']==remote['integrity']=='PASSED' and local['archive_commit']==remote['remote_after'] and local['archive_parent']=='db378040920c006e37c118576d5f9226c36f86d4'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
catalog={r['path']:r for r in io.read(out/'catalog.json')['files']};published={};omitted={}
paths=io.git('diff','--name-only','e784794ded175d35de5dea19a2ca756a68e35fe7',local['source_local_commit']).splitlines();assert len(paths)==158
for name in paths:
    r=catalog[name];assert r['sha256']==io.sha(ROOT/name)
    allowed=r['bytes']<=8*1024**2 and not name.endswith(('.jsonl.gz','.bin'));assert r['published']==allowed
    if allowed:assert io.git('rev-parse',local['archive_commit']+':'+name)==r['oid'];published[name]=r['sha256']
    else:omitted[name]=dict(bytes=r['bytes'],sha256=r['sha256'])
external=Path(__file__).parent
for n in ('build_graybox_qualification_archive_v2.py','finalize_graybox_qualification_archive_receipts_v2.py','verify_graybox_qualification_result_v2.py'):(out/n).write_bytes((external/n).read_bytes())
io.write(out/'source_postcommit_proof.json',io.read(external/'graybox_qualification_result_postcommit_af2b3c6196ba.json'))
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()};p=out/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,pattern in EXTRA.items():assert pattern.search(data.decode('utf8',errors='replace')) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
for n in names:
    if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec')
stage('owned_initial');actual=check()
io.write(out/'archive_delivery_validation.json',dict(integrity='PASSED',source_local_commit=local['source_local_commit'],remote_archive_commit=local['archive_commit'],
    compared_new_source_paths=158,published_paths_sha256=published,omitted_local_data_paths=omitted,actual_index_disk_sha256=actual,
    no_force_no_merge=True,ordinary_head_and_scientific_sources_unchanged=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,
    scientific_qualification_completed=True,scientific_status='CLOSED_NEGATIVE',publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',receipt_objects=len(names),published_new_paths=len(published),omitted_new_paths=len(omitted),remote=local['archive_commit']),flush=True)
