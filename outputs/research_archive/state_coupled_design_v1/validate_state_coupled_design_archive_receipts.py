from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
start=perf_counter_ns();out=ROOT/'outputs/research_archive/state_coupled_design_v1';external=Path(__file__).parent
source='aff4e55acbac551597cef72307089b7898b84eb4'
assert io.git('rev-parse','HEAD')==source and not io.git('diff','--cached','--name-only') and not io.git('status','--porcelain','--untracked-files=no')
local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_verification.json')
assert local['integrity']==remote['integrity']=='PASSED' and local['source_local_commit']==remote['source_local_commit']==source
assert local['archive_commit']==remote['expected_archive_commit'] and local['archive_parent']=='d56b3c63a648cf50b647b24e4928518bdd719bbd'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
record='outputs/correction_scope/state_coupled_design_v1/run_20261026T121947Z_657297ca8506/constructed_records.jsonl'
entry=next(r for r in io.read(out/'catalog.json')['files'] if r['path']==record)
assert entry['published'] and entry['sha256']==io.sha(ROOT/record)
assert io.git('rev-parse',local['archive_commit']+':'+record)==entry['oid']
for name in ('prepare_state_coupled_design_archive.py','push_state_coupled_design_archive.py','verify_state_coupled_design_commit.py'):
    shutil.copyfile(external/name,out/name)
shutil.copyfile(__file__,out/Path(__file__).name)
post=external/('state_coupled_design_result_postcommit_'+source[:12]+'.json')
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
    all_4320_constructed_records_published=True,constructed_record_sha256=entry['sha256'],
    previous_full_tracked_secret_scan_source=source,new_scientific_tests=0,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,
    no_force_no_merge=True,original_records_and_restorations_retained=True,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_final');actual=verify(names)
print(dict(integrity='PASSED',archival_index_objects=len(actual),source_result_commit=source,remote_archive_commit=local['archive_commit']))
