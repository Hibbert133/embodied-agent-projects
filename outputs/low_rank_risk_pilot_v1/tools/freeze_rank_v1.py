"""Freeze the learning pilot before real TRAIN parses, fits or fold evaluation."""
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import json
import subprocess
import sys
import unittest
import numpy as np
import run_rank_v1 as r

sys.path.insert(0,str(r.ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def main():
    start=perf_counter_ns();out=r.FREEZE.parent
    r.need(r.git('rev-parse','HEAD').decode().strip()==r.PARENT and not r.git('status','--porcelain','--untracked-files=no').strip(),'unchanged source parent')
    r.need(not r.OUT.exists(),'no scientific fit before software freeze');out.mkdir(exist_ok=False)
    source={p.relative_to(r.ROOT).as_posix():r.sha(p) for p in r.sources()}
    inputs={p.relative_to(r.ROOT).as_posix():r.sha(p) for p in r.inputs()}
    r.need(r.sha(r.GRAPH)==r.GRAPH_SHA,'frozen complete-cross TRAIN graph')
    receipt=r.read(r.OLD/'fit_receipt.json');r.need(receipt['graphs_sha256']['TRAIN']==r.GRAPH_SHA,'old source extraction proof')
    r.need(r.read(r.OLD/'model_audit.json')['integrity']=='PASSED' and r.read(r.OLD/'replay_audit.json')['integrity']=='PASSED','passed source audits')
    old=r.read(r.ROOT/'outputs/stateful_risk_reference_v1/freeze_v1/complete.json');science=old['scientific_source_sha256'];r.verify(science)
    checks=r.read(r.ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json')
    r.need(checks['integrity']=='PASSED' and checks['unique_tests']==2695,'old source-bound scientific checks')
    r.need(r.sha(r.ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/validation_receipt.json')==checks['validation_receipt_sha256'],'old scientific receipt bytes')
    def deny(*args,**kw):raise RuntimeError('constructed tests cannot read original scientific graph')
    with (out/'unit.log').open('x',encoding='utf-8',newline='\n') as log:
        with mock.patch.object(r,'graphs',deny):
            suite=unittest.defaultTestLoader.loadTestsFromName('test_rank_v1');result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    r.need(result.wasSuccessful() and result.testsRun==22,'22 constructed numeric/data-contract checks')
    import test_rank_v1 as tests
    r.write(out/'unit_receipt.json',dict(integrity='PASSED',unique_tests=22,constructed_only=True,original_graph_semantic_parses=0,
        formal_synthetic_learning_ledger=tests.SYNTHETIC_LEDGER,formal_synthetic_independent_ledger=tests.INDEPENDENT_LEDGER,
        development_test_executions=22,development_ledger_not_captured_in_original_terminal_invocation=True,
        same_code_ledger_may_only_be_inferred_not_claimed_measured=True,
        explicit_original_intercept_reference_solves=2,other_matrix_check_operations_not_scientific_fits=True,
        intentional_guard_rejections=True,counters=r.ZERO))
    with (out/'pip_stdout.log').open('xb') as so,(out/'pip_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','-m','pip','check'],cwd=r.ROOT,stdout=so,stderr=se)
    r.need(p.returncode==0,'dependencies')
    r.verify(source);r.verify(inputs);r.verify(science)
    r.write(r.FREEZE,dict(integrity='FROZEN_TRAIN_ONLY_LOW_RANK_RISK_PILOT_V1',source_parent_commit=r.PARENT,
        source_sha256=source,input_sha256=inputs,scientific_source_sha256=science,new_unique_tests=22,
        old_scientific_checks_source_bound_reused=2695,source_graph_sha256=r.GRAPH_SHA,
        primary_model='RBF_RR2',source_units=54,source_groups=9,source_cases=648,
        numeric_TRAIN_parses_before_freeze=0,scientific_model_solutions_before_freeze=0,
        risk_model_solution_cap=180,shared_linear_solve_cap=20,symmetric_eigendecomposition_cap=50,
        independent_augmented_LS_cap=20,independent_QR_cap=20,independent_kernel_eig_cap=20,
        independent_rank_SVD_cap=40,independent_PCA_SVD_cap=20,
        worker_wall_cap_seconds=1800,output_disk_cap_bytes=100*1024**2,minimum_free_disk_bytes=256*1024**2,
        no_new_environment_or_robot_seeds=True,counters=r.ZERO,publication_goal_complete=False))
    owned={p.relative_to(r.ROOT).as_posix() for p in r.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}|set(r.DOCS)
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(r.ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(r.ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='22_SYNTHETIC_CHECKS_PASSED_NO_SCIENTIFIC_FIT',files=len(owned))),flush=True)
    scan=perf_counter_ns()
    with (out/'secret_stdout.log').open('xb') as so,(out/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=r.ROOT,stdout=so,stderr=se)
    r.write(out/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan,
        all_tracked_worktree_scan=True,actual_index_BASIC_EXTRA_separate=True))
    r.need(p.returncode==0,'secret scan blocks freeze')
    owned.update(p.relative_to(r.ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_checked')
    r.write(out/'index_disk_proof.json',dict(integrity='PASSED',objects=check_index(owned)))
    r.verify(source);r.verify(inputs);r.verify(science)
    r.write(out/'delivery_validation.json',dict(integrity='PASSED_LEARNING_PILOT_SOFTWARE_FREEZE',new_unique_tests=22,
        prior_scientific_checks_reused=2695,dependency_returncode=0,secret_returncode=0,
        compiled_new_Python_in_memory=True,ordinary_and_staged_diff_checks=True,
        original_scientific_graph_parses=0,source_IO=r.shared.IO,wall_ns=perf_counter_ns()-start,counters=r.ZERO))
    owned.update(p.relative_to(r.ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final')
    objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_LOW_RANK_PILOT_FREEZE_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
