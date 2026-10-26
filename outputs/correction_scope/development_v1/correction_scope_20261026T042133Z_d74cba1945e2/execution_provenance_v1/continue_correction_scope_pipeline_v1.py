"""Orchestrate only the already frozen A1 phases; stop on any error."""
from pathlib import Path
from time import perf_counter_ns,sleep
import hashlib,json,sys,traceback
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import correction_scope_io_v1 as a
from src.analysis.correction_scope_audit_v1 import audit
from src.analysis.correction_scope_collect_v1 import collect
from src.analysis import correction_scope_learning_v1 as learning
from src.analysis import correction_scope_statistics_v1 as statistics
manifest=a.OUTPUT/'correction_scope_20261026T042133Z_d74cba1945e2/manifest.json'
out=manifest.parent/'pipeline_control_v1';out.mkdir(exist_ok=False)
steps=[('native_record_audit',lambda:audit(manifest,'NATIVE')),
       ('train_collection',lambda:collect(manifest,'TRAIN')),
       ('train_record_audit',lambda:audit(manifest,'TRAIN')),
       ('forecast_training',lambda:learning.train(manifest)),
       ('independent_model_audit',lambda:learning.audit_models(manifest)),
       ('cal_collection',lambda:collect(manifest,'CAL')),
       ('cal_record_audit',lambda:audit(manifest,'CAL')),
       ('cal_prediction_audit',lambda:learning.prediction_audit(manifest,'CAL')),
       ('calibration_lock',lambda:learning.calibrate(manifest)),
       ('test_collection',lambda:collect(manifest,'TEST')),
       ('test_record_audit',lambda:audit(manifest,'TEST')),
       ('test_prediction_audit',lambda:learning.prediction_audit(manifest,'TEST')),
       ('test_statistics',lambda:statistics.statistics(manifest)),
       ('independent_statistics_audit',lambda:statistics.audit_statistics(manifest))]
io=a.io;m=a.checked(manifest);io.require(io.git('rev-parse','HEAD')==m['source_git_commit'],'exact frozen source head')
io.write(out/'intent.json',dict(manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],
    driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),steps=[k for k,_ in steps],
    started_ns=perf_counter_ns(),no_new_scientific_choices=True,new_online_LLM_API_calls=0))
log=(out/'stdout.log').open('x',encoding='utf8')
class Tee:
    def write(self,text):log.write(text);log.flush();sys.__stdout__.write(text);sys.__stdout__.flush()
    def flush(self):log.flush();sys.__stdout__.flush()
sys.stdout=Tee();completed=[];name='WAIT_FOR_EXISTING_NATIVE_COMPLETION';started=perf_counter_ns()
try:
    completion=manifest.parent/'native/completion.json'
    while not completion.exists():sleep(2)
    io.require(io.read(completion)['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','native collection failed; no retry or replacement')
    for name,fn in steps:
        stage_start=perf_counter_ns();io.write(out/(name+'_intent.json'),dict(started_ns=stage_start,manifest_id=m['manifest_id']))
        print(dict(stage=name,status='STARTED'),flush=True)
        result=fn()
        if isinstance(result,dict) and 'integrity' in result:io.require(result['integrity'] in ('PASSED','FIT_FOR_INDEPENDENT_AUDIT','FOR_INDEPENDENT_STATISTICS_AUDIT'),'phase failed integrity '+name)
        completed.append(name);io.write(out/(name+'_complete.json'),dict(status='COMPLETED',wall_ns=perf_counter_ns()-stage_start))
        io.write(out/'status.json',dict(status='RUNNING',last_completed=name,completed=completed,wall_ns=perf_counter_ns()-started),exclusive=False)
        print(dict(stage=name,status='COMPLETED'),flush=True)
    io.write(out/'completion.json',dict(status='COMPLETED',completed=completed,wall_ns=perf_counter_ns()-started,new_online_LLM_API_calls=0))
except BaseException as e:
    io.write(out/'failed.json',dict(status='FAILED_STOPPED',stage=name,completed=completed,error_type=type(e).__name__,message=str(e),traceback=traceback.format_exc(),wall_ns=perf_counter_ns()-started))
    print(dict(stage=name,status='FAILED_STOPPED',error_type=type(e).__name__,message=str(e)),flush=True)
    raise
finally:log.flush();log.close();sys.stdout=sys.__stdout__
