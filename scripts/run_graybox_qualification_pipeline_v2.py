"""One-shot CAL/QUAL supplement; no source-run resume and no training stage."""
from pathlib import Path
from time import perf_counter_ns
import os,sys,traceback
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_graybox_qualification_v2 as command
a=command.io;io=a.io

def stages(path):
    result=[]
    for split in a.SPLITS:
        result.extend([(split+'_collect',lambda split=split:command.collect(path,split)),(split+'_record_audit',lambda split=split:command.audit_records(path,split)),
            (split+'_evaluate',lambda split=split:command.evaluate(path,split)),(split+'_statistics_audit',lambda split=split:command.audit_statistics(path,split))])
        if split=='CAL':result.append(('model_lock',lambda:command.lock(path)))
    return result

def run():
    path=a.prepare(command.sources());out=path.parent/'pipeline_control';out.mkdir(exist_ok=False);start=perf_counter_ns()
    io.write(out/'process.json',dict(pid=os.getpid(),executable=sys.executable,manifest=str(path),source_git_commit=io.git('rev-parse','HEAD'),source_run_terminal_failure_preserved=True))
    print(str(path),flush=True)
    for phase,entry in stages(path):
        io.write(out/(phase+'_intent.json'),dict(source_commit=io.git('rev-parse','HEAD'),no_automatic_retry=True));t=perf_counter_ns()
        try:
            value=entry();io.write(out/(phase+'_receipt.json'),dict(integrity='PASSED',result=value,wall_ns=perf_counter_ns()-t));print(dict(phase=phase,integrity='PASSED',seconds=(perf_counter_ns()-t)/1e9),flush=True)
        except BaseException:
            details=[];frame=sys.exc_info()[2]
            while frame:
                v=frame.tb_frame.f_locals;module=frame.tb_frame.f_globals.get('__name__','')
                if module.startswith('src.analysis.'):details.append(dict(module=module,function=frame.tb_frame.f_code.co_name,guard=v.get('guard'),counter=v.get('counter'),receipt=v.get('receipt'),completed_cases=len(v['rows']) if isinstance(v.get('rows'),list) else None))
                frame=frame.tb_next
            io.write(out/(phase+'_failure.json'),dict(integrity='FAILED',exception=traceback.format_exc(),partial_counters=details,wall_ns=perf_counter_ns()-t,no_automatic_retry=True));raise
    value=io.read(path.parent/'qual_evaluation/result.json')
    io.write(out/'completion.json',dict(status='COMPLETED_STANDARD_RESPONSE_QUALIFICATION_SUPPLEMENT',qualification_status=value['status'],wall_ns=perf_counter_ns()-start,
        new_primary_training=0,online_LLM_API_calls=0,original_failed_pipeline_still_failed=True,full_task_benefit_established=False,publication_goal_complete=False))

if __name__=='__main__':run()
