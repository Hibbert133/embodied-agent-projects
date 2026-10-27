"""Commit only the read-only repair and completed archival receipts."""
from pathlib import Path
from time import perf_counter_ns
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
out=ROOT/'outputs/graybox_response/audit_repair_v2';archive=ROOT/'outputs/research_archive/graybox_freeze_v1';start=perf_counter_ns()
assert io.git('rev-parse','HEAD').startswith('5405cd4') and not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only')
receipt=io.read(out/'reconstruction_receipt.json');tests=io.read(out/'test_receipt.json');assert receipt['integrity']=='PASSED' and tests['success'] and tests['tests']==2
for n,h in tests['source_sha256'].items():assert io.sha(ROOT/n)==h,n
intent=io.read(out/'reconstruction_intent.json');run=ROOT/'outputs/graybox_response/qualification_v1/graybox_response_20261027T174316Z_cf2712de2ed7'
for n,h in intent['input_sha256'].items():assert io.sha(run/n)==h,n
assert not (run/'cal').exists() and not (run/'qual').exists() and not (run/'training/audit.json').exists()
assert receipt['result']['guard']['operation_counts']['lstsq_attempts']==9 and receipt['result']['independent_counts']['independent_nominal_grid_passes']==27
assert io.read(archive/'publication_validation.json')['all83_completed_source_paths_published']
for n in ('graybox_array_postcommit_92285dd0e4ab.json','graybox_result_postcommit_5405cd452052.json'):
    p=Path(__file__).parent/n
    if p.exists():io.write(out/n,io.read(p))
(out/'freeze_graybox_audit_repair_v2.py').write_bytes(Path(__file__).read_bytes())
names=set(tests['source_sha256'])|{'reports/graybox_audit_repair_v2_zh.md',(run/'training_audit_repair_v2.json').relative_to(ROOT).as_posix()}
names|={p.relative_to(ROOT).as_posix() for base in (out,archive) for p in base.iterdir() if p.is_file()}
for n in names:
    if n.endswith('.py'):compile((ROOT/n).read_bytes(),n,'exec')
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()};spec=out/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,regex in EXTRA.items():assert regex.search(data.decode('utf8',errors='replace')) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_initial');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_index_scan=True))
io.write(out/'complete.json',dict(integrity='PASSED',new_unique_tests=2,unique_tests=2410,reused_unique_tests=2408,source_sha256=tests['source_sha256'],
    supplemental_reconstruction_sha256=io.sha(out/'reconstruction_receipt.json'),new_physics=0,new_primary_fits=0,online_LLM_API_calls=0,
    original_failed_run_unchanged=True,no_CAL_or_QUAL_started=True,additional_independent_lstsq=9,additional_independent_grid=27,constructed_lstsq_separate=18,
    existing_compile_dependency_and_scans_source_bound=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),unique_tests=2410),flush=True)
