"""Read final committed objects, never rewrite a source or an experiment."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');phase,parent=sys.argv[1:];start=perf_counter_ns()
namefile={'result':'outputs/paired_packet_structure/result_validation_v1/owned_final.nul','archive':'outputs/research_archive/packet_structure_v1/owned_paths_final.nul'}[phase]
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)
head=git('rev-parse','HEAD').decode().strip();assert git('rev-parse','HEAD^').decode().strip()==parent and not git('status','--porcelain','--untracked-files=no')
names={x.decode('utf8') for x in (ROOT/namefile).read_bytes().split(b'\0') if x};changed={x.decode('utf8') for x in git('diff-tree','--no-commit-id','--name-only','-r','-z',head).split(b'\0') if x};assert changed==names
reader=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE);proof={};total=0
try:
    for name in sorted(names):
        reader.stdin.write((head+':'+name+'\n').encode());reader.stdin.flush();header=reader.stdout.readline().split();assert len(header)==3 and header[1]==b'blob';size=int(header[2]);remaining=size;digest=hashlib.sha256()
        while remaining:
            data=reader.stdout.read(min(1048576,remaining));assert data;digest.update(data);remaining-=len(data)
        assert reader.stdout.read(1)==b'\n';disk=ROOT/name;other=hashlib.sha256()
        with disk.open('rb') as f:
            for data in iter(lambda:f.read(1048576),b''):other.update(data)
        assert disk.stat().st_size==size and other.hexdigest()==digest.hexdigest(),name
        proof[name]=dict(git_oid=header[0].decode(),bytes=size,sha256=digest.hexdigest());total+=size
    reader.stdin.close();assert reader.wait(timeout=60)==0
finally:
    if reader.poll() is None:reader.kill();reader.wait()
out=Path(__file__).parent/('packet_structure_'+phase+'_postcommit_'+head[:12]+'.json')
with out.open('x',encoding='utf8',newline='\n') as f:json.dump(dict(integrity='PASSED',phase=phase,commit=head,parent=parent,objects=proof,bytes=total,object_count=len(proof),wall_ns=perf_counter_ns()-start,new_physics=0,new_fits=0,online_LLM_API_calls=0),f,indent=2);f.write('\n')
print(dict(integrity='PASSED',phase=phase,commit=head,objects=len(proof),bytes=total))
