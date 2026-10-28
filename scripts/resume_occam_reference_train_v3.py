"""Continue only the untouched V2 TRAIN after a frozen read-only repair."""
from pathlib import Path
from time import perf_counter_ns
import os,subprocess,sys,traceback
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import occam_reader_extension_v3 as e


def main():
    e.verify();e.io.require(not e.io.git('status','--porcelain','--untracked-files=no'),'committed extension before execution')
    e.io.require(not (e.TARGET.parent/'train').exists(),'TRAIN was never started; no repeat or resume of physical cases')
    out=e.a.BASE/'pipeline_reader_v3';out.mkdir(exist_ok=False);start=perf_counter_ns();processes=[];failure=None;current=None
    def status(value):e.io.write(out/'status.json',dict(status=value,pid=os.getpid(),manifest=str(e.TARGET),current=current,processes=processes,wall_ns=perf_counter_ns()-start),exclusive=False)
    def run(label,args):
        nonlocal current
        e.verify();current=label;status('RUNNING');t=perf_counter_ns()
        with (out/(label+'.log')).open('x',encoding='utf8',newline='\n') as log:
            p=subprocess.Popen(args,cwd=e.a.ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',bufsize=1)
            e.io.write(out/'live_child.json',dict(parent_pid=os.getpid(),child_pid=p.pid,label=label,args=args),exclusive=False)
            for line in p.stdout:log.write(line);log.flush();print(label+': '+line.rstrip(),flush=True)
            code=p.wait()
        receipt=dict(label=label,args=args,returncode=code,wall_ns=perf_counter_ns()-t);processes.append(receipt);e.io.write(out/(label+'.json'),receipt)
        e.io.require(code==0,'one-shot extension child failed '+label)
    try:
        run('native_audit_v3',[sys.executable,'-u','scripts/audit_occam_reference_train_v3.py','--phase','NATIVE'])
        e.native_authorization();e.a.phase_gate(e.TARGET,'TRAIN')
        run('train_collect',[sys.executable,'-u','scripts/run_occam_reference_train_v2.py','collect','--manifest',str(e.TARGET),'--phase','TRAIN'])
        run('train_audit_v3',[sys.executable,'-u','scripts/audit_occam_reference_train_v3.py','--phase','TRAIN'])
        from src.analysis.occam_reference_learning_io_v2 import prepare_learning
        spec=prepare_learning(e.TARGET);e.a.verify_training_runtime()
        run('learning',[str(e.a.TRAIN_PYTHON),'-u','scripts/train_occam_reference_v2.py','--spec',str(spec),'--output',str(e.TARGET.parent/'learning')])
        run('model_audit',[sys.executable,'-u','scripts/run_occam_reference_train_v2.py','model-audit','--manifest',str(e.TARGET)])
        e.verify()
    except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
    e.io.write(out/'complete.json',dict(integrity='PASSED' if failure is None else 'FAILED_PARTIAL',pid=os.getpid(),manifest=str(e.TARGET),processes=processes,failure=failure,
        original_failed_pipeline_sha256=e.io.sha(e.a.BASE/'pipeline_v1/complete.json'),online_LLM_API_calls=0,scientific_CAL_QUAL_opened=False,
        publication_goal_complete=False,wall_ns=perf_counter_ns()-start));status('COMPLETE' if failure is None else 'FAILED_PARTIAL')
    if failure is not None:raise RuntimeError('Frozen extension stopped; no retry '+str(failure))


if __name__=='__main__':main()
