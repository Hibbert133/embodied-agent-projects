"""Owned freeze, source-reused old checks, no physical activity or online LLM."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter_ns
import shutil,subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io;OUT=Path(__file__).parent


def command(name,args):
    start=perf_counter_ns();r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
    io.write(OUT/name,dict(command=args,returncode=r.returncode,stdout=r.stdout,stderr=r.stderr,wall_ns=perf_counter_ns()-start))
    io.require(r.returncode==0,'freeze check failed '+name)


def stage(names,label):
    p=OUT/(label+'.nul');names=set(names)|{p.relative_to(ROOT).as_posix()}
    p.write_bytes(b'\0'.join(n.encode('utf8') for n in sorted(names))+b'\0')
    for flags in ((),('--renormalize',)):
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    return names


def main():
    io.require(not io.git('diff','--cached','--name-only'),'empty index before owned freeze')
    prior=io.read(ROOT/'outputs/research_ideation/round_v1/source_binding.json');io.require(prior['integrity']=='PASSED','old passed source binding')
    for n,h in prior['unchanged_source_sha256'].items():io.require(io.sha(ROOT/n)==h,'old check source drift '+n)
    for n,h in prior['prior_test_receipt_sha256'].items():io.require(io.sha(ROOT/n)==h,'old check receipt drift '+n)
    io.write(OUT/'source_reuse.json',dict(integrity='PASSED',source_reused_unique_tests=2022,old_tensor_groups_separate=6,
        source_sha256=prior['unchanged_source_sha256'],previous_binding_sha256=io.sha(ROOT/'outputs/research_ideation/round_v1/source_binding.json'),
        receipt_sha256=prior['prior_test_receipt_sha256'],no_old_simulation_tests_repeated=True))
    names={p.relative_to(ROOT).as_posix() for parent in ('src','scripts','tests') for p in (ROOT/parent).rglob('*correction_scope*v1.py')}
    names|={p.relative_to(ROOT).as_posix() for p in (a.CONFIG,a.PROTOCOL,a.SEEDS,ROOT/'docs/research/correction_scope_decision_v1_zh.md',Path(__file__))}
    names|={'AGENTS.md','.gitattributes'}
    before={n:io.sha(ROOT/n) for n in sorted(names)};io.write(OUT/'source_before_checks.json',before)
    io.require(io.read(a.CONFIG)==a.config() and io.read(a.SEEDS)==a.registry(),'exact prospective configuration')
    io.write(OUT/'seed_scope.json',a.seed_scope());guard={};start=perf_counter_ns()
    with (OUT/'unit.log').open('x',encoding='utf8') as f:
        suite=unittest.defaultTestLoader.discover('tests',pattern='test_correction_scope_v1.py')
        with read_only(guard,max_solve=1,max_lstsq=1):r=unittest.TextTestRunner(stream=f,verbosity=2).run(suite)
    io.write(OUT/'unit_receipt.json',dict(integrity='PASSED' if r.wasSuccessful() else 'FAILED',tests=r.testsRun,
        failures=len(r.failures),errors=len(r.errors),wall_ns=perf_counter_ns()-start,guard=guard,
        scientific_model_fits=0,synthetic_model_solves=guard['operation_counts']['solve_attempts'],synthetic_refits=guard['operation_counts']['lstsq_attempts']))
    io.require(r.wasSuccessful() and r.testsRun==23,'all23 new array/saved-record checks')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(command,'compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']),
                 pool.submit(command,'dependencies.json',[sys.executable,'-m','pip','check'])]
        for f in futures:f.result()
    compile(Path(__file__).read_bytes(),str(__file__),'exec')
    runtime=ROOT/'outputs/memory_reset/validation_v1/runtime_lock.json';verify_runtime(io.read(runtime));shutil.copyfile(runtime,OUT/'runtime_lock.json')
    for n,h in before.items():io.require(io.sha(ROOT/n)==h,'source changed during checks '+n)
    allnames=names|{p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    allowed=stage(allnames,'owned_paths_v1')
    command('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    command('ordinary_diff.json',['git','diff','--check']);command('staged_diff.json',['git','diff','--cached','--check'])
    allowed=stage(allowed|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()},'owned_paths_v2')
    verified=index_bytes(allowed)
    for n in verified:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            value=data.decode('utf8',errors='replace')
            for label,pattern in EXTRA.items():io.require(pattern.search(value) is None,'additional staged secret pattern '+label+' '+n)
    io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=verified,extra_provider_and_GitHub_patterns='PASSED'))
    receipts={p.name:io.sha(p) for p in OUT.iterdir() if p.is_file()}
    io.write(OUT/'complete.json',dict(integrity='PASSED',source_sha256=before,receipt_sha256=receipts,new_unique_tests=23,
        source_reused_unique_tests=2022,cumulative_unique_tests=2045,old_tensor_groups_separate=6,
        new_physical_activity=0,new_scientific_fits=0,online_LLM_API_calls=0,publication_goal_complete=False))
    allowed=stage(allowed|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()},'owned_paths_v3')
    final=index_bytes(allowed);io.require(not io.git('diff','--cached','--check'),'final staged whitespace check')
    print(dict(integrity='PASSED',new_unique_tests=23,source_reused_tests=2022,owned_index_objects=len(final),new_physics=0),flush=True)


if __name__=='__main__':main()
