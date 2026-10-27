"""Verify exact committed array-reference objects; leave pending collector draft."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');start=perf_counter_ns()
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)
head=git('rev-parse','HEAD').decode().strip();assert head.startswith('cf2712d') and not git('status','--porcelain','--untracked-files=no')
spec=ROOT/'outputs/graybox_response/freeze_validation_v1/owned_final.nul';names={n.decode() for n in spec.read_bytes().split(b'\0') if n}
assert names=={n.decode() for n in git('diff-tree','--no-commit-id','--name-only','-r','-z',head).split(b'\0') if n} and len(names)==50
reader=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE);proof={};total=0
try:
    for n in sorted(names):
        reader.stdin.write((head+':'+n+'\n').encode());reader.stdin.flush();header=reader.stdout.readline().split();assert len(header)==3 and header[1]==b'blob'
        data=reader.stdout.read(int(header[2]));assert reader.stdout.read(1)==b'\n' and data==(ROOT/n).read_bytes(),n
        proof[n]=dict(git_oid=header[0].decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest());total+=len(data)
    reader.stdin.close();assert reader.wait(timeout=60)==0
finally:
    if reader.poll() is None:reader.kill();reader.wait()
out=Path(__file__).parent/('graybox_collector_postcommit_'+head[:12]+'.json')
with out.open('x',encoding='utf8',newline='\n') as f:json.dump(dict(integrity='PASSED',commit=head,parent=git('rev-parse',head+'^').decode().strip(),
    object_count=len(names),objects=proof,bytes=total,wall_ns=perf_counter_ns()-start,new_physics=0,new_scientific_model_fits=0,online_LLM_API_calls=0,
    collector_or_sampling_protocol_frozen=True,publication_goal_complete=False),f,indent=2);f.write('\n')
print(dict(integrity='PASSED',commit=head,objects=len(names),bytes=total,science='NOT_STARTED'),flush=True)
