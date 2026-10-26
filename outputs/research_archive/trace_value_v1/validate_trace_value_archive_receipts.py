from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA

start=perf_counter_ns();out=ROOT/'outputs/research_archive/trace_value_v1';external=Path(__file__).parent
source='34ac29d2298fbcabcdf69720bfd6ad13334c547a'
assert io.git('rev-parse','HEAD')==source and not io.git('diff','--cached','--name-only')
assert not io.git('status','--porcelain','--untracked-files=no')
local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_verification.json')
assert local['integrity']==remote['integrity']=='PASSED'
assert local['source_local_commit']==remote['source_local_commit']==source
assert local['archive_commit']==remote['expected_archive_commit']
assert local['archive_parent']=='993bb1d78c9b1948c591be36eaaa90d9a12ced54'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
for name in ('prepare_trace_value_archive.py','push_trace_value_archive.py','verify_trace_value_result_postcommit.py'):
    shutil.copyfile(external/name,out/name)
shutil.copyfile(__file__,out/Path(__file__).name)
post=external/('trace_value_result_postcommit_'+source[:12]+'.json')
assert io.read(post)['integrity']=='PASSED' and io.read(post)['source_local_commit']==source
shutil.copyfile(post,out/'result_postcommit_byte_proof.json')
for p in out.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}

def stage(selected,label):
    p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()}
    p.write_bytes(b'\0'.join(n.encode('utf8') for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    return selected

def verify(selected):
    actual=index_bytes(selected)
    for name in actual:
        data=(ROOT/name).read_bytes()
        if b'\0' not in data:
            text=data.decode('utf8',errors='replace')
            for label,pattern in EXTRA.items():io.require(pattern.search(text) is None,'archival actual-index secret pattern '+label+' '+name)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check')
    return actual

names=stage(names,'owned_paths_initial');actual=verify(names)
io.write(out/'archive_delivery_validation.json',dict(integrity='PASSED',source_local_result_commit=source,
    remote_archive_commit=local['archive_commit'],source_byte_proof_sha256=io.sha(out/'result_postcommit_byte_proof.json'),
    scoped_compilation='PASSED',actual_index_and_disk_sha256=actual,actual_index_secrets='PASSED',ordinary_and_staged_diff='PASSED',
    previous_full_tracked_secret_scan_source=source,new_scientific_tests=0,new_physics=0,new_fits=0,online_LLM_API_calls=0,
    no_force_no_merge=True,original_records_and_restorations_retained=True,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_final')
actual=verify(names)
print(dict(integrity='PASSED',archival_index_objects=len(actual),source_result_commit=source,remote_archive_commit=local['archive_commit']))
