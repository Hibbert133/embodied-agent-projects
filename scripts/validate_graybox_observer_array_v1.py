"""Freeze a standard reference's array implementation, not a sampling protocol."""
from pathlib import Path
from time import perf_counter_ns
from contextlib import ExitStack
from unittest.mock import patch
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis.release_learning_guard_v1 import read_only
from src.probe import graybox_observer_v1 as model
from src.analysis import graybox_observer_independent_v1 as independent
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=ROOT/'outputs/graybox_observer/array_implementation_v1'
OWN=('src/probe/graybox_observer_v1.py','src/analysis/graybox_observer_independent_v1.py','tests/test_graybox_observer_v1.py',
     'docs/research/graybox_observer_reference_v1_zh.md','scripts/validate_graybox_observer_array_v1.py')

def main():
    start=perf_counter_ns();assert OUT.is_dir() and not (OUT/'complete.json').exists()
    io.require(not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only'),'unchanged tracked science sources and empty index')
    prior_path=ROOT/'outputs/episode_seed_inventory/delivery_validation_v2/source_reuse.json';prior=io.read(prior_path)
    io.require(prior['integrity']=='PASSED' and prior['unique_tests']==2348,'source-bound prior checks')
    for n,h in prior['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged old source '+n)
    before={n:io.sha(ROOT/n) for n in OWN};io.write(OUT/'source_before_tests.json',before)
    suite=unittest.defaultTestLoader.loadTestsFromName('tests.test_graybox_observer_v1');ids=[]
    def collect(s):
        for test in s:
            if isinstance(test,unittest.TestSuite):collect(test)
            else:ids.append(test.id())
    collect(suite);guard={};counts={};t=perf_counter_ns()
    def counted(obj,name,label):
        fn=getattr(obj,name)
        def call(*args,**kw):
            counts[label]=counts.get(label,0)+1;io.require(counts[label]<=10000,'constructed numerical operation cap '+label)
            return fn(*args,**kw)
        return patch.object(obj,name,call)
    original_fit=model.fit_nominal_grid
    def fit(*args,**kw):
        counts['constructed_grid_fit_attempts']=counts.get('constructed_grid_fit_attempts',0)+1
        result=original_fit(*args,**kw)
        counts['constructed_grid_fits_completed']=counts.get('constructed_grid_fits_completed',0)+1
        counts['constructed_grid_candidates']=counts.get('constructed_grid_candidates',0)+len(result['per_candidate_per_axis_nll'])
        return result
    import numpy as np
    with (OUT/'tests.log').open('x',encoding='utf8',newline='\n') as log,read_only(guard),ExitStack() as stack:
        for obj,name,label in ((model,'advance','main_axis_predict_attempts'),(model,'observe','main_axis_observe_attempts'),
            (model,'moments','main_gaussian_moment_attempts'),(independent,'predict','independent_axis_predictions'),
            (independent,'update','independent_axis_updates'),(independent,'clipped_moments','independent_moment_calls'),
            (independent,'quad','independent_quadrature_calls'),(np.linalg,'eigvalsh','covariance_eigenvalue_checks')):
            stack.enter_context(counted(obj,name,label))
        stack.enter_context(patch.object(model,'fit_nominal_grid',fit))
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    io.write(OUT/'test_receipt.json',dict(tests=result.testsRun,unique_test_ids=ids,success=result.wasSuccessful(),guard=guard,constructed_numerical_counts=counts,
        wall_ns=perf_counter_ns()-t,source_sha256=before,physical_or_scientific_training_samples=0))
    io.require(result.wasSuccessful() and result.testsRun==len(set(ids))==28,'all28 new pure numerical/interface checks')
    io.require(counts['constructed_grid_candidates']==9 and counts['constructed_grid_fits_completed']==1,'one constructed finite grid fit, nine candidates')
    for n,h in before.items():io.require(io.sha(ROOT/n)==h,'checked source unchanged '+n)
    io.write(OUT/'source_reuse.json',dict(integrity='PASSED',unique_tests=2376,new_unique_tests=28,reused_unique_tests=2348,
        source_sha256=prior['source_sha256'],prior_receipt_sha256=io.sha(prior_path),old_simulation_tests_repeated=False))
    def run(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(OUT/name,dict(args=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t));io.require(p.returncode==0,name)
    names=set(OWN)
    def stage(label):
        nonlocal names
        names|={p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file()}
        spec=OUT/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
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
    io.write(OUT/'complete.json',dict(integrity='PASSED',source_sha256=before,new_unique_tests=28,unique_test_total=2376,
        constructed_numerical_counts=counts,earlier_constructed_grid_candidates_separately_retained=9,
        receipt_sha256={p.name:io.sha(p) for p in OUT.iterdir() if p.is_file()},new_physics=0,new_scientific_model_fits=0,
        new_episode_seed_allocations=0,online_LLM_API_calls=0,physical_prediction_qualified=False,full_task_benefit_established=False,
        scientific_collection_protocol_frozen=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
    stage('owned_final');check();print(dict(integrity='PASSED',owned_objects=len(names),new_tests=28,reused_tests=2348,scientific_collection='NOT_STARTED'),flush=True)

if __name__=='__main__':main()
