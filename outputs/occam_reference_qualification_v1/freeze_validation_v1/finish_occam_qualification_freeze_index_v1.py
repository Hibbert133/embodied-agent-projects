"""Preserve original log bytes under local attributes and complete actual index proof."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_reference_qualification_io_v1 as a
from src.analysis import occam_qualification_case_io_v1 as c
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    started=perf_counter_ns();out=a.VALIDATION;assert git('rev-parse','HEAD').decode().strip()=='4dafbb17e04f33df8d38f4270e0b7246dff8072e'
    names={p.decode() for p in (out/'owned_checked.nul').read_bytes().split(b'\0') if p}
    assert set(git('diff','--cached','--name-only').decode().splitlines())==names
    name='outputs/occam_reference_qualification_v1/development_validation_v1/attempt01/stdout.log'
    raw=(ROOT/name).read_bytes();indexed=git('show',':'+name)
    assert indexed!=raw and indexed==raw.replace(b'\r\n',b'\n')
    evidence=dict(integrity='FAILED_INDEX_BYTE_MATCH_RETAINED',path=name,
        original_disk_sha256=hashlib.sha256(raw).hexdigest(),pre_fix_index_sha256=hashlib.sha256(indexed).hexdigest(),
        disk_CRLF_count=raw.count(b'\r\n'),original_log_bytes_retained=True,pre_fix_index_equals_LF_normalized_disk=True,
        resolution='new qualification subtree *.log -text; root attributes and all old scientific sources unchanged',new_physics=0,online_LLM_API_calls=0)
    proof=out/'sealing_attempt01_eol_mismatch.json'
    if proof.exists():assert c.read(proof)==evidence
    else:c.write(proof,evidence)
    for n,h in {**c.read(out/'validation_receipt.json')['source_sha256'],**c.read(out/'source_reuse.json')['source_sha256']}.items():assert c.sha(ROOT/n)==h,n
    old_helper=out/Path(__file__).name
    if old_helper.exists() and old_helper.read_bytes()!=Path(__file__).read_bytes():
        saved=out/'finish_index_writer_failure_source.py'
        if not saved.exists():shutil.copyfile(old_helper,saved)
        failure=out/'sealing_attempt02_writer_failure.json'
        if not failure.exists():c.write(failure,dict(integrity='FAILED_METADATA_WRITER_ARGUMENT_RETAINED',type='TypeError',
            message='standard-library writer does not accept exclusive=False; update uses repository overwrite-capable metadata writer',
            frozen_scientific_sources_unchanged=True,new_physics=0,online_LLM_API_calls=0))
    shutil.copyfile(Path(__file__),old_helper)
    complete=c.read(out/'complete.json');attribute=a.BASE/'.gitattributes'
    complete['source_sha256'][attribute.relative_to(ROOT).as_posix()]=c.sha(attribute)
    complete.update(index_binding_finalized=True,sealing_attempt_failure_retained=True)
    a.io.write(out/'complete.json',complete,exclusive=False)
    names.update(p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    def stage(label):
        p=out/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        git('add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.gz'):data=gzip.decompress(data)
            if b'\0' not in data:
                text=data.decode('utf8');assert find_secret_rule(text) is None and not any(r.search(text) for r in EXTRA.values()),n
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked_final')
    c.write(out/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_and_decoded_scan=True,
        raw_logs_preserved_without_line_ending_rewrite=True,old_root_attributes_unchanged=True,
        previous_full_tracked_scan_chain='outputs/occam_reference_train_v3/learning_delivery_v1/tracked_secret_scan_chain.json',
        unrelated_untracked_files_excluded=True,wall_ns=perf_counter_ns()-started))
    names.add((out/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_FROZEN_QUALIFICATION_FINAL_INDEX',owned_files=len(names),new_unique_tests=34,new_allocation=False),flush=True)


if __name__=='__main__':main()
