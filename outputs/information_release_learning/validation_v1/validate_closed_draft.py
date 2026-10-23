"""Check and preserve the closed design, never freeze or start a robot study."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis import release_learning_io_v1 as design
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.release_learning_equivalence_v1 import check
OUT=Path(__file__).parent


def command(name,args):
    started=perf_counter_ns()
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    io.write(OUT/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-started))
    io.require(p.returncode==0,'closed-draft check '+name)


def main():
    started=perf_counter_ns();prior={}
    for filename in ('complete.json','source_reuse.json'):
        path=ROOT/'outputs/information_release/validation_v1'/filename
        receipt=io.read(path);io.require(receipt['integrity']=='PASSED','previous passed source-bound checks')
        for name,h in receipt['source_sha256'].items():
            io.require(io.sha(ROOT/name)==h,'previous test source changed '+name);prior[name]=h
    io.require(io.read(ROOT/'outputs/information_release/validation_v1/complete.json')['cumulative_unique_tests']==1984,'exact prior unique count')
    io.write(OUT/'source_reuse.json',dict(integrity='PASSED',source_reused_unique_tests=1984,source_sha256=prior,
        old_tensor_groups_separate=6,no_old_simulation_tests_repeated=True))
    names={p.relative_to(ROOT).as_posix() for base in ('src/analysis','src/probe') for p in (ROOT/base).glob('release_learning_*_v1.py')}
    names|={'tests/test_release_learning_v1.py','scripts/run_release_learning_v1.py',(OUT/'validate_closed_draft.py').relative_to(ROOT).as_posix()}
    names|={p.relative_to(ROOT).as_posix() for p in (design.CONFIG,design.PROTOCOL,design.SEEDS)}
    source={n:io.sha(ROOT/n) for n in sorted(names)};io.write(OUT/'source_before_checks.json',source)
    guard={};unit_started=perf_counter_ns()
    with (OUT/'unit.log').open('x',encoding='utf-8') as log:
        with read_only(guard,max_solve=5,max_lstsq=1):
            suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_release_learning_v1')
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(OUT/'unit_receipt.json',dict(integrity='PASSED' if result.wasSuccessful() else 'FAILED',new_unique_tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),wall_ns=perf_counter_ns()-unit_started,guard=guard,
        earlier_16_and22_test_runs_not_added_to_unique_count=True))
    io.require(result.wasSuccessful() and result.testsRun==25,'all25 closed-draft array checks')
    io.require(not any(guard['operation_counts'][k] for k in ('environment_creations','resets','simulation','cold_fit_attempts','cold_estimator_entries')),
        'no new physical operations or C4/C8 fitting')
    io.require(guard['network']=={'attempted_network_calls':0},'no network attempts in array validation')
    eq_guard={};eq_started=perf_counter_ns()
    with read_only(eq_guard,max_solve=3):equivalence=check()
    io.write(OUT/'equivalence.json',dict(**equivalence,guard=eq_guard,wall_ns=perf_counter_ns()-eq_started,
        source_sha256=source,constructed_not_robot_or_independent_statistical_samples=True))
    io.require(design.config()['collection_status']=='CLOSED_BEFORE_COLLECTION' and not list(design.OUTPUT.glob('*/manifest.json')),
        'no new experiment manifest or executed population')
    for n,h in source.items():io.require(io.sha(ROOT/n)==h,'checked source changed '+n)
    command('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests'])
    compile((OUT/'validate_closed_draft.py').read_bytes(),str(OUT/'validate_closed_draft.py'),'exec')
    command('dependencies.json',[sys.executable,'-m','pip','check'])
    command('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    command('ordinary_diff.json',['git','diff','--check'])
    io.write(OUT/'complete.json',dict(integrity='PASSED',classification='CLOSED_DRAFT_ARRAY_VALIDATION_ONLY',source_sha256=source,
        new_unique_tests=25,source_reused_unique_tests=1984,cumulative_unique_tests=2009,old_tensor_groups_separate=6,
        unit_synthetic_solves=guard['operation_counts']['solve_attempts'],unit_synthetic_lstsq=guard['operation_counts']['lstsq_attempts'],
        separate_equivalence_synthetic_solves=eq_guard['operation_counts']['solve_attempts'],
        environment_steps=0,all_resets=0,physical_frames=0,scientific_model_fits=0,legacy_c4_c8_refits=0,online_LLM_API_calls=0,
        native_qualified=False,task_benefit_established=False,novelty_established=False,publication_goal_complete=False,
        whole_validation_wall_ns=perf_counter_ns()-started,
        receipt_sha256={p.name:io.sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='complete.json'}))
    print(dict(integrity='PASSED',new_unique_tests=25,reused_unique_tests=1984,closed_before_collection=True,
        scientific_model_fits=0,new_physics=0,online_LLM_API_calls=0),flush=True)


if __name__=='__main__':main()
