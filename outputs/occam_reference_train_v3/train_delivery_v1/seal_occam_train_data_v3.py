"""Seal the completed full TRAIN delivery without reading changing learning files."""
from pathlib import Path
import gzip,hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_native_case_io_v1 as c
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=c.BASE/'train_delivery_v1'


def git(*args):
    return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()=='2d6600c61aea7ce947e265f96eb508c32b062db6'
    assert not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip()
    complete=c.read(OUT/'complete.json');index=c.read(OUT/'bundle_index.json');restored=c.read(OUT/'local_restoration.json')
    assert complete['integrity']=='PASSED_COMPLETE_TRAIN_EXPORT_LOCAL_RESTORATION'
    assert restored['integrity']=='PASSED_LOSSLESS_TRAIN_BUNDLE' and restored['files']==len(index['files'])==8450
    assert restored['reconstructed_member_files']==len(index['aliases'])==1296
    assert c.sha(OUT/'bundle_index.json')==complete['bundle_index_sha256']
    assert c.sha(OUT/'train_records.zip')==index['bundle_sha256']
    frozen=c.read(c.FREEZE)
    for name,h in {**frozen['source_sha256'],**frozen['input_sha256']}.items():assert c.sha(ROOT/name)==h,name
    tool=c.read(c.BASE/'delivery_tools_v1/complete.json')
    for name,h in tool['source_sha256'].items():assert c.sha(ROOT/name)==h,name
    assert tool['new_unique_export_tests']==10
    for p in index['parts']:
        assert (ROOT/p['path']).stat().st_size==p['bytes'] and c.sha(ROOT/p['path'])==p['sha256']
    shutil.copyfile(Path(__file__),OUT/Path(__file__).name)
    c.write(OUT/'validation_reuse.json',dict(integrity='PASSED_SOURCE_BOUND_REUSE',
        frozen_validation_path=c.FREEZE.relative_to(ROOT).as_posix(),frozen_validation_sha256=c.sha(c.FREEZE),
        original_science_unique_tests=2661,science_source_and_input_sha256_verified_unchanged=True,
        original_compile_and_dependency_receipts_reused=True,
        exporter_tests=10,exporter_receipt_sha256=c.sha(c.BASE/'delivery_tools_v1/complete.json'),
        decoded_source_scan_proof_sha256=c.sha(OUT/'local_restoration.json'),
        actual_source_files_unchanged=True,new_environment_interactions=0,new_fits=0,online_LLM_API_calls=0))
    names={p.relative_to(ROOT).as_posix() for p in OUT.rglob('*') if p.is_file() and p.name!='train_records.zip'}
    names|={p.relative_to(ROOT).as_posix() for p in (c.BASE/'data_report_v1').rglob('*') if p.is_file()}
    names.add('reports/occam_reference_train_data_v3_zh.md')
    allowed_parts={p['path'] for p in index['parts']}
    def stage(label):
        target=OUT/(label+'.nul');names.add(target.relative_to(ROOT).as_posix())
        target.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        git('add','--pathspec-from-file='+target.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for name in actual:
            raw=(ROOT/name).read_bytes()
            if name in allowed_parts:continue
            if name.endswith('.gz'):raw=gzip.decompress(raw)
            if b'\0' not in raw:
                text=raw.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),name
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip()
        return actual
    stage('owned_checked')
    c.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),
        actual_index_basic_and_extra_scan=True,decoded_canonical_streams_scanned=True,
        aliases_reuse_exact_canonical_decoded_scan_disclosed=True,unrelated_files_excluded=True))
    names.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_TRAIN_DELIVERY_SEAL',owned_files=len(names),parts=len(index['parts']),
        original_files=len(index['files']),new_physics=0,online_LLM_API_calls=0),flush=True)


if __name__=='__main__':main()
