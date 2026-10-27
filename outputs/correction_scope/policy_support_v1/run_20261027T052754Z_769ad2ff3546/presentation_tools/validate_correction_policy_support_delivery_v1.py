"""Actual-index, full-denominator and artifact delivery checks."""
from pathlib import Path
from time import perf_counter_ns
import csv,shutil,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_correction_policy_support_v1 as command
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=command.main;io=main.io;external=Path(__file__).parent;path=Path(sys.argv[1]).resolve();m=main.checked(path);run=path.parent;start=perf_counter_ns()
assert io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
frozen=io.read(main.BASE/'freeze_validation/complete.json');reuse=io.read(main.BASE/'freeze_validation/source_reuse.json');assert frozen['unique_test_total']==2202 and frozen['new_unique_tests']==19
for mapping in (frozen['source_sha256'],reuse['source_sha256']):
    for n,h in mapping.items():assert io.sha(ROOT/n)==h
verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
receipt=io.read(run/'analysis/receipt.json');audit=io.read(run/'analysis/audit.json');assert audit['integrity']=='PASSED'
assert io.read(run/'pipeline_control/completion.json')['status']=='COMPLETED_POST_HOC_ANALYSIS'
for r in (receipt,audit):
    assert all(v==0 for v in r['guard']['operation_counts'].values()) and r['guard']['network']['attempted_network_calls']==0 and r['model_guard']['attempts']==0
assert receipt['replay_fixed_policy_queries']==audit['independent_replay_fixed_policy_queries']==26822
assert receipt['responses_consumed']==28348 and audit['literal_pi_checks']==26822
rows=io.read(run/'analysis/attempts.json');bounds=io.read(run/'analysis/unit_bounds.json');summaries=io.read(run/'analysis/fixed_program_bounds.json')
assert len(rows)==648 and len(bounds)==216 and len(summaries)==12
assert sum(r['status']=='SUPPORTED_FACTUAL_OUTCOME' for r in rows)==198
for r in rows:
    assert r['source_responses_consumed']==r['matched_prefix_steps']
    if r['status']=='UNKNOWN_AFTER_COMMAND_DIFFERENCE':assert r['supported_loss'] is None and r['supported_success'] is None and r['source_commands_examined']==r['matched_prefix_steps']+1
    else:assert r['source_commands_examined']==r['matched_prefix_steps']
for action,rate in main.CANDIDATES:
    r=next(x for x in summaries if x['action']==action and x['rate']==rate);b=[x for x in bounds if x['action']==action and x['rate']==rate]
    assert r['n']==18 and r['supported']+r['unknown']==18 and r['lower_total']==sum(x['lower'] for x in b) and r['upper_total']==sum(x['upper'] for x in b)
    assert r['lower_mean']<=1435/18<=r['upper_mean']
    assert r['supported']==sum(x['status']=='SUPPORTED_FACTUAL_OUTCOME' for x in b)
presentation=run/'presentation';primary=next(x for x in summaries if x['action']=='VALIDATE8' and x['rate']==.125)
assert primary['supported']==15 and primary['unknown']==3 and (primary['lower_total'],primary['upper_total'])==(1048,2473)
assert io.read(presentation/'research_decision.json')['all12_intervals_include_model']
with (presentation/'unit_bounds.csv').open(encoding='utf8',newline='') as stream:
    exported=list(csv.DictReader(stream));assert len(exported)==216
    for x,b in zip(exported,bounds):
        assert [x[k] for k in ('cohort','group','task','context')]==[str(v) for v in b['unit']]
        assert x['action']==b['action'] and float(x['rate'])==b['rate'] and int(x['lower'])==b['lower'] and int(x['upper'])==b['upper']
report=io.read(presentation/'report_receipt.json');assert report['report_sha256']==io.sha(ROOT/'reports/correction_policy_support_v1_zh.md')
plots=io.read(presentation/'figures/plot_receipt.json')
for n,h in plots['artifact_sha256'].items():assert io.sha(presentation/'figures'/n)==h
assert io.read(presentation/'figures/visual_review.json')['png_sha256']==io.sha(presentation/'figures/fixed_program_bounds.png')
io.write(presentation/'supplemental_statistics_audit.json',dict(integrity='PASSED',all648_attempts_and216_bounds_retained=True,
    all12_programs_full_denominators=True,CSV216_rows_checked=True,primary_integer_total_bound=[1048,2473],
    first_difference_responses_never_consumed=True,no_unknown_outcome_imputed=True,original_native_qualification='FAILED_RETAINED',
    new_physics=0,new_fits=0,online_LLM_API_calls=0))
io.write(presentation/'literature_reading.json',dict(classification='PARTIAL_PRIMARY_READING_NOT_REPRODUCTION',UTC_date='2026-10-27',
    sources=[dict(url='https://arxiv.org/html/2505.24097v1',read='Official abstract/introduction and selected Definition3.1, Assumption3.2, per-round sample paragraphs',limit='No proof or algorithm reproduction; do not transfer guarantees; attempted v3 returned404'),
        dict(url='https://www.microsoft.com/en-us/research/publication/unbiased-offline-evaluation-of-contextual-bandit-based-news-article-recommendation-algorithms-2/',read='Publisher abstract',limit='No unbiased bandit claim applied to the robot'),
        dict(url='https://proceedings.mlr.press/v235/khan24b.html',read='Official abstract',limit='No smoothness or sharp-bound theorem claimed'),
        dict(url='https://arxiv.org/html/2401.04007v2',read='Selected introduction and limitations',limit='No full reproduction'),
        dict(url='https://proceedings.mlr.press/v211/ma23a.html',read='Official abstract and prior saved selected-body note',limit='No complete reproduction')],novelty_established=False))
tools=run/'presentation_tools';tools.mkdir(exist_ok=False)
for n in ('plot_correction_policy_support_v1.py','build_correction_policy_support_report_v1.py','validate_correction_policy_support_delivery_v1.py','verify_correction_policy_support_commit_v1.py'):shutil.copyfile(external/n,tools/n)
proof=external/('correction_policy_support_freeze_postcommit_'+m['source_git_commit'][:12]+'.json');assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,tools/'freeze_postcommit_byte_proof.json')
for n in ('import_receipt.json','install_receipt.json','pip_report.json'):shutil.copyfile(external/'correction_scope_plotting_v1'/n,tools/('plot_'+n))
for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
out=main.BASE/'result_validation';out.mkdir(exist_ok=False)
names=set(command.SOURCES)|{'reports/correction_policy_support_v1_zh.md'}|{p.relative_to(ROOT).as_posix() for p in main.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
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
io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2202,source_sha256={**reuse['source_sha256'],**frozen['source_sha256']},
    old_simulation_tests_repeated=False,old_six_tensor_groups_separate=True,previously_tracked_files_unchanged=True,
    full_tracked_secret_scan_reused_sha256=io.sha(main.BASE/'freeze_validation/tracked_secret_scan.json'),new_staged_bytes_basic_and_extra_secret_scanned=True))
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,all648_attempts_and_all_bounds_included=True,no_new_large_record_requires_sharding=True))
io.write(out/'complete.json',dict(integrity='PASSED',source_freeze_commit=m['source_git_commit'],source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},
    receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},unique_tests=2202,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,
    original_native_qualification='FAILED_RETAINED',task_gain_qualified=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=scan(names)
print(dict(integrity='PASSED',staged_objects=len(actual),unique_source_bound_tests=2202,new_physics=0),flush=True)
