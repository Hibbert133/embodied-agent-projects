"""Exact committed/disk bytes; no scientific computation."""
from pathlib import Path
import hashlib,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
head=io.git('rev-parse','HEAD');assert head.startswith(sys.argv[1]) and not io.git('status','--porcelain','--untracked-files=no')
names=io.git('diff-tree','--no-commit-id','--name-only','-r',head).splitlines();proof={};total=0
p=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
try:
    for n in names:
        p.stdin.write((head+':'+n+'\n').encode());p.stdin.flush();h=p.stdout.readline().split();assert len(h)==3 and h[1]==b'blob'
        data=p.stdout.read(int(h[2]));assert p.stdout.read(1)==b'\n' and data==(ROOT/n).read_bytes(),n
        proof[n]=dict(git_oid=h[0].decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest());total+=len(data)
    p.stdin.close();assert p.wait(timeout=60)==0
finally:
    if p.poll() is None:p.kill();p.wait()
io.write(Path(__file__).parent/('policy_mode_postcommit_'+head[:12]+'.json'),dict(integrity='PASSED',commit=head,parent=io.git('rev-parse',head+'^'),object_count=len(names),bytes=total,objects=proof,new_physics=0,new_fits=0,online_LLM_API_calls=0))
print(dict(integrity='PASSED',commit=head,objects=len(names),bytes=total),flush=True)
