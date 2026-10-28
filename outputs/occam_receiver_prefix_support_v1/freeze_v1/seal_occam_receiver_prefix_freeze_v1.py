"""Commit the TRAIN-only receiver analysis freeze before any complete replay."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
BASE=ROOT/'outputs/occam_receiver_prefix_support_v1';sys.path.insert(0,str(BASE/'tools'))
import run_prefix_support_v1 as r
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
SOURCE='66556a4e6c5212681b7e2e0943f5e5d809f1dde2';OUT=BASE/'freeze_v1'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip() and not (BASE/'analysis_v1').exists()
    f=r.read(r.FREEZE);assert f['unit_tests']==20 and f['strict_in_sample_description'] and not f['current_QUAL_outcomes_used']
    for section in ('input_sha256','component_sha256','source_sha256'):r.verify(f[section])
    q=r.read(r.QMANIFEST);r.verify(q['source_sha256']);shutil.copyfile(__file__,OUT/Path(__file__).name)
    r.write(OUT/'delivery_validation.json',dict(integrity='PASSED_TRAIN_ONLY_RECEIVER_ANALYSIS_SOFTWARE_FREEZE',source_parent_commit=SOURCE,
        source_freeze_sha256=r.sha(r.FREEZE),new_array_tests=20,all_development_test_executions=20,formal_test_executions=20,
        old_scientific_source_files_verified_unchanged=len(q['source_sha256']),prior_scientific_compile_and_dependency_receipts_reused=True,
        complete_source_replay_started=False,new_scientific_population=False,new_neural_or_batch_training=0,new_physics=0,online_LLM_API_calls=0))
    owned={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={'docs/protocols/occam_receiver_prefix_support_v1_zh.md','docs/research/correction_scope_contribution_review_v7_zh.md'}
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
    stage('owned_checked');r.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',sha256=check(),actual_index_basic_extra_scan=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_PREFIX_ANALYSIS_FREEZE_STAGED',files=len(owned),new_array_tests=20),flush=True)


if __name__=='__main__':main()
