"""One-shot sequential collection and independent postprocessing, pinned source."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_paired_probe_effects_v1 as collector
from scripts import run_strong_chronological_reference_v1 as io


def execute(path,phase):
    io.clean();m,_=collector.load(path)
    if io.git('rev-parse','HEAD')!=m['source_git_commit']:raise ValueError('frozen HEAD required')
    python=ROOT/'.venv/Scripts/python.exe';plotting=Path('C:/Python314/python.exe')
    if not python.is_file() or not plotting.is_file():raise FileNotFoundError('registered research and plot runtimes required')
    if (path.parent/phase.lower()).exists():raise FileExistsError('one-shot phase already exists; never restart it')
    identity={k:m[k] for k in io.IDENTITY};started=perf_counter_ns();steps=[]
    commands=[(python,'run_paired_probe_effects_v1.py',['run']),
        (python,'audit_paired_probe_effects_v1.py',[]),(python,'analyze_paired_probe_effects_v1.py',['analyze']),
        (python,'audit_paired_probe_statistics_v1.py',[]),(plotting,'plot_paired_probe_effects_v1.py',[]),
        (python,'analyze_paired_probe_effects_v1.py',['report'])]
    failure=None
    for runtime,script,arguments in commands:
        command=[str(runtime),str(ROOT/'scripts'/script),*arguments,'--manifest',str(path),'--phase',phase]
        at=perf_counter_ns();result=subprocess.run(command,cwd=ROOT,check=False)
        item={'script':script,'arguments':arguments,'runtime':str(runtime),'returncode':result.returncode,'wall_ns':perf_counter_ns()-at};steps.append(item)
        io.write(path.parent/(phase.lower()+'_pipeline_status.json'),{**identity,'phase':phase,'steps':steps,'status':'RUNNING' if result.returncode==0 else 'FAILED_SAVED_NOT_RETRIED'})
        if result.returncode:
            failure=item;break
    value={**identity,'phase':phase,'status':'COMPLETED_FOR_REVIEW' if failure is None else 'FAILED_SAVED_NOT_RETRIED',
        'steps':steps,'wall_ns':perf_counter_ns()-started,'failure':failure}
    io.write(path.parent/(phase.lower()+'_pipeline_completion.json'),value,exclusive=True)
    print(json.dumps(value),flush=True)
    if failure:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--phase',choices=['SMOKE','MAIN'],required=True);args=parser.parse_args();execute(args.manifest.resolve(),args.phase)
