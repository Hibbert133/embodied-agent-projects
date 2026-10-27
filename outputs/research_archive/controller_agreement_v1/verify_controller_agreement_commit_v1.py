"""Exact committed/disk proof for this phase; does not inspect scientific data."""
from pathlib import Path
import hashlib,subprocess,sys,json
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
head=io.git('rev-parse','HEAD');assert head.startswith(sys.argv[1]) and not io.git('status','--porcelain','--untracked-files=no')
names=io.git('diff-tree','--no-commit-id','--name-only','-r',head).splitlines()
reader=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE);proof={};total=0
try:
    for n in names:
        reader.stdin.write((head+':'+n+'\n').encode());reader.stdin.flush();h=reader.stdout.readline().split();assert len(h)==3 and h[1]==b'blob'
        data=reader.stdout.read(int(h[2]));assert reader.stdout.read(1)==b'\n' and data==(ROOT/n).read_bytes(),n
        proof[n]=dict(git_oid=h[0].decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest());total+=len(data)
    reader.stdin.close();assert reader.wait(timeout=60)==0
finally:
    if reader.poll() is None:reader.kill();reader.wait()
out=Path(__file__).parent/('controller_agreement_postcommit_'+head[:12]+'.json')
io.write(out,dict(integrity='PASSED',commit=head,parent=io.git('rev-parse',head+'^'),objects=proof,object_count=len(names),bytes=total,new_physics=0,new_fits=0,online_LLM_API_calls=0,publication_goal_complete=False))
print(dict(integrity='PASSED',commit=head,objects=len(names),bytes=total),flush=True)
