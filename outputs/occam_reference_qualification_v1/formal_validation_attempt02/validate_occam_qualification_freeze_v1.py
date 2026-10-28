"""Formal source-bound arrays/runtime/dependency/compile validation, zero sampling."""
from pathlib import Path
from time import perf_counter_ns
from contextlib import redirect_stdout,redirect_stderr
from unittest.mock import patch
import compileall,gzip,json,os,runpy,shutil,subprocess,sys,traceback,unittest
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_qualification_case_io_v1 as c
from src.analysis import occam_reference_qualification_io_v1 as a
from src.analysis.occam_platform_bootstrap_v1 import in_process_queries,module_sha256
out=a.VALIDATION;out.mkdir(exist_ok=False);started=perf_counter_ns();guard={};platform={};result=None;failure=None;real_process_attempts=0;pip_status=None
old=ROOT/'outputs/occam_reference_train_v3/freeze_validation_v1';prior=c.read(old/'source_reuse.json')['source_sha256'];prior.update(c.read(old/'complete.json')['source_sha256'])
for name,h in prior.items():assert c.sha(ROOT/name)==h,name
names=[p.relative_to(ROOT).as_posix() for area in ('src','scripts','tests') for p in (ROOT/area).rglob('*.py')
    if 'occam_qualification' in p.name or 'occam_reference_qualification' in p.name or 'occam_own_history_qualification' in p.name]
names+=['configs/movement_task/occam_reference_qualification_v1.json','docs/protocols/occam_reference_qualification_v1_zh.md','docs/protocols/occam_reference_qualification_seeds_v1.json']
source={n:c.sha(ROOT/n) for n in sorted(names)};c.write(out/'source_binding.json',source)
inputs=a.sources();inputs[(old/'complete.json').relative_to(ROOT).as_posix()]=c.sha(old/'complete.json')
inputs[(old/'source_reuse.json').relative_to(ROOT).as_posix()]=c.sha(old/'source_reuse.json')
inputs[a.RUNTIME.relative_to(ROOT).as_posix()]=c.sha(a.RUNTIME)
index_path=ROOT/'outputs/occam_reference_train_v3/native_delivery_v1/bundle_index.json';index=c.read(index_path)
entries={r['path']:r for r in index['files']}
for name in ('case.json','events.jsonl.gz','witnesses.jsonl.gz'):
    p=a.TRAIN/'native/case_0002'/name;relative=p.relative_to(ROOT).as_posix();assert c.sha(p)==entries[relative]['sha256']
    inputs[relative]=c.sha(p)
inputs[index_path.relative_to(ROOT).as_posix()]=c.sha(index_path)
for p in (a.BASE/'seed_precheck_v1').iterdir():
    if p.is_file():inputs[p.relative_to(ROOT).as_posix()]=c.sha(p)
c.write(out/'input_binding.json',inputs)
def denied(*args,**kwargs):
    global real_process_attempts
    real_process_attempts+=1;raise AssertionError('real Popen forbidden in formal qualification validation')
with (out/'stdout.log').open('x',encoding='utf8') as log,(out/'stderr.log').open('x',encoding='utf8') as err,redirect_stdout(log),redirect_stderr(err):
    try:
        with in_process_queries(module_sha256()) as platform:
            from src.analysis.release_learning_guard_v1 import read_only
            from src.analysis.response_action_io_v1 import verify_runtime
            with read_only(guard,max_solve=500),patch.object(subprocess,'Popen',denied):
                verify_runtime(c.read(a.RUNTIME));assert c.read(a.CONFIG)==a.config() and c.read(a.SEEDS)==a.registry()
                suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_own_history_qualification_v1')
                result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
                assert compileall.compile_dir(ROOT/'src',quiet=1) and compileall.compile_dir(ROOT/'scripts',quiet=1) and compileall.compile_dir(ROOT/'tests',quiet=1)
                argv=sys.argv[:];previous=os.environ.get('PIP_DISABLE_PIP_VERSION_CHECK');os.environ['PIP_DISABLE_PIP_VERSION_CHECK']='1'
                try:
                    sys.argv=['pip','check','--disable-pip-version-check']
                    with (out/'pip_check_stdout.log').open('x',encoding='utf8') as plog,(out/'pip_check_stderr.log').open('x',encoding='utf8') as perr,redirect_stdout(plog),redirect_stderr(perr):
                        try:runpy.run_module('pip',run_name='__main__');pip_status=0
                        except SystemExit as done:pip_status=done.code
                finally:
                    sys.argv=argv
                    if previous is None:os.environ.pop('PIP_DISABLE_PIP_VERSION_CHECK',None)
                    else:os.environ['PIP_DISABLE_PIP_VERSION_CHECK']=previous
                assert pip_status==0,'main runtime dependency conflict; full output retained'
    except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
assert all(c.sha(ROOT/n)==h for n,h in {**source,**inputs,**prior}.items()),'source/input changed while validating'
c.write(out/'source_reuse.json',dict(integrity='PASSED_SOURCE_HASH_REUSE',source_sha256=prior,reused_unique_tests=2661,
    original_receipt=(old/'complete.json').relative_to(ROOT).as_posix(),original_receipt_sha256=c.sha(old/'complete.json'),
    no_historical_simulation_or_optimizer_tests_reexecuted=True))
sample=c.resources.snapshot(ROOT);decision=c.resources.gate(sample,minimum_commit_bytes=4*1024**3,minimum_disk_bytes=4*1024**3)
c.write(out/'resource_readiness.json',dict(sample=sample,decision=decision,allocation_created=False))
receipt=dict(integrity='PASSED_FORMAL_ARRAY_RUNTIME_COMPILE_DEPENDENCIES' if result is not None and result.wasSuccessful() and failure is None else 'FAILED_FORMAL_ARRAY_VALIDATION',
    source_sha256=source,input_sha256=inputs,source_reuse_sha256=c.sha(out/'source_reuse.json'),
    new_unique_tests=0 if result is None else result.testsRun,reused_unique_tests=2661,actual_formal_tests=0 if result is None else result.testsRun,
    failures=0 if result is None else len(result.failures),errors=0 if result is None else len(result.errors),failure=failure,
    guard=guard,real_process_launch_attempts=real_process_attempts,platform=platform,main_pip_check_exitcode=pip_status,
    source_bound_training_runtime_receipt_reused=True,all_source_compileall_passed=failure is None,
    resource_admissible_at_observation=decision['allowed'],new_scientific_allocation_created=False,native_workers=0,
    array_callbacks_are_not_physical_interactions=True,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-started)
c.write(out/'validation_receipt.json',receipt)
for name in ('validate_occam_qualification_freeze_v1.py','create_occam_own_history_qualification_v1.py',
    'create_occam_qualification_record_audit_v1.py','validate_occam_qualification_arrays_v1.py','check_occam_qualification_seed_scope_v1.py'):
    shutil.copyfile(Path(__file__).parent/name,out/name)
print({k:receipt[k] for k in ('integrity','actual_formal_tests','failures','errors','main_pip_check_exitcode','resource_admissible_at_observation','wall_ns')},flush=True)
if receipt['integrity']!='PASSED_FORMAL_ARRAY_RUNTIME_COMPILE_DEPENDENCIES':raise SystemExit(1)
