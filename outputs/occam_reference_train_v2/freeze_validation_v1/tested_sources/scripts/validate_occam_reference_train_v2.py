"""Freeze the namespace repair and independent allocation before any physics."""
from pathlib import Path
from time import perf_counter_ns
import gzip,subprocess,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_reference_train_io_v2 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=a.io;ROOT=a.ROOT
OWN=tuple('src/analysis/'+n+'.py' for n in (
    'occam_case_events_v2','occam_reference_train_io_v2','occam_reference_train_host_v2',
    'occam_reference_train_collect_v2','occam_reference_train_audit_v2',
    'occam_reference_learning_io_v2','occam_reference_learner_v2','occam_train_envelope_v2'))+(
    'scripts/train_occam_reference_v2.py','scripts/run_occam_reference_train_v2.py',
    'scripts/run_occam_reference_train_pipeline_v2.py','scripts/check_occam_training_isolated_v2.py',
    'scripts/validate_occam_reference_train_v2.py','tests/test_occam_case_namespace_v2.py',
    'tests/test_occam_training_population_v2.py','tests/test_occam_training_torch_v2.py',
    'configs/movement_task/occam_reference_train_v2.json','docs/protocols/occam_reference_train_v2_zh.md',
    'docs/protocols/occam_reference_train_seeds_v2.json','docs/research/occam_reference_training_v2_decision_zh.md')


