"""Exact committed entry/source proof before any supplementary science."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
start=perf_counter_ns();head=io.git('rev-parse','HEAD');assert head.startswith(sys.argv[1]) and not io.git('status','--porcelain','--untracked-files=no')
names={n.decode() for n in (ROOT/'outputs/graybox_qualification/freeze_validation_v2/owned_final.nul').read_bytes().split(b'\0') if n}
actual=set(io.git('diff-tree','--no-commit-id','--name-only','-r',head).splitlines());assert actual==names
reader=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE);proof={};total=0
try:
    for n in sorted(names):
        reader.stdin.write((head+':'+n+'\n').encode());reader.stdin.flush();h=reader.stdout.readline().split();assert len(h)==3 and h[1]==b'blob'
        data=reader.stdout.read(int(h[2]));assert reader.stdout.read(1)==b'\n' and data==(ROOT/n).read_bytes(),n
        proof[n]=dict(git_oid=h[0].decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest());total+=len(data)
    reader.stdin.close();assert reader.wait(timeout=60)==0
finally:
    if reader.poll() is None:reader.kill();reader.wait()
io.write(Path(__file__).parent/('graybox_qualification_freeze_postcommit_'+head[:12]+'.json'),dict(integrity='PASSED',commit=head,parent=io.git('rev-parse',head+'^'),
    object_count=len(names),objects=proof,bytes=total,new_physics=0,new_primary_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False))
print(dict(integrity='PASSED',commit=head,objects=len(names),bytes=total),flush=True)
