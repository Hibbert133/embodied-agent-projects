"""One frozen matched-response development run; preserve all partial failures."""
from pathlib import Path
from time import perf_counter_ns
import os,sys,traceback
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts import run_correction_effect_learning_v1 as command
main=command.main;io=main.io;path=main.prepare(command.SOURCES);out=path.parent/'pipeline_control';out.mkdir(exist_ok=False);start=perf_counter_ns()
io.write(out/'process.json',dict(pid=os.getpid(),executable=sys.executable,argv=sys.argv,manifest=str(path),source_git_commit=io.git('rev-parse','HEAD')))
print(str(path),flush=True)
for phase,entry in command.PHASES.items():
    io.write(out/(phase+'_intent.json'),dict(entry=entry.__module__+'.'+entry.__name__,source_commit=io.git('rev-parse','HEAD'),no_automatic_retry=True));t=perf_counter_ns()
    try:
        result=entry(path);io.write(out/(phase+'_receipt.json'),dict(integrity='PASSED',result=result,wall_ns=perf_counter_ns()-t))
        print(dict(phase=phase,integrity='PASSED',seconds=(perf_counter_ns()-t)/1e9),flush=True)
    except BaseException:
        details=[];frame=sys.exc_info()[2]
        while frame:
            values=frame.tb_frame.f_locals;module=frame.tb_frame.f_globals.get('__name__','')
            if module.startswith('src.analysis.'):
                details.append(dict(module=module,function=frame.tb_frame.f_code.co_name,guard=values.get('guard'),fold=values.get('fold'),kind=values.get('kind'),
                    completed_pairs=len(values['register']) if isinstance(values.get('register'),list) else None,completed_public_pairs=len(values['public']) if isinstance(values.get('public'),list) else None))
            frame=frame.tb_next
        io.write(out/(phase+'_failure.json'),dict(integrity='FAILED',exception=traceback.format_exc(),partial_counters=details,wall_ns=perf_counter_ns()-t,no_automatic_retry=True));raise
io.write(out/'completion.json',dict(status='COMPLETED_TRAIN_COMPONENT_DEVELOPMENT',wall_ns=perf_counter_ns()-start,new_physics=0,scientific_regressions=36,independent_refits=36,
    online_LLM_API_calls=0,original_native_qualification='FAILED_RETAINED',new_deployment_executions=0,publication_goal_complete=False))
