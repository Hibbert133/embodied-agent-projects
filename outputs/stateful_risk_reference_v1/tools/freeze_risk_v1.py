"""Source-bound software freeze; no original case parse or actual run before commit."""
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import json
import subprocess
import sys
import unittest
import run_risk_v1 as r

sys.path.insert(0,str(r.ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def main():
    started=perf_counter_ns();out=r.FREEZE.parent
    r.need(r.git('rev-parse','HEAD').decode().strip()==r.PARENT and not r.git('status','--porcelain','--untracked-files=no').strip(),'clean original parent')
    r.need(not r.OUT.exists(),'finite validation not started');out.mkdir(exist_ok=False)
    source={p.relative_to(r.ROOT).as_posix():r.sha(p) for p in r.sources()}
    inputs={p.relative_to(r.ROOT).as_posix():r.sha(p) for p in r.inputs()}
    r.need(r.sha(r.CASE_SOURCE)==r.CASE_SHA,'unchanged source case contracts')
    old=r.read(r.ROOT/'outputs/train_decision_contract_v1/freeze_v1/complete.json')
    science=old['scientific_source_sha256'];r.verify(science)
    checks=r.read(r.ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json')
    r.need(checks['integrity']=='PASSED' and checks['unique_tests']==2695,'prior source-bound checks')
    r.need(r.sha(r.ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/validation_receipt.json')==checks['validation_receipt_sha256'],'prior receipt bytes')
    def deny(*args,**kw):raise RuntimeError('formal tests forbid original JSON data reads')
    with (out/'unit.log').open('x',encoding='utf-8',newline='\n') as log:
        with mock.patch.object(r,'read',deny):
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('test_risk_v1'))
    r.need(result.wasSuccessful() and result.testsRun==22,'22 pure constructed tests')
    r.write(out/'unit_receipt.json',dict(integrity='PASSED',unique_tests=22,formal_executions=22,
        constructed_only=True,actual_scientific_JSON_parses=0,intentional_guard_rejections=True,counters=r.ZERO))
    with (out/'pip_stdout.log').open('xb') as so,(out/'pip_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','-m','pip','check'],cwd=r.ROOT,stdout=so,stderr=se)
    r.need(p.returncode==0,'dependencies')
    r.verify(source);r.verify(inputs);r.verify(science)
    r.write(r.FREEZE,dict(integrity='FROZEN_STANDARD_STATEFUL_RISK_REFERENCE_V1',source_parent_commit=r.PARENT,
        source_sha256=source,input_sha256=inputs,scientific_source_sha256=science,new_unique_tests=22,
        development_executions=22,formal_executions=22,prior_scientific_checks_reused=2695,
        actual_finite_validation_started=False,original_terminal_count_previously_post_hoc_inspected=True,
        no_new_robot_experiment=True,no_training_or_deployment=True,worker_hard_timeout_seconds=60,
        counters=r.ZERO,publication_goal_complete=False))
    owned={p.relative_to(r.ROOT).as_posix() for p in r.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}|set(r.DOCS)
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(r.ROOT).as_posix())
        spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(r.ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='22_REFERENCE_CORE_TESTS_PASSED_BEFORE_FROZEN_RUN',files=len(owned))),flush=True)
    scan=perf_counter_ns()
    with (out/'secret_stdout.log').open('xb') as so,(out/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=r.ROOT,stdout=so,stderr=se)
    r.write(out/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan,
        all_tracked_worktree_scan=True,actual_index_basic_and_EXTRA_separate=True))
    r.need(p.returncode==0,'secret scan')
    owned.update(p.relative_to(r.ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_checked')
    r.write(out/'index_disk_proof.json',dict(integrity='PASSED',objects=check_index(owned)))
    r.verify(source);r.verify(inputs);r.verify(science)
    r.write(out/'delivery_validation.json',dict(integrity='PASSED_STANDARD_REFERENCE_CORE_FREEZE',new_unique_tests=22,
        source_bound_original_scientific_checks_reused=2695,no_simulation_tests_repeated=True,
        dependency_returncode=0,secret_returncode=0,ordinary_and_staged_diff_checks=True,
        actual_index_BASIC_EXTRA_scan=True,new_Python_compiled_in_memory=True,
        source_IO=r.shared.IO,wall_ns=perf_counter_ns()-started,counters=r.ZERO))
    owned.update(p.relative_to(r.ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final')
    objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_STANDARD_REFERENCE_FREEZE_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
