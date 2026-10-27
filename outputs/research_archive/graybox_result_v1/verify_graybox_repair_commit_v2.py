"""Byte-for-byte committed delivery proof; does not modify the checkout."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
start=perf_counter_ns();head=io.git('rev-parse','HEAD');assert not io.git('status','--porcelain','--untracked-files=no')
spec=ROOT/'outputs/graybox_response/audit_repair_v2/owned_final.nul';names={n.decode() for n in spec.read_bytes().split(b'\0') if n}
actual=set(io.git('diff-tree','--no-commit-id','--name-only','-r',head).splitlines());assert actual==names
reader=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE);proof={};total=0
try:
    for n in sorted(names):
        reader.stdin.write((head+':'+n+'\n').encode());reader.stdin.flush();header=reader.stdout.readline().split();assert len(header)==3 and header[1]==b'blob'
        data=reader.stdout.read(int(header[2]));assert reader.stdout.read(1)==b'\n' and data==(ROOT/n).read_bytes(),n
        proof[n]=dict(git_oid=header[0].decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest());total+=len(data)
    reader.stdin.close();assert reader.wait(timeout=60)==0
finally:
    if reader.poll() is None:reader.kill();reader.wait()
out=Path(__file__).parent/('graybox_repair_postcommit_'+head[:12]+'.json')
io.write(out,dict(integrity='PASSED',commit=head,parent=io.git('rev-parse',head+'^'),object_count=len(names),objects=proof,bytes=total,
    wall_ns=perf_counter_ns()-start,new_physics_in_commit_verification=0,new_model_fits_in_commit_verification=0,online_LLM_API_calls=0,publication_goal_complete=False))
print(dict(integrity='PASSED',commit=head,objects=len(names),bytes=total),flush=True)
