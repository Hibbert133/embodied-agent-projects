"""Check published objects and persist verified archival receipts locally."""
from pathlib import Path
from time import perf_counter_ns
import shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
out=ROOT/'outputs/research_archive/learned_native_v1';external=Path(__file__).parent;source='2c50164b3a69a044133ef93e51ee280a2a2bf4a7';start=perf_counter_ns()
assert io.git('rev-parse','HEAD')==source and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_receipt.json');intent=io.read(out/'push_intent.json')
assert local['integrity']==remote['integrity']=='PASSED' and local['source_local_commit']==intent['source_local_commit']==source
assert local['archive_commit']==remote['remote_after']=='ea8fe4e9e0601885238d607bf59c0b80ea4e3db0'
assert local['archive_parent']==remote['remote_before']=='f478a2a73da035d69dd97164b2f1713e85bc4c8a'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
catalog={r['path']:r for r in io.read(out/'catalog.json')['files']};published={}
run=ROOT/'outputs/learned_acquisition/native_v1/run_20261027T042530Z_3c437c6d3f5d'
paths=[ROOT/'reports/learned_acquisition_native_v1_zh.md',ROOT/'configs/movement_task/learned_acquisition_native_v1.json',
    ROOT/'src/analysis/learned_acquisition_native_audit_v1.py',ROOT/'src/analysis/learned_acquisition_native_audit_v2.py']
paths.extend((ROOT/'assets/learned_acquisition_native_v1').iterdir())
paths.extend(run/'result_delivery'/n for n in ('results.json','all_native_cases.json','all_native_failures.json','all_paired_differences.json','source_future_cells.json','native_group_task_context_cells.json','independent_descriptive_audit.json','stage_completion.json','all_live_decision_wall_intervals.json'))
paths.extend(run/'training_signal'/n for n in ('case_signal.json','shared_past_signal.json','public_window_terms.csv','analysis.json','audit.json'))
paths.extend(run/'native_audit_repair_v2'/n for n in ('audit.json','native_gate.json','actual_closed_loop_chains.json','actual_command_divergences.json'))
paths.extend((run/'pipeline_control/audit-native_failure.json',run/'audit_repair_control_v2/receipt.json',run/'record_archives/index.json',run/'result_delivery/figures/native_and_signal.png'))
for p in paths:
    name=p.relative_to(ROOT).as_posix();entry=catalog[name];assert entry['published'] and entry['sha256']==io.sha(p)
    assert io.git('rev-parse',local['archive_commit']+':'+name)==entry['oid'];published[name]=entry['sha256']
pack=io.read(run/'record_archives/index.json')
for f in pack['files']:
    assert f['original'] not in catalog
    for part in f['parts']:assert not catalog[(run/'record_archives'/part['file']).relative_to(ROOT).as_posix()]['published']
for name in ('build_learned_native_archive_v1.py','push_learned_native_archive_v1.py','validate_learned_native_archive_v1.py','verify_learned_acquisition_native_commit_v1.py'):
    shutil.copyfile(external/name,out/name)
proof=external/('learned_acquisition_native_result_postcommit_'+source[:12]+'.json');assert io.read(proof)['integrity']=='PASSED'
shutil.copyfile(proof,out/'result_postcommit_byte_proof.json')
for p in out.glob('*.py'):compile(p.read_bytes(),str(p),'exec')
names={p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()}
def stage(selected,label):
    p=out/(label+'.nul');selected=set(selected)|{p.relative_to(ROOT).as_posix()};p.write_bytes(b'\0'.join(n.encode() for n in sorted(selected))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+p.relative_to(ROOT).as_posix(),'--pathspec-file-nul');return selected
def scan(selected):
    actual=index_bytes(selected)
    for name in actual:
        data=(ROOT/name).read_bytes()
        if b'\0' not in data:assert not any(pattern.search(data.decode('utf8',errors='replace')) for pattern in EXTRA.values())
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
names=stage(names,'owned_paths_initial');actual=scan(names)
io.write(out/'archive_delivery_validation.json',dict(integrity='PASSED',source_local_result_commit=source,remote_archive_commit=local['archive_commit'],
    published_key_assets_sha256=published,scoped_compilation='PASSED',actual_index_and_disk_sha256=actual,actual_index_secrets='PASSED',
    ordinary_and_staged_diff='PASSED',original_frozen_qualification='FAILED_RETAINED',supplemental_behavior_chain_count=0,
    raw_originals_local_and_bounded_shards_unpublished=True,original_records_and_restorations_retained=True,
    no_force_no_merge=True,receipt_work_new_physics=0,new_model_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start))
names=stage(names|{p.relative_to(ROOT).as_posix() for p in out.iterdir() if p.is_file()},'owned_paths_final');actual=scan(names)
print(dict(integrity='PASSED',archival_index_objects=len(actual),key_published_assets=len(published),remote_archive_commit=local['archive_commit']))
