from pathlib import Path
from datetime import datetime,timezone
import subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
OUT=ROOT/'outputs/research_archive/program_support_v1';r=io.read(OUT/'local_receipt.json');ref='refs/heads/'+r['archive_branch']
def run(args):return subprocess.run(['git','-c','maintenance.auto=false','-c','gc.auto=0',*args],cwd=ROOT,capture_output=True,text=True)
assert run(['rev-parse','HEAD']).stdout.strip()==r['source_local_commit'] and not (OUT/'push_receipt.json').exists()
before=run(['ls-remote','origin',ref]);io.write(OUT/'remote_before_push.json',dict(returncode=before.returncode,stdout=before.stdout,stderr=before.stderr))
io.require(before.returncode==0 and before.stdout.split()[0]==r['archive_parent'],'verified expected remote archival parent')
p=run(['push','origin',ref+':'+ref]);io.write(OUT/'push_receipt.json',dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,utc=datetime.now(timezone.utc).isoformat()))
after=run(['ls-remote','origin',ref]);verified=after.returncode==0 and after.stdout.split()[0]==r['archive_commit']
io.write(OUT/'remote_verification.json',dict(integrity='PASSED' if verified else 'FAILED_OR_UNKNOWN',returncode=after.returncode,
    stdout=after.stdout,stderr=after.stderr,expected_archive_commit=r['archive_commit'],source_local_commit=r['source_local_commit'],no_force_no_merge=True))
io.require(verified,'remote archival result unknown; investigate without blind retry')
assert run(['rev-parse','HEAD']).stdout.strip()==r['source_local_commit']
print(dict(integrity='PASSED',archive_commit=r['archive_commit'],source_local_commit=r['source_local_commit']))
