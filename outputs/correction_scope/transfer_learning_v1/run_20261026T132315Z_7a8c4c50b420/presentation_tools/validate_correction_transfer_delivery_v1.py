from pathlib import Path
from time import perf_counter_ns
import json,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_transfer_learning_v1 as m
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
io=m.io


def validate(path):
    path=Path(path).resolve();manifest=m.checked(path);base=path.parent;start=perf_counter_ns();external=Path(__file__).parent
    assert io.git('rev-parse','HEAD')==manifest['source_git_commit'] and not io.git('diff','HEAD','--name-only')
    assert not io.git('diff','--cached','--name-only')
    receipts={name:io.read(base/(name+'.json')) for name in ('fit_receipt','model_audit','replay_receipt','replay_audit')}
    assert receipts['model_audit']['integrity']==receipts['replay_audit']['integrity']=='PASSED'
    assert io.read(base/'pipeline_control/completion.json')['status']=='COMPLETED'
    assert receipts['fit_receipt']['neural_ledger']==dict(fit_attempts=15,optimizer_steps=15000)
    assert receipts['model_audit']['independent_neural_ledger']==dict(fit_attempts=15,optimizer_steps=15000)
    assert receipts['fit_receipt']['ridge_fits']==receipts['model_audit']['independent_ridge_refits']==15
    for name,r in receipts.items():
        counts=r['guard']['operation_counts'];assert r['guard']['network']['attempted_network_calls']==0
        allowed={'solve_attempts':15} if name=='fit_receipt' else {'lstsq_attempts':15} if name=='model_audit' else {}
        assert all(v==allowed.get(k,0) for k,v in counts.items())
    frozen=io.read(m.BASE/'freeze_validation/complete.json');reuse=io.read(m.BASE/'freeze_validation/source_reuse.json')
    assert frozen['unique_test_total']==2139 and frozen['new_unique_tests']==24 and reuse['old_unique_tests_reused']==2115
    for mapping in (frozen['source_sha256'],reuse['source_sha256']):
        for name,digest in mapping.items():assert io.sha(ROOT/name)==digest
    verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
    report=io.read(base/'presentation/report_receipt.json');assert report['report_sha256']==io.sha(ROOT/'reports/correction_transfer_learning_v1_zh.md')
    for name,digest in report['export_sha256'].items():assert io.sha(base/'presentation'/name)==digest
    plots=io.read(base/'presentation/figures_v2/plot_receipt.json')
    for name,digest in plots['artifact_sha256'].items():assert io.sha(base/'presentation/figures_v2'/name)==digest
    io.write(base/'presentation/figures_v2/visual_review.json',dict(integrity='PASSED',actual_PNG_viewed='learning_comparison.png',
        review='Actual PNG opened after moving legend above axes: all20 bars, full-group panel, labels, annotation and Chinese limits readable; no overlap. First visual repair and original PNG/SVG retained.',
        artifact_sha256=plots['artifact_sha256'],plot_receipt_sha256=io.sha(base/'presentation/figures_v2/plot_receipt.json')))
    io.write(base/'literature_reading.json',dict(classification='PARTIAL_PRIMARY_READING_NOT_REPRODUCTION',read_UTC_date='2026-10-26',
        sources=[dict(url='https://arxiv.org/abs/1606.05312',read='Official abstract; fixed dynamics/reward-transfer setting',limit='No all-proof reading/reproduction; state dependence can still be fixed MDP'),
                 dict(url='https://arxiv.org/abs/2204.01464',read='Official abstract about prediction/value objective mismatch',limit='No all-proof reading/reproduction'),
                 dict(url='https://arxiv.org/abs/1710.08005',read='Official abstract refreshed; finite-choice SPO+ follows prior definition reading',limit='No claim of original empirical reproduction')],
        required_MDE_ResidualRL_OCCAM_GAUGE_PokeStrike_TOM_neighbors_retained=True,novelty_established=False))
    # Additional strict timestamp audit, without changing the frozen policy,
    # training or original audit. No equal-time or cross-unit reversal allowed.
    strict={}
    for filename in ('fit_attempts.jsonl','replay.jsonl'):
        events=[json.loads(line) for line in (base/filename).read_text(encoding='utf8').splitlines()]
        assert [e['sequence'] for e in events]==list(range(len(events)))
        assert all(a['saved_ns']<b['saved_ns'] for a,b in zip(events,events[1:]))
        strict[filename]=dict(events=len(events),sha256=io.sha(base/filename),strictly_increasing_saved_ns=True)
    results=io.read(base/'results.json');rows=io.read(base/'selected_rows.json');decision=io.read(base/'development_decision.json')
    assert len(rows)==1728 and results['n_selectors']==32
    candidate=sum(r['leaf']['loss'] for r in rows if r['selector']=='JOINT_SPO/TWO_STAGE')
    assert decision['candidate_total_loss']==candidate
    for name,total in decision['all_comparator_total_losses'].items():assert total==sum(r['leaf']['loss'] for r in rows if r['selector']==name)
    assert decision['complete_population_mean_loss_criterion']==all(candidate<t for t in decision['all_comparator_total_losses'].values())
    assert not decision['independent_task_benefit_qualified'] and not decision['permission_for_new_physical_collection']
    io.write(base/'supplemental_delivery_audit.json',dict(integrity='PASSED',strict_time= strict,integer_total_loss_gate_rebuilt=True,
        old_TEST_bytes_unchanged=True,new_physics=0,new_fits=0,online_LLM_API_calls=0))
    out=m.BASE/'result_validation';out.mkdir(exist_ok=False);tools=base/'presentation_tools';tools.mkdir(exist_ok=False)
    for name in ('run_correction_transfer_pipeline_v1.py','build_correction_transfer_report_v1.py','plot_correction_transfer_v1.py',
                 'validate_correction_transfer_delivery_v1.py','verify_correction_transfer_commit_v1.py'):
        shutil.copyfile(external/name,tools/name)
    proof=external/('correction_transfer_freeze_postcommit_'+manifest['source_git_commit'][:12]+'.json')
    assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,tools/'freeze_postcommit_byte_proof.json')
    for name in ('import_receipt.json','install_receipt.json','pip_report.json'):
        shutil.copyfile(external/'correction_scope_plotting_v1'/name,tools/('plot_'+name))
    for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
    io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
    names=set(m.SOURCES)|{'reports/correction_transfer_learning_v1_zh.md'}|{
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
        assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
    names=stage(names,'owned_initial');actual=check(names)
    for label,command in (('dependencies',[sys.executable,'-m','pip','check']),('compile',[sys.executable,'-m','compileall','-q','src','scripts','tests'])):
        p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        io.write(out/(label+'.json'),dict(command=command,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
    assert not io.git('diff','HEAD','--name-only','--diff-filter=M')
    io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2139,new_scientific_tests_after_freeze=0,old_simulation_tests_repeated=False,
        source_sha256={**reuse['source_sha256'],**frozen['source_sha256']},freeze_complete_sha256=io.sha(m.BASE/'freeze_validation/complete.json'),
        full_tracked_secret_scan_reused_sha256=io.sha(m.BASE/'freeze_validation/tracked_secret_scan.json'),
        previously_tracked_files_unchanged_since_freeze=True,all_new_staged_bytes_secret_scanned=True,original_records_and_old_restorations_retained=True))
    io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_and_extra_secret_patterns='PASSED',
        all_new_models_records_failures_staged=True,no_new_large_record_requires_sharding=True))
    io.write(out/'complete.json',dict(integrity='PASSED',source_freeze_commit=manifest['source_git_commit'],manifest_id=manifest['manifest_id'],
        source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
        scientific_neural_fits=15,scientific_neural_updates=15000,scientific_ridge_fits=15,independent_neural_refits=15,independent_neural_updates=15000,
        independent_ridge_refits=15,new_physics=0,online_LLM_API_calls=0,no_independent_robot_qualification=True,wall_ns=perf_counter_ns()-start))
    names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=check(names)
    print(dict(integrity='PASSED',staged_objects=len(actual),unique_source_bound_tests=2139,new_physics=0,online_LLM_API_calls=0))

if __name__=='__main__':validate(sys.argv[1])
