"""Freeze constructed tests and hashes before semantic data reads; no data fit."""
from pathlib import Path
from time import perf_counter_ns
from unittest import mock
import gzip
import hashlib
import json
import subprocess
import sys
import unittest
import run_contract_v1 as r

ROOT=r.ROOT;OUT=r.FREEZE.parent
sys.path.insert(0,str(ROOT))
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA


def check_index(owned):
    names=r.git('diff','--cached','--name-only').decode().splitlines()
    r.need(set(names)==owned,'only explicitly owned staged paths')
    objects={}
    with subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE) as p:
        for n in sorted(names):
            p.stdin.write((':'+n+'\n').encode());p.stdin.flush();header=p.stdout.readline().split()
            r.need(len(header)==3 and header[1]==b'blob','index blob')
            b=p.stdout.read(int(header[2]));r.need(p.stdout.read(1)==b'\n' and b==(ROOT/n).read_bytes(),'actual index/disk bytes '+n)
            if n.endswith('.py'):compile(b,n,'exec')
            decoded=gzip.decompress(b) if n.endswith('.gz') else b
            if b'\0' not in decoded:
                s=decoded.decode('utf-8');r.need(not find_secret_rule(s) and not any(v.search(s) for v in EXTRA.values()),'actual index secret pattern '+n)
            objects[n]=dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),git_oid=header[0].decode())
        p.stdin.close();r.need(p.wait(timeout=60)==0,'index reader')
    r.need(not r.git('diff','--check').strip() and not r.git('diff','--cached','--check').strip(),'ordinary/staged diff')
    return objects


def main():
    started=perf_counter_ns()
    r.need(r.git('rev-parse','HEAD').decode().strip()==r.PARENT and not r.git('status','--porcelain','--untracked-files=no').strip(),'clean original parent')
    r.need(not r.OUT.exists(),'actual semantics not started before freeze');OUT.mkdir(exist_ok=False)
    src={p.relative_to(ROOT).as_posix():r.sha(p) for p in r.source_paths()}
    ins={p.relative_to(ROOT).as_posix():r.sha(p) for p in r.inputs()}
    r.need(r.sha(r.RUN/'manifest.json')=='7416700122909b15ffeda1a3ca2925d325bebe92b1eab00cbe3dfea329e0a413','original TRAIN manifest')
    m=r.read(r.RUN/'manifest.json');r.need(m['manifest_id']==r.MID,'original MID')
    binding=r.read(ROOT/'outputs/occam_opportunity_census_v1/freeze_v1/source_binding.json')
    science=binding['scientific_source_sha256'];r.verify(science)
    old=r.read(ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/complete.json')
    r.need(old['integrity']=='PASSED' and old['unique_tests']==2695,'source-bound old scientific checks')
    r.need(r.sha(ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1/validation_receipt.json')==old['validation_receipt_sha256'],'old check receipt')
    for cohort in ('native','train'):
        audit=r.read(r.RUN/cohort/'audit.json');completion=r.read(r.RUN/cohort/'completion.json')
        process=r.read(r.RUN/cohort/'process_audit.json')
        r.need(audit['integrity']=='PASSED' and process['integrity']=='PASSED_ISOLATED_PROCESS_AND_BYTE_CONTINUITY_ONLY','two levels source audit')
        r.need(r.sha(r.RUN/cohort/'events.jsonl.gz')==completion['artifact_sha256']['events.jsonl.gz']
            and r.sha(r.RUN/cohort/'public_trajectories.jsonl.gz')==audit['public_trajectories_sha256'],'source audited raw/public bytes')
    def deny(*args,**kwargs):raise RuntimeError('formal tests cannot parse actual scientific gzip')
    with (OUT/'unit.log').open('x',encoding='utf-8',newline='\n') as log:
        with mock.patch.object(r,'rows',deny):
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('test_contract_v1'))
    r.need(result.wasSuccessful() and result.testsRun==22,'22 pure constructed tests')
    r.write(OUT/'unit_receipt.json',dict(integrity='PASSED',unique_tests=22,constructed_only=True,
        actual_scientific_semantic_parses=0,intentional_guard_rejections_in_tests=True,counters=r.ZERO))
    with (OUT/'pip_stdout.log').open('xb') as so,(OUT/'pip_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','-m','pip','check'],cwd=ROOT,stdout=so,stderr=se)
    r.need(p.returncode==0,'dependency check')
    r.verify(src);r.verify(ins);r.verify(science)
    r.write(r.FREEZE,dict(integrity='FROZEN_TRAIN_DECISION_CONTRACT_V1',source_parent_commit=r.PARENT,
        source_sha256=src,input_sha256=ins,scientific_source_sha256=science,
        original_manifest_id=r.MID,new_unique_tests=22,development_executions=22,formal_executions=22,
        reused_source_bound_scientific_checks=2695,source_bound_compilation_reused=True,actual_scientific_semantic_parses=0,
        two_semantic_passes_per_input_stream=True,worker_hard_timeout_seconds=1800,
        no_model_or_policy_queries=True,counters=r.ZERO,publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for p in r.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}|set(r.DOCS)
    def stage(label):
        spec=OUT/(label+'.nul');owned.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):r.git('add',*flags,'--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    stage('owned_initial');print(json.dumps(dict(stage='22_CONSTRUCTED_TESTS_PASSED_BEFORE_REAL_DATA',files=len(owned))),flush=True)
    scan=perf_counter_ns()
    with (OUT/'secret_stdout.log').open('xb') as so,(OUT/'secret_stderr.log').open('xb') as se:
        p=subprocess.run([sys.executable,'-B','scripts/check_tracked_secrets.py','--staged'],cwd=ROOT,stdout=so,stderr=se)
    r.write(OUT/'secret_receipt.json',dict(returncode=p.returncode,wall_ns=perf_counter_ns()-scan,
        actual_script_scans_all_tracked_worktree=True,index_EXTRA_scan_separate=True))
    r.need(p.returncode==0,'secret scan blocks commit')
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file());stage('owned_checked')
    r.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check_index(owned)))
    r.verify(src);r.verify(ins);r.verify(science)
    r.write(OUT/'delivery_validation.json',dict(integrity='PASSED_SOFTWARE_ONLY_FREEZE',new_unique_tests=22,
        original_source_checks_reused=2695,dependency_returncode=0,secret_returncode=0,
        staged_Python_compiled_in_memory=True,source_bound_scientific_compilation_reused=True,
        ordinary_and_staged_diff_checks=True,actual_scientific_semantic_parses=0,
        source_IO=r.IO,wall_ns=perf_counter_ns()-started,counters=r.ZERO))
    owned.update(p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file());stage('owned_final')
    objects=check_index(owned)
    print(json.dumps(dict(integrity='PASSED_READY_FOR_CONTRACT_FREEZE_COMMIT',files=len(objects),bytes=sum(v['bytes'] for v in objects.values()))),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
