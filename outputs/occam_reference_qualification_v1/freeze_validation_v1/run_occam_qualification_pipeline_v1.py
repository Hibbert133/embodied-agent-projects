"""One frozen sequence of collection and audit entries, no retries or resampling."""
from pathlib import Path
from time import perf_counter_ns
import argparse,os,subprocess,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import occam_qualification_case_io_v1 as c


def run(manifest):
    manifest=Path(manifest).resolve();m=c.check_manifest(manifest);out=manifest.parent/'pipeline_v1';out.mkdir(exist_ok=False);started=perf_counter_ns()
    script=ROOT/'scripts/run_occam_reference_qualification_v1.py';python=ROOT/'.venv/Scripts/python.exe';steps=[];failure=None
    c.write(out/'intent.json',dict(manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],started_ns=started,
        pid=os.getpid(),one_shot=True,no_retries=True,online_LLM_API_calls=0))
    def invoke(command,phase=None):
        label=command+('_'+phase if phase else '');args=[str(python),str(script),command,'--manifest',str(manifest)]
        if phase:args+=['--phase',phase]
        index=len(steps)+1;begin=perf_counter_ns();c.write(out/('%02d_'%index+label+'_intent.json'),dict(command=args,started_ns=begin))
        with (out/('%02d_'%index+label+'_stdout.log')).open('xb') as log,(out/('%02d_'%index+label+'_stderr.log')).open('xb') as err:
            result=subprocess.run(args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        row=dict(index=index,command=command,phase=phase,returncode=result.returncode,wall_ns=perf_counter_ns()-begin);steps.append(row)
        c.write(out/('%02d_'%index+label+'_complete.json'),row);print(row,flush=True);return result.returncode
    for command,phase in (('collect','NATIVE'),('process-audit','NATIVE'),('audit','NATIVE'),
        ('collect','QUAL'),('process-audit','QUAL'),('audit','QUAL'),('statistics',None),('statistics-audit',None)):
        code=invoke(command,phase)
        if code!=0:failure=dict(command=command,phase=phase,returncode=code);break
    report_code=invoke('report')
    receipt=dict(integrity='PASSED_COMPLETE_SEQUENCE' if failure is None and report_code==0 else 'STOPPED_WITH_RETAINED_FAILURE',
        manifest_id=m['manifest_id'],steps=steps,failure=failure,report_returncode=report_code,wall_ns=perf_counter_ns()-started,
        no_retries_or_additional_allocations=True,online_LLM_API_calls=0,publication_goal_complete=False)
    c.write(out/'complete.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',required=True);x=p.parse_args();print(run(x.manifest),flush=True)
