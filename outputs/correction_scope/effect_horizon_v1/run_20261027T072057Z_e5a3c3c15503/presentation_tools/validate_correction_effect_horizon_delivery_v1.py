"""Full-denominator CSV/source/index proof for the descriptive audit."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
import csv,json,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_correction_effect_horizon_v1 as command
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=command.main;io=main.io;external=Path(__file__).parent;path=Path(sys.argv[1]).resolve();m=main.checked(path);run=path.parent;start=perf_counter_ns()
assert io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
frozen=io.read(main.BASE/'freeze_validation/complete.json');reuse=io.read(main.BASE/'freeze_validation/source_reuse.json')
assert frozen['unique_test_total']==2228 and frozen['new_unique_tests']==12 and reuse['prior_unique_tests']==2216
for mapping in (frozen['source_sha256'],reuse['source_sha256']):
    for n,h in mapping.items():assert io.sha(ROOT/n)==h
verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
assert io.read(run/'pipeline_control/completion.json')['status']=='COMPLETED_DESCRIPTIVE_HORIZON_AUDIT'
receipt=io.read(run/'analysis/receipt.json');audit=io.read(run/'analysis/audit.json');assert audit['integrity']=='PASSED'
for r in (receipt,audit):assert all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']['attempted_network_calls']==0
assert receipt['frozen_matrix_file_reads']==audit['independent_frozen_matrix_file_reads']==9
assert receipt['frozen_matrix_evaluations']==audit['independent_frozen_matrix_evaluations']==4373
assert receipt['deterministic_reference_evaluations']==audit['independent_deterministic_reference_evaluations']==8746
windows=io.read(run/'analysis/windows.json');panels=io.read(run/'analysis/panels.json');presentation=run/'presentation'
assert len(windows)==5832 and len(panels)==2214 and len({(r['pair_id'],r['horizon']) for r in windows})==5832
totals=sorted([p for p in panels if not p['axes']],key=lambda p:p['horizon'])
assert [p['horizon'] for p in totals]==[1,2,4,8,16,32] and [p['available'] for p in totals]==[803,803,772,755,680,560]
assert all(p['registered']==972 for p in totals) and len(io.read(presentation/'full1944_strata.json'))==1944
for r in windows:
    assert r['analysis_semantics']=='POST_HOC_EXECUTED_INPUTS_NOT_FORECAST'
    if r['status']=='COMPLETE_FACTUAL_WINDOW':assert r['future_commands_consumed_for_evaluation']==r['horizon']-1 and r['no_unexecuted_states_generated']
    else:assert r['mse'] is None and r['predictions'] is None and 'actual_endpoint_difference_xy' not in r
with (presentation/'all5832_windows.csv').open(encoding='utf8',newline='') as f:
    exported=list(csv.DictReader(f));assert len(exported)==5832
    for item,r in zip(exported,windows):
        assert item['pair_id']==r['pair_id'] and int(item['horizon'])==r['horizon'] and item['status']==r['status']
        for kind in main.METHODS:
            if r['mse'] is None:assert item[kind]==''
            else:assert float(item[kind])==r['mse'][kind]
with (presentation/'all2214_panels.csv').open(encoding='utf8',newline='') as f:
    exported=list(csv.DictReader(f));assert len(exported)==2214
    for item,p in zip(exported,panels):
        assert int(item['horizon'])==p['horizon'] and json.loads(item['axes'])==p['axes'] and json.loads(item['values'])==p['values']
        assert int(item['registered'])==p['registered'] and int(item['available'])==p['available'] and json.loads(item['statuses'])==p['statuses']
        for kind in main.METHODS:
            if p['mse'][kind] is None:assert item[kind]==''
            else:assert float(item[kind])==p['mse'][kind]
assert io.sha(main.previous.SOURCE/'results/statistics.json')=='d567b1a827b11edb1237b20f59d554fc1cf1a91733adc58b8b614e370c7826a4'
assert io.read(main.EFFECT/'evaluation/decision.json')['status']=='NO_DEV_PREDICTIVE_ADVANTAGE'
decision=io.read(presentation/'research_decision.json');assert not decision['new_collection_unlocked'] and decision['earlier_paired_context_version']=='CLOSED_NEGATIVE'
cost=io.read(presentation/'costs.json');assert cost['main_frozen_matrix_evaluations']==4373 and cost['new_fits']==0
for r in cost['development_attempts']:assert all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']['attempted_network_calls']==0
assert io.read(presentation/'report_receipt.json')['report_sha256']==io.sha(ROOT/'reports/correction_effect_horizon_v1_zh.md')
figures=presentation/'figures'
io.write(figures/'plot_receipt.json',dict(integrity='PASSED',artifact_sha256={p.name:io.sha(p) for p in figures.iterdir() if p.suffix in ('.png','.pdf','.svg')},first_layout_retained=True))
io.write(figures/'visual_review.json',dict(integrity='PASSED',method='Actual revised PNG inspected through view_image',png_sha256=io.sha(figures/'effect_horizon.png'),Chinese_glyphs_axes_caption_legend_and_margins_checked=True))
io.write(presentation/'supplemental_statistics_audit.json',dict(integrity='PASSED',all5832_windows_and2214_panels_CSV_exact=True,
    all1944_full_strata=True,missing_responses_not_padded=True,old_A1_statistics_and_closed_negative_unchanged=True,new_physics=0,new_fits=0,online_LLM_API_calls=0))
tools=run/'presentation_tools';tools.mkdir(exist_ok=False)
for n in ('plot_correction_effect_horizon_v1.py','build_correction_effect_horizon_report_v1.py','validate_correction_effect_horizon_delivery_v1.py','verify_correction_effect_horizon_commit_v1.py'):shutil.copyfile(external/n,tools/n)
proof=external/('correction_effect_horizon_freeze_postcommit_'+m['source_git_commit'][:12]+'.json');assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,tools/'freeze_postcommit_byte_proof.json')
for n in ('import_receipt.json','install_receipt.json','pip_report.json'):shutil.copyfile(external/'correction_scope_plotting_v1'/n,tools/('plot_'+n))
for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
out=main.BASE/'result_validation';out.mkdir(exist_ok=False)
names=set(command.SOURCES)|{'reports/correction_effect_horizon_v1_zh.md'}|{p.relative_to(ROOT).as_posix() for p in main.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
assert all((ROOT/n).stat().st_size<=8*1024**2 for n in names)
def stage(selected,label):
    p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def scan(selected):
    actual=index_bytes(selected)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,pattern in EXTRA.items():assert pattern.search(data.decode('utf8',errors='replace')) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names,'owned_initial');actual=scan(names)
for label,args in (('compile',[sys.executable,'-m','compileall','-q','src','scripts','tests']),('dependencies',[sys.executable,'-m','pip','check'])):
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True);io.write(out/(label+'.json'),dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
assert not io.git('diff','HEAD','--name-only','--diff-filter=M')
io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2228,source_sha256={**reuse['source_sha256'],**frozen['source_sha256']},
    old_simulation_tests_repeated=False,old_six_tensor_groups_separate=True,previously_tracked_files_unchanged=True,
    full_tracked_secret_scan_reused_sha256=io.sha(main.BASE/'freeze_validation/tracked_secret_scan.json'),new_staged_bytes_basic_and_extra_secret_scanned=True))
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,all5832_windows_and2214_panels_retained=True,no_new_large_record_requires_sharding=True))
io.write(out/'complete.json',dict(integrity='PASSED',source_freeze_commit=m['source_git_commit'],source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},
    receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},unique_tests=2228,new_physics=0,new_fits=0,online_LLM_API_calls=0,
    original_native_qualification='FAILED_RETAINED',descriptive_only_not_entry_forecast=True,task_gain_qualified=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=scan(names)
print(dict(integrity='PASSED',staged_objects=len(actual),unique_source_bound_tests=2228,new_physics=0),flush=True)
