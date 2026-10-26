from pathlib import Path
from time import perf_counter_ns
import gzip, json, shutil, sys

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0,str(ROOT))
from src.analysis import correction_trace_value_v1 as m
io=m.io


def preserve(path):
    path=Path(path).resolve();manifest=m.checked(path);base=path.parent
    assert io.read(base/'pipeline_control/completion.json')['status']=='COMPLETED'
    audit=io.read(base/'replay_audit.json');assert audit['integrity']=='PASSED'
    out=base/'preservation';out.mkdir(exist_ok=False)
    restore=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent/trace_value_restored_20261026_3875955')
    restore.mkdir(exist_ok=False)
    start=perf_counter_ns();guard={}
    with m.old.recorded_guard(guard,out/'failure.json'):
        source=base/'replay.jsonl';source_hash=io.sha(source)
        assert source_hash==audit['replay_sha256']
        archive=out/'replay.jsonl.gz'
        with source.open('rb') as stream,gzip.open(archive,'xb',compresslevel=6) as dest:
            shutil.copyfileobj(stream,dest,1024**2)
        assert archive.stat().st_size<=8*1024**2
        rebuilt=restore/'replay.jsonl';lines=0
        with gzip.open(archive,'rb') as stream,rebuilt.open('xb') as dest:
            for block in iter(lambda:stream.read(1024**2),b''):
                dest.write(block);lines+=block.count(b'\n')
        assert io.sha(rebuilt)==source_hash and rebuilt.stat().st_size==source.stat().st_size
        with rebuilt.open(encoding='utf8') as f:
            previous=-1
            for line in f:
                event=json.loads(line);assert event['sequence']==previous+1;previous=event['sequence']
        assert lines==previous+1
        entry=dict(original=source.relative_to(ROOT).as_posix(),bytes=source.stat().st_size,sha256=source_hash,
            committed_compressed=archive.relative_to(ROOT).as_posix(),compressed_bytes=archive.stat().st_size,
            compressed_sha256=io.sha(archive),restored_path=str(rebuilt),restored_sha256=io.sha(rebuilt),
            restored_bytes=rebuilt.stat().st_size,lines=lines,original_large_file_retained_local=True)
    io.write(out/'index.json',dict(integrity='PASSED',manifest_id=manifest['manifest_id'],files=[entry],
        stage_excluded_local_originals=[source.relative_to(ROOT).as_posix()],
        all_originals_and_actual_restorations_retained=True))
    io.write(out/'restoration_validation.json',dict(integrity='PASSED',actual_file_restorations=1,
        index_sha256=io.sha(out/'index.json'),restore_directory=str(restore),guard=guard,
        wall_ns=perf_counter_ns()-start,script_sha256=io.sha(__file__),
        new_physics=0,new_fits=0,new_policy_queries=0,online_LLM_API_calls=0))
    print(dict(integrity='PASSED',actual_file_restorations=1,compressed_replay_bytes=archive.stat().st_size,
        original_replay_bytes=source.stat().st_size,rows=lines))


if __name__=='__main__':preserve(sys.argv[1])
