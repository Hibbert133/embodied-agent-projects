"""Stage only the complete audited Native data bundle and offline delivery tools."""
from pathlib import Path
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from outputs.occam_reference_qualification_v1.delivery_tools_v1 import qualification_bundle_v1 as b
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from scripts.check_tracked_secrets import find_secret_rule
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
OUT=b.c.BASE/'native_delivery_v1';TOOLS=b.c.BASE/'delivery_tools_v1';SOURCE='c745bd4ecdb1ba61768849c93611e64b6c861188'
MANIFEST=b.c.OUTPUT/'occam_reference_qualification_v1_20261028T125131Z_7abaec83b085/manifest.json'


def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)


def main():
    assert git('rev-parse','HEAD').decode().strip()==SOURCE and not git('status','--porcelain','--untracked-files=no').strip()
    assert not git('diff','--cached','--name-only').strip()
    m,s,p,a=b.ready(MANIFEST,'NATIVE');index=io.read(OUT/'bundle_index.json');local=io.read(OUT/'local_restoration.json')
    assert local['all_files_byte_identical'] and local['files']==len(index['files'])==2288 and len(index['parts'])==12
    assert local['decoded_canonical_gzip_lines']==158286 and len(index['aliases'])==348
    assert io.read(OUT/'complete.json')['bundle_index_sha256']==io.sha(OUT/'bundle_index.json')
    assert not any(io.read(OUT/'guard.json')['counts'].values())
    f=io.read(TOOLS/'validation_v1/complete.json');assert f['unit_tests']==13 and f['new_records_exported_during_validation']==0
    for n,h in f['source_sha256'].items():assert io.sha(ROOT/n)==h,n
    for n,h in m['source_sha256'].items():assert io.sha(ROOT/n)==h,n
    source=io.read(OUT/'delivery_sources.json');assert source['source_files']==index['files']
    for n,item in index['files'].items():assert (ROOT/n).stat().st_size==item['bytes'] and io.sha(ROOT/n)==item['sha256'],n
    for part in index['parts']:assert (ROOT/part['path']).stat().st_size==part['bytes'] and io.sha(ROOT/part['path'])==part['sha256']
    shutil.copyfile(__file__,OUT/Path(__file__).name)
    io.write(OUT/'data_delivery_validation.json',dict(integrity='PASSED_COMPLETE_NATIVE_DATA_DELIVERY_VALIDATION',source_parent_commit=SOURCE,
        science_source_commit=m['source_git_commit'],manifest_id=m['manifest_id'],phase='NATIVE',executions=174,task_successes=173,task_failures=1,
        files=2288,parts=12,part_bytes_max=4*1024**2,zip_bytes=index['bundle_bytes'],exact_member_aliases=348,
        local_all_files_byte_identical=True,decoded_canonical_gzip_lines=158286,aliases_reuse_canonical_decoded_scan=True,
        offline_export_tests=13,source_bound_archive_algorithms_AST_identical=4,all_new_python_compiled=True,
        prior_scientific_2695_checks_compilation_and_dependencies_reused=True,
        current_science_source_files_verified_unchanged=len(m['source_sha256']),
        new_environment_interactions_during_delivery=0,new_fits_during_delivery=0,online_LLM_API_calls=0,
        independent_QUAL_population_or_novelty_qualified=False,publication_goal_complete=False))
    owned={p.relative_to(ROOT).as_posix() for root in (OUT,TOOLS) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.zip'}
    owned.add('reports/occam_reference_qualification_native_v1_zh.md')
    part_paths={r['path'] for r in index['parts']}
    def scan_all():
        for n in owned:
            raw=(ROOT/n).read_bytes()
            if n.endswith('.py'):compile(raw,n,'exec')
            if n in part_paths:
                item=next(x for x in index['parts'] if x['path']==n);assert io.sha(ROOT/n)==item['sha256'];continue
            if b'\0' not in raw:
                text=raw.decode('utf8-sig');assert find_secret_rule(text) is None and not any(x.search(text) for x in EXTRA.values()),n
    scan_all()
    def stage(label):
        path=OUT/(label+'.nul');owned.add(path.relative_to(ROOT).as_posix());path.write_bytes(b'\0'.join(n.encode() for n in sorted(owned))+b'\0')
        for flags in ((),('--renormalize',)):
            git('add',*flags,'--pathspec-from-file='+path.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
    def check():
        actual=index_bytes(owned);assert set(actual)==owned
        scan_all();assert not git('diff','--check').strip() and not git('diff','--cached','--check').strip();return actual
    stage('owned_checked')
    io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',objects=check(),actual_index_basic_extra_scan=True,
        raw_shards_hash_bound_to_complete_decoded_scan=True,unrelated_files_excluded=True,original_CSV_bytes_preserved=True))
    owned.add((OUT/'index_disk_proof.json').relative_to(ROOT).as_posix());stage('owned_final');check()
    print(dict(integrity='PASSED_NATIVE_DATA_DELIVERY_STAGED',files=len(owned),parts=12,bytes=sum((ROOT/n).stat().st_size for n in owned)),flush=True)


if __name__=='__main__':main()
