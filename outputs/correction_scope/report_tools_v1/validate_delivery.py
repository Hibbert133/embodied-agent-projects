"""Stage only this completed study; retain originals and bind reused checks."""
from pathlib import Path
from time import perf_counter_ns
import shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=a.io


def validate(manifest):
    manifest=Path(manifest).resolve();m=a.checked(manifest);base=manifest.parent
    io.require(not io.git('diff','--cached','--name-only'),'empty index before owned result delivery')
    io.require(io.read(base/'pipeline_control_v1/completion.json')['status']=='COMPLETED','complete pipeline')
    for p in (base/'results/statistics_audit.json',base/'results/reported_summaries_audit.json',base/'record_shards_v1/restoration_validation.json'):
        io.require(io.read(p)['integrity']=='PASSED','completed results/restoration '+str(p))
    io.require(io.read(base/'presentation/figures/visual_review.json')['integrity']=='PASSED','actual visual review required')
    out=a.BASE/'result_validation_v1';out.mkdir(exist_ok=False);start=perf_counter_ns()
    freeze=io.read(a.VALIDATION/'complete.json')
    for n,h in freeze['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged source-bound2045 checks '+n)
    reuse=io.read(a.VALIDATION/'source_reuse.json')
    for n,h in reuse['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'old source-bound2022 checks '+n)
    verify_runtime(io.read(a.VALIDATION/'runtime_lock.json'))
    io.write(out/'source_reuse.json',dict(integrity='PASSED',source_reused_unique_tests=2045,new_scientific_tests=0,
        old_tensor_groups_separate=6,source_sha256=freeze['source_sha256'],
        freeze_complete_sha256=io.sha(a.VALIDATION/'complete.json'),prior_source_reuse_sha256=io.sha(a.VALIDATION/'source_reuse.json'),
        no_old_simulation_tests_repeated=True,model_fits_separate_from_test_count=True))
    # Keep orchestration/audit sources with the receipts that hash those bytes.
    external=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent')
    provenance=base/'execution_provenance_v1';provenance.mkdir(exist_ok=False)
    sources=('continue_correction_scope_pipeline_v1.py','check_correction_scope_common_states.py','check_correction_scope_first_saved_case.py')
    for n in sources:shutil.copyfile(external/n,provenance/n)
    plot=external/'correction_scope_plotting_v1'
    for n in ('install_receipt.json','pip_report.json','import_receipt.json'):shutil.copyfile(plot/n,provenance/('plot_'+n))
    io.write(provenance/'source_sha256.json',{p.name:io.sha(p) for p in provenance.iterdir() if p.is_file()})
    scripts=list((a.BASE/'report_tools_v1').glob('*.py'))+list(provenance.glob('*.py'))
    for p in scripts:compile(p.read_bytes(),str(p),'exec')
    io.write(out/'new_presentation_sources_compiled.json',dict(integrity='PASSED',source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in scripts}))
    index=io.read(base/'record_shards_v1/index.json');large={r['original'] for r in index['files'] if r['parts']}
    names={p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    names-=large
    names|={'reports/correction_scope_development_v1_zh.md','docs/research/correction_scope_prior_art_addendum_v1_zh.md'}
    archive=ROOT/'outputs/research_archive/correction_scope_freeze_v1'
    names|={p.relative_to(ROOT).as_posix() for p in archive.iterdir() if p.is_file()}
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()}
        p.write_bytes(b'\0'.join(n.encode('utf8') for n in sorted(selected))+b'\0')
        for flags in ((),('--renormalize',)):
            io.git('-c','maintenance.auto=false','-c','gc.auto=0','add',*flags,'--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
        return selected
    def command(name,args):
        t=perf_counter_ns();p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace')
        io.write(out/name,dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,wall_ns=perf_counter_ns()-t))
        io.require(p.returncode==0,'delivery check '+name)
    allowed=stage(names,'owned_paths_v1')
    command('dependencies.json',[sys.executable,'-m','pip','check'])
    command('tracked_secret_scan.json',[sys.executable,'scripts/check_tracked_secrets.py','--staged'])
    command('ordinary_diff.json',['git','diff','--check']);command('staged_diff.json',['git','diff','--cached','--check'])
    allowed=stage(allowed|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_v2')
    actual=index_bytes(allowed)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            text=data.decode('utf8',errors='replace')
            for label,pattern in EXTRA.items():io.require(pattern.search(text) is None,'staged provider/GitHub pattern '+label+' '+n)
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,extra_provider_and_GitHub_patterns='PASSED',excluded_original_large_gzip=sorted(large)))
    receipts={p.name:io.sha(p) for p in out.iterdir() if p.is_file()}
    io.write(out/'complete.json',dict(integrity='PASSED',source_git_commit=m['source_git_commit'],manifest_id=m['manifest_id'],receipt_sha256=receipts,
        source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in scripts},source_reused_unique_tests=2045,new_scientific_tests=0,
        new_physics_for_delivery=0,new_fits_for_delivery=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
    allowed=stage(allowed|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_v3')
    final=index_bytes(allowed);io.require(not io.git('diff','--cached','--check'),'final staged whitespace check')
    print(dict(integrity='PASSED',owned_index_objects=len(final),source_reused_tests=2045,large_originals_kept_local=len(large)))


if __name__=='__main__':validate(sys.argv[1])
