"""Read completed phase blobs and compare exact disk bytes, without mutation."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');phase,commit,parent=sys.argv[1:];start=perf_counter_ns()
spec={'freeze':'outputs/episode_seed_inventory/freeze_validation_v2/owned_final.nul',
      'result':'outputs/episode_seed_inventory/delivery_validation_v2/owned_final.nul','archive':'outputs/research_archive/episode_seed_inventory_v2/owned_paths_final.nul'}[phase]
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)
assert git('rev-parse',commit+'^').decode().strip()==parent and not git('status','--porcelain','--untracked-files=no')
names={n.decode() for n in (ROOT/spec).read_bytes().split(b'\0') if n}
changed={n.decode() for n in git('diff-tree','--no-commit-id','--name-only','-r','-z',commit).split(b'\0') if n};assert names==changed
reader=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE);proof={};total=0
try:
    for name in sorted(names):
        reader.stdin.write((commit+':'+name+'\n').encode());reader.stdin.flush();h=reader.stdout.readline().split();assert len(h)==3 and h[1]==b'blob'
        data=reader.stdout.read(int(h[2]));assert reader.stdout.read(1)==b'\n' and data==(ROOT/name).read_bytes(),name
        proof[name]=dict(git_oid=h[0].decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest());total+=len(data)
    reader.stdin.close();assert reader.wait(timeout=60)==0
finally:
    if reader.poll() is None:reader.kill();reader.wait()
out=Path(__file__).parent/('seed_inventory_'+phase+'_postcommit_'+commit[:12]+'.json')
with out.open('x',encoding='utf8',newline='\n') as f:json.dump(dict(integrity='PASSED',phase=phase,commit=commit,parent=parent,object_count=len(names),bytes=total,
    objects=proof,new_physics=0,new_model_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start),f,indent=2);f.write('\n')
print(dict(integrity='PASSED',phase=phase,objects=len(names),bytes=total),flush=True)
