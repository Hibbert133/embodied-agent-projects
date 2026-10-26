from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
start=perf_counter_ns();out=ROOT/'outputs/research_archive/transfer_learning_v1';external=Path(__file__).parent
source='bb19bd7b2e9eabd668bda9266601e2c843bd1ca9'
assert io.git('rev-parse','HEAD')==source and not io.git('diff','--cached','--name-only') and not io.git('status','--porcelain','--untracked-files=no')
local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_verification.json')
assert local['integrity']==remote['integrity']=='PASSED' and local['source_local_commit']==remote['source_local_commit']==source
assert local['archive_commit']==remote['expected_archive_commit'] and local['archive_parent']=='c1339e2126d34f8e10953c1a8acb9bc33ca7edb4'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
run='outputs/correction_scope/transfer_learning_v1/run_20261026T132315Z_7a8c4c50b420/'
catalog={r['path']:r for r in io.read(out/'catalog.json')['files']};published={}
names=[run+n for n in ('replay.jsonl','forecast_diagnostics.json','selected_rows.json','results.json','bank.json','fixed_receiver_labels.json','fit_attempts.jsonl')]
names.extend(p.relative_to(ROOT).as_posix() for p in (ROOT/run/'models').iterdir());assert len(names)==37
for name in names:
    entry=catalog[name];assert entry['published'] and entry['sha256']==io.sha(ROOT/name)
    assert io.git('rev-parse',local['archive_commit']+':'+name)==entry['oid'];published[name]=entry['sha256']
for name in ('prepare_correction_transfer_archive_v1.py','push_correction_transfer_archive_v1.py','verify_correction_transfer_commit_v1.py'):
    shutil.copyfile(external/name,out/name)
shutil.copyfile(__file__,out/Path(__file__).name)
post=external/('correction_transfer_result_postcommit_'+source[:12]+'.json')
assert io.read(post)['integrity']=='PASSED' and io.read(post)['source_local_commit']==source
shutil.copyfile(post,out/'result_postcommit_byte_proof.json')
for p in out.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
def stage(selected,label):
    p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()}
    p.write_bytes(b'\0'.join(name.encode() for name in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def verify(selected):
    actual=index_bytes(selected)
    for name in actual:
        data=(ROOT/name).read_bytes()
        if b'\0' not in data:
            for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'archive actual-index secret '+label+' '+name)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names,'owned_paths_initial');actual=verify(names)
io.write(out/'archive_delivery_validation.json',dict(integrity='PASSED',source_local_result_commit=source,
    remote_archive_commit=local['archive_commit'],source_byte_proof_sha256=io.sha(out/'result_postcommit_byte_proof.json'),
    scoped_compilation='PASSED',actual_index_and_disk_sha256=actual,actual_index_secrets='PASSED',ordinary_and_staged_diff='PASSED',
    all_new_replay_diagnostics_results_and_30_models_published=True,published_sha256=published,
    previous_full_tracked_secret_scan_source=source,new_scientific_tests=0,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,
    no_force_no_merge=True,original_records_and_restorations_retained=True,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_final');actual=verify(names)
print(dict(integrity='PASSED',archival_index_objects=len(actual),source_result_commit=source,remote_archive_commit=local['archive_commit']))
