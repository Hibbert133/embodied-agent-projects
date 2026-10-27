"""Verify all completed phase paths and retain archival receipts locally."""
from pathlib import Path
from time import perf_counter_ns
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
out=ROOT/'outputs/research_archive/episode_seed_inventory_v2';external=Path(__file__).parent;start=perf_counter_ns()
local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_receipt.json');source=local['source_local_commit']
assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
assert local['integrity']==remote['integrity']=='PASSED' and local['archive_commit']==remote['remote_after'] and local['archive_parent']=='750b48e6f67f39f9dbb088dcb84af20cd3fce898'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
catalog={r['path']:r for r in io.read(out/'catalog.json')['files']};published={};omitted={}
paths=io.git('diff','--name-only','93efd5ff43744626d46b27005f4b1cbfa7df99f2',source).splitlines();assert len(paths)==38
for name in paths:
    row=catalog[name];assert row['sha256']==io.sha(ROOT/name)
    allowed=row['bytes']<=8*1024**2 and not name.endswith(('.jsonl.gz','.bin'));assert row['published']==allowed
    if allowed:assert io.git('rev-parse',local['archive_commit']+':'+name)==row['oid'];published[name]=row['sha256']
    else:omitted[name]=dict(bytes=row['bytes'],sha256=row['sha256'])
assert len(published)==38 and not omitted
for n in ('build_seed_inventory_archive_v2.py','push_seed_inventory_archive_v2.py','validate_seed_inventory_archive_v2.py','verify_seed_inventory_commit_v2.py'):
    (out/n).write_bytes((external/n).read_bytes().replace(b'\r\n',b'\n'))
proofs={}
for phase,commit,count in (('freeze','8e3e8e428aac40adb689a7562fb4a47fd1143737',22),('result',source,16)):
    p=external/('seed_inventory_'+phase+'_postcommit_'+commit[:12]+'.json');v=io.read(p)
    assert v['integrity']=='PASSED' and v['commit']==commit and v['object_count']==count
    io.write(out/(phase+'_postcommit_byte_proof.json'),v);proofs[phase]=io.sha(p)
for p in out.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
    p=out/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def scan():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:assert not any(p.search(data.decode('utf8',errors='replace')) for p in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_paths_initial');actual=scan()
io.write(out/'archive_delivery_validation.json',dict(integrity='PASSED',source_local_result_commit=source,remote_archive_commit=local['archive_commit'],
    all38_new_phase_paths_published=True,published_new_phase_paths_sha256=published,omitted_new_phase_paths=omitted,actual_index_and_disk_sha256=actual,
    source_postcommit_proofs_sha256=proofs,scoped_compilation='PASSED',actual_index_secrets='PASSED',ordinary_and_staged_diff='PASSED',
    source_head_and_old_science_unchanged=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,seed_reservations=0,
    no_force_no_merge=True,raw_metadata_and_actual_restorations_retained_local=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_paths_final');scan();print(dict(integrity='PASSED',receipt_objects=len(names),new_published_paths=len(published),new_omitted_paths=len(omitted),remote_archive_commit=local['archive_commit']),flush=True)
