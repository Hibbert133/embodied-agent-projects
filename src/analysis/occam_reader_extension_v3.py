"""Source-bound read-only repair and continuation of unstarted V2 TRAIN only."""
from pathlib import Path
from src.analysis import occam_reference_train_io_v2 as a
io=a.io
BASE=a.BASE/'audit_repair_v3';VALIDATION=BASE/'freeze_validation_v1'
TARGET=a.OUTPUT/'occam_reference_train_v2_20261027T233346Z_e695620a8a91/manifest.json'
PROTOCOL=a.ROOT/'docs/protocols/occam_reference_train_reader_v3_zh.md'
OWN=(
    'src/analysis/occam_reference_train_audit_v3.py','src/analysis/occam_reader_extension_v3.py',
    'scripts/audit_occam_reference_train_v3.py','scripts/resume_occam_reference_train_v3.py',
    'scripts/validate_occam_reader_v3.py','tests/test_occam_reader_noise_v3.py',
    'tests/test_occam_training_population_v3.py','docs/protocols/occam_reference_train_reader_v3_zh.md')


def verify():
    q=io.read(VALIDATION/'complete.json');m=a.checked(TARGET)
    io.require(q['integrity']=='PASSED' and q['source_manifest_id']==m['manifest_id'],'frozen read-only extension')
    for name,h in q['source_sha256'].items():
        io.require(io.sha(a.ROOT/name)==h and io.git('ls-files','--error-unmatch',name)==name,'reader extension source changed '+name)
    for name,h in q['preserved_source_sha256'].items():io.require(io.sha(a.ROOT/name)==h,'original record or failed attempt changed '+name)
    io.require(io.read(a.BASE/'pipeline_v1/complete.json')['integrity']=='FAILED_PARTIAL','preserved stopped original pipeline')
    return q,m


def native_authorization():
    q,m=verify();raw=TARGET.parent/'native';result=io.read(raw/'audit_repair_v3/audit.json');approval=io.read(raw/'audit.json')
    meta=dict(reader_version=3,extension_freeze_sha256=io.sha(VALIDATION/'complete.json'),
        repaired_audit_path='native/audit_repair_v3/audit.json',repaired_audit_sha256=io.sha(raw/'audit_repair_v3/audit.json'),
        original_failed_attempt_sha256=io.sha(raw/'audit_attempt01/complete.json'))
    io.require(approval=={**result,'reader_repair':meta} and result['integrity']=='PASSED'
        and result['manifest_id']==m['manifest_id'] and result['phase']=='NATIVE' and result['counts']['executions']==36,
        'verified repaired native approval, without overwriting failed outputs')
    return approval
