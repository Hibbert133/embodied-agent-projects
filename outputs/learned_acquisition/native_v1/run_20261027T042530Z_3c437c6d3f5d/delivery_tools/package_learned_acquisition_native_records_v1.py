"""Keep original gzip journals, commit bounded shards and actually restore them."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,json,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import learned_acquisition_native_io_v1 as a
io=a.io;path=Path(sys.argv[1]).resolve();m=a.checked(path);run=path.parent
out=run/'record_archives';out.mkdir(exist_ok=False);start=perf_counter_ns()
restore=Path(r'C:/Users/Administrator/Documents/ChatGPT/robotic agent')/('learned_native_restoration_'+run.name);restore.mkdir(exist_ok=False)
files=[]
for source in sorted([p for folder in ('native','native_audit_repair_v2') for p in (run/folder).glob('*.jsonl.gz')]):
    prefix=source.parent.name+'_'+source.name.removesuffix('.jsonl.gz');parts=[]
    with source.open('rb') as stream:
        for i,block in enumerate(iter(lambda:stream.read(4*1024**2),b'')):
            p=out/(prefix+'.part%03d.bin'%i)
            with p.open('xb') as target:target.write(block)
            parts.append(dict(file=p.name,bytes=len(block),sha256=io.sha(p)))
    folder=restore/source.parent.name;folder.mkdir(exist_ok=True);restored=folder/source.name
    with restored.open('xb') as target:
        for part in parts:
            p=out/part['file'];assert io.sha(p)==part['sha256']
            with p.open('rb') as stream:
                for block in iter(lambda:stream.read(1024**2),b''):target.write(block)
    assert restored.stat().st_size==source.stat().st_size and io.sha(restored)==io.sha(source)
    count=decoded=0
    with gzip.open(restored,'rb') as stream:
        for line in stream:
            decoded+=len(line);json.loads(line);count+=1
    files.append(dict(original=source.relative_to(ROOT).as_posix(),bytes=source.stat().st_size,sha256=io.sha(source),parts=parts,
        actual_restored_path=str(restored),actual_restored_sha256=io.sha(restored),decoded_jsonl_rows=count,decoded_bytes=decoded,gzip_crc_and_utf8_json_complete=True))
io.write(out/'index.json',dict(schema='LEARNED_NATIVE_EXACT_GZIP_SHARDS_V1',integrity='PASSED',manifest_id=m['manifest_id'],
    files=files,maximum_part_bytes=4*1024**2,original_raw_files_preserved=True,restore_directory_preserved=str(restore),
    wall_ns=perf_counter_ns()-start,new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
print(dict(integrity='PASSED',files=len(files),parts=sum(len(f['parts']) for f in files),raw_bytes=sum(f['bytes'] for f in files)))
