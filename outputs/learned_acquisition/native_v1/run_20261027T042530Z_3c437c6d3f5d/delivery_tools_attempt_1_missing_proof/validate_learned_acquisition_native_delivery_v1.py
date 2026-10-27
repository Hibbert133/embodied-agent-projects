"""Scoped delivery validation; no old population recollection or test inflation."""
from pathlib import Path
from time import perf_counter_ns
import shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_learned_acquisition_native_v1 as command
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
a=command.a;io=a.io;external=Path(__file__).parent;path=Path(sys.argv[1]).resolve();m=a.checked(path);run=path.parent;start=perf_counter_ns()
assert io.git('rev-parse','HEAD')=='33fcb953ad9f30a7975e4bde3694625322ef5472'
assert not io.git('diff','HEAD','--name-only') and not io.git('diff','--cached','--name-only')
frozen=io.read(a.BASE/'freeze_validation/complete.json');reuse=io.read(a.BASE/'freeze_validation/source_reuse.json');repair=io.read(a.BASE/'audit_repair_v2/complete.json')
assert frozen['unique_test_total']==2181 and repair['tests']==2183 and repair['new_array_tests']==2
for mapping in (frozen['source_sha256'],reuse['source_sha256'],repair['source_sha256']):
    for n,h in mapping.items():assert io.sha(ROOT/n)==h
verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
assert io.read(run/'pipeline_control/audit-native_failure.json')['integrity']=='FAILED'
assert not (run/'pipeline_control/completion.json').exists() and not (run/'native/audit.json').exists()
sa=io.read(run/'training_signal/audit.json');na=io.read(run/'native_audit_repair_v2/audit.json')
assert sa['integrity']==na['integrity']=='PASSED'
assert io.read(run/'audit_repair_control_v2/receipt.json')['all_original_live_query_and_decision_values_unchanged']
gate=io.read(run/'native_audit_repair_v2/native_gate.json');assert gate['complete_neural_MOVE_measure_correct_tail_chains']==0 and not gate['task_gain_qualified']
assert gate['original_frozen_audit_status']=='FAILED_RETAINED'
summary=io.read(run/'native/summary.json');assert summary['executions']==54 and summary['control_steps']==5207 and summary['live_model_calls']==28
assert summary['forbidden_fit_guard']['attempts']==summary['network_guard']['attempted_network_calls']==0
assert summary['lifecycle']['counts']['reset_attempts']==2754 and summary['lifecycle']['counts']['simulation_frames_completed']==1403035
for receipt in (sa,na):
    assert all(v==0 for v in receipt['guard']['operation_counts'].values()) and receipt['guard']['network']['attempted_network_calls']==0
delivery=run/'result_delivery';assert io.read(delivery/'independent_descriptive_audit.json')['integrity']=='PASSED'
assert io.read(delivery/'report_receipt.json')['report_sha256']==io.sha(ROOT/'reports/learned_acquisition_native_v1_zh.md')
plots=io.read(delivery/'figures/plot_receipt.json')
for n,h in plots['artifact_sha256'].items():assert io.sha(delivery/'figures'/n)==h
assert io.read(delivery/'figures/visual_review.json')['png_sha256']==io.sha(delivery/'figures/native_and_signal.png')
parts=io.read(run/'record_archives/index.json');assert parts['integrity']=='PASSED' and len(parts['files'])==5
raw_names=set()
for f in parts['files']:
    raw_names.add(f['original']);assert io.sha(ROOT/f['original'])==f['sha256'] and io.sha(Path(f['actual_restored_path']))==f['sha256']
    assert f['gzip_crc_and_utf8_json_complete']
    for part in f['parts']:
        p=run/'record_archives'/part['file'];assert io.sha(p)==part['sha256'] and p.stat().st_size<=4*1024**2
tools=run/'delivery_tools';tools.mkdir(exist_ok=False)
for name in ('summarize_learned_acquisition_native_v1.py','audit_learned_acquisition_native_delivery_v1.py',
    'plot_learned_acquisition_native_v1.py','package_learned_acquisition_native_records_v1.py','build_learned_acquisition_native_report_v1.py',
    'validate_learned_acquisition_native_delivery_v1.py','verify_learned_acquisition_native_commit_v1.py','verify_learned_native_audit_repair_commit_v2.py'):
    shutil.copyfile(external/name,tools/name)
