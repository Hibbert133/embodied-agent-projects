"""Seal only the completed read-only support check; leave live science untouched."""
from pathlib import Path
import shutil, subprocess, sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'outputs/occam_behavior_support_v1/tools'))
import run_support_v1 as analysis
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
BASE=ROOT/'outputs/occam_behavior_support_v1';OUT=BASE/'delivery_v1'
SOURCE='e706dacc6d9d680e5424d306078dc48164089b93'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip()
    frozen=analysis.check_frozen();complete=io.read(BASE/'analysis_v1/complete.json')
    assert complete['integrity']=='PASSED_COMPLETE_DESCRIPTIVE_TRAIN_SUPPORT_AUDIT'
    for n,h in complete['artifact_sha256'].items():assert io.sha(ROOT/n)==h,n
    audit=io.read(BASE/'analysis_v1/audit.json');guard=io.read(BASE/'analysis_v1/guard.json')
    assert audit['main_probability_and_statistics_disabled'] and not any(guard['counts'].values())
    assert audit['trajectories']==648 and audit['windows']==3296 and audit['cells']==108
    q=io.read(ROOT/'outputs/occam_reference_qualification_v1/qualification_v1/occam_reference_qualification_v1_20261028T125131Z_7abaec83b085/manifest.json')
    for n,h in q['source_sha256'].items():assert io.sha(ROOT/n)==h,n
    OUT.mkdir(exist_ok=False);shutil.copyfile(__file__,OUT/Path(__file__).name)
    io.write(OUT/'complete.json',dict(integrity='PASSED_COMPLETE_READ_ONLY_SUPPORT_DELIVERY',
        source_parent_commit=SOURCE,analysis_complete_sha256=io.sha(BASE/'analysis_v1/complete.json'),
        frozen_plan_sha256=io.sha(analysis.FROZEN),new_unique_tests=24,failed_formal_executions=24,failed_formal_errors=1,
        earlier_development_executions=38,final_formal_executions=24,all_failed_sources_and_logs_preserved=True,
        new_tools_compiled=4,prior_scientific_compilation_and_dependency_receipts_source_bound_reused=True,
        active_science_source_files_verified_unchanged=len(q['source_sha256']),
        active_science_manifest_id=q['manifest_id'],active_science_parameters_or_inputs_changed=False,
        counters=analysis.scientific_zero(),independent_qualification_or_novelty_claim=False,publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for p in BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    owned|={'docs/protocols/occam_behavior_support_v1_zh.md','docs/research/correction_scope_contribution_review_v6_zh.md','reports/occam_behavior_support_v1_zh.md'}
    for n in owned:
        raw=(ROOT/n).read_bytes()
        if n.endswith('.py'):compile(raw,n,'exec')
        if b'\0' not in raw:
            text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
    def stage(label):
        path=OUT/(label+'.nul');owned.add(path.relative_to(ROOT).as_posix())
        path.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):
            git('add',*flags,'--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned)
        assert set(actual)==owned,'all and only owned files staged'
        for n in actual:
            raw=(ROOT/n).read_bytes()
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip()
        return actual
    stage('owned_checked')
    io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',sha256=check(),actual_index_basic_extra_scan=True,unrelated_files_excluded=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_SUPPORT_DELIVERY_STAGED',files=len(owned),bytes=sum((ROOT/n).stat().st_size for n in owned)),flush=True)


if __name__=='__main__':main()
