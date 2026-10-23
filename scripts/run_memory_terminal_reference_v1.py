"""Source-bound preparation and guarded finite reference output generation."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import memory_terminal_qualification_v1 as q
from scripts.analyze_acquisition_support_v1 import guarded
io=q.io


def prepare():
    io.require(not list((q.BASE/'qualification_v1').glob('*/manifest.json')),'one immutable numerical output run')
    qa=io.read(q.BASE/'validation_v1/complete.json');io.require(qa['integrity']=='PASSED','source-bound component checks')
    for n,h in qa['source_sha256'].items():io.require(io.sha(io.ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'checked committed source')
    source={n:io.sha(io.ROOT/n) for n in q.OWN};source[(q.BASE/'validation_v1/complete.json').relative_to(io.ROOT).as_posix()]=io.sha(q.BASE/'validation_v1/complete.json')
    source['src/probe/task_passive_pi_v1.py']=io.sha(io.ROOT/'src/probe/task_passive_pi_v1.py')
    head=io.git('rev-parse','HEAD');run_id='memory_terminal_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]
    value={'run_id':run_id,'source_git_commit':head,'source_sha256':source,'config':io.read(q.CONFIG),
        'classification':'STANDARD_REFERENCE_SYNTHETIC_QUALIFICATION','development_checks_not_unseen_data':True,'publication_goal_complete':False}
    value['manifest_id']=io.digest(value);out=q.BASE/'qualification_v1'/run_id;out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',value);return out/'manifest.json'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=('prepare','run'));p.add_argument('--manifest',type=Path);a=p.parse_args()
    if a.phase=='prepare':
        if a.manifest is not None:p.error('prepare has no existing manifest')
        print(prepare(),flush=True)
    else:
        if a.manifest is None:p.error('manifest required')
        value,guard=guarded(lambda:q.run(a.manifest));io.write(a.manifest.parent/'interaction_guard.json',guard);print(value,flush=True)
