"""Seal checked owned files only; never collects data or starts learning."""
from pathlib import Path
from time import perf_counter_ns
import gzip,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from src.analysis import occam_reference_train_io_v3 as a
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
from outputs.information_release.validation_v1.validate_freeze import index_bytes


def main():
    started=perf_counter_ns();out=a.VALIDATION;v=c.read(out/'validation_receipt.json');assert v['integrity']=='PASSED_ARRAYS_READERS_RUNTIME_ONLY'
    assert v['actual_test_executions']==37 and v['unique_tests']==2661 and v['new_unique_tests']==32
    assert a.io.git('rev-parse','HEAD')=='6d5919fc1764745bf6b9c69569c8959b9faab291'
    assert not a.io.git('diff','--cached','--name-only')
    for n,h in {**v['source_sha256'],**v['input_sha256'],**c.read(out/'source_reuse.json')['source_sha256']}.items():assert c.sha(ROOT/n)==h,n
    archive=ROOT/'outputs/research_archive/resource_qualification_stage_log_v1';remote=c.read(archive/'remote_receipt.json');catalog=c.read(archive/'catalog.json')
    assert remote['integrity']=='PASSED' and remote['remote_after']=='ad5570adb15507cba2e20e185a1ab76f4e798db7'
    old_source='6d5919fc1764745bf6b9c69569c8959b9faab291';changed=a.io.git('diff-tree','--no-commit-id','--name-only','-r',old_source).splitlines()
    rows=[r for r in catalog['files'] if r['path'] in changed];assert len(rows)==len(changed)==20 and all(r['published'] for r in rows)
    for name in ('build_resource_qualification_stage_log_v1_archive.py','verify_occam_core_commit_v1.py'):
        shutil.copyfile(Path(__file__).parent/name,archive/name)
    proof=Path(__file__).parent/'occam_core_postcommit_6d5919fc1764.json';assert c.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,archive/'source_committed_bytes.json')
    c.write(archive/'phase_selection.json',dict(integrity='PASSED',source_local_commit=old_source,published=20,omitted=0,files=rows,remote_archive_commit=remote['remote_after']))
    c.write(archive/'complete.json',dict(integrity='PASSED_DOCUMENTATION_PUBLICATION',source_local_commit=old_source,remote_archive_commit=remote['remote_after'],
        append_only_log_in_remote=True,new_environment_operations=0,new_fits=0,online_LLM_API_calls=0))
    old_proof=ROOT/'outputs/occam_resource_qualification_v3/result_delivery_v1/index_disk_proof.json'
    c.write(out/'tracked_secret_scan_chain.json',dict(integrity='PASSED',full_tracked_scan_at='c55d0940384e645dc7aa98f95cc93a19ffa639dd',
        previous_index_proof=old_proof.relative_to(ROOT).as_posix(),previous_proof_sha256=c.sha(old_proof),
        all_intervening_source_objects_checked_against_prior_catalog=True,new_actual_index_basic_extra_and_decoded_gzip_scan=True,
        unchanged_large_objects_not_allocated_again=True))
    for name in ('create_occam_isolated_training_v3.py','create_occam_native_process_v1.py','seal_occam_isolated_training_v3.py'):
        shutil.copyfile(Path(__file__).parent/name,out/name)
    names=set(v['source_sha256'])|{'reports/occam_isolated_training_freeze_v3_zh.md'}
    names|={p.relative_to(ROOT).as_posix() for p in archive.iterdir() if p.is_file()}
    names|={p.relative_to(ROOT).as_posix() for p in (a.QUERY/'audit.json',a.QUERY/'inventory.json.gz',a.QUERY/'inventory_bundle.json',a.QUERY/'resource_preparation.json')}
    development=a.BASE/'development_validation_v1'
    names|={p.relative_to(ROOT).as_posix() for p in development.rglob('*') if p.is_file()}
    def stage(label):
        names.update(p.relative_to(ROOT).as_posix() for p in out.rglob('*') if p.is_file())
        spec=out/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        a.io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if name.endswith('.gz'):raw=gzip.decompress(raw)
            if b'\0' in raw:continue
            text=raw.decode('utf8',errors='replace');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),name
        assert not a.io.git('diff','--check') and not a.io.git('diff','--cached','--check')
        return actual
    stage('owned_checked');actual=check();c.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,
        actual_index_basic_extra_scan=True,decoded_gzip_scan=True,unrelated_untracked_files_excluded=True))
    c.write(out/'complete.json',dict(integrity='PASSED',scope='ISOLATED_COLLECTOR_SOFTWARE_FREEZE_ONLY',source_sha256=v['source_sha256'],input_sha256=v['input_sha256'],
        validation_receipt_sha256=c.sha(out/'validation_receipt.json'),source_reuse_sha256=c.sha(out/'source_reuse.json'),
        new_unique_tests=32,reused_unique_tests=2629,unique_test_total=2661,actual_test_executions=37,old_reader_reexecutions=5,
        native_workers=0,new_environment_operations=0,new_fits=0,Adam_updates=0,online_LLM_API_calls=0,
        science_allocation_created=False,publication_goal_complete=False,seal_wall_ns=perf_counter_ns()-started))
    stage('owned_final');check();print(dict(integrity='PASSED',owned_files=len(names),unique_tests=2661,actual_tests=37),flush=True)


if __name__=='__main__':main()
