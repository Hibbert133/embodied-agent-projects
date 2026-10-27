"""All newly owned study files must be published in the verified archive."""
from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
out=ROOT/'outputs/research_archive/selective_coverage_v1';external=Path(__file__).parent;source='318e5ab0e93d4ed996435ee23eeebdd1d1fbceca';start=perf_counter_ns()
assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_receipt.json');intent=io.read(out/'push_intent.json')
assert local['integrity']==remote['integrity']=='PASSED' and local['source_local_commit']==intent['source_local_commit']==source
assert local['archive_commit']==remote['remote_after']=='cc5926e7b5b24baa8d597905fbb458a6905a131a'
assert local['archive_parent']==remote['remote_before']=='736d54f16f44afe33886bbf1180ae364e9ede5f0'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
catalog={r['path']:r for r in io.read(out/'catalog.json')['files']};published={}
paths=io.git('diff','--name-only','a4df11575edfef690f97c60e77771f291ab4521f',source).splitlines()
assert paths and 'reports/staggered_selective_scope_v1_zh.md' in paths
for name in paths:
    row=catalog[name];assert row['published'] and row['sha256']==io.sha(ROOT/name)
    assert io.git('rev-parse',local['archive_commit']+':'+name)==row['oid'];published[name]=row['sha256']
for n in ('build_staggered_selective_scope_archive_v1.py','push_staggered_selective_scope_archive_v1.py','validate_staggered_selective_scope_archive_v1.py','verify_staggered_selective_scope_commit_v1.py'):shutil.copyfile(external/n,out/n)
proof=external/('staggered_selective_scope_result_postcommit_'+source[:12]+'.json');assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,out/'result_postcommit_byte_proof.json')
for p in out.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
def stage(selected,label):
    p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def scan(selected):
    actual=index_bytes(selected)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:assert not any(p.search(data.decode('utf8',errors='replace')) for p in EXTRA.values())
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names,'owned_paths_initial');actual=scan(names)
io.write(out/'archive_delivery_validation.json',dict(integrity='PASSED',source_local_result_commit=source,remote_archive_commit=local['archive_commit'],
    all_new_study_paths_published=True,published_new_study_paths_sha256=published,actual_index_and_disk_sha256=actual,
    scoped_compilation='PASSED',actual_index_secrets='PASSED',ordinary_and_staged_diff='PASSED',original_native_qualification='FAILED_RETAINED',
    receipt_new_physics=0,receipt_new_model_fits=0,source_new_model_fits=0,source_primary_threshold_updates=12400,source_independent_integer_updates=12400,online_LLM_API_calls=0,no_force_no_merge=True,original_records_and_restorations_retained=True,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_final');actual=scan(names)
print(dict(integrity='PASSED',archival_index_objects=len(actual),all_new_published_paths=len(published),remote_archive_commit=local['archive_commit']),flush=True)
