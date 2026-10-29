"""Freeze constructed information constraints before actual TRAIN inspection."""
from time import perf_counter_ns
from unittest import mock
import json
import subprocess
import sys
import unittest
import run_frontier_v1 as r

sys.path.insert(0,str(r.ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def main():
    started=perf_counter_ns();out=r.FREEZE.parent
    r.need(r.git('rev-parse','HEAD').decode().strip()==r.PARENT and not r.git('status','--porcelain','--untracked-files=no').strip(),'clean source parent')
    r.need(not r.OUT.exists(),'actual analysis not started');out.mkdir(exist_ok=False)
    source={p.relative_to(r.ROOT).as_posix():r.sha(p) for p in r.sources()}
    ins={p.relative_to(r.ROOT).as_posix():r.sha(p) for p in r.inputs()}
    r.need(r.sha(r.GRAPH)==r.GRAPH_SHA and r.read(r.OLD/'fit_receipt.json')['graphs_sha256']['TRAIN']==r.GRAPH_SHA,'frozen TRAIN source')
    r.need(r.read(r.OLD/'model_audit.json')['integrity']=='PASSED' and r.read(r.OLD/'replay_audit.json')['integrity']=='PASSED','prior complete source audits')
    science=r.read(r.ROOT/'outputs/low_rank_risk_recovery_v2/freeze_v1/complete.json')['scientific_source_sha256'];r.verify(science)
    old=r.read(r.ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json')
    r.need(old['integrity']=='PASSED' and old['unique_tests']==2695,'old source-bound scientific receipt')
    r.need(r.sha(r.ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/validation_receipt.json')==old['validation_receipt_sha256'],'exact original check receipt')
    def deny(*args,**kwargs):raise RuntimeError('constructed tests cannot read scientific graph')
    with (out/'unit.log').open('x',encoding='utf-8',newline='\n') as log:
        with mock.patch.object(r,'graphs',deny):
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('test_frontier_v1'))
    r.need(result.wasSuccessful() and result.testsRun==15,'fifteen constructed information/support tests')
    r.write(out/'unit_receipt.json',dict(integrity='PASSED',unique_tests=15,synthetic_future_tables_only=True,
        real_graph_parses=0,predictive_fits_and_queries=0,oracle_table_optimization_in_tests_disclosed=True,counters=r.ZERO))
    with (out/'pip_stdout.log').open('xb') as so,(out/'pip_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','-m','pip','check'],cwd=r.ROOT,stdout=so,stderr=se)
    r.need(p.returncode==0,'dependency check')
    r.write(r.FREEZE,dict(integrity='FROZEN_OBSERVABLE_FRONTIER_DIAGNOSTIC_V1',source_parent_commit=r.PARENT,
        source_sha256=source,input_sha256=ins,scientific_source_sha256=science,new_tests=15,prior_source_bound_scientific_tests=2695,
        source_graph_sha256=r.GRAPH_SHA,source_cases=648,source_units=54,groups=9,uses_future_labels=True,deployable=False,
        actual_TRAIN_graph_parses_before_freeze=0,independent_plan_enumeration_cap=1_000_000,
        hard_timeout_seconds=600,output_cap_bytes=64*1024**2,minimum_analysis_free_space=256*1024**2,counters=r.ZERO,publication_goal_complete=False))
    owned={p.relative_to(r.ROOT).as_posix() for p in r.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}|set(r.DOCS)
    def stage(label):
        spec=out/(label+'.nul');owned.add(spec.relative_to(r.ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(r.ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='15_SYNTHETIC_INFORMATION_CHECKS_PASSED',files=len(owned))),flush=True)
    scan=perf_counter_ns()
    with (out/'secret_stdout.log').open('xb') as so,(out/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=r.ROOT,stdout=so,stderr=se)
    r.write(out/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan));r.need(p.returncode==0,'secrets block freeze')
    owned.update(p.relative_to(r.ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_checked')
    r.write(out/'index_disk_proof.json',dict(integrity='PASSED',objects=check_index(owned)))
    for binding in (source,ins,science):r.verify(binding)
    r.write(out/'delivery_validation.json',dict(integrity='PASSED_OBSERVABLE_FRONTIER_FREEZE',new_tests=15,
        dependency_returncode=0,secret_returncode=0,source_bound_2695_scientific_receipt_reused=True,
        actual_index_basic_EXTRA_scan=True,compiled_new_Python_in_memory=True,ordinary_and_staged_diff_checks=True,
        actual_scientific_semantic_parses=0,source_IO=r.io.IO,wall_ns=perf_counter_ns()-started,counters=r.ZERO))
    owned.update(p.relative_to(r.ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final');objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_OBSERVABLE_FRONTIER_FREEZE_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
