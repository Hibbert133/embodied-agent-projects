from pathlib import Path
from time import perf_counter_ns
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import verify_state_coupled_actuation_design_v1 as m
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=m.io

def validate(path):
    path=Path(path).resolve();manifest=m.checked(path);base=path.parent;start=perf_counter_ns()
    assert io.git('rev-parse','HEAD')==manifest['source_git_commit']
    assert not io.git('diff','HEAD','--name-only') and not io.git('diff','--cached','--name-only')
    construction=io.read(base/'construction.json');audit=io.read(base/'audit.json')
    assert audit['integrity']=='PASSED' and audit['records_sha256']==io.sha(base/'constructed_records.jsonl')
    assert audit['construction_sha256']==io.sha(base/'construction.json')
    assert audit['constructed_rows']==4320 and audit['legacy_float32_byte_exact_rows']==2880
    assert io.read(base/'pipeline_control/completion.json')['status']=='COMPLETED'
    assert manifest['status']=='DESIGN_ONLY_NO_ROBOT_ALLOCATION' and manifest['config']['actual_robot_episode_seeds']==[]
    assert manifest['config']['native_collector'] is manifest['config']['TRAIN_CAL_TEST_allocation'] is None
    for receipt in (construction,audit):
        assert receipt['guard']['network']['attempted_network_calls']==0
        assert all(v==0 for v in receipt['guard']['operation_counts'].values())
    frozen=io.read(m.BASE/'freeze_validation/complete.json');reuse=io.read(m.BASE/'freeze_validation/source_reuse.json')
    assert frozen['unique_test_total']==2115 and frozen['new_unique_tests']==12 and reuse['old_unique_tests_reused']==2103
    for mapping in (frozen['source_sha256'],reuse['source_sha256']):
        for name,digest in mapping.items():assert io.sha(ROOT/name)==digest
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    report=io.read(base/'presentation/report_receipt.json')
    assert report['report_sha256']==io.sha(ROOT/'reports/state_coupled_actuation_design_v1_zh.md')
    plots=io.read(base/'presentation/figures/plot_receipt.json')
    for name,digest in plots['artifact_sha256'].items():assert io.sha(base/'presentation/figures'/name)==digest
    io.write(base/'presentation/figures/visual_review.json',dict(integrity='PASSED',actual_PNGs_viewed=['operator_and_example.png'],
        review='Actual PNG opened with view_image: all3 panels readable, Chinese labels visible, action units separated from meters/task costs, constructed-only limits explicit; no clipping or overlap.',
        artifact_sha256=plots['artifact_sha256'],plot_receipt_sha256=io.sha(base/'presentation/figures/plot_receipt.json')))
    io.write(base/'literature_reading.json',dict(classification='PARTIAL_PRIMARY_SOURCE_REVIEW_NOT_REPRODUCTION',read_UTC_date='2026-10-26',
        sources=[dict(url='https://proceedings.mlr.press/v211/li23a.html',read='Official abstract and PDF selected Section2/3 lines, Assumptions1-3, Algorithm1-related text',
                      limit='No all-proof audit or implementation reproduction; stability assumptions not verified for this project'),
                 dict(url='https://personalpages.manchester.ac.uk/staff/Alexander.Lanzon/publications/open_pdf_files/ecc-07_Dehghani-Anderson-Lanzon.pdf',
                      read='Opening abstract fragment and search-returned cost/controller-falsification definitions',limit='Full reread timed out; not the original1997 paper'),
                 dict(url='https://www.jmlr.org/papers/v27/25-2248.html',read='Official abstract only',limit='Mentor assumptions and guarantees not transferred'),
                 dict(url='https://arxiv.org/html/2401.04007v2',read='Abstract/introduction relevant text',limit='No reproduction or all-proof reading'),
                 dict(url='https://arxiv.org/html/2406.17620v1',read='Abstract/introduction relevant text',limit='No reproduction or all-proof reading'),
                 dict(url='https://ieeexplore.ieee.org/document/11488285/',read='Publisher search-returned abstract/introduction fragments',
                      limit='Direct webpage required robot verification; not bypassed; synthetic operator not fitted to this hardware')],
        novelty_established=False,new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
    out=m.BASE/'result_validation';out.mkdir(exist_ok=False);tools=base/'presentation_tools';tools.mkdir(exist_ok=False);external=Path(__file__).parent
    for name in ('run_state_coupled_design_pipeline.py','build_state_coupled_design_report.py','plot_state_coupled_design.py',
                 'validate_state_coupled_design_delivery.py','verify_state_coupled_design_commit.py'):
        shutil.copyfile(external/name,tools/name)
    proof=external/('state_coupled_design_freeze_postcommit_'+manifest['source_git_commit'][:12]+'.json')
    assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,tools/'freeze_postcommit_byte_proof.json')
    for name in ('import_receipt.json','install_receipt.json','pip_report.json'):
        shutil.copyfile(external/'correction_scope_plotting_v1'/name,tools/('plot_'+name))
    for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
    io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
    names=set(m.SOURCES)|{'reports/state_coupled_actuation_design_v1_zh.md'}|{
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
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2115,new_scientific_tests_after_freeze=0,old_simulation_tests_repeated=False,
        source_sha256={**reuse['source_sha256'],**frozen['source_sha256']},freeze_complete_sha256=io.sha(m.BASE/'freeze_validation/complete.json'),
        full_tracked_secret_scan_reused_sha256=io.sha(m.BASE/'freeze_validation/tracked_secret_scan.json'),
        previously_tracked_files_unchanged_since_freeze=True,all_new_staged_bytes_secret_scanned=True,original_records_and_old_restorations_retained=True))
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_secret_patterns='PASSED',all_new_constructed_records_staged=True,no_new_large_record_requires_sharding=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_freeze_commit=manifest['source_git_commit'],manifest_id=manifest['manifest_id'],
        source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
        new_physics=0,new_model_fits=0,online_LLM_API_calls=0,no_robot_or_method_qualification=True,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=check(names)
    print(dict(integrity='PASSED',staged_objects=len(actual),unique_source_bound_tests=2115,new_physics=0,new_model_fits=0))

if __name__=='__main__':validate(sys.argv[1])