def main():
    start=perf_counter_ns();out=a.VALIDATION;out.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'unchanged old tracked sources and empty index')
    io.require(io.read(a.CONFIG)==a.config() and io.read(a.SEEDS)==a.registry(),'exact independent training allocation')
    previous=ROOT/'outputs/occam_reference_train/freeze_validation_v1'
    q=io.read(previous/'complete.json');reuse=io.read(previous/'source_reuse.json')
    diagnostic=io.read(ROOT/'outputs/occam_reference_train/failure_delivery_v1/diagnostic_final_checks.json')
    io.require(q['integrity']==reuse['integrity']=='PASSED' and q['unique_test_total']==2554 and diagnostic['success'] and diagnostic['tests']==4,'complete source-bound prior checks')
    prior={**reuse['source_sha256'],**q['source_sha256'],**diagnostic['source_sha256']}
    for n,h in prior.items():io.require(io.sha(ROOT/n)==h,'prior tested source changed '+n)
    from src.analysis import occam_reference_train_io_v1 as old
    original=(ROOT/'src/analysis/occam_reference_learner_v1.py').read_text(encoding='utf8')
    current=(ROOT/'src/analysis/occam_reference_learner_v2.py').read_text(encoding='utf8')
    io.require(current.replace('occam_reference_train_io_v2','occam_reference_train_io_v1')==original,'learner changed beyond independent path import')
    io.require(old.learning()==a.learning() and all(old.limits(p)==a.limits(p) for p in a.PHASES),'unchanged learning and physical caps')
    io.write(out/'algorithm_scope_equivalence.json',dict(integrity='PASSED',only_learner_change='independent V2 allocation import',learning_and_physical_caps_unchanged=True,old_population_closed=True))
    source={n:io.sha(ROOT/n) for n in OWN};io.write(out/'source_before_tests.json',source)
    snapshot=out/'tested_sources';snapshot.mkdir()
    for n in OWN:
        target=snapshot/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    guard={};ids=[]
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard):
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in ('tests.test_occam_case_namespace_v2','tests.test_occam_training_population_v2'))
        def collect(s):
            for t in s:
                if isinstance(t,unittest.TestSuite):collect(t)
                else:ids.append(t.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,ids=ids,guard=guard))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==12,'12 namespace and complete-population checks')
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    run('isolated_process.json',[str(a.TRAIN_PYTHON),'scripts/check_occam_training_isolated_v2.py','--output',str(out/'isolated')])
    child=io.read(out/'isolated/complete.json')
    io.require(child['integrity']=='PASSED' and child['tests']==8 and not child['skipped'],'isolated eight executions')
    new_scope=[n for n in child['ids'] if n.endswith('.test_v2_learner_cannot_consume_closed_v1_public_data')]
    io.require(len(new_scope)==1 and len(ids)+len(new_scope)==13,'13 new unique checks; seven isolated numerical checks repeated')
    runtime=io.read(ROOT/'outputs/occam_performance_core/software_validation_v1/runtime_entry_hashes.json')
    for n,h in runtime['critical_entry_sha256'].items():io.require(io.sha(Path(n))==h,'existing isolated runtime unchanged')
    io.write(out/'training_runtime_lock.json',runtime);a.verify_training_runtime()
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.RUNTIME))
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
    run('main_dependencies.json',[sys.executable,'-m','pip','check'])
    run('training_dependencies.json',[str(a.TRAIN_PYTHON),'-m','pip','check'])
    io.write(out/'source_reuse.json',dict(integrity='PASSED',reused_unique_tests=2558,new_unique_tests=13,unique_tests=2571,
        repeated_isolated_numerical_tests=7,source_sha256=prior,old_physics_tests_repeated=False))
    original=a.QUERY/'inventory.json';packed=a.QUERY/'inventory.json.gz';raw=original.read_bytes()
    with packed.open('xb') as f:
        with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as stream:stream.write(raw)
    restored=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/occam_reference_training_inventory_restored_v2.json')
    with restored.open('xb') as f:f.write(gzip.decompress(packed.read_bytes()))
    io.require(restored.read_bytes()==raw,'actual inventory restoration')
    io.write(a.QUERY/'inventory_bundle.json',dict(integrity='PASSED',original_path=original.relative_to(ROOT).as_posix(),original_bytes=len(raw),original_sha256=io.sha(original),
        compressed_path=packed.relative_to(ROOT).as_posix(),compressed_sha256=io.sha(packed),actual_restored_sha256=io.sha(restored),original_retained_local=True))
    names=set(OWN)|{p.relative_to(ROOT).as_posix() for p in (a.BASE/'development_validation_v1').rglob('*') if p.is_file()}
    names|={p.relative_to(ROOT).as_posix() for p in (a.BASE/'array_integration_fixtures_v1').rglob('*') if p.is_file()}
    names|={p.relative_to(ROOT).as_posix() for p in a.QUERY.iterdir() if p.is_file() and p.name!='inventory.json'}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
        q=out/(label+'.nul');names.add(q.relative_to(ROOT).as_posix());q.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+q.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.gz'):data=gzip.decompress(data)
            if b'\0' in data:continue
            text=data.decode('utf8',errors='replace');io.require(find_secret_rule(text) is None,'actual index basic secret '+n)
            for label,p in EXTRA.items():io.require(p.search(text) is None,'actual index extra secret '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged diff');return actual
    stage('owned_initial')
    # This legacy flag scans tracked working-tree bytes; check() also proves
    # exact staged bytes and independently scans decoded compressed content.
    run('tracked_secret_script.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_decoded_scan=True,object_sha256=actual))
    for n,h in source.items():io.require(io.sha(ROOT/n)==h,'tested new source changed '+n)
    dev=io.read(a.BASE/'development_validation_v1/isolated01/complete.json')
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=source,unique_test_total=2571,new_unique_tests=13,reused_unique_tests=2558,
        repeated_isolated_numerical_checks=7,formal_test_executions=20,main_guard=guard,isolated_guard=child['guard'],
        synthetic_Adam_attempts=dev['operation_counts']['synthetic_Adam_attempts']+child['operation_counts']['synthetic_Adam_attempts'],
        source_reuse_sha256=io.sha(out/'source_reuse.json'),seed_inventory_actual_restore_verified=True,
        scientific_model_training=0,new_robot_interactions=0,online_LLM_API_calls=0,scientific_CAL_QUAL_opened=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',new_unique_tests=13,unique_test_total=2571,owned_objects=len(names),new_physics=0),flush=True)


if __name__=='__main__':main()
