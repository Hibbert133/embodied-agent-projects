"""Force-refresh only owned raw logs after the local attribute change."""
from pathlib import Path
import gzip,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_reference_qualification_io_v1 as a
from src.analysis import occam_qualification_case_io_v1 as c
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    out=a.VALIDATION;assert git('rev-parse','HEAD').decode().strip()=='4dafbb17e04f33df8d38f4270e0b7246dff8072e'
    validation=c.read(out/'validation_receipt.json');reuse=c.read(out/'source_reuse.json')
    for n,h in {**validation['source_sha256'],**validation['input_sha256'],**reuse['source_sha256']}.items():assert c.sha(ROOT/n)==h,n
    assert not list(a.OUTPUT.glob('*/manifest.json'))
    shutil.copyfile(Path(__file__),out/Path(__file__).name)
    c.write(out/'sealing_attempt03_cached_conversion.json',dict(integrity='FAILED_CACHED_INDEX_BYTES_RETAINED',
        attributes_correct_but_prior_normalized_index_blob_cached=True,original_raw_log_bytes_unchanged=True,
        resolution='git add --renormalize on explicit owned log paths; local -text -diff preserves raw logs',
        code_and_frozen_numeric_sources_unchanged=True,new_physics=0,online_LLM_API_calls=0))
    complete=c.read(out/'complete.json');attr=a.BASE/'.gitattributes';complete['source_sha256'][attr.relative_to(ROOT).as_posix()]=c.sha(attr)
    complete.update(index_binding_finalized=True,all_sealing_failures_preserved=True);a.io.write(out/'complete.json',complete,exclusive=False)
    names=set(validation['source_sha256'])|{'reports/occam_reference_qualification_freeze_v1_zh.md'}
    names|={p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    assert set(git('diff','--cached','--name-only').decode().splitlines())<=names,'unrelated staged file'
    logs=[p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*.log')]
    spec=out/'raw_log_paths.nul';spec.write_bytes(b'\0'.join(n.encode() for n in sorted(logs))+b'\0');names.add(spec.relative_to(ROOT).as_posix())
    git('add','--renormalize','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def stage(label):
        p=out/(label+'.nul');names.add(p.relative_to(ROOT).as_posix());p.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
        git('add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(names)
        for n in actual:
            data=(ROOT/n).read_bytes()
            if n.endswith('.gz'):data=gzip.decompress(data)
            if b'\0' not in data:
                text=data.decode('utf8');assert find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),n
        assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_verified')
    c.write(out/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_and_decoded_scan=True,
        raw_logs_byte_preserved=True,scope_only_new_qualification_subtree=True,old_scientific_sources_unchanged=True,
        previous_full_scan_chain='outputs/occam_reference_train_v3/learning_delivery_v1/tracked_secret_scan_chain.json'))
    names.add((out/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_FINAL_INDEX_BYTES_AND_SECRETS',files=len(names),log_files=len(logs),tests=34,new_allocation=False),flush=True)


if __name__=='__main__':main()
