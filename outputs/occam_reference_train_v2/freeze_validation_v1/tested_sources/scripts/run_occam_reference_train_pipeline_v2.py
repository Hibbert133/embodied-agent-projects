"""One bounded frozen NATIVE/TRAIN/learning allocation; never restarts a phase."""
from pathlib import Path
from time import perf_counter_ns
import os,subprocess,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import occam_reference_train_io_v2 as a


def main():
    out=a.BASE/'pipeline_v1';out.mkdir(parents=True,exist_ok=False);started=perf_counter_ns();processes=[];manifest=None;failure=None;current=None
    def status(value):a.io.write(out/'status.json',dict(status=value,pid=os.getpid(),manifest=None if manifest is None else str(manifest),current=current,processes=processes,wall_ns=perf_counter_ns()-started),exclusive=False)
    def run(label,args):
        nonlocal current
        current=label;status('RUNNING');t=perf_counter_ns()
        with (out/(label+'.log')).open('x',encoding='utf8',newline='\n') as log:
            p=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',bufsize=1)
            a.io.write(out/'live_child.json',dict(parent_pid=os.getpid(),child_pid=p.pid,label=label,args=args),exclusive=False)
            for line in p.stdout:log.write(line);log.flush();print(label+': '+line.rstrip(),flush=True)
            code=p.wait()
        receipt=dict(label=label,args=args,returncode=code,wall_ns=perf_counter_ns()-t);processes.append(receipt);a.io.write(out/(label+'.json'),receipt)
        a.io.require(code==0,'one-shot child failed '+label)
    try:
        manifest=a.prepare();status('RUNNING')
        for phase in a.PHASES:
            for operation in ('collect','audit'):run(phase.lower()+'_'+operation,[sys.executable,'-u','scripts/run_occam_reference_train_v2.py',operation,'--manifest',str(manifest),'--phase',phase])
        from src.analysis.occam_reference_learning_io_v2 import prepare_learning
        spec=prepare_learning(manifest)
        a.verify_training_runtime()
        run('learning',[str(a.TRAIN_PYTHON),'-u','scripts/train_occam_reference_v2.py','--spec',str(spec),'--output',str(manifest.parent/'learning')])
        run('model_audit',[sys.executable,'-u','scripts/run_occam_reference_train_v2.py','model-audit','--manifest',str(manifest)])
        a.checked(manifest)
    except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
    a.io.write(out/'complete.json',dict(integrity='PASSED' if failure is None else 'FAILED_PARTIAL',pid=os.getpid(),manifest=None if manifest is None else str(manifest),processes=processes,failure=failure,
        scientific_CAL_QUAL_opened=False,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-started,publication_goal_complete=False));status('COMPLETE' if failure is None else 'FAILED_PARTIAL')
    if failure is not None:raise RuntimeError('Frozen pipeline stopped; no retry '+str(failure))


if __name__=='__main__':main()