for name in ('learned_acquisition_native_freeze_postcommit_3c437c6d3f5d.json','learned_acquisition_native_repair_postcommit_33fcb953ad9f.json'):
    assert io.read(external/name)['integrity']=='PASSED';shutil.copyfile(external/name,tools/name)
for name in ('import_receipt.json','install_receipt.json','pip_report.json'):shutil.copyfile(external/'correction_scope_plotting_v1'/name,tools/('plot_'+name))
for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
io.write(delivery/'literature_reading.json',dict(classification='PARTIAL_PRIMARY_READING_NOT_REPRODUCTION',UTC_date='2026-10-27',
    sources=[dict(url='https://arxiv.org/html/2609.32154v1',read='Official abstract, selected equations and discussion; inverse objective already penalizes uncertainty at candidate actual command',limit='No complete replication or novelty claim'),
             dict(url='https://proceedings.mlr.press/v305/aoyama25a.html',read='Official abstract; task-informed exploration and uncertainty stopping',limit='PDF fetch returned internal error; no full-text reading or replication claim')],
    required_MDE_ResidualRL_OCCAM_GAUGE_Poke_routes_retained=True,novelty_established=False))
io.write(delivery/'stage_completion.json',dict(status='COLLECTED_ORIGINAL_AUDIT_FAILED_SUPPLEMENTED_WITH_NEGATIVE_BEHAVIOR_GATE',manifest_id=m['manifest_id'],
    original_frozen_qualification='FAILED_RETAINED',supplementary_audit='PASSED',complete_neural_MOVE_chains=0,
    new_physical_executions=54,control_steps=5207,all_resets=2754,physical_frames=1403035,
    live_RBF_decisions=14,live_neural_decisions=14,new_model_fits=0,online_LLM_API_calls=0,task_gain_qualified=False,publication_goal_complete=False))
out=a.BASE/'result_validation';out.mkdir(exist_ok=False)
names=set(command.SOURCES)|{'src/analysis/learned_acquisition_native_audit_v2.py','tests/test_learned_native_audit_repair_v2.py',
    'docs/protocols/learned_native_audit_repair_v2_zh.md','reports/learned_acquisition_native_v1_zh.md'}|{
    p.relative_to(ROOT).as_posix() for p in a.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
names-=raw_names;assert all((ROOT/n).stat().st_size<=8*1024**2 for n in names)
def stage(selected,label):
    p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode('utf8') for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def check(selected):
    actual=index_bytes(selected)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if b'\0' not in data:
            for label,pattern in EXTRA.items():assert pattern.search(data.decode('utf8',errors='replace')) is None,(label,n)
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names,'owned_initial');actual=check(names)
for label,args in (('dependencies',[sys.executable,'-m','pip','check']),('compile',[sys.executable,'-m','compileall','-q','src','scripts','tests'])):
    p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True);io.write(out/(label+'.json'),dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr));assert p.returncode==0
assert not io.git('diff','HEAD','--name-only','--diff-filter=M')
io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2183,new_scientific_tests_after_repair_freeze=0,
    source_sha256={**reuse['source_sha256'],**frozen['source_sha256'],**repair['source_sha256']},old_simulation_tests_repeated=False,
    full_tracked_secret_scan_reused_sha256=io.sha(a.BASE/'freeze_validation/tracked_secret_scan.json'),
    unchanged_original_tracked_files_and_new_repair_files_already_scanned=True,all_new_staged_bytes_scanned=True,unrelated_untracked_excluded=True))
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,secret_patterns='basic_and_EXTRA_PASSED',
    excluded_original_raw_files=sorted(raw_names),bounded_shards_and_actual_restoration_index_sha256=io.sha(run/'record_archives/index.json')))
io.write(out/'complete.json',dict(integrity='PASSED',original_source_freeze=m['source_git_commit'],repair_source_freeze=na['repair_source_git_commit'],
    original_frozen_qualification='FAILED_RETAINED',supplementary_audit='PASSED',complete_neural_MOVE_chains=0,unique_tests=2183,
    source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
    new_physical_executions=54,control_steps=5207,new_model_fits=0,online_LLM_API_calls=0,task_gain_qualified=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=check(names)
print(dict(integrity='PASSED',staged_changed_objects=len(actual),unique_source_bound_tests=2183,original_qualification='FAILED_RETAINED',actual_control_steps=5207))
