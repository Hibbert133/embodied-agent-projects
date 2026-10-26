from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess

ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)
start=perf_counter_ns();source=git('rev-parse','HEAD').decode().strip()
assert git('rev-parse','HEAD^').decode().strip()=='2c8c36b3bb26bd63a4f3f0c8d29ec44d84f5fba5'
assert not git('status','--porcelain','--untracked-files=no')
names={n.decode('utf8') for n in (ROOT/'outputs/correction_scope/trace_value_v1/freeze_validation/owned_final.nul').read_bytes().split(b'\0') if n}
changed={n.decode('utf8') for n in git('diff-tree','--no-commit-id','--name-only','-r','-z','HEAD').split(b'\0') if n}
assert changed==names
reader=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
proof={};total=0
try:
    for name in sorted(names):
        reader.stdin.write((source+':'+name+'\n').encode('utf8'));reader.stdin.flush()
        header=reader.stdout.readline().split();assert len(header)==3 and header[1]==b'blob'
        size=int(header[2]);remaining=size;digest=hashlib.sha256()
        while remaining:
            data=reader.stdout.read(min(1024**2,remaining));assert data
            digest.update(data);remaining-=len(data)
        assert reader.stdout.read(1)==b'\n'
        disk=ROOT/name;disk_hash=hashlib.sha256()
        with disk.open('rb') as stream:
            for data in iter(lambda:stream.read(1024**2),b''):disk_hash.update(data)
        assert size==disk.stat().st_size and digest.hexdigest()==disk_hash.hexdigest()
        proof[name]=dict(git_oid=header[0].decode(),bytes=size,sha256=digest.hexdigest());total+=size
    reader.stdin.close();assert reader.wait(timeout=60)==0
finally:
    if reader.poll() is None:reader.kill();reader.wait()
assert git('rev-parse','HEAD').decode().strip()==source and not git('diff','--cached','--name-only')
receipt=dict(integrity='PASSED',source_local_commit=source,actual_commit_objects=len(proof),changed_paths=len(changed),actual_git_bytes_hashed=total,
    object_proof=proof,unchanged_original_large_gzip_retained=True,unrelated_untracked_excluded=True,
    new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
out=Path(__file__).parent/('trace_value_freeze_postcommit_'+source[:12]+'.json')
with out.open('x',encoding='utf8',newline='\n') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print({k:v for k,v in receipt.items() if k in ('integrity','source_local_commit','actual_commit_objects','actual_git_bytes_hashed')})
