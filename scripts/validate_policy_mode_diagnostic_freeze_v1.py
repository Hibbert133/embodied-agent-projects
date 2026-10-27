"""Freeze only checked owned diagnostic sources; no factual trajectory reads."""
from pathlib import Path
from time import perf_counter_ns
from contextlib import ExitStack
from unittest.mock import patch
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_policy_mode_diagnostic_v1 as entry
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=entry.io


def main():
    started=perf_counter_ns();out=entry.BASE/'freeze_validation_v1';out.mkdir(parents=True,exist_ok=False)
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'unchanged previous tracked sources and empty index')
    io.require(io.read(entry.CONFIG)==entry.config(),'exact source-only configuration')
    previous=ROOT/'outputs/controller_agreement/freeze_validation_v1/source_reuse.json';phase=ROOT/'outputs/controller_agreement/freeze_validation_v1/complete.json'
    prior=io.read(previous);complete=io.read(phase);io.require(prior['integrity']==complete['integrity']=='PASSED' and complete['unique_test_total']==2448,'2448 prior source-bound checks')
    old={**prior['source_sha256'],**complete['source_sha256']}
    for n,h in old.items():io.require(io.sha(ROOT/n)==h,'unchanged tested source '+n)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    before={n:io.sha(ROOT/n) for n in (*entry.OWN,*entry.DOCS)};guard={};calls={};ids=[]
    from metaworld.policies import SawyerPushV3Policy,SawyerReachV3Policy,SawyerDoorOpenV3Policy
    def count(cls):
        fn=cls.get_action
        def f(self,*args,**kw):
            label=cls.__name__;calls[label]=calls.get(label,0)+1;io.require(sum(calls.values())<=18,'synthetic policy query cap18');return fn(self,*args,**kw)
        return patch.object(cls,'get_action',f)
    with (out/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard),ExitStack() as stack:
        for cls in (SawyerPushV3Policy,SawyerReachV3Policy,SawyerDoorOpenV3Policy):stack.enter_context(count(cls))
        suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_policy_mode_diagnostic_v1')
        def collect(s):
            for t in s:
                if isinstance(t,unittest.TestSuite):collect(t)
                else:ids.append(t.id())
        collect(suite);result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(out/'tests.json',dict(success=result.wasSuccessful(),tests=result.testsRun,ids=ids,guard=guard,synthetic_policy_calls=calls,source_sha256=before))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==15 and sum(calls.values())==18,'15 pure checks,18 synthetic-only installed policy calls')
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2463,new_tests=15,reused_tests=2448,source_sha256=old,
        prior_receipt_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in (previous,phase)},old_simulation_tests_repeated=False))
    io.write(out/'source_contract.json',entry.contract())
    names=set(entry.OWN)|set(entry.DOCS)
    development=entry.BASE/'development_validation_v1'
    if development.exists():names|={p.relative_to(ROOT).as_posix() for p in development.rglob('*') if p.is_file()}
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
        path=out/(label+'.nul');names.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,p in EXTRA.items():io.require(p.search(data.decode('utf8',errors='replace')) is None,'actual staged credential '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'ordinary and staged diff checks');return actual
    run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check'])
    stage('owned_initial');run('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py'])
    stage('owned_checked');actual=check();io.write(out/'index_disk_proof.json',dict(integrity='PASSED',actual_index_extra_scan=True,object_sha256=actual))
    for n,h in before.items():io.require(io.sha(ROOT/n)==h,'checked source changed '+n)
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256=before,unique_test_total=2463,new_tests=15,reused_tests=2448,guard=guard,
        synthetic_policy_calls=calls,scientific_trajectories_read=False,new_physics=0,new_fits=0,online_LLM_API_calls=0,
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},wall_ns=perf_counter_ns()-started,publication_goal_complete=False))
    stage('owned_final');check();print(dict(integrity='PASSED',objects=len(names),unique_tests=2463,science='NOT_STARTED'),flush=True)


if __name__=='__main__':main()
