"""Source-bound unchanged tests; math will be independently checked after freeze."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts import run_staggered_selective_scope_v1 as command
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=command.main;io=main.io;BASE=main.BASE

def freeze():
    out=BASE/'freeze_validation';out.mkdir(exist_ok=False);start=perf_counter_ns()
    config=io.read(main.CONFIG);io.require(config['delays']==list(main.DELAYS) and config['rounds_per_thread']==main.ROUNDS and config['alpha_fraction']==main.encode(main.ALPHA),'exact configuration and arithmetic source')
    io.require(config['forecasts']==12400 and config['events']==37210 and config['new_unit_tests_claimed']==0,'registered exact counts and no invented test additions')
    old=ROOT/'outputs/correction_scope/effect_horizon_v1/result_validation/source_reuse.json';reuse=io.read(old);io.require(reuse['unique_tests']==2228,'source-bound old2228')
    for n,h in reuse['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged old source '+n)
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    io.require(not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only'),'clean tracked files and index before scope freeze')
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2228,new_unit_tests=0,source_sha256=reuse['source_sha256'],
        prior_receipt_sha256=io.sha(old),old_simulation_tests_repeated=False,old_six_tensor_groups_separate=True,exact_construction_and_integer_audit_pending_frozen_run=True))
    names=set(command.SOURCES)|{p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,'scope freeze '+name)
    def verify(selected):
        actual=index_bytes(selected)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'extra staged secret '+label+' '+n)
        io.require(not io.git('diff','--check') and not io.git('diff','--cached','--check'),'scope diff checks');return actual
    names=stage(names,'owned_initial');run('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);run('dependencies.json',[sys.executable,'-m','pip','check'])
    run('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_scan');actual=verify(names)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,extra_secret_patterns='PASSED'))
    io.write(out/'complete.json',dict(integrity='PASSED',source_sha256={n:io.sha(ROOT/n) for n in command.SOURCES},unique_test_total=2228,new_unique_tests=0,
        old_unique_tests_reused=2228,mathematical_validation='PENDING_FROZEN_EXACT_GENERATION_AND_INDEPENDENT_INTEGER_AUDIT',
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},new_physics=0,new_model_fits=0,online_LLM_API_calls=0,
        original_native_qualification='FAILED_RETAINED',publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');verify(names)
    print(dict(integrity='PASSED',unique_source_bound_reused_tests=2228,new_unit_tests=0,mathematical_audit='pending frozen run'),flush=True)
if __name__=='__main__':freeze()
