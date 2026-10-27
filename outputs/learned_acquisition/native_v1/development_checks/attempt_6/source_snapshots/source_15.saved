"""One frozen native allocation; retain all phase failures without retry."""
from pathlib import Path
from time import perf_counter_ns
import contextlib,os,sys,traceback
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from scripts import run_learned_acquisition_native_v1 as m
io=m.io


class Tee:
    def __init__(self,*streams):self.streams=streams
    def write(self,text):
        for stream in self.streams:stream.write(text);stream.flush()
        return len(text)
    def flush(self):
        for stream in self.streams:stream.flush()


start=perf_counter_ns();path=m.a.prepare();out=path.parent/'pipeline_control';out.mkdir(exist_ok=False)
io.write(out/'process.json',dict(pid=os.getpid(),executable=sys.executable,argv=sys.argv,manifest=str(path),
    source_git_commit=io.git('rev-parse','HEAD'),one_allocation=True,no_automatic_retry=True))
print(str(path),flush=True)
phases=(('signal',m.signal.analyze),('audit-signal',m.signal.audit),('collect',m.collector.collect),('audit-native',m.audit.audit))
for phase,entry in phases:
    io.write(out/(phase+'_intent.json'),dict(phase=phase,entry=entry.__module__+'.'+entry.__name__,source_git_commit=io.git('rev-parse','HEAD'),no_automatic_retry=True))
    t=perf_counter_ns()
    with (out/(phase+'.log')).open('x',encoding='utf8',newline='\n') as log:
        try:
            with contextlib.redirect_stdout(Tee(sys.stdout,log)),contextlib.redirect_stderr(Tee(sys.stderr,log)):result=entry(path)
            if isinstance(result,Path):result=str(result)
            io.write(out/(phase+'_receipt.json'),dict(phase=phase,integrity='PASSED',wall_ns=perf_counter_ns()-t,result=result,log_sha256=io.sha(out/(phase+'.log'))))
            print(dict(phase=phase,integrity='PASSED',seconds=(perf_counter_ns()-t)/1e9),flush=True)
        except BaseException:
            typ,error,tb=sys.exc_info();partial=[];frame=tb
            while frame:
                values=frame.tb_frame.f_locals;module=frame.tb_frame.f_globals.get('__name__','')
                if module.startswith('src.analysis.'):
                    ledger=values.get('ledger')
                    if hasattr(ledger,'snapshot'):ledger=ledger.snapshot()
                    partial.append(dict(module=module,function=frame.tb_frame.f_code.co_name,ledger=ledger,
                        guard=values.get('guard'),budget=values.get('budget'),failed_spec=values.get('spec')))
                frame=frame.tb_next
            io.write(out/(phase+'_failure.json'),dict(integrity='FAILED',phase=phase,exception=traceback.format_exc(),
                partial_counters=partial,wall_ns=perf_counter_ns()-t,no_automatic_retry=True))
            print(dict(phase=phase,integrity='FAILED',failure_file=str(out/(phase+'_failure.json'))),flush=True);raise
summary=io.read(path.parent/'native/summary.json');gate=io.read(path.parent/'native/native_gate.json')
io.write(out/'completion.json',dict(status='COMPLETED',phases=[p for p,_ in phases],wall_ns=perf_counter_ns()-start,
    actual_native_cost={k:summary[k] for k in ('executions','control_steps','lifecycle','live_model_calls')},
    native_gate=gate['status'],new_model_fits=0,online_LLM_API_calls=0,task_gain_qualified=False,publication_goal_complete=False))
