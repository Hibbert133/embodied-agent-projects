"""Frozen ordered one-shot stages; partial attempts stay on disk, never retry."""
from pathlib import Path
from time import perf_counter_ns
import os,sys,traceback
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1';os.environ['MKL_NUM_THREADS']='1'
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import run_history_response_v1 as command
a=command.io;io=a.io


def run():
    path=a.prepare(command.sources());out=path.parent/'pipeline_control';out.mkdir(exist_ok=False);start=perf_counter_ns()
    io.write(out/'process.json',dict(pid=os.getpid(),executable=sys.executable,manifest=str(path),source_git_commit=io.git('rev-parse','HEAD')))
    print(str(path),flush=True)
    stages=[]
    for split in ('SOFTWARE','TRAIN'):
        stages.extend([(split+'_collect',lambda split=split:command.collector.collect(path,split)),(split+'_audit',lambda split=split:command.audit_records(path,split))])
    stages.extend([('train',lambda:command.training.train(path)),('training_audit',lambda:command.training.audit_training(path))])
    for split in ('CAL','QUAL'):
        stages.extend([(split+'_collect',lambda split=split:command.collector.collect(path,split)),(split+'_record_audit',lambda split=split:command.audit_records(path,split)),
            (split+'_evaluate',lambda split=split:command.evaluation.evaluate_split(path,split)),(split+'_statistics_audit',lambda split=split:command.statistics.audit(path,split))])
        if split=='CAL':stages.append(('model_lock',lambda:command.evaluation.lock(path)))
    for phase,entry in stages:
        io.write(out/(phase+'_intent.json'),dict(source_commit=io.git('rev-parse','HEAD'),no_automatic_retry=True));t=perf_counter_ns()
        try:
            result=entry();io.write(out/(phase+'_receipt.json'),dict(integrity='PASSED',result=result,wall_ns=perf_counter_ns()-t))
            print(dict(phase=phase,integrity='PASSED',seconds=(perf_counter_ns()-t)/1e9),flush=True)
        except BaseException:
            details=[];frame=sys.exc_info()[2]
            while frame:
                values=frame.tb_frame.f_locals;module=frame.tb_frame.f_globals.get('__name__','')
                if module.startswith('src.analysis.'):
                    details.append(dict(module=module,function=frame.tb_frame.f_code.co_name,guard=values.get('guard'),receipt=values.get('receipt'),
                        completed_cases=len(values['rows']) if isinstance(values.get('rows'),list) else None))
                frame=frame.tb_next
            io.write(out/(phase+'_failure.json'),dict(integrity='FAILED',exception=traceback.format_exc(),partial_counters=details,wall_ns=perf_counter_ns()-t,no_automatic_retry=True));raise
    result=io.read(path.parent/'qual_evaluation/result.json')
    io.write(out/'completion.json',dict(status='COMPLETED_INDEPENDENT_COMPONENT_QUALIFICATION',qualification_status=result['status'],wall_ns=perf_counter_ns()-start,
        online_LLM_API_calls=0,new_forward_model_used_for_control=False,publication_goal_complete=False))

if __name__=='__main__':run()
