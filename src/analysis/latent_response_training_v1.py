"""Public TRAIN export and fixed weighted baselines; no private training labels."""
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess,sys
from itertools import zip_longest
import numpy as np
from src.analysis import latent_response_io_v1 as a
from src.probe.latent_response_query_v1 import make_query,raw_frames,context,ForecastQuery,assert_public_training_window
from src.probe.observable_history_model_v1 import HistoryTrajectory,fit_linear
io=a.io


def windows(public,meta):
    io.require(set(meta)=={'schema','entry_at_calls','packet_commands','reason'} and meta['schema']=='PUBLIC_PACKET_METADATA_V1','only public packet metadata')
    entry=meta['entry_at_calls'];commands=meta['packet_commands'];out=[]
    if entry is None:return out
    n=len(public['steps'])-entry;states=[public['initial_observation'],*(r['observation_after'] for r in public['steps'])]
    for k in range(min(n,25)):
        planned=commands[k:k+8]
        if len(planned)!=8:break
        q=make_query(public,entry+k,planned);actual=min(8,n-k);target=np.zeros((8,2),float)
        for h in range(actual):target[h]=np.asarray(states[entry+k+h+1][:2])-states[entry+k][:2]
        value={'query':q.to_dict(),'targets':target.tolist(),'mask':[h<actual for h in range(8)]};assert_public_training_window(value);out.append(value)
    return out


def statistics(trajectories):
    rows=[];weights=[];offset=[];ow=[]
    for t in trajectories:
        ws=t['windows'];io.require(ws,'available public TRAIN trajectory')
        for w in ws:
            q,_,_=assert_public_training_window(w);v=raw_frames(q);rows.extend(v);weights.extend([1/(len(ws)*len(v))]*len(v));offset.append(q.nominal_offset);ow.append(1/len(ws))
    def moments(x,w):
        x=np.asarray(x,float);w=np.asarray(w,float);mu=np.sum(x*w[:,None],axis=0)/w.sum();scale=np.sqrt(np.sum((x-mu)**2*w[:,None],axis=0)/w.sum())
        return mu.tolist(),np.where(scale>1e-6,scale,1.).tolist()
    hm,hs=moments(rows,weights);om,os=moments(offset,ow)
    return {'history_mean':hm,'history_scale':hs,'offset_mean':om,'offset_scale':os,'trajectory_total_weight':1.,'only_public_TRAIN':True}


def export(path):
    m=a.checked(path);root=Path(path).parent;out=root/'training';out.mkdir(exist_ok=False);record=io.read(root/'train/audit.json')
    io.require(record['integrity']=='PASSED' and record['native_target_updates_bit_exact'],'independent TRAIN integrity/native audit first')
    for n,h in record['artifact_sha256'].items():io.require(io.sha(root/'train'/n)==h,'unchanged TRAIN')
    publics=iter(io.rows(root/'train/public_trajectories.jsonl.gz'));metadata=iter(io.rows(root/'train/public_packet_metadata.jsonl.gz'));by_task={task:[] for task in io.TASKS};legacy={task:[] for task in io.TASKS};unavailable={task:0 for task in io.TASKS};complete={task:0 for task in io.TASKS}
    count=0
    for index,(public,meta) in enumerate(zip_longest(publics,metadata)):
        io.require(public is not None and meta is not None,'aligned complete public export');count+=1
        task=public['task'];ws=windows(public,meta)
        if not ws:unavailable[task]+=1;continue
        by_task[task].append({'windows':ws});complete[task]+=sum(ws[0]['mask'])==8
        start=meta['entry_at_calls'];states=[public['initial_observation'],*(r['observation_after'] for r in public['steps'])]
        io.require(start>=2,'real first two displacements required')
        commands=[r['command'] for r in public['steps'][start-2:]]
        ts=HistoryTrajectory(task,f'PUBLIC_TRAIN_{index}','TRAIN',states[start-2],commands,states[start-1:])
        legacy[task].append({'task':task,'trajectory_id':ts.trajectory_id,'split':'TRAIN','initial':list(ts.initial),'commands':[list(v) for v in ts.commands],'observations':[list(v) for v in ts.observations]})
    io.require(count==len(a.population('TRAIN')),'full public TRAIN export population')
    support={task:{'available':len(by_task[task]),'complete_entry_packets':complete[task],'unavailable':unavailable[task]} for task in io.TASKS}
    io.write(out/'support.json',support)
    io.require(all(v['available']>=24 and v['complete_entry_packets']>=16 for v in support.values()),'registered TRAIN support failed; no fits or extra sampling')
    entries=[]
    for i,task in enumerate(io.TASKS):entries.append({'task':task,'trajectories':by_task[task],'one_step_trajectories':legacy[task],
        'normalization':statistics(by_task[task]),'initialization_seed':2026102430+i,'sampling_seed':2026102434+i})
    bundle={'schema':'PUBLIC_LATENT_TRAIN_BUNDLE_V1','entries':entries};io.write(out/'public_train_bundle.json',bundle)
    io.write(out/'export_receipt.json',{'status':'PUBLIC_TRAIN_EXPORTED','manifest_id':m['manifest_id'],'bundle_sha256':io.sha(out/'public_train_bundle.json'),
        'public_source_sha256':{n:io.sha(root/'train'/n) for n in ('public_trajectories.jsonl.gz','public_packet_metadata.jsonl.gz')},'support':support,'new_model_fits':0})
    return out/'public_train_bundle.json'


