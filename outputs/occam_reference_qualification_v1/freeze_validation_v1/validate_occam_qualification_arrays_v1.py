"""Retained pure-array development validation; no scientific allocation."""
from pathlib import Path
from time import perf_counter_ns
from contextlib import redirect_stdout,redirect_stderr
from unittest.mock import patch
import json,shutil,subprocess,sys,unittest,traceback
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_qualification_case_io_v1 as c
from src.analysis.occam_platform_bootstrap_v1 import in_process_queries,module_sha256
base=c.BASE/'development_validation_v1';base.mkdir(exist_ok=True);number=1
while (base/('attempt%02d'%number)).exists():number+=1
out=base/('attempt%02d'%number);out.mkdir();started=perf_counter_ns();guard={};failure=None;result=None;process_attempts=0
names=[p.relative_to(ROOT).as_posix() for area in ('src','scripts','tests') for p in (ROOT/area).rglob('*.py')
    if 'occam_qualification' in p.name or 'occam_reference_qualification' in p.name or 'occam_own_history_qualification' in p.name]
c.write(out/'source_binding.json',{n:c.sha(ROOT/n) for n in sorted(names)})
snapshots=out/'source_snapshot';snapshots.mkdir()
for name in names:
    target=snapshots/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
def denied(*args,**kwargs):
    global process_attempts
    process_attempts+=1;raise AssertionError('real Popen forbidden in qualification software tests')
with (out/'stdout.log').open('x',encoding='utf8') as log,(out/'stderr.log').open('x',encoding='utf8') as err,redirect_stdout(log),redirect_stderr(err):
    try:
        with in_process_queries(module_sha256()) as platform:
            from src.analysis.release_learning_guard_v1 import read_only
            with read_only(guard,max_solve=500),patch.object(subprocess,'Popen',denied):
                suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_own_history_qualification_v1')
                result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
receipt=dict(integrity='PASSED_ARRAYS_ONLY' if result is not None and result.wasSuccessful() and failure is None else 'FAILED_ARRAYS_ONLY',
    tests=0 if result is None else result.testsRun,failures=0 if result is None else len(result.failures),errors=0 if result is None else len(result.errors),
    failure=failure,guard=guard,real_process_launch_attempts=process_attempts,platform=platform,source_binding_sha256=c.sha(out/'source_binding.json'),
    allocation_created=False,new_physics=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-started)
c.write(out/'complete.json',receipt);shutil.copyfile(Path(__file__),out/Path(__file__).name)
print({k:receipt[k] for k in ('integrity','tests','failures','errors','real_process_launch_attempts','wall_ns')},flush=True)
if receipt['integrity']!='PASSED_ARRAYS_ONLY':raise SystemExit(1)
