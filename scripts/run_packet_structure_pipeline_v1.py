"""One immutable zero-interaction diagnosis, preserving any partial failure."""
from pathlib import Path
from time import perf_counter_ns
import os,sys,traceback
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_packet_structure_v1 as command
a=command.source;io=a.io


def run():
    path=a.prepare(command.SOURCES);out=path.parent/'pipeline_control';out.mkdir(exist_ok=False);start=perf_counter_ns()
    io.write(out/'process.json',dict(pid=os.getpid(),executable=sys.executable,manifest=str(path),analysis_git_commit=io.git('rev-parse','HEAD')));print(path,flush=True)
    for phase in ('analyze','audit'):
        io.write(out/(phase+'_intent.json'),dict(no_automatic_retry=True));t=perf_counter_ns()
        try:
            result=command.execute(phase,path);io.write(out/(phase+'_receipt.json'),dict(integrity='PASSED',result=result,wall_ns=perf_counter_ns()-t));print(dict(phase=phase,status='PASSED',seconds=(perf_counter_ns()-t)/1e9),flush=True)
        except BaseException:
            counters=[];frame=sys.exc_info()[2]
            while frame:
                module=frame.tb_frame.f_globals.get('__name__','');v=frame.tb_frame.f_locals
                if module.startswith('src.analysis.'):counters.append(dict(module=module,function=frame.tb_frame.f_code.co_name,counts=dict(v.get('counts',{})),guard=v.get('guard')))
                frame=frame.tb_next
            io.write(out/(phase+'_failure.json'),dict(integrity='FAILED',exception=traceback.format_exc(),partial_counters=counters,wall_ns=perf_counter_ns()-t,no_automatic_retry=True));raise
    io.write(out/'completion.json',dict(status='COMPLETED_POST_HOC_STRUCTURE_ANALYSIS',wall_ns=perf_counter_ns()-start,new_physics=0,new_model_fits=0,new_predictions=0,online_LLM_API_calls=0,source_qualification='CLOSED_NEGATIVE_RETAINED',publication_goal_complete=False))


if __name__=='__main__':run()