def fit_direct(entry,log):
    method='DIRECT_RIDGE_H8';normal=entry['normalization'];data=[]
    for t in entry['trajectories']:
        rows=[]
        for w in t['windows']:
            q,y,mask=assert_public_training_window(w);x=np.r_[1.,context(q,normal,method),np.asarray(q.planned_commands).ravel()/.8];rows.append((x,y,mask))
        data.append(rows)
    coefficients=[]
    for h in range(8):
        x=[];y=[];weights=[]
        for rows in data:
            valid=[r for r in rows if r[2][h]]
            for row in valid:x.append(row[0]);y.append(row[1][h]);weights.append(1/len(valid))
        io.require(len(x)>=32,'enough real horizon responses');x=np.asarray(x);y=np.asarray(y);weights=np.asarray(weights);reg=.001*np.eye(x.shape[1]);reg[0,0]=0
        log({'method':method,'task':entry['task'],'horizon':h+1,'status':'ATTEMPTED'})
        c=np.linalg.solve(x.T@(weights[:,None]*x)+reg,x.T@(weights[:,None]*y));io.require(np.isfinite(c).all(),'finite direct regression');coefficients.append(c.tolist())
        log({'method':method,'task':entry['task'],'horizon':h+1,'status':'SAVED','coefficients':c.tolist()})
    return {'method':method,'task':entry['task'],'normalization':normal,'horizon_coefficients':coefficients,'ridge':.001,'probability_or_safety_guarantee':False}


def fit_baselines(bundle_path,output):
    start=perf_counter_ns();bundle=io.read(bundle_path);by_task={};attempts=[]
    with (output/'ridge_fit_log.jsonl').open('x',encoding='utf-8',newline='\n') as f:
        def log(value):attempts.append(value);f.write(json.dumps(value)+'\n');f.flush()
        for entry in bundle['entries']:
            task=entry['task'];models={'PERSIST_ZERO':{'task':task,'method':'PERSIST_ZERO'}}
            models['DIRECT_RIDGE_H8']=fit_direct(entry,log)
            io.write(output/(task+'_DIRECT_RIDGE_H8.json'),models['DIRECT_RIDGE_H8'])
            ts=[HistoryTrajectory.from_dict(v) for v in entry['one_step_trajectories']]
            for method in ('HISTORY_LINEAR10','QUADRATIC_STATE20'):
                log({'method':method,'task':task,'status':'ATTEMPTED'});models[method]=fit_linear(ts,task,method);log({'method':method,'task':task,'status':'SAVED'})
                io.write(output/(task+'_'+method+'.json'),models[method])
            by_task[task]=models
    io.write(output/'baseline_models.json',{'by_task':by_task,'source_bundle_sha256':io.sha(bundle_path)})
    io.write(output/'baseline_receipt.json',{'status':'BASELINES_SAVED','ridge_systems_attempted':sum(v['status']=='ATTEMPTED' for v in attempts),
        'ridge_systems_saved':sum(v['status']=='SAVED' for v in attempts),'wall_ns':perf_counter_ns()-start,'source_bundle_sha256':io.sha(bundle_path)})
    return by_task


