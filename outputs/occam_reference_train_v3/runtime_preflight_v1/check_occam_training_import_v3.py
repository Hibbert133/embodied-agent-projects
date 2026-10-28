"""Cold import only: no data read, model construction, solve or optimizer."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,sys,traceback
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
OUT=ROOT/'outputs/occam_reference_train_v3/runtime_preflight_v1'
start=perf_counter_ns();attempts=dict(physics_imports=0,network_calls=0);failure=None;versions={}
OUT.mkdir(exist_ok=False)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024**2),b''):h.update(data)
    return h.hexdigest()
def guard(event,args):
    if event=='import' and any(args[0]==p or args[0].startswith(p+'.') for p in ('metaworld','mujoco','gymnasium','src.rollout')):
        attempts['physics_imports']+=1;raise RuntimeError('physics forbidden in cold training import')
    if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','socket.gethostbyname','socket.gethostbyaddr'):
        attempts['network_calls']+=1;raise RuntimeError('network forbidden in cold training import')
sys.addaudithook(guard)
try:
    lock=json.loads((ROOT/'outputs/occam_reference_train_v3/freeze_validation_v1/training_runtime_lock.json').read_text(encoding='utf8'))
    for name,h in lock['critical_entry_sha256'].items():assert sha(name)==h,name
    import numpy as np
    import torch
    assert sys.version_info[:2]==(3,12) and np.__version__=='1.26.4' and torch.__version__=='2.2.2+cpu' and not torch.cuda.is_available()
    from src.analysis import occam_reference_learner_v3 as learner
    assert callable(learner.train) and callable(learner.validate_spec)
    assert not any(name==p or name.startswith(p+'.') for name in sys.modules for p in ('metaworld','mujoco','gymnasium','src.rollout'))
    versions=dict(python=sys.version,executable=sys.executable,numpy=np.__version__,torch=torch.__version__,cuda=False)
except BaseException as error:failure=dict(type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
result=dict(integrity='PASSED_COLD_TRAINING_IMPORT_ONLY' if failure is None else 'FAILED_COLD_TRAINING_IMPORT_ONLY',failure=failure,versions=versions,attempts=attempts,
    critical_entry_hashes_verified=True if failure is None else None,full_binary_supply_chain_claim=False,public_or_private_training_records_read=0,
    models_constructed=0,scientific_fits=0,linear_solves=0,Adam_updates=0,new_physics=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
with (OUT/'complete.json').open('x',encoding='utf8',newline='\n') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps(result,ensure_ascii=False))
raise SystemExit(0 if failure is None else 1)
