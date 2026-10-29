"""Freeze read-only recovery without reading numeric scientific parameters."""
from time import perf_counter_ns
from unittest import mock
import json
import subprocess
import sys
import unittest
import run_saved_v2 as s

r=s.r
sys.path.insert(0,str(r.ROOT/'outputs/train_decision_contract_v1/tools'))
from freeze_contract_v1 import check_index


def main():
    started=perf_counter_ns();out=s.FREEZE.parent
    r.need(r.git('rev-parse','HEAD').decode().strip()==s.FREEZE_PARENT and not r.git('status','--porcelain','--untracked-files=no').strip(),'clean initial frozen parent')
    r.need(not s.OUT.exists(),'no saved inference before recovery freeze');out.mkdir(exist_ok=False)
    old=r.read(r.FREEZE)
    for key in ('source_sha256','input_sha256','scientific_source_sha256'):r.verify(old[key])
    source=old['source_sha256']|{p.relative_to(r.ROOT).as_posix():r.sha(p) for p in s.sources()}
    ins=old['input_sha256']|{p.relative_to(r.ROOT).as_posix():r.sha(p) for p in s.ORIGINAL.rglob('*') if p.is_file()}
    ins[r.FREEZE.relative_to(r.ROOT).as_posix()]=r.sha(r.FREEZE)
    prior=r.ROOT/'outputs/low_rank_risk_recovery_v1'
    ins.update({p.relative_to(r.ROOT).as_posix():r.sha(p) for p in prior.rglob('*') if p.is_file() and '__pycache__' not in p.parts})
    r.need(len(list((s.ORIGINAL/'models').glob('*.npz')))==20,'all twenty preserved shared models')
    failure=r.read(s.ORIGINAL/'failure.json');r.need(failure['source_commit']==s.INITIAL_COMMIT,'original failed run provenance')
    def deny(*args,**kwargs):raise RuntimeError('tests cannot inspect original scientific data')
    with (out/'unit.log').open('x',encoding='utf-8',newline='\n') as log:
        with mock.patch.object(r,'graphs',deny),s.saved.no_fit():
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('test_saved_v2'))
    r.need(result.wasSuccessful() and result.testsRun==12,'twelve constructed saved-solution checks')
    r.write(out/'unit_receipt.json',dict(integrity='PASSED',new_tests=12,synthetic_only=True,all_fits_and_decompositions=0,original_graph_or_numeric_model_parses=0,counters=r.ZERO))
    r.write(s.FREEZE,dict(integrity='FROZEN_READ_ONLY_SAVED_MODEL_RECOVERY_V2',source_parent_commit=s.FREEZE_PARENT,
        source_sha256=source,input_sha256=ins,scientific_source_sha256=old['scientific_source_sha256'],new_tests=12,
        prior_22_array_checks_and_2695_scientific_receipt_reused=True,prior_dependency_receipt_reused=True,
        original_failed_attempt_unchanged=True,new_risk_fits=0,new_spectral_decompositions=0,primary='RBF_RR2',counters=r.ZERO))
    owned={p.relative_to(r.ROOT).as_posix() for p in s.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}|{s.DOC}
    def stage(label):
        path=out/(label+'.nul');owned.add(path.relative_to(r.ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+path.relative_to(r.ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='12_NO_FIT_RECOVERY_CHECKS_PASSED',files=len(owned))),flush=True)
    scan=perf_counter_ns()
    with (out/'secret_stdout.log').open('xb') as so,(out/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=r.ROOT,stdout=so,stderr=se)
    r.write(out/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan));r.need(p.returncode==0,'freeze secrets')
    owned.update(p.relative_to(r.ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_checked')
    r.write(out/'index_disk_proof.json',dict(integrity='PASSED',objects=check_index(owned)))
    for mapping in (source,ins,old['scientific_source_sha256']):r.verify(mapping)
    r.write(out/'delivery_validation.json',dict(integrity='PASSED_READ_ONLY_RECOVERY_FREEZE',new_tests=12,
        dependency_and_science_receipts_source_bound_reused=True,compiled_in_memory=True,index_basic_EXTRA_scan=True,
        ordinary_and_staged_diff_checks=True,secret_returncode=0,new_model_fits=0,wall_ns=perf_counter_ns()-started,counters=r.ZERO))
    owned.update(p.relative_to(r.ROOT).as_posix() for p in out.iterdir() if p.is_file());stage('owned_final');objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_READ_ONLY_RECOVERY_FREEZE',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
