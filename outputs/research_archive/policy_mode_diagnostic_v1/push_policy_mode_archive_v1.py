"""Ordinary authorized archival push; verify unknown outcomes before any retry."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
out=ROOT/'outputs/research_archive/policy_mode_diagnostic_v1';r=io.read(out/'local_receipt.json');start=perf_counter_ns();branch=r['archive_branch']
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,text=True,timeout=40).strip()
def remote():
    values=git('ls-remote','--heads','origin','refs/heads/'+branch).split();assert len(values)==2 and values[1]=='refs/heads/'+branch;return values[0]
assert git('rev-parse','HEAD')==r['source_local_commit'] and not git('status','--porcelain','--untracked-files=no')
before=remote();assert before in (r['archive_parent'],r['archive_commit'])
attempt=dict(returncode=None,stdout='',stderr='',timed_out=False,recovered_existing_target=before==r['archive_commit'])
if before!=r['archive_commit']:
    number=1
    while (out/('push_intent%02d.json'%number)).exists():number+=1
    io.write(out/('push_intent%02d.json'%number),dict(remote_before=before,archive_commit=r['archive_commit'],source_local_commit=r['source_local_commit'],branch=branch,ordinary_fast_forward=True))
    try:
        p=subprocess.run(['git','-c','maintenance.auto=false','-c','gc.auto=0','push','origin',branch],cwd=ROOT,capture_output=True,text=True,timeout=50)
        attempt.update(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
    except subprocess.TimeoutExpired as ex:
        def decode(v):return v.decode('utf8',errors='replace') if isinstance(v,bytes) else (v or '')
        attempt.update(stdout=decode(ex.stdout),stderr=decode(ex.stderr),timed_out=True)
    after=remote();io.write(out/('push_attempt%02d.json'%number),dict(remote_before=before,remote_after=after,archive_commit=r['archive_commit'],attempt=attempt,wall_ns=perf_counter_ns()-start))
else:after=before
assert after==r['archive_commit'],('REMOTE_NOT_TARGET_INSPECT_BEFORE_RETRY',after)
assert git('rev-parse','HEAD')==r['source_local_commit'] and not git('status','--porcelain','--untracked-files=no')
io.write(out/'remote_receipt.json',dict(integrity='PASSED',branch=branch,archive_parent=r['archive_parent'],remote_before=before,remote_after=after,archive_commit=after,
    push_returncode=attempt['returncode'],stdout=attempt['stdout'],stderr=attempt['stderr'],recovered_existing_target=attempt['recovered_existing_target'],
    ordinary_fast_forward=True,no_force_or_merge=True,original_source_head_worktree_index_unchanged=True,wall_ns=perf_counter_ns()-start))
print(dict(integrity='PASSED',remote_archive_commit=after,source_local_commit=r['source_local_commit']),flush=True)
