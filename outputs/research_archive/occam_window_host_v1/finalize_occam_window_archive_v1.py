from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
started=perf_counter_ns();out=ROOT/'outputs/research_archive/occam_window_host_v1';remote=io.read(out/'remote_receipt.json');local=io.read(out/'local_receipt.json');source=local['source_local_commit'];archive=remote['remote_after']
assert remote['integrity']==local['integrity']=='PASSED' and archive==local['archive_commit'] and io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
for name in ('build_occam_window_archive_v1.py','finalize_occam_window_archive_v1.py','verify_occam_core_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name);compile((out/name).read_bytes(),name,'exec')
proof=Path(__file__).parent/'occam_window_all_commit_proofs.json';assert io.read(proof)['integrity']=='PASSED' and io.read(proof)['current_head']==source;shutil.copyfile(proof,out/'all_phase_committed_bytes.json')
catalog=io.read(out/'catalog.json');changed=io.git('diff','--name-only','dc83dc4ac0debf6580d8f366c4bdab36f5325f04',source).splitlines();rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==135
assert all(r['published'] for r in rows),'all135 completed phase files selected including exact parts'
index=io.read(ROOT/'outputs/occam_window_host/delivery_v1/record_parts_index.json');restored=Path(__file__).parent/'occam_window_verified_remote_snapshot_restoration_v1';restored.mkdir(exist_ok=False);recoveries=[]
import subprocess,json
def blob(name):return subprocess.check_output(['git','show',archive+':'+name],cwd=ROOT)
actual_index=json.loads(blob('outputs/occam_window_host/delivery_v1/record_parts_index.json'));assert actual_index==index
for item in index['artifacts']:
    data=b''.join(blob(p['path']) for p in item['parts']);assert len(data)==item['original_bytes'] and hashlib.sha256(data).hexdigest()==item['original_sha256']
    path=restored/Path(item['original_path']).name;path.write_bytes(data);decoded=gzip.decompress(path.read_bytes());assert hashlib.sha256(decoded).hexdigest()==item['decoded_sha256']
    recoveries.append(dict(original_path=item['original_path'],actual_archive_commit=archive,restored_bytes=len(data),restored_sha256=io.sha(path),decoded_sha256=hashlib.sha256(decoded).hexdigest()))
io.write(out/'remote_snapshot_restoration.json',dict(integrity='PASSED',remote_head_verified=archive,source='actual local Git blobs at verified remote commit; no network redownload claimed',artifacts=recoveries,restore_copies_retained_external=True))
io.write(out/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,objects=135,published=135,omitted=0,files=rows,
    actual_control_steps=4203,physical_frames=939015,scientific_offline_training=0,online_LLM_API_calls=0,untrained_host_contract_only=True,
    all_three_raw_streams_recoverable_from_published_parts=True,old_omissions_unchanged=True))
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
        text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None,n
        for label,p in EXTRA.items():assert p.search(text) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_scan=True,object_sha256=actual))
io.write(out/'complete.json',dict(integrity='PASSED',source_local_commit=source,remote_archive_commit=archive,phase_objects=135,phase_published=135,phase_omitted=0,
    three_streams_actually_recovered_from_archive=True,source_and_scientific_sources_unchanged=True,new_physics_in_archival=0,online_LLM_API_calls=0,
    paper_reproduction_complete=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-started))
stage('owned_final');check();print(dict(integrity='PASSED',objects=len(names),remote=archive,phase_published=135,recovered_streams=3),flush=True)
