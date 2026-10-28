"""Software freeze only: arrays, fake handles, no native launches or Adam."""
from contextlib import ExitStack,redirect_stdout,redirect_stderr
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import gzip,shutil,subprocess,sys,unittest
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from src.analysis import occam_reference_train_io_v3 as a
from src.analysis.occam_platform_bootstrap_v1 import in_process_queries,module_sha256
from src.analysis.release_learning_guard_v1 import read_only

OWN=('.gitattributes','configs/movement_task/occam_reference_train_v3.json','docs/protocols/occam_reference_train_seeds_v3.json',
    'docs/protocols/occam_reference_train_v3_zh.md','scripts/occam_native_case_worker_v1.py','scripts/run_occam_reference_train_v3.py',
    'scripts/train_occam_reference_v3.py','src/analysis/occam_live_rng_guard_v1.py','src/analysis/occam_native_case_audit_v1.py',
    'src/analysis/occam_native_case_io_v1.py','src/analysis/occam_native_case_process_v1.py','src/analysis/occam_reference_learner_v3.py',
    'src/analysis/occam_reference_learning_io_v3.py','src/analysis/occam_reference_train_audit_v4.py','src/analysis/occam_reference_train_case_v3.py',
    'src/analysis/occam_reference_train_collect_v3.py','src/analysis/occam_reference_train_host_v3.py','src/analysis/occam_reference_train_io_v3.py',
    'tests/test_occam_isolated_collection_v1.py')


