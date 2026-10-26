from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,shutil,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_risk_reference_v1 as m
io=m.io

def preserve(path):
    path=Path(path).resolve();manifest=m.checked(path);base=path.parent
    assert io.read(base/'pipeline_control/completion.json')['status']=='COMPLETED'
    assert io.read(base/'replay_audit.json')['integrity']=='PASSED'
    out=base/'preservation';out.mkdir(exist_ok=False)
    restore=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/risk_reference_restored_20261026_82a3873');restore.mkdir(exist_ok=False)
    start=perf_counter_ns();guard={};entries=[]
    with m.recorded_guard(guard,out/'failure.json'):
        source=base/'development_replay.jsonl';source_hash=io.sha(source)
        assert source_hash==io.read(base/'replay_audit.json')['replay_sha256']
        archive=out/'development_replay.jsonl.gz'
        with source.open('rb') as stream,gzip.open(archive,'xb',compresslevel=6) as dest:shutil.copyfileobj(stream,dest,1024**2)
        assert archive.stat().st_size<=8*1024**2
        rebuilt=restore/'development_replay.jsonl';lines=0
        with gzip.open(archive,'rb') as stream,rebuilt.open('xb') as dest:
            for block in iter(lambda:stream.read(1024**2),b''):dest.write(block);lines+=block.count(b'\n')
        assert io.sha(rebuilt)==source_hash and rebuilt.stat().st_size==source.stat().st_size
        last=next(reversed(source.read_text(encoding='utf8').splitlines()));assert lines==io.json.loads(last)['sequence']+1
        entries.append(dict(original=source.relative_to(ROOT).as_posix(),bytes=source.stat().st_size,sha256=source_hash,
            committed_compressed=archive.relative_to(ROOT).as_posix(),compressed_bytes=archive.stat().st_size,compressed_sha256=io.sha(archive),
            restored_path=str(rebuilt),restored_sha256=io.sha(rebuilt),lines=lines,original_large_file_retained_local=True))
        fit=io.read(base/'fit_receipt.json')
        for cohort,count in (('TRAIN',54),('CAL',18)):
            p=base/(cohort.lower()+'_graphs.jsonl.gz');rebuilt=restore/p.name
            assert io.sha(p)==fit['graphs_sha256'][cohort];shutil.copyfile(p,rebuilt);assert io.sha(p)==io.sha(rebuilt)
            with gzip.open(rebuilt,'rb') as stream:actual=sum(block.count(b'\n') for block in iter(lambda:stream.read(1024**2),b''))
            assert actual==count
            entries.append(dict(original=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=io.sha(p),committed_direct=True,
                restored_path=str(rebuilt),restored_sha256=io.sha(rebuilt),gzip_rows=actual))
    io.write(out/'index.json',dict(integrity='PASSED',manifest_id=manifest['manifest_id'],files=entries,
        stage_excluded_local_originals=[source.relative_to(ROOT).as_posix()],all_originals_and_actual_restorations_retained=True))
    io.write(out/'restoration_validation.json',dict(integrity='PASSED',actual_file_restorations=3,index_sha256=io.sha(out/'index.json'),
        restore_directory=str(restore),guard=guard,wall_ns=perf_counter_ns()-start,script_sha256=io.sha(__file__),
        new_physics=0,new_fits=0,new_policy_queries=0,online_LLM_API_calls=0))
    print(dict(integrity='PASSED',actual_file_restorations=3,compressed_replay_bytes=archive.stat().st_size,original_replay_bytes=source.stat().st_size))

if __name__=='__main__':preserve(sys.argv[1])
