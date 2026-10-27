"""Deliver immutable seed-query snapshots; no scientific operations or old edits."""
from pathlib import Path
from time import perf_counter_ns
import gzip,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis.episode_seed_inventory_v2 import verify_unchanged
from src.analysis.episode_seed_inventory_audit_v2 import audit
from src.analysis.release_learning_guard_v1 import read_only
from outputs.information_release.validation_v1.validate_freeze import index_bytes
from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
BASE=ROOT/'outputs/episode_seed_inventory';OUT=BASE/'delivery_validation_v2';FROZEN='8e3e8e428aac40adb689a7562fb4a47fd1143737'
start=perf_counter_ns();OUT.mkdir(parents=True,exist_ok=False)
assert io.git('rev-parse','HEAD')==FROZEN and not io.git('diff','--name-only') and not io.git('diff','--cached','--name-only')
freeze=io.read(BASE/'freeze_validation_v2/complete.json');assert freeze['integrity']=='PASSED' and freeze['unique_test_total']==2348
for n,h in freeze['source_sha256'].items():assert io.sha(ROOT/n)==h,n
prior=io.read(BASE/'freeze_validation_v2/source_reuse.json');assert prior['unique_tests']==2348
for n,h in prior['source_sha256'].items():assert io.sha(ROOT/n)==h,n
guard={};exports=[];queries=[];names={'reports/episode_seed_inventory_v2_zh.md','docs/research/correction_scope_mechanism_review_v2_zh.md'}
with read_only(guard):
    for tag in ('read_only_20261027','read_only_20261027_final'):
        folder=BASE/'query_v2'/tag;r=io.read(folder/'receipt.json');v=io.read(folder/'inventory.json')
        assert r['integrity']=='PASSED' and r['source_commit']==FROZEN and r['query_status']=='NO_REGISTERED_COLLISION'
        assert r['sampling_authorized'] is False and r['seed_reservation_created'] is False and not any(r['guard']['operation_counts'].values())
        for n,h in r['source_sha256'].items():assert io.sha(ROOT/n)==h,n
        for n,h in r['artifact_sha256'].items():assert io.sha(folder/n)==h,n
        verify_unchanged(ROOT,v)
        if tag.endswith('_final'):independent=audit(ROOT,v)  # First query predates the newly added review document.
        raw=(folder/'inventory.json').read_bytes();packed=gzip.compress(raw,compresslevel=9,mtime=0)
        assert gzip.decompress(packed)==raw
        dest=folder/'inventory.json.gz';dest.write_bytes(packed)
        restored=OUT/(tag+'_inventory.restored.json');restored.write_bytes(gzip.decompress(dest.read_bytes()))
        assert restored.read_bytes()==raw
        exports.append(dict(raw_path=(folder/'inventory.json').relative_to(ROOT).as_posix(),raw_sha256=io.sha(folder/'inventory.json'),raw_bytes=len(raw),
            compressed_path=dest.relative_to(ROOT).as_posix(),compressed_sha256=io.sha(dest),compressed_bytes=len(packed),
            actual_restoration_path=restored.relative_to(ROOT).as_posix(),actual_restoration_sha256=io.sha(restored),actual_restoration_retained_local=True))
        names|={p.relative_to(ROOT).as_posix() for p in folder.iterdir() if p.is_file() and p.name!='inventory.json'}
        queries.append(dict(tag=tag,sources=len(v['sources']),records=len(v['records']),inventory_sha256=io.sha(folder/'inventory.json'),query_wall_ns=r['wall_ns'],
            at_query_independent_audit_sha256=io.sha(folder/'audit.json'),current_source_hashes_unchanged=True))
io.write(OUT/'query_export_index.json',dict(integrity='PASSED',snapshots=exports,raw_JSON_and_actual_restorations_retained_local=True))
io.write(OUT/'source_reuse.json',dict(integrity='PASSED',unique_tests=2348,new_tests_at_delivery=0,source_sha256={**prior['source_sha256'],**freeze['source_sha256']},
    freeze_complete_sha256=io.sha(BASE/'freeze_validation_v2/complete.json'),old_simulation_tests_repeated=False))
io.write(OUT/'costs.json',dict(integrity='PASSED',queries=queries,total_query_wall_ns=sum(q['query_wall_ns'] for q in queries),delivery_guard=guard,
    additional_physical_steps=0,resets=0,physical_frames=0,model_fits=0,policy_queries=0,episode_seed_reservations=0,online_LLM_API_calls=0,
    literature_web_reading_is_not_online_LLM_or_robot_cost=True))
copy=OUT/'validate_delivery.py';copy.write_bytes(Path(__file__).read_bytes().replace(b'\r\n',b'\n'));compile(copy.read_bytes(),str(copy),'exec')
def stage(label):
    global names
    names|={p.relative_to(ROOT).as_posix() for p in OUT.iterdir() if p.is_file() and '.restored.' not in p.name}
    spec=OUT/(label+'.nul');names.add(spec.relative_to(ROOT).as_posix());spec.write_bytes(b'\0'.join(n.encode() for n in sorted(names))+b'\0')
    io.git('-c','maintenance.auto=false','-c','gc.auto=0','add','--pathspec-from-file='+spec.relative_to(ROOT).as_posix(),'--pathspec-file-nul')
def check():
    actual=index_bytes(names)
    for n in actual:
        data=(ROOT/n).read_bytes()
        if n.endswith('.gz'):data=gzip.decompress(data)
        if b'\0' not in data:
            from scripts.check_tracked_secrets import find_secret_rule
            text=data.decode('utf8',errors='replace');assert find_secret_rule(text) is None,n
            assert not any(regex.search(text) for regex in EXTRA.values()),n
    assert not io.git('diff','--check') and not io.git('diff','--cached','--check');return actual
stage('owned_initial');actual=check()
io.write(OUT/'index_disk_proof.json',dict(integrity='PASSED',object_sha256=actual,basic_extra_and_decompressed_index_secret_scans=True))
io.write(OUT/'complete.json',dict(integrity='PASSED',source_freeze_commit=FROZEN,report_sha256=io.sha(ROOT/'reports/episode_seed_inventory_v2_zh.md'),
    mechanism_review_sha256=io.sha(ROOT/'docs/research/correction_scope_mechanism_review_v2_zh.md'),query_snapshots=queries,final_independent_audit=independent,
    full_tracked_secret_scan_reused_sha256=io.sha(BASE/'freeze_validation_v2/tracked_secret_scan.json'),actual_new_index_secrets='PASSED',ordinary_and_staged_diffs='PASSED',
    no_scientific_collection_or_qualification_authorized=True,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,seed_reservations=0,
    raw_sources_and_failed_development_receipts_retained=True,publication_goal_complete=False,wall_ns=perf_counter_ns()-start,
    receipt_sha256={p.name:io.sha(p) for p in OUT.iterdir() if p.is_file() and '.restored.' not in p.name}))
stage('owned_final');check();print(dict(integrity='PASSED',objects=len(names),query_sources=605,new_physics=0,new_fits=0,online_LLM_API_calls=0),flush=True)
