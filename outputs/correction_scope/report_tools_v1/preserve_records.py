"""Retain originals; commit bounded chunks and verify real restored gzip bytes."""
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,shutil,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
io=a.io;CHUNK=8*1024**2


def preserve(manifest,restoration):
    manifest=Path(manifest).resolve();m=a.checked(manifest);base=manifest.parent
    io.require(io.read(base/'pipeline_control_v1/completion.json')['status']=='COMPLETED','finished frozen pipeline required')
    out=base/'record_shards_v1';out.mkdir(exist_ok=False)
    restoration=Path(restoration).resolve();restoration.mkdir(exist_ok=False)
    start=perf_counter_ns();guard={};entries=[];compressed=expanded=0
    with read_only(guard):
        for cohort in a.COHORTS:
            folder=base/cohort.lower();audit=io.read(folder/'audit.json');summary=io.read(folder/'summary.json')
            io.require(audit['integrity']=='PASSED','complete journal audit before splitting')
            expected={**audit['collection_sha256'],'examples.jsonl.gz':audit['examples_sha256']}
            counts={'cases.jsonl.gz':summary['executions'],'events.jsonl.gz':summary['events'],
                'witnesses.jsonl.gz':summary['private_records'],'examples.jsonl.gz':2*summary['executions']}
            for name in counts:
                source=folder/name;source_sha=io.sha(source);io.require(source_sha==expected[name],'frozen raw changed before sharding')
                size=source.stat().st_size;parts=[]
                if size>CHUNK:
                    target=out/cohort.lower()/name;target.mkdir(parents=True,exist_ok=False)
                    with source.open('rb') as f:
                        i=0
                        while True:
                            data=f.read(CHUNK)
                            if not data:break
                            i+=1;p=target/f'part-{i:04d}.bin'
                            with p.open('xb') as dest:dest.write(data)
                            parts.append(dict(path=p.relative_to(ROOT).as_posix(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
                relative=source.relative_to(base);rebuilt=restoration/relative
                io.require(rebuilt.resolve().is_relative_to(restoration),'owned absolute restoration path')
                rebuilt.parent.mkdir(parents=True,exist_ok=True)
                if parts:
                    with rebuilt.open('xb') as dest:
                        for part in parts:
                            p=ROOT/part['path'];io.require(io.sha(p)==part['sha256'] and p.stat().st_size==part['bytes'],'actual chunk bytes')
                            with p.open('rb') as stream:shutil.copyfileobj(stream,dest,1024*1024)
                else:
                    with source.open('rb') as stream,rebuilt.open('xb') as dest:shutil.copyfileobj(stream,dest,1024*1024)
                io.require(rebuilt.stat().st_size==size and io.sha(rebuilt)==source_sha and io.sha(source)==source_sha,'independent restored file bytes')
                lines=raw_bytes=0
                with gzip.open(rebuilt,'rb') as f:
                    for block in iter(lambda:f.read(1024*1024),b''):
                        lines+=block.count(b'\n');raw_bytes+=len(block)
                io.require(lines==counts[name],'restored gzip CRC/row count')
                entries.append(dict(original=source.relative_to(ROOT).as_posix(),bytes=size,sha256=source_sha,
                    storage='BOUNDED_CHUNKS_ORIGINAL_LOCAL' if parts else 'SMALL_GZIP_DIRECT',parts=parts,
                    restored_file=str(rebuilt),restored_sha256=io.sha(rebuilt),restored_gzip_lines=lines,uncompressed_bytes=raw_bytes))
                compressed+=size;expanded+=raw_bytes
    index=dict(integrity='PASSED',manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],chunk_bytes=CHUNK,
        files=entries,originals_and_actual_restorations_retained=True,no_original_files_removed_or_moved=True)
    io.write(out/'index.json',index)
    receipt=dict(integrity='PASSED',manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],restoration_directory=str(restoration),
        actual_restored_files=len(entries),chunk_files=sum(len(e['parts']) for e in entries),compressed_bytes=compressed,uncompressed_bytes_checked=expanded,
        index_sha256=io.sha(out/'index.json'),script_sha256=io.sha(__file__),guard=guard,wall_ns=perf_counter_ns()-start,
        new_physics=0,new_fits=0,new_policy_queries=0,online_LLM_API_calls=0)
    io.write(out/'restoration_validation.json',receipt);print({k:v for k,v in receipt.items() if k in ('integrity','actual_restored_files','chunk_files','compressed_bytes')})
    return receipt


if __name__=='__main__':preserve(sys.argv[1],sys.argv[2])