def validate():
    total_start=perf_counter_ns();out=a.VALIDATION;out.mkdir(parents=True,exist_ok=True)
    assert a.io.git('rev-parse','HEAD')=='6d5919fc1764745bf6b9c69569c8959b9faab291'
    assert a.io.git('status','--porcelain','--untracked-files=no').strip()=='M .gitattributes'
    old_root=ROOT/'outputs/occam_resource_qualification_v3/freeze_v1';old=c.read(old_root/'complete.json');reuse=c.read(old_root/'source_reuse.json')
    assert old['unique_test_total']==2629 and c.sha(old_root/'source_reuse.json')==old['source_reuse_sha256']
    prior={**reuse['source_sha256'],**old['source_sha256']}
    for name,h in prior.items():assert c.sha(ROOT/name)==h,name
    number=1
    while (out/('attempt%02d'%number)).exists():number+=1
    attempt=out/('attempt%02d'%number);attempt.mkdir();before={n:c.sha(ROOT/n) for n in OWN};c.write(attempt/'source_before_tests.json',before)
    guard={};start=perf_counter_ns()
    with (attempt/'tests.log').open('x',encoding='utf8',newline='\n') as log,redirect_stdout(log),redirect_stderr(log),read_only(guard),ExitStack() as stack:
        stack.enter_context(patch('subprocess.Popen',side_effect=AssertionError('no real process in array/reader tests')))
        from tests import test_occam_training_population_v3 as population_tests
        from src.analysis import occam_reference_train_audit_v4 as reader
        stack.enter_context(patch.object(population_tests,'reader',reader))
        suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromName('tests.test_occam_isolated_collection_v1'),
            unittest.defaultTestLoader.loadTestsFromModule(population_tests)])
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    c.write(attempt/'tests.json',dict(integrity='PASSED' if result.wasSuccessful() else 'FAILED',tests=result.testsRun,new_unique_tests=32,
        old_reader_reexecutions=5,failures=len(result.failures),errors=len(result.errors),guard=guard,wall_ns=perf_counter_ns()-start,
        native_workers=0,new_physics=0,new_fits=0,Adam_updates=0,online_LLM_API_calls=0))
    assert result.wasSuccessful() and result.testsRun==37,'see retained tests.log'
    for name,h in before.items():assert c.sha(ROOT/name)==h,name
    assert not any(guard['operation_counts'].values()) and guard['network']['attempted_network_calls']==0
    def command(name,args):
        t=perf_counter_ns();v=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        c.write(attempt/name,dict(args=args,returncode=v.returncode,stdout=v.stdout,stderr=v.stderr,wall_ns=perf_counter_ns()-t));assert v.returncode==0,name
    command('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
    command('main_dependencies.json',[sys.executable,'-m','pip','check'])
    command('training_dependencies.json',[str(a.TRAIN_PYTHON),'-m','pip','check'])
    runtime_guard={};t=perf_counter_ns()
    with in_process_queries(module_sha256()) as bootstrap,read_only(runtime_guard),patch('subprocess.Popen',side_effect=AssertionError('no subprocess in runtime hash audit')):
        from src.analysis.response_action_io_v1 import verify_runtime
        verify_runtime(c.read(a.RUNTIME))
    old_lock=ROOT/'outputs/occam_reference_train_v2/freeze_validation_v1/training_runtime_lock.json'
    if not (out/'training_runtime_lock.json').exists():shutil.copyfile(old_lock,out/'training_runtime_lock.json')
    assert c.sha(old_lock)==c.sha(out/'training_runtime_lock.json');a.verify_training_runtime()
    c.write(attempt/'runtime.json',dict(integrity='PASSED',guard=runtime_guard,platform_query=bootstrap,wall_ns=perf_counter_ns()-t,
        main_runtime_sha256=c.sha(a.RUNTIME),training_runtime_lock_sha256=c.sha(out/'training_runtime_lock.json'),new_packages=0))
    query=a.QUERY;inventory=c.read(query/'inventory.json');assert inventory['status']=='NO_REGISTERED_COLLISION' and c.read(query/'audit.json')['integrity']=='PASSED'
    from src.analysis.episode_seed_inventory_v2 import verify_unchanged,discover,scan
    from src.analysis.episode_seed_inventory_audit_v2 import audit as seed_audit
    verify_unchanged(ROOT,inventory)
    excluded={a.CONFIG.resolve(),a.PROTOCOL.resolve(),a.SEEDS.resolve()};fresh=scan(ROOT,172000,174999,[p for p in discover(ROOT) if p.resolve() not in excluded])
    audited=seed_audit(ROOT,fresh);assert fresh['status']=='NO_REGISTERED_COLLISION' and audited['integrity']=='PASSED'
    c.write(attempt/'seed_recheck.json',dict(integrity='PASSED',original_inventory_sha256=c.sha(query/'inventory.json'),
        original_source_count=len(inventory['sources']),fresh_status=fresh['status'],fresh_source_count=len(fresh['sources']),independent_audit=audited,
        excluded_only_own_config_protocol_registry=[p.relative_to(ROOT).as_posix() for p in sorted(excluded)],allocation_created=False))
    bundle=query/'inventory.json.gz'
    if not bundle.exists():
        with (query/'inventory.json').open('rb') as source,gzip.open(bundle,'xb') as target:shutil.copyfileobj(source,target)
    restore=query/'restoration_v1/inventory.restored.json';restore.parent.mkdir(exist_ok=True)
    with gzip.open(bundle,'rb') as source,restore.open('xb') as target:shutil.copyfileobj(source,target)
    assert c.sha(restore)==c.sha(query/'inventory.json')
    c.write(query/'inventory_bundle.json',dict(integrity='PASSED',raw_sha256=c.sha(restore),raw_bytes=restore.stat().st_size,
        gzip_sha256=c.sha(bundle),gzip_bytes=bundle.stat().st_size,restored_local_path=str(restore),raw_retained_local=True,
        contains_no_robot_data=True,allocation_created=False))
    sample=c.resources.snapshot(ROOT);decision=c.resources.gate(sample,minimum_commit_bytes=4*1024**3,minimum_disk_bytes=4*1024**3)
    c.write(attempt/'resource_readiness.json',dict(sample=sample,decision=decision,no_allocation_created=True))
    c.write(out/'source_reuse.json',dict(integrity='PASSED',source_sha256=prior,reused_unique_tests=2629,new_unique_tests=32,unique_tests=2661,
        source_receipt=(old_root/'complete.json').relative_to(ROOT).as_posix(),source_receipt_sha256=c.sha(old_root/'complete.json'),
        separately_reexecuted_record_reader_tests=5,no_old_simulation_or_optimizer_checks_repeated=True))
    inputs={n:c.sha(ROOT/n) for n in ('outputs/occam_resource_qualification_v3/freeze_v1/complete.json','outputs/occam_resource_qualification_v3/freeze_v1/source_reuse.json',
        'outputs/occam_resource_qualification_v3/qualification_v1/complete.json','outputs/occam_resource_qualification_v3/qualification_v1/audit.json',
        'outputs/response_action/validation_v1/runtime_lock.json','outputs/occam_reference_train_v2/freeze_validation_v1/training_runtime_lock.json',
        'outputs/occam_reference_train_v2/development_v1/occam_reference_train_v2_20261027T233346Z_e695620a8a91/CLOSED_TECHNICAL_FAILURE.json')}
    c.write(out/'validation_receipt.json',dict(integrity='PASSED_ARRAYS_READERS_RUNTIME_ONLY',source_sha256=before,input_sha256=inputs,
        source_reuse_sha256=c.sha(out/'source_reuse.json'),attempt=attempt.name,unique_tests=2661,actual_test_executions=37,
        new_unique_tests=32,reused_unique_tests=2629,guard=guard,native_workers=0,new_environment_operations=0,new_fits=0,Adam_updates=0,
        online_LLM_API_calls=0,science_collection_opened=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-total_start))
    shutil.copyfile(Path(__file__),out/Path(__file__).name)
    print(dict(integrity='PASSED_ARRAYS_READERS_RUNTIME_ONLY',actual_tests=37,unique_tests=2661,resource_allowed=decision['allowed']),flush=True)


if __name__=='__main__':validate()
