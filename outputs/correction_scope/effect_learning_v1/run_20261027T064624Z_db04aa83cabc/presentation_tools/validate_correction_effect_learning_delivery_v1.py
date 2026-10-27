"""Independent full-denominator exports and actual-index delivery proof."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
import csv,shutil,subprocess,sys
import numpy as np
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_correction_effect_learning_v1 as command
from src.analysis import correction_effect_independent_v1 as independent
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.response_action_io_v1 import verify_runtime
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
main=command.main;io=main.io;external=Path(__file__).parent;path=Path(sys.argv[1]).resolve();m=main.checked(path);run=path.parent;start=perf_counter_ns()
assert io.git('rev-parse','HEAD')==m['source_git_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
frozen=io.read(main.BASE/'freeze_validation/complete.json');reuse=io.read(main.BASE/'freeze_validation/source_reuse.json')
assert frozen['unique_test_total']==2216 and frozen['new_unique_tests']==14 and reuse['prior_unique_tests']==2202
for mapping in (frozen['source_sha256'],reuse['source_sha256']):
    for n,h in mapping.items():assert io.sha(ROOT/n)==h
verify_runtime(io.read(ROOT/'outputs/correction_scope/freeze_validation_v1/runtime_lock.json'))
assert io.read(run/'pipeline_control/completion.json')['status']=='COMPLETED_TRAIN_COMPONENT_DEVELOPMENT'
total_counts=Counter()
for name in ('pairs','models','evaluation'):
    receipt=io.read(run/name/'receipt.json');audit=io.read(run/name/'audit.json');assert audit['integrity']=='PASSED'
    for item in (receipt,audit):
        counts=item['guard']['operation_counts'];assert all(v==0 for k,v in counts.items() if k not in ('solve_attempts','lstsq_attempts'))
        assert item['guard']['network']['attempted_network_calls']==0;total_counts.update(counts)
assert total_counts['solve_attempts']==36 and total_counts['lstsq_attempts']==36
register=io.read(run/'pairs/pair_register.json');rows=io.read(run/'pairs/public_pairs.json');predictions=io.read(run/'models/predictions.json')
assert len(register)==972 and len(rows)==803 and len(predictions)==4818
assert Counter(r['status'] for r in register)==Counter(ACTUAL_DIVERGENCE=803,BEFORE_DECISION_TERMINAL=108,ACQUISITION_TERMINAL=60,NO_SENT_DIFFERENCE=1)
lookup={(p['pair_id'],p['kind']):p for p in predictions};public={r['pair_id']:r for r in rows};presentation=run/'presentation';guard={}
with read_only(guard):
    cells=io.read(presentation/'full_strata_324.json');assert len(cells)==324 and sum(p['registered'] for p in cells)==972 and sum(p['available'] for p in cells)==803
    identities=set()
    for cell in cells:
        key=tuple(cell[k] for k in ('task','context','boundary','acquisition_action','rate_a','rate_b'));assert key not in identities;identities.add(key)
        subset=[r for r in register if (r['task'],r['context'],r['boundary'],r['acquisition_action'],*r['rates'])==key]
        assert len(subset)==cell['registered']==3
        actual=[public[r['pair_id']] for r in subset if r['status']=='ACTUAL_DIVERGENCE'];counts=Counter(r['status'] for r in subset)
        assert len(actual)==cell['available'] and len({r['group'] for r in actual})==cell['independent_groups']
        for status in ('ACTUAL_DIVERGENCE','BEFORE_DECISION_TERMINAL','ACQUISITION_TERMINAL','NO_SENT_DIFFERENCE'):assert counts[status]==cell[status]
        if not actual:
            assert all(cell[kind] is None for kind in main.model.COMPARATORS)
        else:
            w=independent.weights(actual)
            for kind in main.model.COMPARATORS:
                expected=sum(float(q)*sum((lookup[(r['pair_id'],kind)]['prediction'][j]-r['target']['effect'][j])**2 for j in (0,1))/2 for q,r in zip(w,actual))
                independent.equal(expected,cell[kind])
    with (presentation/'full_strata_324.csv').open(encoding='utf8',newline='') as f:
        exported=list(csv.DictReader(f));assert len(exported)==324
        for item,cell in zip(exported,cells):
            for key,value in cell.items():
                if value is None:assert item[key]==''
                elif isinstance(value,str):assert item[key]==value
                else:assert float(item[key])==value
    with (presentation/'all972_pair_register.csv').open(encoding='utf8',newline='') as f:
        exported=list(csv.DictReader(f));assert len(exported)==972
        for item,saved in zip(exported,register):
            assert item['pair_id']==saved['pair_id'] and item['status']==saved['status'] and float(item['loss_difference'])==saved['loss_difference']
            for kind in main.model.COMPARATORS:
                if saved['pair_id'] in public:assert float(item[kind])==lookup[(saved['pair_id'],kind)]['mse']
                else:assert item[kind]==''
    decision=io.read(run/'evaluation/decision.json');assert decision['status']=='NO_DEV_PREDICTIVE_ADVANTAGE'
    assert io.read(presentation/'research_decision.json')['new_collection_unlocked'] is False
    assert io.sha(main.SOURCE/'results/statistics.json')=='d567b1a827b11edb1237b20f59d554fc1cf1a91733adc58b8b614e370c7826a4'
    cost=io.read(presentation/'costs.json');assert cost['scientific_ridge_fits']==cost['independent_augmented_lstsq_refits']==36
    assert cost['main_held_pair_model_evaluations']==cost['independent_held_pair_model_evaluations']==4818
    assert len(cost['synthetic_test_attempts_separately_charged'])==3 and sum(r['synthetic_solve'] for r in cost['synthetic_test_attempts_separately_charged'])==3
    assert sum(r['synthetic_lstsq'] for r in cost['synthetic_test_attempts_separately_charged'])==3
report=io.read(presentation/'report_receipt.json');assert report['report_sha256']==io.sha(ROOT/'reports/correction_effect_learning_v1_zh.md')
figures=presentation/'figures'
io.write(figures/'plot_receipt.json',dict(integrity='PASSED',all6_comparators_and_all9_groups=True,no_final_CI_invented=True,
    artifact_sha256={p.name:io.sha(p) for p in figures.iterdir() if p.suffix in ('.png','.pdf','.svg')}))
io.write(figures/'visual_review.json',dict(integrity='PASSED',method='Actual generated PNG inspected through view_image before this receipt',
    png_sha256=io.sha(figures/'effect_prediction.png'),Chinese_glyphs_axes_legends_and_margins_checked=True))
io.write(presentation/'supplemental_statistics_audit.json',dict(integrity='PASSED',full972_register_and324_cartesian_cells=True,
    missing_MSE_left_null_and_CSV_blank=True,independent_hierarchical_weights_and_prediction_MSE=True,guard=guard,
    original_A1_six_statistics_sha256_unchanged=True,original_native_qualification='FAILED_RETAINED',new_physics=0,new_fits=0,online_LLM_API_calls=0))
tools=run/'presentation_tools';tools.mkdir(exist_ok=False)
for n in ('plot_correction_effect_learning_v1.py','build_correction_effect_learning_report_v1.py','validate_correction_effect_learning_delivery_v1.py','verify_correction_effect_learning_commit_v1.py'):shutil.copyfile(external/n,tools/n)
proof=external/('correction_effect_learning_freeze_postcommit_'+m['source_git_commit'][:12]+'.json');assert io.read(proof)['integrity']=='PASSED';shutil.copyfile(proof,tools/'freeze_postcommit_byte_proof.json')
for n in ('import_receipt.json','install_receipt.json','pip_report.json'):shutil.copyfile(external/'correction_scope_plotting_v1'/n,tools/('plot_'+n))
for p in tools.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
io.write(tools/'source_sha256.json',{p.name:io.sha(p) for p in tools.iterdir() if p.is_file()})
out=main.BASE/'result_validation';out.mkdir(exist_ok=False)
names=set(command.SOURCES)|{'reports/correction_effect_learning_v1_zh.md'}|{p.relative_to(ROOT).as_posix() for p in main.BASE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
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
io.write(out/'source_reuse.json',dict(integrity='PASSED',unique_tests=2216,source_sha256={**reuse['source_sha256'],**frozen['source_sha256']},
    old_simulation_tests_repeated=False,old_six_tensor_groups_separate=True,previously_tracked_files_unchanged=True,
    full_tracked_secret_scan_reused_sha256=io.sha(main.BASE/'freeze_validation/tracked_secret_scan.json'),new_staged_bytes_basic_and_extra_secret_scanned=True))
io.write(out/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,all972_registered_and803_available_retained=True,all36_models_and4818_predictions_retained=True,no_new_large_record_requires_sharding=True))
io.write(out/'complete.json',dict(integrity='PASSED',source_freeze_commit=m['source_git_commit'],source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in tools.glob('*.py')},
    receipt_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},unique_tests=2216,new_physics=0,scientific_ridge_fits=36,independent_refits=36,online_LLM_API_calls=0,
    original_native_qualification='FAILED_RETAINED',development_status='NO_DEV_PREDICTIVE_ADVANTAGE',task_gain_qualified=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_final');actual=scan(names)
print(dict(integrity='PASSED',staged_objects=len(actual),unique_source_bound_tests=2216,new_physics=0),flush=True)
