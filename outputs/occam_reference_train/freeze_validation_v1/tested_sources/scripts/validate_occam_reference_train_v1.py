"""Freeze independent behavior acquisition and standard-reference learning."""
from pathlib import Path
from time import perf_counter_ns
import gzip,shutil,subprocess,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_reference_train_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=a.io;ROOT=a.ROOT
OWN=tuple('src/analysis/'+n+'.py' for n in ('occam_training_data_v1','occam_reference_train_io_v1','occam_reference_train_host_v1',
    'occam_reference_train_collect_v1','occam_reference_train_audit_v1','occam_reference_learning_io_v1','occam_reference_learner_v1','occam_train_envelope_v1'))+(
    'src/probe/occam_training_behavior_v1.py','src/probe/occam_training_program_v1.py',
    'scripts/train_occam_reference_v1.py','scripts/run_occam_reference_train_v1.py','scripts/run_occam_reference_train_pipeline_v1.py',
    'scripts/check_occam_training_isolated_v1.py','scripts/validate_occam_reference_train_v1.py',
    'tests/test_occam_training_contract_v1.py','tests/test_occam_training_population_v1.py','tests/test_occam_training_torch_v1.py',
    'configs/movement_task/occam_reference_train_v1.json','docs/protocols/occam_reference_train_v1_zh.md',
    'docs/protocols/occam_reference_train_seeds_v1.json','docs/research/occam_reference_training_decision_v1_zh.md')


def main():
    start=perf_counter_ns();out=a.VALIDATION;out.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'unchanged old tracked sources and empty index')
    io.require(io.read(a.CONFIG)==a.config() and io.read(a.SEEDS)==a.registry(),'exact independent training allocation')
    previous=ROOT/'outputs/occam_window_host/software_validation_v1';q=io.read(previous/'complete.json');reuse=io.read(previous/'source_reuse.json')
    reader=io.read(ROOT/'outputs/occam_window_host/audit_repair_v3/freeze_complete.json')
    io.require(q['integrity']==reuse['integrity']==reader['integrity']=='PASSED' and q['unique_test_total']==2518 and reader['unique_test_total']==2522,'complete source-bound prior checks')
    prior={**reuse['source_sha256'],**q['source_sha256'],**reader['source_sha256']}
    for n,h in prior.items():io.require(io.sha(ROOT/n)==h,'prior tested source changed '+n)
    source={n:io.sha(ROOT/n) for n in OWN};io.write(out/'source_before_tests.json',source)
    snapshot=out/'tested_sources';snapshot.mkdir()
    for n in OWN:
        target=snapshot/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/n).read_bytes())
    guard={};ids=[]
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard,max_solve=1000):
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in ('tests.test_occam_training_contract_v1','tests.test_occam_training_population_v1'))
        def collect(s):
            for t in s:
                if isinstance(t,unittest.TestSuite):collect(t)
                else:ids.append(t.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,ids=ids,guard=guard))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==25,'25 main checks')
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    run('isolated_process.json',[str(a.TRAIN_PYTHON),'scripts/check_occam_training_isolated_v1.py','--output',str(out/'isolated')])
    child=io.read(out/'isolated/complete.json');io.require(child['integrity']=='PASSED' and child['tests']==7 and not child['skipped'],'isolated seven checks')
    io.require(len(set(ids)|set(child['ids']))==32,'new unique test count')
    runtime=io.read(ROOT/'outputs/occam_performance_core/software_validation_v1/runtime_entry_hashes.json')
    for n,h in runtime['critical_entry_sha256'].items():io.require(io.sha(Path(n))==h,'existing isolated runtime unchanged')
    io.write(out/'training_runtime_lock.json',runtime);a.verify_training_runtime()
    from src.analysis.response_action_io_v1 import verify_runtime
    verify_runtime(io.read(a.RUNTIME))
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('main_dependencies.json',[sys.executable,'-m','pip','check'])
    run('training_dependencies.json',[str(a.TRAIN_PYTHON),'-m','pip','check'])
    io.write(out/'source_reuse.json',dict(integrity='PASSED',reused_unique_tests=2522,new_unique_tests=32,unique_tests=2554,source_sha256=prior,old_physics_tests_repeated=False))
    original=a.QUERY/'inventory.json';packed=a.QUERY/'inventory.json.gz';raw=original.read_bytes()
    with packed.open('xb') as f:
        with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as stream:stream.write(raw)
    restored=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/occam_reference_training_inventory_restored_v1.json');restored.write_bytes(gzip.decompress(packed.read_bytes()));io.require(restored.read_bytes()==raw,'actual inventory restoration')
    io.write(a.QUERY/'inventory_bundle.json',dict(integrity='PASSED',original_path=original.relative_to(ROOT).as_posix(),original_bytes=len(raw),original_sha256=io.sha(original),
        compressed_path=packed.relative_to(ROOT).as_posix(),compressed_sha256=io.sha(packed),actual_restored_sha256=io.sha(restored),original_retained_local=True))
    names=set(OWN)|{p.relative_to(ROOT).as_posix() for p in (a.BASE/'development_validation_v1').rglob('*') if p.is_file()}
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
    # The legacy flag scans tracked working-tree bytes. The independent index
    # check below additionally scans the actual staged blobs and decoded gzip.
    run('tracked_secret_script.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_basic_extra_decoded_scan=True,object_sha256=actual))
    for n,h in source.items():io.require(io.sha(ROOT/n)==h,'tested new source changed '+n)
    dev=io.read(a.BASE/'development_validation_v1/isolated01/complete.json')
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=source,unique_test_total=2554,new_unique_tests=32,reused_unique_tests=2522,
        main_guard=guard,isolated_guard=child['guard'],development_plus_formal_test_executions=64,synthetic_Adam_attempts=dev['operation_counts']['synthetic_Adam_attempts']+child['operation_counts']['synthetic_Adam_attempts'],
        source_reuse_sha256=io.sha(out/'source_reuse.json'),seed_inventory_actual_restore_verified=True,
        scientific_model_training=0,new_robot_interactions=0,online_LLM_API_calls=0,scientific_CAL_QUAL_opened=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',new_unique_tests=32,unique_test_total=2554,owned_objects=len(names),new_physics=0),flush=True)


if __name__=='__main__':main()
