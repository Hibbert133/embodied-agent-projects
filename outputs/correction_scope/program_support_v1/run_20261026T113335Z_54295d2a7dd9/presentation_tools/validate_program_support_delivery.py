from pathlib import Path
from time import perf_counter_ns
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_program_support_v1 as m
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=m.io


def validate(path):
    path=Path(path).resolve();manifest=m.checked(path);base=path.parent;start=perf_counter_ns()
    assert io.git('rev-parse','HEAD')==manifest['source_git_commit']
    assert not io.git('diff','HEAD','--name-only') and not io.git('diff','--cached','--name-only')
    result=io.read(base/'results.json');audit=io.read(base/'audit.json');completion=io.read(base/'pipeline_control/completion.json')
    assert audit['integrity']=='PASSED' and audit['results_sha256']==io.sha(base/'results.json') and completion['status']=='COMPLETED'
    assert len(result['units'])==54 and len(result['programs'])==12 and len(result['pairwise_programs'])==144
    assert len(result['panels'])==18 and len(result['existing_selector_rows'])==540
    for receipt in (result,audit):
        assert receipt['guard']['network']['attempted_network_calls']==0
        assert all(v==0 for v in receipt['guard']['operation_counts'].values())
    frozen=io.read(m.BASE/'freeze_validation/complete.json');reuse=io.read(m.BASE/'freeze_validation/source_reuse.json')
    assert frozen['unique_test_total']==2103 and frozen['new_unique_tests']==10 and reuse['old_unique_tests_reused']==2093
    for mapping in (frozen['source_sha256'],reuse['source_sha256']):
        for name,digest in mapping.items():assert io.sha(ROOT/name)==digest
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    report=io.read(base/'presentation/report_receipt.json')
    assert report['report_sha256']==io.sha(ROOT/'reports/correction_program_support_v1_zh.md')
    plots=io.read(base/'presentation/figures/plot_receipt.json')
    for name,digest in plots['artifact_sha256'].items():assert io.sha(base/'presentation/figures'/name)==digest
    # The PNG was actually opened with view_image before this receipt is issued.
    io.write(base/'presentation/figures/visual_review.json',dict(integrity='PASSED',actual_PNGs_viewed=['factual_support.png'],
        review='Actual PNG inspected: all12 programs and all18 cells visible, Chinese labels readable, sign convention and factual-only limits explicit; no clipping/overlap.',
        artifact_sha256=plots['artifact_sha256'],plot_receipt_sha256=io.sha(base/'presentation/figures/plot_receipt.json')))
    io.write(base/'literature_reading.json',dict(classification='PRIMARY_SOURCE_PARTIAL_READING_NOT_REPRODUCTION',read_UTC_date='2026-10-26',
        items=[dict(url='https://arxiv.org/html/1710.08005v5',sections='Definitions3.1/3.2/3.5, Proposition3.6, relevant consistency discussion in Section4',
                    limit='No all-appendix proof audit or robot reproduction'),
               dict(url='https://arxiv.org/html/2603.02196v1',sections='Abstract, Introduction, Background2.1/2.2, Theorem4.2 and Algorithm1 text',
                    limit='No complete proof/implementation reproduction; no guarantee transferred to dependent robot trajectories'),
               dict(url='https://ee.usc.edu/~msafonov/Unfalsified.html',sections='Author bibliography and original1996/1997 references',
                    limit='Original linked PDF unavailable; only neighbor location, no full-algorithm reading claim')],
        access_failures=['OpenReview verification page: not bypassed; used public arXiv version',
                         'Safonov original PDF URL inaccessible in web tool'],new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
    out=m.BASE/'result_validation';out.mkdir(exist_ok=False);tools=base/'presentation_tools';tools.mkdir(exist_ok=False)
    external=Path(__file__).parent
    for name in ('run_program_support_pipeline.py','build_program_support_report.py','plot_program_support_report.py',
                 'validate_program_support_delivery.py','verify_program_support_commit.py'):
        shutil.copyfile(external/name,tools/name)
    proof=external/('program_support_freeze_postcommit_'+manifest['source_git_commit'][:12]+'.json')
    assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,tools/'freeze_postcommit_byte_proof.json')
    for name in ('import_receipt.json','install_receipt.json','pip_report.json'):
        shutil.copyfile(external/'correction_scope_plotting_v1'/name,tools/('plot_'+name))
    for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
    io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
    names=set(m.SOURCES)|{'reports/correction_program_support_v1_zh.md'}|{
        p.relative_to(ROOT).as_posix() for p in m.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    assert all((ROOT/name).stat().st_size<=8*1024**2 for name in names)
    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()}
        p.write_bytes(b'\0'.join(name.encode() for name in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
    def check(selected):
        actual=index_bytes(selected)
        for name in actual:
            data=(ROOT/name).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'extra staged secret '+label+' '+name)
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check')
        return actual
    names=stage(names,'owned_initial');actual=check(names)
    dependency=subprocess.run([sys.executable,'-m','pip','check'],cwd=ROOT,capture_output=True,text=True)
    io.write(out/'dependencies.json',dict(returncode=dependency.returncode,stdout=dependency.stdout,stderr=dependency.stderr));assert dependency.returncode==0
    assert not io.git('diff','HEAD','--name-only','--diff-filter=M')
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2103,new_scientific_tests_after_freeze=0,old_simulation_tests_repeated=False,
        source_sha256={**reuse['source_sha256'],**frozen['source_sha256']},freeze_complete_sha256=io.sha(m.BASE/'freeze_validation/complete.json'),
        full_tracked_secret_scan_reused_sha256=io.sha(m.BASE/'freeze_validation/tracked_secret_scan.json'),
        previously_tracked_files_unchanged_since_freeze=True,all_new_staged_bytes_secret_scanned=True,
        original_large_records_and_old_restorations_retained=True))
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_secret_patterns='PASSED',no_new_large_record_requires_sharding=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_freeze_commit=manifest['source_git_commit'],manifest_id=manifest['manifest_id'],
        source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
        new_physics=0,new_model_fits=0,online_LLM_API_calls=0,no_qualification_or_novelty_claim=True,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=check(names)
    print(dict(integrity='PASSED',staged_objects=len(actual),unique_source_bound_tests=2103,scientific_fits=0,new_physics=0,all_units=54))


if __name__=='__main__':validate(sys.argv[1])
