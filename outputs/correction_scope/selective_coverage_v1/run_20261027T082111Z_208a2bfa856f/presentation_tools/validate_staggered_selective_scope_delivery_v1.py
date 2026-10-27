"""Actual-index/source proof; original failed reader remains distinct from v2."""
from pathlib import Path
from time import perf_counter_ns
import csv,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_staggered_selective_scope_v1 as command
from src.analysis.staggered_selective_reader_v2 import plain_rows
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=command.main;io=main.io;external=Path(__file__).parent;path=Path(sys.argv[1]).resolve();m=main.checked(path);run=path.parent;start=perf_counter_ns()
reader=io.read(run/'reader_audit_v2/manifest.json');head=reader['source_git_commit']
assert io.git('rev-parse','HEAD')==head and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
frozen=io.read(main.BASE/'freeze_validation/complete.json');reuse=io.read(main.BASE/'freeze_validation/source_reuse.json');repair=io.read(main.BASE/'reader_freeze_v2/complete.json')
assert frozen['unique_test_total']==reuse['unique_tests']==2228 and frozen['new_unique_tests']==0
for mapping in (frozen['source_sha256'],reuse['source_sha256'],repair['source_sha256'],repair['unchanged_input_sha256']):
    for n,h in mapping.items():assert io.sha(ROOT/n)==h
verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
assert io.read(run/'pipeline_control/construct_receipt.json')['integrity']=='PASSED'
failure=io.read(run/'pipeline_control/audit_failure.json');assert failure['integrity']=='FAILED' and 'BadGzipFile' in failure['exception']
assert not (run/'pipeline_control/completion.json').exists() and not (run/'construction/audit.json').exists()
audit=io.read(run/'reader_audit_v2/audit.json');assert audit['integrity']=='PASSED' and io.read(run/'reader_audit_v2/completion.json')['primary_construction_not_repeated']
receipt=io.read(run/'construction/receipt.json');assert receipt['forecasts']==receipt['threshold_updates']==audit['independent_integer_reconstruction_updates']==12400
assert receipt['events']==audit['events']==37210
for r in (receipt,audit,io.read(run/'presentation/report_receipt.json')):
    assert all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']['attempted_network_calls']==0
expected=[];selected=0
for p in (1,2,4,8,16):
    summary=io.read(run/'construction'/('P'+str(p))/'summary.json');assert summary['marginal_coverage']==[19,20] and summary['selected_coverage']==[0,1]
    assert summary['counts']==dict(predictions=400*p,labels=400*p,updates=400*p,miscovered=20*p,selected=19*p,selected_miscovered=19*p)
    pending={}
    for e in plain_rows(run/'construction'/('P'+str(p))/'events.jsonl'):
        if e['event']=='PREDICTION':pending[e['forecast_index']]=e
        elif e['event']=='THRESHOLD_UPDATE':
            pred=pending.pop(e['forecast_index']);assert pred['time']<e['time']==pred['label_due'] and e['before']==pred['threshold']
            expected.append(dict(delay=p,forecast_index=pred['forecast_index'],thread=pred['thread'],forecast_time=pred['time'],label_available_time=pred['label_due'],
                threshold_numerator=pred['threshold'][0],threshold_denominator=pred['threshold'][1],warmup_complete=pred['eligible'],selected=pred['selected'],
                miscovered_when_label_revealed=e['miscovered'],threshold_after_update_numerator=e['after'][0],threshold_after_update_denominator=e['after'][1]))
            selected+=pred['selected']
    assert not pending
assert len(expected)==12400 and selected==589
presentation=run/'presentation'
with (presentation/'all12400_forecasts.csv').open(encoding='utf8',newline='') as stream:
    actual=list(csv.DictReader(stream));assert len(actual)==12400
    for item,saved in zip(actual,expected):assert item=={k:str(v) for k,v in saved.items()}
assert io.read(presentation/'report_receipt.json')['report_sha256']==io.sha(ROOT/'reports/staggered_selective_scope_v1_zh.md')
assert io.read(presentation/'research_decision.json')['not_a_robot_harm_rate']
cost=io.read(presentation/'costs.json');assert cost['primary_threshold_calibration_updates']==cost['independent_integer_reconstruction_updates']==12400
assert cost['first_failed_reader_integer_updates']==0 and cost['new_unit_tests_claimed']==0
io.write(presentation/'supplemental_statistics_audit.json',dict(integrity='PASSED',all12400_CSV_rows_exact=True,all5_cases_retained=True,all589_selected_predictions_miscovered=True,
    original_reader_failure_retained_and_v2_separate=True,all_labels_revealed_after_forecast=True,no_pending_labels_discarded=True,
    source_math_and_original_generated_bytes_unchanged=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
tools=run/'presentation_tools';tools.mkdir(exist_ok=False)
for n in ('build_staggered_selective_scope_report_v1.py','validate_staggered_selective_scope_delivery_v1.py','verify_staggered_selective_scope_commit_v1.py'):shutil.copyfile(external/n,tools/n)
for phase,commit in (('freeze',m['source_git_commit']),('reader-v2',head)):
    p=external/f'staggered_selective_scope_{phase}_postcommit_{commit[:12]}.json';assert io.read(p)['integrity']=='PASSED';shutil.copyfile(p,tools/(phase+'_postcommit_byte_proof.json'))
for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
out=main.BASE/'result_validation';out.mkdir(exist_ok=False)
names=set(command.SOURCES)|set(repair['source_sha256'])|{'reports/staggered_selective_scope_v1_zh.md'}|{p.relative_to(ROOT).as_posix() for p in main.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
assert all((ROOT/n).stat().st_size<=8*1024**2 for n in names)
def stage(selected,label):
    p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def scan(selected):
    actual=index_bytes(selected)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:assert not any(pattern.search(data.decode('utf8',errors='replace')) for pattern in EXTRA.values())
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names,'owned_initial');actual=scan(names)
for label,args in (('compile',[sys.executable,'-m','compileall','-q','src','scripts','tests']),('dependencies',[sys.executable,'-m','pip','check'])):
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True);io.write(out/(label+'.json'),dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
assert not io.git('diff','HEAD','--name-only','--diff-filter=M')
io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2228,new_unit_tests=0,source_sha256={**reuse['source_sha256'],**frozen['source_sha256'],**repair['source_sha256']},
    exact_mathematical_audit_sha256=io.sha(run/'reader_audit_v2/audit.json'),old_simulation_tests_repeated=False,old_six_tensor_groups_separate=True,previously_tracked_files_unchanged=True,
    full_tracked_secret_scan_reused_sha256=io.sha(main.BASE/'freeze_validation/tracked_secret_scan.json'),reader_new_index_secret_scan_proof_sha256=io.sha(main.BASE/'reader_freeze_v2/index_disk_proof.json'),new_actual_index_basic_and_extra_secrets=True))
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,all37210_events_and12400_CSV_rows_retained=True,no_new_large_record_requires_sharding=True))
io.write(out/'complete.json',dict(integrity='PASSED',original_source_freeze_commit=m['source_git_commit'],reader_freeze_commit=head,
    source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
    unique_source_bound_reused_tests=2228,new_unit_tests=0,independent_exact_reconstruction='PASSED',original_reader_failure='RETAINED',
    primary_threshold_updates=12400,independent_integer_updates=12400,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,
    not_a_robot_or_method_qualification=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=scan(names)
print(dict(integrity='PASSED',staged_objects=len(actual),mathematical_audit='PASSED',new_unit_tests=0),flush=True)
