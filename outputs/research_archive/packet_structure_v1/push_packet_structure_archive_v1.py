"""Ordinary archival fast-forward with explicit before/after remote inspection."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
out=ROOT/'outputs/research_archive/packet_structure_v1';r=io.read(out/'local_receipt.json');branch=r['archive_branch'];start=perf_counter_ns()

def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,text=True).strip()

def remote():
    value=git('ls-remote','--heads','origin','refs/heads/'+branch);items=value.split();assert len(items)==2 and items[1]=='refs/heads/'+branch;return items[0]

assert git('rev-parse','HEAD')==r['source_local_commit'] and not git('status','--porcelain','--untracked-files=no')
before=remote();assert before==r['archive_parent']
if not (out/'push_attempt01_observation.json').exists():
    io.write(out/'push_attempt01_observation.json',dict(status='NO_SUCCESS_RECEIPT_REMOTE_STILL_PARENT_NO_PUSH_PROCESS',remote_before_retry=before,prior_process_handle='63764 no longer exists',prior_returncode=None,prior_stdout=None,prior_stderr=None,reason='prior terminal outcome unavailable; no reason inferred',ordinary_retry_after_remote_inspection=True))
if not (out/'push_helper_preflight_failure02.json').exists():
    io.write(out/'push_helper_preflight_failure02.json',dict(status='FAILED_BEFORE_PUSH',exception='FileExistsError',existing_path='push_intent.json',reason='exclusive write preserved original intent',git_push_invoked=False))
number=2
while (out/('push_intent%02d.json'%number)).exists() or (out/('push_attempt%02d.json'%number)).exists():number+=1
io.write(out/('push_intent%02d.json'%number),dict(remote_before=before,archive_commit=r['archive_commit'],source_local_commit=r['source_local_commit'],branch=branch,ordinary_fast_forward=True,no_force_or_merge=True))
try:
    p=subprocess.run(['git','-c','maintenance.auto=false','-c','gc.auto=0','push','origin',branch],cwd=ROOT,capture_output=True,text=True,timeout=50)
    attempt=dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,timed_out=False)
except subprocess.TimeoutExpired as exc:
    def decode(value):return value.decode('utf8',errors='replace') if isinstance(value,bytes) else (value or '')
    attempt=dict(returncode=None,stdout=decode(exc.stdout),stderr=decode(exc.stderr),timed_out=True)
after=remote()
io.write(out/('push_attempt%02d.json'%number),dict(remote_before=before,remote_after=after,archive_commit=r['archive_commit'],attempt=attempt,wall_ns=perf_counter_ns()-start))
assert after==r['archive_commit'],(attempt,after)
assert git('rev-parse','HEAD')==r['source_local_commit'] and not git('status','--porcelain','--untracked-files=no') and not git('diff','--cached','--name-only')
io.write(out/'remote_receipt.json',dict(integrity='PASSED',branch=branch,remote_before=before,remote_after=after,archive_commit=after,push_returncode=attempt['returncode'],stdout=attempt['stdout'],stderr=attempt['stderr'],unknown_outcome_handling='inspect remote, never blindly retry',ordinary_fast_forward=True,no_force_or_merge=True,original_source_head_worktree_index_unchanged=True,wall_ns=perf_counter_ns()-start))
print(dict(integrity='PASSED',remote_archive_commit=after,source_local_commit=r['source_local_commit']),flush=True)
