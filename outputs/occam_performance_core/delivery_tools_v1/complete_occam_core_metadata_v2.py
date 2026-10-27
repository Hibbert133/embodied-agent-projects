"""Finish checked core delivery after LF-only provenance repair, no re-testing."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from scripts import validate_occam_performance_core_v1 as validator
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from scripts.check_tracked_secrets import find_secret_rule
started=perf_counter_ns();base=validator.BASE;out=base/'software_validation_v1';retained=out/'retained_metadata_failure01'
before=io.read(out/'source_before_tests.json');entry='scripts/validate_occam_performance_core_v1.py'
for n,h in before.items():
    if n!=entry:assert io.sha(ROOT/n)==h,n
old=(retained/'validator_before_lf_fix.txt').read_bytes();assert hashlib.sha256(old).hexdigest()==before[entry]
old_line=b"review=BASE/'source_review_v1';review.mkdir(exist_ok=False);shutil.copyfile(REVIEW/'provenance.json',review/'provenance.json')"
new_line=b"review=BASE/'source_review_v1';review.mkdir(exist_ok=False);io.write(review/'provenance.json',io.read(REVIEW/'provenance.json'))"
assert old.count(old_line)==1 and old.replace(old_line,new_line)==(ROOT/entry).read_bytes()
provenance=base/'source_review_v1/provenance.json';raw=provenance.read_bytes()
with (retained/'provenance.original.json.gz').open('xb') as f,gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as z:z.write(raw)
assert gzip.decompress((retained/'provenance.original.json.gz').read_bytes())==raw
previous=io.read(provenance);io.write(provenance,previous,exclusive=False);assert io.read(provenance)==previous
io.write(retained/'failure.json',dict(stage='post_tests_actual_index_disk_check',error='index and disk differ outputs/occam_performance_core/source_review_v1/provenance.json',
    cause='external provenance JSON retained Windows CRLF while Git indexed LF',raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest(),
    numeric_source_changed=False,tests_or_optimizer_repeated=False,metadata_validator_change_exact_single_line_verified=True,new_robot_interactions=0,scientific_model_training=0,online_LLM_API_calls=0))
first=io.read(out/'main_runtime_tests.json');isolated=io.read(out/'isolated/complete.json')
assert first['success'] and first['tests']==18 and isolated['integrity']=='PASSED' and isolated['tests']==24 and len(set(first['ids'])|set(isolated['ids']))==24
assert isolated['operation_counts']['synthetic_Adam_steps']==1 and isolated['operation_counts']['reviewed_upstream_inverse_attempts']==12
assert io.read(out/'full_tracked_secrets.json')['returncode']==0
for name in ('compile.json','main_dependencies.json','isolated_dependencies.json'):assert io.read(out/name)['returncode']==0
for d in (first['guard']['operation_counts'],isolated['guard']['counts']):
    for k,v in d.items():
        if k in ('environment_creations','resets','simulation','forbidden_physics_import_attempts','old_experiment_data_open_attempts'):assert v==0
tools=base/'delivery_tools_v1';tools.mkdir(exist_ok=False);shutil.copyfile(Path(__file__),tools/Path(__file__).name);compile((ROOT/entry).read_bytes(),entry,'exec');compile(Path(__file__).read_bytes(),str(__file__),'exec')
names={n.decode() for n in (out/'owned_checked.nul').read_bytes().split(b'\0') if n}
names|={p.relative_to(ROOT).as_posix() for p in retained.rglob('*') if p.is_file()}|{p.relative_to(ROOT).as_posix() for p in tools.iterdir() if p.is_file()}
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
    path=out/(label+'.nul');names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if n.endswith('.gz'):data=gzip.decompress(data)
        if b'\0' not in data:
            text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None,n
            for label,p in EXTRA.items():assert p.search(text) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_repaired');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_decompressed_scan=True,object_sha256=actual))
final={n:io.sha(ROOT/n) for n in before};io.write(out/'source_after_metadata_fix.json',final)
io.write(out/'complete.json',dict(integrity='PASSED',classification='STANDARD_REFERENCE_CORE_NOT_ROBOT_BASELINE_QUALIFICATION',source_sha256=final,
    numeric_source_and_tests_unchanged=True,metadata_only_validator_repair=True,numerical_tests_or_optimizer_repeated=False,
    unique_test_total=2487,new_unique_tests=24,reused_unique_tests=2463,root_guard=first['guard'],isolated_guard=isolated['guard'],
    isolated_operations=isolated['operation_counts'],upstream_contract_cases=12,max_export_basis_difference=io.read(out/'export_actor_check.json')['max_absolute_difference'],
    max_upstream_absolute_difference=max(r['max_absolute_difference'] for r in isolated['source_contract_cases']),
    new_robot_interactions=0,scientific_model_training=0,synthetic_Adam_steps=1,online_LLM_API_calls=0,
    paper_reproduction_complete=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-started,
    receipt_sha256={p.relative_to(out).as_posix():io.sha(p) for p in out.rglob('*') if p.is_file()}))
stage('owned_final');check();print(dict(integrity='PASSED',objects=len(names),new_unique_checks=24,synthetic_Adam_steps=1,numeric_checks_repeated=False),flush=True)
