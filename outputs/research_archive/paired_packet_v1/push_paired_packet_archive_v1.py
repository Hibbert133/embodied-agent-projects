"""Ordinary archival fast-forward with explicit before/after remote inspection."""
from pathlib import Path
from time import perf_counter_ns
import subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
out=ROOT/'outputs/research_archive/paired_packet_v1';r=io.read(out/'local_receipt.json');branch=r['archive_branch'];start=perf_counter_ns()
def git(*args):return subprocess.check_output(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,text=True).strip()
def remote():
    text=git('ls-remote','--heads','origin','refs/heads/'+branch);items=text.split();assert len(items)==2 and items[1]=='refs/heads/'+branch;return items[0]
assert git('rev-parse','HEAD')==r['source_local_commit'] and not git('status','--porcelain','--untracked-files=no')
before=remote();assert before==r['archive_parent']
io.write(out/'push_intent.json',dict(remote_before=before,archive_commit=r['archive_commit'],source_local_commit=r['source_local_commit'],branch=branch,ordinary_fast_forward=True,no_force_or_merge=True))
p=subprocess.run(['git','-c','maintenance.auto=false','-c','gc.auto=0','push','origin',branch],cwd=ROOT,capture_output=True,text=True)
after=remote();assert after==r['archive_commit'],(p.returncode,after)
assert git('rev-parse','HEAD')==r['source_local_commit'] and not git('status','--porcelain','--untracked-files=no') and not git('diff','--cached','--name-only')
io.write(out/'remote_receipt.json',dict(integrity='PASSED',branch=branch,remote_before=before,remote_after=after,archive_commit=after,push_returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,
    unknown_outcome_handling='inspect remote, never blindly retry',ordinary_fast_forward=True,no_force_or_merge=True,original_source_head_worktree_index_unchanged=True,wall_ns=perf_counter_ns()-start))
print(dict(integrity='PASSED',remote_archive_commit=after,source_local_commit=r['source_local_commit']),flush=True)
