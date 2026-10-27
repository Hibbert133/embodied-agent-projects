"""Source-bound no-interaction checks, exact staged bytes, and freeze receipt."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/episode_seed_inventory/freeze_validation_v2'
OWN=('src/analysis/episode_seed_inventory_v2.py','src/analysis/episode_seed_inventory_audit_v2.py','scripts/check_episode_seed_scope_v2.py',
     'scripts/validate_episode_seed_inventory_v2.py','tests/test_episode_seed_inventory_v2.py','docs/research/episode_seed_inventory_v2_zh.md')

def main():
    start=perf_counter_ns();OUT.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'unchanged old tracked files and empty index')
    prior_path=ROOT/'outputs/history_response/result_validation_v1/source_reuse.json';prior=io.read(prior_path)
    io.require(prior['integrity']=='PASSED' and prior['unique_tests']==2318,'source-bound prior checks')
    for n,h in prior['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged old source '+n)
    before={n:io.sha(ROOT/n) for n in OWN};io.write(OUT/'source_before_tests.json',before)
    suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_episode_seed_inventory_v2');ids=[]
    def collect(s):
        for test in s:
            if isinstance(test,unittest.TestSuite):collect(test)
            else:ids.append(test.id())
    collect(suite);guard={};t=perf_counter_ns()
    with (OUT/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(OUT/'test_receipt.json',dict(tests=result.testsRun,unique_test_ids=ids,success=result.wasSuccessful(),guard=guard,wall_ns=perf_counter_ns()-t,source_sha256=before))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==30,'all30 new metadata integrity checks')
    for n,h in before.items():io.require(io.sha(ROOT/n)==h,'unchanged checked source '+n)
    io.write(OUT/'source_reuse.json',dict(integrity='PASSED',unique_tests=2348,new_unique_tests=30,reused_unique_tests=2318,
        source_sha256=prior['source_sha256'],prior_receipt_sha256=io.sha(prior_path),old_simulation_tests_repeated=False))
    names=set(OWN)|{p.relative_to(ROOT).as_posix() for p in (ROOT/'outputs/episode_seed_inventory/development_attempts_v2').iterdir() if p.is_file()}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
        spec=OUT/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(OUT/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    def check():
        actual=index_bytes(names)
        for name in actual:
            data=(ROOT/name).read_bytes()
            if b'\0' not in data:
                for label,regex in EXTRA.items():io.require(regex.search(data.decode('utf8',errors='replace')) is None,'extra indexed secret '+label+' '+name)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged differences');return actual
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check'])
    stage('owned_initial');run('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    stage('owned_checked');actual=check();io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_index_secret_scan=True))
    io.write(OUT/'complete.json',dict(integrity='PASSED',source_sha256=before,new_unique_tests=30,unique_test_total=2348,
        receipt_sha256={p.name:io.sha(p) for p in OUT.iterdir() if p.is_file()},
        new_physics=0,new_model_fits=0,new_episode_seed_allocations=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),new_tests=30,reused_tests=2318),flush=True)

if __name__=='__main__':main()
