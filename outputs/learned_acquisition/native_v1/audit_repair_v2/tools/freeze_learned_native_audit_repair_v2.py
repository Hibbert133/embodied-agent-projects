"""Freeze a zero-interaction auditor repair before reading the data again."""
from pathlib import Path
from time import perf_counter_ns
import difflib,io as stdio,shutil,subprocess,sys,unittest
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import learned_acquisition_native_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io;BASE=a.BASE/'audit_repair_v2';BASE.mkdir(exist_ok=False);start=perf_counter_ns();guard={};log=stdio.StringIO()
assert io.git('rev-parse','HEAD')=='3c437c6d3f5dc9bc18cc146a8e0776c52d3ada52' and not io.git('status','--porcelain','--untracked-files=no')
assert not io.git('diff','--cached','--name-only')
run=a.BASE/'run_20261027T042530Z_3c437c6d3f5d';m=a.checked(run/'manifest.json')
old=io.read(a.BASE/'freeze_validation/complete.json');assert old['unique_test_total']==2181
reuse=io.read(a.BASE/'freeze_validation/source_reuse.json')
for mapping in (old['source_sha256'],reuse['source_sha256']):
    for name,h in mapping.items():assert io.sha(ROOT/name)==h
with read_only(guard):
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_learned_native_audit_repair_v2.py')
    test=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
assert test.wasSuccessful() and test.testsRun==2
io.write(BASE/'tests.json',dict(integrity='PASSED',tests_run=2,log=log.getvalue(),guard=guard,source_bound_old_tests=2181,unique_total=2183,new_physics=0,new_fits=0,online_LLM_API_calls=0))
failure=run/'pipeline_control/audit-native_failure.json';assert io.read(failure)['integrity']=='FAILED'
io.write(BASE/'original_failure_binding.json',dict(original_frozen_audit_status='FAILED_RETAINED',failure_sha256=io.sha(failure),
    source_manifest_sha256=io.sha(run/'manifest.json'),collection_completion_sha256=io.sha(run/'native/completion.json'),
    collection_summary_sha256=io.sha(run/'native/summary.json'),original_v1_query_sha256=io.sha(run/'native/decision_queries.jsonl.gz'),
    original_model_bundle_sha256=io.sha(a.ASSETS/'bundle.json'),v1_source_sha256=io.sha(ROOT/'src/analysis/learned_acquisition_native_audit_v1.py')))
tools=BASE/'tools';tools.mkdir()
for name in ('freeze_learned_native_audit_repair_v2.py','build_learned_native_audit_repair_v2.py','run_learned_native_audit_repair_v2.py'):shutil.copyfile(Path(__file__).parent/name,tools/name)
v1=(ROOT/'src/analysis/learned_acquisition_native_audit_v1.py').read_text('utf8');v2=(ROOT/'src/analysis/learned_acquisition_native_audit_v2.py').read_text('utf8')
with (BASE/'orchestration_diff.patch').open('x',encoding='utf8',newline='\n') as stream:
    stream.writelines(difflib.unified_diff(v1[v1.index('def audit(path):'):].splitlines(True),v2[v2.index('def audit(path):'):].splitlines(True),fromfile='frozen_v1_audit_body',tofile='read_only_v2_audit_body'))
names={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file()}|{'src/analysis/learned_acquisition_native_audit_v2.py','tests/test_learned_native_audit_repair_v2.py','docs/protocols/learned_native_audit_repair_v2_zh.md'}
for name in names:
    if name.endswith('.py'):compile((ROOT/name).read_bytes(),name,'exec')
for label,cmd in (('compile',[sys.executable,'-m','compileall','-q','src','scripts','tests']),('dependencies',[sys.executable,'-m','pip','check'])):
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True);io.write(BASE/(label+'.json'),dict(command=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
def stage(selected,label):
    p=BASE/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode('utf8') for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def scan(selected):
    actual=index_bytes(selected)
    for name in actual:
        data=(ROOT/name).read_bytes()
        if b'\0' not in data:
            assert not any(pattern.search(data.decode('utf8',errors='replace')) for pattern in EXTRA.values())
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names|{p.relative_to(ROOT).as_posix() for p in BASE.iterdir() if p.is_file()},'owned_initial');actual=scan(names)
io.write(BASE/'complete.json',dict(integrity='PASSED',source_sha256={n:io.sha(ROOT/n) for n in names},tests=2183,new_array_tests=2,
    source_bound_tests_reused=2181,full_tracked_secret_scan_reused_sha256=io.sha(a.BASE/'freeze_validation/tracked_secret_scan.json'),
    previously_tracked_files_unchanged=True,new_staged_bytes_basic_and_extra_secret_scanned=True,index_disk_sha256=actual,
    original_frozen_qualification='FAILED_RETAINED',repair_is_supplemental_read_only=True,new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in BASE.iterdir() if p.is_file()},'owned_final');scan(names)
print(dict(integrity='PASSED',new_tests=2,unique_source_bound_tests=2183,staged_files=len(names),new_physics=0))
