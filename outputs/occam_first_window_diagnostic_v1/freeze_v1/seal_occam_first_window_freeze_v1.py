"""Own-scope sealing: immutable scientific run and no outcome access by new reader."""
from pathlib import Path
import hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
BASE=ROOT/'outputs/occam_first_window_diagnostic_v1';sys.path.insert(0,str(BASE/'tools'))
import run_first_window_v1 as r
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
SOURCE='263f1b581548c7d95277cf8acd6dad91da0b2454';OUT=BASE/'freeze_v1'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip() and not r.OUT.exists()
    f=r.read(r.FREEZE);assert f['tests']==43 and not f['QUAL_outcomes_read'] and not f['full_diagnostic_started']
    r.verify(f['source_sha256']);m=r.read(r.RUN/'manifest.json');r.verify(m['source_sha256']);r.verify(m['input_sha256'])
    assert len(m['source_sha256'])==1393 and r.sha(r.RUN/'manifest.json')==f['run_manifest_sha256']
    probe=r.read(BASE/'development_v1/live_admission_refusal.json');assert probe['status']=='EXPECTED_REFUSAL_BEFORE_ANY_QUAL_OUTCOME_READ' and not probe['analysis_directory_created']
    args=[str(ROOT/'.venv/Scripts/python.exe'),'-B','-m','pip','check']
    pip=subprocess.run(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (OUT/'pip_check_stdout.log').write_bytes(pip.stdout);(OUT/'pip_check_stderr.log').write_bytes(pip.stderr);assert pip.returncode==0
    old=ROOT/'outputs/occam_reference_qualification_v1/freeze_validation_v1'
    reused={}
    for name in ('complete.json','validation_receipt.json','source_reuse.json','pip_check_stdout.log','pip_check_stderr.log'):
        p=old/name;reused[p.relative_to(ROOT).as_posix()]=r.sha(p)
    q=r.read(old/'complete.json');assert q['integrity']=='PASSED' and q['unique_tests']==2695
    r.write(OUT/'source_reuse.json',dict(integrity='PASSED_UNCHANGED_SCIENTIFIC_SOURCE_BINDING',source_sha256=m['source_sha256'],
        frozen_input_sha256=m['input_sha256'],prior_receipt_sha256=reused,prior_qualification_unique_tests=2695,
        source_hashes_verified_not_rerun=True,prior_compilation_receipt_reused=True,new_standard_library_only_tools_compiled=True))
    shutil.copyfile(__file__,OUT/Path(__file__).name)
    r.write(OUT/'delivery_validation.json',dict(integrity='PASSED_FIRST_WINDOW_DIAGNOSTIC_SOFTWARE_FREEZE',source_parent_commit=SOURCE,
        source_freeze_sha256=r.sha(r.FREEZE),new_unique_tests=43,development_test_executions=83,formal_test_executions=43,
        total_new_test_executions=126,old_qualification_unique_checks_source_bound_reused=2695,
        frozen_scientific_source_files_verified_unchanged=1393,QUAL_outcomes_read=False,full_diagnostic_started=False,
        recorded_refusal_before_outcome_read=True,own_source_compilation=True,pip_check_passed=True,
        original_primary_comparisons_unchanged=True,counters=r.counters(),publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={'docs/protocols/occam_first_window_diagnostic_v1_zh.md','reports/occam_first_window_diagnostic_freeze_v1_zh.md'}
    def stage(label):
        p=OUT/(label+'.nul');owned.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):git('add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned);assert set(actual)==owned
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.py'):compile(data,n,'exec')
            if b'\0' not in data:
                text=data.decode('utf8');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked');r.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_FIRST_WINDOW_FREEZE_STAGED',files=len(owned),new_unique_tests=43),flush=True)


if __name__=='__main__':main()
