"""Retain verified remote receipts without changing completed scientific source."""
from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
start=perf_counter_ns();out=ROOT/'outputs/research_archive/controller_agreement_v1';remote=io.read(out/'remote_receipt.json');local=io.read(out/'local_receipt.json')
assert remote['integrity']==local['integrity']=='PASSED' and remote['remote_after']==local['archive_commit']
source=local['source_local_commit'];assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no')
for name in ('build_controller_agreement_archive_v1.py','finalize_controller_agreement_archive_receipts_v1.py','verify_controller_agreement_commit_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name);compile((out/name).read_bytes(),name,'exec')
proof=Path(__file__).parent/('controller_agreement_postcommit_'+source[:12]+'.json')
assert io.read(proof)['integrity']=='PASSED' and io.read(proof)['commit']==source
shutil.copyfile(proof,out/'scientific_delivery_committed_bytes.json')
catalog=io.read(out/'catalog.json');changed=io.git('diff','--name-only','1962d42caefcbfa40ef254c2754a9263b53ff3ec',source).splitlines()
selection=[r for r in catalog['files'] if r['path'] in changed]
assert len(selection)==len(changed)
io.write(out/'phase_selection.json',dict(integrity='PASSED',source_local_commit=source,changed_objects=len(changed),published=sum(r['published'] for r in selection),
    omitted=sum(not r['published'] for r in selection),files=selection,old_raw_data_and_restorations_preserved=True,new_physics=0,new_fits=0,online_LLM_API_calls=0))
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
        if b'\0' not in data:
            text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None,n
            for label,p in EXTRA.items():assert p.search(text) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_checked');actual=check()
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,actual_index_basic_extra_scan=True))
io.write(out/'complete.json',dict(integrity='PASSED',scientific_source_commit=source,remote_archive_commit=remote['remote_after'],
    phase_objects=len(selection),phase_published=sum(r['published'] for r in selection),phase_omitted=sum(not r['published'] for r in selection),
    scientific_source_unchanged=True,prior_full_tracked_scan_sha256=io.sha(ROOT/'outputs/controller_agreement/result_validation_v1/tracked_secret_scan.json'),
    new_physics=0,new_fits=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),remote_archive_commit=remote['remote_after'],phase_published=sum(r['published'] for r in selection),phase_omitted=sum(not r['published'] for r in selection)),flush=True)
