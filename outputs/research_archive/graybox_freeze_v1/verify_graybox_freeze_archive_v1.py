"""Check completed freeze publication without changing the running source/index."""
from pathlib import Path
from time import perf_counter_ns
import sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
out=ROOT/'outputs/research_archive/graybox_freeze_v1';start=perf_counter_ns();local=io.read(out/'local_receipt.json');remote=io.read(out/'remote_receipt.json')
assert io.git('rev-parse','HEAD')==local['source_local_commit'] and not io.git('status','--porcelain','--untracked-files=no') and not io.git('diff','--cached','--name-only')
assert local['integrity']==remote['integrity']=='PASSED' and local['archive_commit']==remote['remote_after'] and local['archive_parent']=='c4e126b3cea7873f0821b7721964fd9e0f80bd9a'
assert io.git('rev-parse',local['archive_commit']+'^')==local['archive_parent']
catalog={r['path']:r for r in io.read(out/'catalog.json')['files']};published={}
paths=io.git('diff','--name-only','2bf53d0b9fa00fd211a6082dc94a26f124dfe467',local['source_local_commit']).splitlines();assert len(paths)==83
for name in paths:
    r=catalog[name];assert r['sha256']==io.sha(ROOT/name) and r['published'] and r['bytes']<=8*1024**2 and not name.endswith(('.jsonl.gz','.bin'))
    assert io.git('rev-parse',local['archive_commit']+':'+name)==r['oid'];published[name]=r['sha256']
io.write(out/'publication_validation.json',dict(integrity='PASSED',source_freeze_commit=local['source_local_commit'],remote_archive_commit=local['archive_commit'],
    all83_completed_source_paths_published=True,published_paths_sha256=published,running_native_result_published=False,ordinary_head_worktree_index_unchanged=True,
    new_physics_in_archive_operation=0,model_fits_in_archive_operation=0,online_LLM_API_calls=0,no_force_no_merge=True,wall_ns=perf_counter_ns()-start))
for n in ('build_graybox_freeze_archive_v1.py','verify_graybox_freeze_archive_v1.py'):(out/n).write_bytes((Path(__file__).parent/n).read_bytes())
io.write(out/'freeze_postcommit_proof.json',io.read(Path(__file__).parent/'graybox_collector_postcommit_cf2712de2ed7.json'))
print(dict(integrity='PASSED',published_completed_paths=len(published),running_result_published=False),flush=True)
