"""Resume after a retained presentation-whitespace failure, without new science."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io

def resume(manifest):
    manifest=Path(manifest).resolve();m=a.checked(manifest);base=manifest.parent;start=perf_counter_ns()
    out=a.BASE/'result_validation_v1';final=out/'complete.json';assert not final.exists()
    for name in ('dependencies.json','tracked_secret_scan.json','ordinary_diff.json'):
        assert io.read(out/name)['returncode']==0
    assert io.read(out/'staged_diff.json')['returncode']==2
    freeze=io.read(a.VALIDATION/'complete.json');reuse=io.read(a.VALIDATION/'source_reuse.json')
    for names in (freeze['source_sha256'],reuse['source_sha256']):
        for n,h in names.items():io.require(io.sha(ROOT/n)==h,'source-bound checks unchanged '+n)
    verify_runtime(io.read(a.VALIDATION/'runtime_lock.json'))
    for p in (base/'results/statistics_audit.json',base/'results/reported_summaries_audit.json',base/'record_shards_v1/restoration_validation.json'):
        assert io.read(p)['integrity']=='PASSED'
    figures=base/'presentation/figures';visual=io.read(figures/'visual_review_after_formatting.json')
    assert visual['integrity']=='PASSED'
    for n,h in visual['artifact_sha256'].items():assert io.sha(figures/n)==h
    scripts=list((a.BASE/'report_tools_v1').glob('*.py'))+list((base/'execution_provenance_v1').glob('*.py'))
    for p in scripts:compile(p.read_bytes(),str(p),'exec')
    io.write(out/'new_presentation_sources_compiled_v2.json',dict(integrity='PASSED',source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in scripts}))
    large={r['original'] for r in io.read(base/'record_shards_v1/index.json')['files'] if r['parts']}
    names={p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}-large
    names|={'reports/correction_scope_development_v1_zh.md','docs/research/correction_scope_prior_art_addendum_v1_zh.md'}
    names|={p.relative_to(ROOT).as_posix() for p in (ROOT/'outputs/research_archive/correction_scope_freeze_v1').iterdir() if p.is_file()}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()}
        p.write_bytes(b'\0'.join(n.encode('utf8') for n in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
        return selected
    names=stage(names,'owned_paths_repaired_v2')
    for name,args in (('ordinary_diff_v2.json',['git','diff','--check']),('staged_diff_v2.json',['git','diff','--cached','--check'])):
        p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        io.require(p.returncode==0,'repaired presentation diff '+name)
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_repaired_scan_v2')
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'actual-index additional secret pattern '+label+' '+n)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,
        extra_provider_and_GitHub_patterns='PASSED',excluded_original_large_gzip=sorted(large),
        full_tracked_secret_scan_reused_sha256=io.sha(out/'tracked_secret_scan.json'),all_current_owned_index_bytes_rechecked=True))
    io.write(final,dict(integrity='PASSED',source_git_commit=m['source_git_commit'],manifest_id=m['manifest_id'],
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
        source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in scripts},source_reused_unique_tests=2045,new_scientific_tests=0,
        presentation_only_repair=True,retained_failed_staged_diff_sha256=io.sha(out/'staged_diff.json'),
        new_physics_for_delivery=0,new_fits_for_delivery=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_v3')
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'final-index additional secret pattern '+label+' '+n)
    assert not io.git('diff','--cached','--check')
    print(dict(integrity='PASSED',owned_index_objects=len(actual),source_reused_tests=2045,large_originals_kept_local=len(large),presentation_only_repair=True))

if __name__=='__main__':resume(sys.argv[1])
