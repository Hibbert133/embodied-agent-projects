"""Verify every new study path by original publication rules, including omissions."""
from pathlib import Path
from time import perf_counter_ns
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
out=ROOT/'outputs/research_archive/packet_structure_v1';external=Path(__file__).parent;start=perf_counter_ns()
local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_receipt.json');source=local['source_local_commit']
assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
assert local['integrity']==remote['integrity']=='PASSED' and local['archive_commit']==remote['remote_after'] and local['archive_parent']==remote['remote_before']=='61e9865b6e0c1ee0f0c1ae360adb281cda41b1a4'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
catalog={r['path']:r for r in io.read(out/'catalog.json')['files']};published={};omitted={}
paths=io.git('diff','--name-only','671d28924283adc6c0dddb7212798979bbe489e3',source).splitlines();assert 'reports/packet_structure_diagnosis_v1_zh.md' in paths
for name in paths:
    row=catalog[name];assert row['sha256']==io.sha(ROOT/name)
    allowed=row['bytes']<=8*1024**2 and not name.endswith(('.jsonl.gz','.bin'));assert row['published']==allowed
    if allowed:
        assert io.git('rev-parse',local['archive_commit']+':'+name)==row['oid'];published[name]=row['sha256']
    else:omitted[name]=dict(bytes=row['bytes'],sha256=row['sha256'],reason='ORIGINAL_TYPE_OR_SIZE_RULE_RETAINED_LOCAL')
for n in ('build_packet_structure_archive_v1.py','push_packet_structure_archive_v1.py','validate_packet_structure_archive_v1.py','verify_packet_structure_commit_v1.py'):(out/n).write_bytes((external/n).read_bytes().replace(b'\r\n',b'\n'))
proof=io.read(external/('packet_structure_result_postcommit_'+source[:12]+'.json'));assert proof['integrity']=='PASSED';io.write(out/'result_postcommit_byte_proof.json',proof)
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
    all_new_study_paths_accounted=True,published_new_study_paths_sha256=published,omitted_new_study_paths=omitted,actual_index_and_disk_sha256=actual,
    scoped_compilation='PASSED',actual_index_secrets='PASSED',ordinary_and_staged_diff='PASSED',receipt_new_physics=0,receipt_new_model_fits=0,online_LLM_API_calls=0,
    no_force_no_merge=True,original_raw_records_parts_and_restoration_retained=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_final');actual=scan(names)
print(dict(integrity='PASSED',archive_receipt_objects=len(actual),new_published_paths=len(published),new_omitted_paths=len(omitted),remote_archive_commit=local['archive_commit']),flush=True)