def train(path):
    import os
    start=perf_counter_ns();m=a.checked(path);root=Path(path).parent;failure=None;result=None
    try:
        bundle_path=export(path);out=root/'training';baselines=fit_baselines(bundle_path,out)
        for name,h in m['training_runtime']['file_sha256'].items():io.require(io.sha(Path(name))==h,'isolated training runtime changed '+name)
        command=[str(a.TRAIN_PYTHON),'-B','scripts/train_latent_response_v1.py','--bundle',str(bundle_path),'--output',str(out/'neural')]
        before=perf_counter_ns();timed_out=False;kill_receipt=None
        with (out/'neural_process.log').open('x',encoding='utf-8',newline='\n') as log:
            process=subprocess.Popen(command,cwd=a.ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000 if os.name=='nt' else 0)
            try:code=process.wait(timeout=7200)
            except subprocess.TimeoutExpired:
                timed_out=True
                if process.poll() is None:
                    if os.name=='nt':
                        killed=subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,text=True)
                        kill_receipt={'returncode':killed.returncode,'stdout':killed.stdout,'stderr':killed.stderr}
                    else:process.kill()
                code=process.wait(timeout=30)
        io.write(out/'neural_process_receipt.json',{'command':command,'returncode':code,'timed_out':timed_out,'kill_receipt':kill_receipt,
            'wall_ns':perf_counter_ns()-before,'log_sha256':io.sha(out/'neural_process.log'),'retry':False})
        io.require(not timed_out and code==0,'one-shot neural process failed; no retry')
        neural=io.read(out/'neural/completion.json');io.require(neural['status']=='TWELVE_NEURAL_MODELS_SAVED' and neural['fits_saved']==12,'all neural models required')
        for task in io.TASKS:
            for method in ('SS_SENT','SS_NO_SENT','SS_CURRENT_SENT','DIRECT_MLP_H8'):baselines[task][method]=io.read(out/'neural'/(task+'_'+method+'.json'))
        io.write(out/'models.json',{'schema':'LATENT_RESPONSE_MODEL_BANK_V1','by_task':baselines,'source_bundle_sha256':io.sha(bundle_path),
            'fitted_models':21,'deterministic_zero_models':3,'scientific_ridge_systems':30,'neural_trainings':12,'probability_or_safety_guarantee':False})
        result={'status':'TWENTY_ONE_MODELS_SAVED_TRAIN_ONLY','manifest_id':m['manifest_id'],'models_sha256':io.sha(out/'models.json'),
            'public_bundle_sha256':io.sha(bundle_path),'ridge_systems':30,'neural_trainings':12,'optimizer_updates':60000,'new_environment_steps':0,'online_LLM_API_calls':0}
        io.write(out/'completion.json',result)
    except BaseException as error:
        import traceback
        failure={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
    receipt={'status':'PASSED' if failure is None else 'FAILED_NO_RETRY','failure':failure,'wall_ns':perf_counter_ns()-start,
        'new_environment_steps':0,'online_LLM_API_calls':0,'all_partial_outputs_preserved':True}
    io.write(root/'training_process_receipt.json',receipt)
    if failure is not None:raise RuntimeError('TRAIN failed with partial outputs retained '+str(failure))
    return result
