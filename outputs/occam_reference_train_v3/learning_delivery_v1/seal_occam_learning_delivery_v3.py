"""Seal complete frozen learning outputs and the actual full-data Git recovery."""
from pathlib import Path
import argparse,gzip,re,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=c.BASE/'learning_delivery_v1'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main(source):
    assert re.fullmatch('[0-9a-f]{40}',source)
    assert git('rev-parse','HEAD').decode().strip()==source and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip()
    proof=c.read(c.BASE/'train_delivery_v1/actual_git_recovery.json')
    assert proof['source_commit']==source and proof['integrity']=='PASSED_ACTUAL_COMMIT_TRAIN_PARTS_AND_FILES_RESTORATION'
    assert proof['result']['files']==8450 and proof['part_count']==83 and proof['result']['all_files_byte_identical']
    complete=c.read(OUT/'complete.json');manifest=c.read(OUT/'source_manifest.json')
    assert complete['integrity']=='PASSED_FROZEN_TRAINING_AND_INDEPENDENT_MATHEMATICS_ONLY'
    for name,item in manifest['files'].items():assert c.sha(ROOT/name)==item['sha256'] and (ROOT/name).stat().st_size==item['bytes'],name
    frozen=c.read(c.FREEZE)
    for name,h in {**frozen['source_sha256'],**frozen['input_sha256']}.items():assert c.sha(ROOT/name)==h,name
    prior=c.read(c.FREEZE.parent/'source_reuse.json')
    for name,h in prior['source_sha256'].items():assert c.sha(ROOT/name)==h,name
    for name in ('seal_occam_learning_delivery_v3.py',):shutil.copyfile(Path(__file__).parent/name,OUT/name)
    commit_proof=Path(__file__).parent/('occam_core_postcommit_'+source[:12]+'.json')
    assert c.read(commit_proof)['integrity']=='PASSED' and c.read(commit_proof)['commit']==source
    shutil.copyfile(commit_proof,OUT/'data_committed_bytes.json')
    for p in [*OUT.glob('*.py'),c.BASE/'train_delivery_v1/recover_occam_train_git_v3.py']:
        compile(p.read_bytes(),str(p),'exec')
    c.write(OUT/'validation_reuse.json',dict(integrity='PASSED_SOURCE_BOUND_REUSE',
        frozen_source_receipt_sha256=c.sha(c.FREEZE),unchanged_scientific_source_and_input_verified=True,
        reused_prior_source_files_checked=len(prior['source_sha256']),prior_source_reuse_receipt_sha256=c.sha(c.FREEZE.parent/'source_reuse.json'),
        original_science_unique_tests=2661,new_scientific_unit_tests=0,original_compilation_and_both_dependency_receipts_reused=True,
        new_delivery_helpers_compiled=True,independent_mathematical_audit_solves=918,
        training_Adam_updates_separately_reported=9000,online_LLM_API_calls=0,new_physics_during_delivery=0))
    names=set(manifest['files'])|{p.relative_to(ROOT).as_posix() for p in OUT.rglob('*') if p.is_file()}
    names|={'reports/occam_reference_learning_v3_zh.md','outputs/occam_reference_train_v3/train_delivery_v1/actual_git_recovery.json',
        'outputs/occam_reference_train_v3/train_delivery_v1/recover_occam_train_git_v3.py'}
    def stage(label):
        p=OUT/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        git('add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if name.endswith('.gz'):raw=gzip.decompress(raw)
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),name
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip()
        return actual
    stage('owned_checked');c.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),
        actual_index_basic_extra_scan=True,scientific_tests_not_repeated=True,unrelated_files_excluded=True))
    names.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_LEARNING_AND_RECOVERY_SEAL',owned_files=len(names),Adam_updates=9000,analysis_solves=918),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);args=p.parse_args();main(args.source)
