from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');phase,parent=sys.argv[1:]
prefix='outputs/correction_scope/transfer_ablation_v1/'
namefile={'freeze':prefix+'freeze_validation/owned_final.nul','result':prefix+'result_validation/owned_final.nul',
          'archive':'outputs/research_archive/transfer_ablation_v1/owned_paths_final.nul'}[phase]
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT)
start=perf_counter_ns();head=git('rev-parse','HEAD').decode().strip()
assert git('rev-parse','HEAD^').decode().strip()==parent and not git('status','--porcelain','--untracked-files=no')
names={n.decode('utf8') for n in (ROOT/namefile).read_bytes().split(b'\0') if n}
changed={n.decode('utf8') for n in git('diff-tree','--no-commit-id','--name-only','-r','-z','HEAD').split(b'\0') if n};assert changed<=names
if phase=='archive':assert changed==names
if phase=='freeze':
    sys.path.insert(0,str(ROOT));from src.analysis import correction_transfer_ablation_v1 as m
    assert 'src/analysis/correction_transfer_ablation_v1.py' in changed and names-changed==set(m.DEPENDENCIES)
if phase=='result':assert 'reports/correction_transfer_ablation_v1_zh.md' in changed
reader=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE);proof={};total=0
try:
    for name in sorted(names):
        reader.stdin.write((head+':'+name+'\n').encode('utf8'));reader.stdin.flush();header=reader.stdout.readline().split()
        assert len(header)==3 and header[1]==b'blob';size=int(header[2]);remaining=size;digest=hashlib.sha256()
        while remaining:
            data=reader.stdout.read(min(1024**2,remaining));assert data;digest.update(data);remaining-=len(data)
        assert reader.stdout.read(1)==b'\n';disk=ROOT/name;disk_hash=hashlib.sha256()
        with disk.open('rb') as stream:
            for data in iter(lambda:stream.read(1024**2),b''):disk_hash.update(data)
        assert size==disk.stat().st_size and digest.hexdigest()==disk_hash.hexdigest()
        proof[name]=dict(git_oid=header[0].decode(),bytes=size,sha256=digest.hexdigest());total+=size
    reader.stdin.close();assert reader.wait(timeout=60)==0
finally:
    if reader.poll() is None:reader.kill();reader.wait()
assert git('rev-parse','HEAD').decode().strip()==head and not git('diff','--cached','--name-only')
receipt=dict(integrity='PASSED',phase=phase,source_local_commit=head,expected_parent=parent,actual_commit_objects=len(proof),changed_paths=len(changed),
    actual_git_bytes_hashed=total,object_proof=proof,unrelated_untracked_excluded=True,new_physics=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
out=Path(__file__).parent/('correction_transfer_ablation_'+phase+'_postcommit_'+head[:12]+'.json')
with out.open('x',encoding='utf8',newline='\n') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print({k:v for k,v in receipt.items() if k in ('integrity','source_local_commit','actual_commit_objects','actual_git_bytes_hashed')})
