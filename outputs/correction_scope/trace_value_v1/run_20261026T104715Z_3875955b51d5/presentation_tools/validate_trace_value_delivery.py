from pathlib import Path
from time import perf_counter_ns
import shutil, subprocess, sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_trace_value_v1 as m
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=m.io


def validate(path):
    path=Path(path).resolve();manifest=m.checked(path);base=path.parent;start=perf_counter_ns()
    assert io.git('rev-parse','HEAD')==manifest['source_git_commit']
    assert not io.git('diff','--cached','--name-only') and not io.git('diff','HEAD','--name-only')
    for name in ('model_audit.json','replay_audit.json','preservation/restoration_validation.json',
                 'presentation/figures/visual_review.json','posthoc_choice_diagnosis_v2/audit.json'):
        assert io.read(base/name)['integrity']=='PASSED'
    assert io.read(base/'pipeline_control/completion.json')['status']=='COMPLETED'
    frozen=io.read(m.BASE/'freeze_validation/complete.json');reuse=io.read(m.BASE/'freeze_validation/source_reuse.json')
    assert frozen['unique_test_total']==2093 and reuse['old_unique_tests_reused']==2073
    for names in (frozen['source_sha256'],reuse['source_sha256']):
        for name,digest in names.items():assert io.sha(ROOT/name)==digest
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    fit=io.read(base/'fit_receipt.json');audit=io.read(base/'model_audit.json');bank=io.read(base/'bank.json')
    replay=io.read(base/'replay_audit.json');result=io.read(base/'results.json')
    assert fit['actual_fits']==fit['guard']['operation_counts']['solve_attempts']==6
    assert audit['independent_refits']==audit['guard']['operation_counts']['lstsq_attempts']==6
    assert len(bank['models'])==6 and fit['bank_sha256']==audit['bank_sha256']==io.sha(base/'bank.json')
    assert replay['results_sha256']==io.sha(base/'results.json')
    assert replay['replay_sha256']==result['replay_sha256']==io.sha(base/'replay.jsonl')
    assert len(result['results'])==540
    for model in bank['models'].values():assert io.sha(base/'models'/model['file'])==model['sha256']
    for receipt in (fit,audit,replay,result,io.read(base/'posthoc_choice_diagnosis_v2/audit.json'),
                    io.read(base/'posthoc_choice_diagnosis/failure.json'),io.read(base/'preservation/restoration_validation.json')):
        guard=receipt['guard'];assert guard['network']['attempted_network_calls']==0
        for name in ('environment_creations','resets','simulation'):assert guard['operation_counts'][name]==0
    visual=io.read(base/'presentation/figures/visual_review.json')
    for name,digest in visual['artifact_sha256'].items():assert io.sha(base/'presentation/figures'/name)==digest
    presentation=io.read(base/'presentation/report_receipt.json')
    assert presentation['report_sha256']==io.sha(ROOT/'reports/correction_trace_value_v1_zh.md')
    preserved=io.read(base/'preservation/index.json')
    assert len(preserved['files'])==1
    for entry in preserved['files']:
        assert io.sha(ROOT/entry['original'])==entry['sha256']==io.sha(entry['restored_path'])
        assert io.sha(ROOT/entry['committed_compressed'])==entry['compressed_sha256']
        assert Path(entry['restored_path']).stat().st_size==entry['bytes']
    out=m.BASE/'result_validation';out.mkdir(exist_ok=False)
    tools=base/'presentation_tools';tools.mkdir(exist_ok=False);external=Path(__file__).parent
    for name in ('build_trace_value_report.py','plot_trace_value_report.py','preserve_trace_value_records.py',
                 'diagnose_trace_value_choices.py','record_trace_value_visual_review.py',
                 'validate_trace_value_delivery.py','verify_trace_value_freeze_postcommit.py'):
        shutil.copyfile(external/name,tools/name)
    post=external/'trace_value_freeze_postcommit_3875955b51d5.json'
    assert io.read(post)['integrity']=='PASSED' and io.read(post)['source_local_commit']==manifest['source_git_commit']
    shutil.copyfile(post,tools/'freeze_postcommit_byte_proof.json')
    for name in ('import_receipt.json','install_receipt.json','pip_report.json'):
        shutil.copyfile(external/'correction_scope_plotting_v1'/name,tools/('plot_'+name))
    for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
    failed_source=base/'posthoc_choice_diagnosis/reader_before_plaintext_fix.py.saved'
    compile(failed_source.read_bytes(),str(failed_source),'exec')
    io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
    names={p.relative_to(ROOT).as_posix() for p in m.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    names|=set(manifest['source_sha256'])|{'reports/correction_trace_value_v1_zh.md'}
    exclusions=preserved['stage_excluded_local_originals'];names-=set(exclusions)
    assert all((ROOT/name).stat().st_size<=8*1024**2 for name in names)

    def stage(selected,label):
        p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()}
        p.write_bytes(b'\0'.join(name.encode() for name in sorted(selected))+b'\0')
        io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
        return selected

    def check(selected):
        actual=index_bytes(selected)
        for name in actual:
            data=(ROOT/name).read_bytes()
            if b'\0' not in data:
                for label,pattern in EXTRA.items():
                    io.require(pattern.search(data.decode('utf8',errors='replace')) is None,'additional staged secret '+label+' '+name)
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check')
        return actual

    names=stage(names,'owned_initial');actual=check(names)
    dependency=subprocess.run([sys.executable,'-m','pip','check'],cwd=ROOT,capture_output=True,text=True)
    io.write(out/'dependencies.json',dict(returncode=dependency.returncode,stdout=dependency.stdout,stderr=dependency.stderr))
    assert dependency.returncode==0
    # All previously tracked paths were unchanged before staging. Freeze's
    # whole-tracked scan is reused, while every newly staged blob is scanned now.
    assert not io.git('diff','HEAD','--name-only','--diff-filter=M')
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2093,new_scientific_tests_after_freeze=0,
        old_simulation_tests_repeated=False,source_sha256={**reuse['source_sha256'],**frozen['source_sha256']},
        freeze_complete_sha256=io.sha(m.BASE/'freeze_validation/complete.json'),
        full_tracked_secret_scan_reused_sha256=io.sha(m.BASE/'freeze_validation/tracked_secret_scan.json'),
        previously_tracked_files_unchanged_since_freeze=True,all_new_staged_bytes_secret_scanned=True,
        old_runtime_and_compilation_source_bound=True))
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,
        basic_and_extra_secret_patterns='PASSED',excluded_local_large_originals=exclusions,
        actual_file_restoration_receipt_sha256=io.sha(base/'preservation/restoration_validation.json')))
    io.write(out/'complete.json',dict(integrity='PASSED',source_freeze_commit=manifest['source_git_commit'],
        manifest_id=manifest['manifest_id'],source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},
        receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
        new_physics=0,new_fits_for_delivery=0,online_LLM_API_calls=0,
        no_qualification_or_novelty_claim=True,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final')
    actual=check(names)
    print(dict(integrity='PASSED',staged_objects=len(actual),unique_source_bound_tests=2093,
        scientific_fits=6,independent_refits=6,offline_replays=540,new_physics=0))


if __name__=='__main__':validate(sys.argv[1])
