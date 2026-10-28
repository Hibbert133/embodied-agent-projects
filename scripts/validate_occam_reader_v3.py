"""Freeze a non-relaxing reader repair; preserve all original physical bytes."""
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import gzip,hashlib,inspect,subprocess,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_reader_extension_v3 as e
from src.analysis import occam_reference_train_audit_v2 as old,occam_reference_train_audit_v3 as new
from src.analysis.release_learning_guard_v1 import read_only
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes
io=e.io;ROOT=e.a.ROOT


def scan(data,name):
    if b'\0' in data:return
    text=data.decode('utf8',errors='replace')
    io.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'credential pattern '+name)


def main():
    start=perf_counter_ns();out=e.VALIDATION;out.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'original tracked files unchanged and empty index')
    m=e.a.checked(e.TARGET);raw=e.TARGET.parent/'native';pipeline=e.a.BASE/'pipeline_v1'
    io.require(not (e.TARGET.parent/'train').exists() and io.read(pipeline/'complete.json')['integrity']=='FAILED_PARTIAL','unstarted TRAIN; original pipeline stopped')
    completion=io.read(raw/'completion.json');io.require(completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','complete original physical collection')
    for n,h in completion['artifact_sha256'].items():io.require(io.sha(raw/n)==h,'original completion bytes '+n)
    prior=io.read(e.a.VALIDATION/'complete.json');reuse=io.read(e.a.VALIDATION/'source_reuse.json')
    io.require(prior['integrity']=='PASSED' and prior['unique_test_total']==2571,'previous tested freeze')
    previous={**reuse['source_sha256'],**prior['source_sha256']}
    for n,h in previous.items():io.require(io.sha(ROOT/n)==h,'prior tested source changed '+n)
    protected={p.relative_to(ROOT).as_posix():io.sha(p) for p in list(raw.rglob('*'))+list(pipeline.rglob('*')) if p.is_file()}
    for p in (e.TARGET,e.TARGET.parent/'seed_scope.json',e.TARGET.parent/'seed_scope_audit.json'):protected[p.relative_to(ROOT).as_posix()]=io.sha(p)
    source={n:io.sha(ROOT/n) for n in e.OWN};io.write(out/'source_before_tests.json',source)
    lhs=inspect.getsource(old.reconstruct);rhs=inspect.getsource(new.reconstruct)
    stale="elif k=='NOISE_COMMITMENT':same(e['tape_sha256_oracle'],io.digest(tape.tolist()));same(e['noise_namespace_oracle'],2026102832)"
    fixed="elif k=='NOISE_COMMITMENT':same(e['tape_sha256_oracle'],io.digest(tape.tolist()),'noise tape commitment');same(e['noise_namespace_oracle'],e.a.registry()['noise_namespace'],'frozen noise namespace')"
    actual_fixed=fixed.replace('e.a.registry()','a.registry()')
    io.require(stale in lhs and actual_fixed in rhs and rhs.replace(actual_fixed,stale)==lhs,'reconstruct changed only frozen namespace attestation')
    for name in ('same','scalar_cost','replay'):io.require(inspect.getsource(getattr(old,name))==inspect.getsource(getattr(new,name)),'other scientific function unchanged '+name)
    io.write(out/'source_scope_proof.json',dict(integrity='PASSED',unchanged_functions=['same','scalar_cost','replay'],
        reconstruct_only_change='frozen namespace assertion and specific error messages; full noise hash retained',
        other_reader_changes='read original raw directory; separate NATIVE outputs and exclusive output checks',original_source_sha256=io.sha(ROOT/'src/analysis/occam_reference_train_audit_v2.py')))
    guard={};ids=[];policy_attempts=0
    def no_policy(*args,**kw):
        nonlocal policy_attempts
        policy_attempts+=1;raise AssertionError('policy calls forbidden in reader software tests')
    from src.rollout import task_registry
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard),patch.object(task_registry,'create_task_policy',no_policy):
        suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in ('tests.test_occam_reader_noise_v3','tests.test_occam_training_population_v3'))
        def collect(s):
            for t in s:
                if isinstance(t,unittest.TestSuite):collect(t)
                else:ids.append(t.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,ids=ids,guard=guard,policy_query_attempts=policy_attempts))
    io.require(result.wasSuccessful() and result.testsRun==12 and policy_attempts==0,'seven new and five repeated record-only checks')
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
    run('main_dependencies.json',[sys.executable,'-m','pip','check']);run('training_dependencies.json',[str(e.a.TRAIN_PYTHON),'-m','pip','check'])
    e.a.verify_training_runtime()
    io.write(out/'source_reuse.json',dict(integrity='PASSED',reused_unique_tests=2571,new_unique_tests=7,repeated_population_regressions=5,
        unique_tests=2578,source_sha256=previous,old_physics_or_Torch_optimizer_tests_repeated=False))
    delivery=e.BASE/'source_delivery_v1';delivery.mkdir();parts=delivery/'parts';parts.mkdir();restore=delivery/'restoration_v1';restore.mkdir();artifacts=[]
    for name in ('events.jsonl.gz','witnesses.jsonl.gz'):
        original=raw/name;data=original.read_bytes();rows=[];values=[]
        for i,j in enumerate(range(0,len(data),4*1024**2)):
            part=parts/(name+'.part%03d.bin'%(i+1));value=data[j:j+4*1024**2];part.write_bytes(value);values.append(part.read_bytes())
            rows.append(dict(path=part.relative_to(ROOT).as_posix(),bytes=len(value),sha256=io.sha(part)))
        recovered=restore/name;recovered.write_bytes(b''.join(values));io.require(recovered.read_bytes()==data,'actual part recovery')
        decoded=gzip.decompress(recovered.read_bytes());scan(decoded,name+'.decoded')
        artifacts.append(dict(original_path=original.relative_to(ROOT).as_posix(),original_bytes=len(data),original_sha256=io.sha(original),
            completion_sha256=completion['artifact_sha256'][name],decoded_bytes=len(decoded),decoded_sha256=hashlib.sha256(decoded).hexdigest(),parts=rows,actual_restored_sha256=io.sha(recovered),full_decoded_credential_scan=True))
    io.write(delivery/'record_parts_index.json',dict(integrity='PASSED',artifacts=artifacts,originals_and_actual_restorations_retained_local=True))
    original=e.TARGET.parent/'seed_scope.json';packed=delivery/'seed_scope.json.gz'
    with packed.open('xb') as f:
        with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as stream:stream.write(original.read_bytes())
    recovered=restore/'seed_scope.restored.json';recovered.write_bytes(gzip.decompress(packed.read_bytes()))
    io.require(io.sha(recovered)==io.sha(original),'actual scope restoration')
    io.write(delivery/'seed_scope_bundle.json',dict(integrity='PASSED',original_path=original.relative_to(ROOT).as_posix(),original_sha256=io.sha(original),
        compressed_sha256=io.sha(packed),actual_restored_sha256=io.sha(recovered),original_retained_local=True))
    census=[];cases=list(io.rows(raw/'cases.jsonl.gz'))
    io.require(len(cases)==36,'complete original NATIVE census')
    for case in cases:census.append({**{k:case[k] for k in e.a.KEYS},'status':'COLLECTED_PENDING_REPAIRED_AUDIT','success':case['success'],'deadline_loss':case['deadline_loss'],'total_steps':case['total_steps']})
    for spec in e.a.population('TRAIN'):census.append({**spec,'status':'NOT_STARTED_AT_READER_FREEZE','success':None,'deadline_loss':None,'total_steps':None})
    io.write(delivery/'allocation_status_at_reader_freeze.json',dict(rows=census,allocated=684,not_started=648,task_metrics_for_unstarted_cases_are_null=True))
    io.write(out/'preserved_sources.json',protected)
    names=set(e.OWN)|{'docs/research/occam_reference_train_v2_prior_art_update_zh.md'}
    names|={p.relative_to(ROOT).as_posix() for p in raw.rglob('*') if p.is_file() and p.name not in ('events.jsonl.gz','witnesses.jsonl.gz')}
    names|={p.relative_to(ROOT).as_posix() for p in pipeline.rglob('*') if p.is_file()}
    names|={p.relative_to(ROOT).as_posix() for p in (e.TARGET,e.TARGET.parent/'seed_scope_audit.json')}
    names|={p.relative_to(ROOT).as_posix() for p in delivery.rglob('*') if p.is_file() and not p.is_relative_to(restore)}
    names|={p.relative_to(ROOT).as_posix() for p in (e.BASE/'development_validation_v1').rglob('*') if p.is_file()}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file()}
        path=out/(label+'.nul');names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.gz'):data=gzip.decompress(data)
            scan(data,n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged diff');return actual
    stage('owned_initial');run('tracked_secret_script.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    stage('owned_checked');proof=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=proof,actual_index_basic_extra_decoded_scan=True,record_parts_decoded_scan=True))
    for n,h in {**source,**protected,**previous}.items():io.require(io.sha(ROOT/n)==h,'source or records changed '+n)
    io.write(out/'complete.json',dict(integrity='PASSED',source_manifest_id=m['manifest_id'],source_sha256=source,preserved_source_sha256=protected,
        unique_test_total=2578,new_unique_tests=7,reused_unique_tests=2571,repeated_population_regressions=5,formal_test_executions=12,
        source_reuse_sha256=io.sha(out/'source_reuse.json'),guard=guard,policy_queries=0,new_environment_interactions=0,scientific_model_training=0,
        scientific_CAL_QUAL_opened=False,online_LLM_API_calls=0,original_pipeline_failure_preserved=True,NATIVE_recollection_allowed=False,
        only_unstarted_original_TRAIN_may_continue_after_native_audit=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),new_unique_tests=7,new_physics=0),flush=True)


if __name__=='__main__':main()
