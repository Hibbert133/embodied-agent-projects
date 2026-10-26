from pathlib import Path
from time import perf_counter_ns
import contextlib,io as stdio,os,sys,traceback
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_transfer_ablation_v1 as m
from src.analysis import correction_transfer_ablation_independent_v1 as independent
io=m.io;start=perf_counter_ns();path=m.prepare();out=path.parent/'pipeline_control';out.mkdir(exist_ok=False)
print(str(path),flush=True)
phases=(('fit',m.fit),('audit-models',independent.audit_models),('evaluate',m.evaluate),('audit-replay',independent.audit_replay))
for phase,entry in phases:
    io.write(out/(phase+'_intent.json'),dict(phase=phase,entry=entry.__module__+'.'+entry.__name__,source_git_commit=io.git('rev-parse','HEAD'),no_automatic_retry=True))
    t=perf_counter_ns();stream=stdio.StringIO()
    try:
        with contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):result=entry(path)
        io.write(out/(phase+'_receipt.json'),dict(phase=phase,integrity='PASSED',wall_ns=perf_counter_ns()-t,result=result,stdout_stderr=stream.getvalue()))
        print(dict(phase=phase,integrity='PASSED',seconds=(perf_counter_ns()-t)/1e9),flush=True)
    except BaseException:
        typ,error,tb=sys.exc_info();partial=[];frame=tb
        while frame:
            values=frame.tb_frame.f_locals
            if frame.tb_frame.f_globals.get('__name__','').startswith('src.analysis.'):
                partial.append(dict(module=frame.tb_frame.f_globals.get('__name__'),function=frame.tb_frame.f_code.co_name,
                    ledger=values.get('ledger'),guard=values.get('guard'),loop_step=values.get('step'),fold=values.get('fold'),variant=values.get('variant'),auxiliary_kind=values.get('kind')))
            frame=frame.tb_next
        io.write(out/(phase+'_failure.json'),dict(integrity='FAILED',phase=phase,exception=traceback.format_exc(),partial_counters=partial,
            stdout_stderr=stream.getvalue(),wall_ns=perf_counter_ns()-t,no_automatic_retry=True))
        print(dict(phase=phase,integrity='FAILED',failure_file=str(out/(phase+'_failure.json'))),flush=True);raise
io.write(out/'completion.json',dict(status='COMPLETED',phases=[p for p,_ in phases],wall_ns=perf_counter_ns()-start,
    scientific_neural_fits=9,scientific_neural_updates=9000,scientific_ridge_fits=9,independent_neural_refits=9,
    independent_neural_updates=9000,independent_ridge_refits=9,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0))
