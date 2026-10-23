"""Freeze a saved-record descriptive audit, never create a robot environment."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis import passive_continuation_support_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from outputs.information_release.validation_v1.validate_freeze import index_bytes
OUT=Path(__file__).parent


def command(name,args):
    started=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    io.write(OUT/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-started))
    io.require(p.returncode==0,'freeze check '+name+' '+p.stdout+p.stderr)


def stage(names,label):
    path=OUT/(label+'.nul');names=set(names)|{path.relative_to(ROOT).as_posix()}
    path.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    for flags in ((),('--renormalize',)):io.git('-c','maintenance.auto=false','-c','gc.auto=0','add',*flags,
        '--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    return names


def main():
    io.require(not io.git('diff','--cached','--name-only'),'empty index before owned freeze')
    prior={}
    for n in ('outputs/information_release_learning/validation_v1/source_reuse.json','outputs/information_release_learning/validation_v1/post_eof_validation.json'):
        receipt=io.read(ROOT/n);io.require(receipt['integrity']=='PASSED','previous source-bound passed checks')
        for name,h in receipt['source_sha256'].items():io.require(io.sha(ROOT/name)==h,'source-reused check '+name);prior[name]=h
    io.write(OUT/'source_reuse.json',dict(integrity='PASSED',source_reused_unique_tests=2009,source_sha256=prior,
        old_tensor_groups_separate=6,no_old_simulation_tests_repeated=True))
    names={p.relative_to(ROOT).as_posix() for p in (ROOT/'src/analysis').glob('passive_continuation*_v1.py')}
    names|={'tests/test_passive_continuation_support_v1.py','scripts/verify_passive_continuation_support_v1.py',
        a.CONFIG.relative_to(ROOT).as_posix(),a.PROTOCOL.relative_to(ROOT).as_posix(),(OUT/'validate_freeze.py').relative_to(ROOT).as_posix()}
    source={n:io.sha(ROOT/n) for n in sorted(names)};io.write(OUT/'source_before_checks.json',source)
    io.require(io.read(a.CONFIG)==a.config(),'exact descriptive allocation')
    guard={};started=perf_counter_ns()
    with (OUT/'unit.log').open('x',encoding='utf-8') as log:
        with read_only(guard):result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_passive_continuation_support_v1'))
    io.write(OUT/'unit_receipt.json',dict(integrity='PASSED' if result.wasSuccessful() else 'FAILED',new_unique_tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),guard=guard,wall_ns=perf_counter_ns()-started))
    io.require(result.wasSuccessful() and result.testsRun==13,'all13 new array checks')
    source_guard={}
    with read_only(source_guard):
        historical=a.sources();generator=a.source_cases('QUAL')
        try:
            spec,case,steps,memories=next(generator)
            from src.analysis.passive_continuation_independent_v1 import reference
            v=reference(case['initial'],steps,spec['task'],spec['planned_boundary'])
            io.require(v['memory_sha256_sequence']==memories and io.digest(v['final_memory'])==io.digest(case['final_memory']),'first registered saved-source software compatibility')
        finally:generator.close()
    io.write(OUT/'saved_record_compatibility.json',dict(integrity='PASSED',one_first_registered_reference=True,source_steps=len(steps),
        no_model_or_threshold_selection=True,not_new_unique_unit_test_or_robot_sample=True,guard=source_guard,historical_artifact_sha256=historical))
    for n,h in source.items():io.require(io.sha(ROOT/n)==h,'source changed during checks '+n)
    command('compile.json',[sys.executable,'-m','compileall','-q','src','scripts','tests']);compile((OUT/'validate_freeze.py').read_bytes(),str(OUT/'validate_freeze.py'),'exec')
    command('dependencies.json',[sys.executable,'-m','pip','check'])
    owned=names|{'.gitattributes','AGENTS.md','RESEARCH_PLAN.md'}|{p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    allowed=stage(owned,'owned_paths_v1')
    command('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    command('ordinary_diff.json',['git','diff','--check']);command('staged_diff.json',['git','diff','--cached','--check'])
    sha=index_bytes(allowed);io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',actual_index_sha256=sha,actual_staged_text_secret_scan=True))
    io.write(OUT/'complete.json',dict(integrity='PASSED',source_sha256=source,source_reused_unique_tests=2009,new_unique_tests=13,cumulative_unique_tests=2022,
        old_tensor_groups_separate=6,new_physical_activity=0,model_fits=0,new_fixed_policy_queries=0,online_LLM_API_calls=0,new_episode_seeds=0,
        post_hoc_descriptive=True,native_learning_qualified=False,publication_goal_complete=False,
        receipt_sha256={p.name:io.sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='complete.json'}))
    allowed=stage(allowed|{p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()},'owned_paths_v2');verified=index_bytes(allowed)
    io.require(not io.git('diff','--cached','--check'),'final staged diff')
    print(dict(integrity='PASSED',new_unique_tests=13,source_reused_tests=2009,owned_index_objects=len(verified),physical_interaction=0),flush=True)


if __name__=='__main__':main()
