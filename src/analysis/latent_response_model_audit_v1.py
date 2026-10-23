"""Separate scalar features/weighted normal equations and saved-network forward audit."""
from pathlib import Path
from time import perf_counter_ns
from math import fsum,sqrt
import hashlib
import numpy as np
from src.analysis import latent_response_io_v1 as a
from src.probe.latent_response_query_v1 import ForecastQuery
io=a.io


def independent_context(raw,normal,method):
    q=ForecastQuery.from_dict(raw);result=[0.]*720;offset=16-len(q.observations)
    for k,(obs,previous,has) in enumerate(zip(q.observations,q.previous_commands,q.has_previous)):
        j=(offset+k)*45
        if method=='SS_CURRENT_SENT' and k!=len(q.observations)-1:continue
        for d,x in enumerate((*obs,*previous)):result[j+d]=(x-normal['history_mean'][d])/normal['history_scale'][d]
        result[j+43]=float(has);result[j+44]=1.
    extra=[0.,0.,0.] if method=='SS_NO_SENT' else [(q.nominal_offset[j]-normal['offset_mean'][j])/normal['offset_scale'][j] for j in range(3)]
    return result+extra


def independent20(raw):
    q=ForecastQuery.from_dict(raw);io.require(len(q.observations)>=3,'real baseline history');s=q.observations;p=s[-1]
    return [*p[:3],*(p[j]-s[-2][j] for j in range(3)),*(s[-2][j]-s[-3][j] for j in range(3)),*q.planned_commands[0],p[3],
        *(p[4+j]-p[j] for j in range(3)),*(p[-3+j]-p[j] for j in range(3))]


def independent_predict(model,raws):
    method=model['method'];n=len(raws)
    if not n:return np.empty((0,8,2))
    if method=='PERSIST_ZERO':return np.zeros((n,8,2))
    if method in ('HISTORY_LINEAR10','QUADRATIC_STATE20'):
        data=[]
        for raw in raws:
            v=independent20(raw);v=v[3:13] if method=='HISTORY_LINEAR10' else v
            z=[(x-m)/s for x,m,s in zip(v,model['mean'],model['scale'])];features=[1.,*z]
            if method=='QUADRATIC_STATE20':features.extend(z[i]*z[j] for i in range(20) for j in range(i,20))
            data.append(features)
        return (np.array(data)@np.array(model['coefficients']))[:,None,:]
    context=np.array([independent_context(q,model['normalization'],method) for q in raws]);commands=np.array([q['planned_commands'] for q in raws],float)/.8
    if method=='DIRECT_RIDGE_H8':
        x=np.c_[np.ones(n),context,commands.reshape(n,32)];return np.stack([x@np.array(c) for c in model['horizon_coefficients']],1)
    def affine(x,name):p=model[name];return np.matmul(x,np.array(p['weight']).T)+np.array(p['bias'])
    state=np.tanh(affine(np.tanh(affine(context,'encoder1')),'encoder2'))
    if method=='DIRECT_MLP_H8':return (.01*affine(np.tanh(affine(np.concatenate((state,commands.reshape(n,32)),1),'direct1')),'direct2')).reshape(n,8,2)
    out=np.zeros((n,8,2));acc=np.zeros((n,2))
    for h in range(8):
        state=np.tanh(state+affine(np.tanh(affine(np.concatenate((state,commands[:,h]),1),'transition1')),'transition2'))
        acc=acc+.01*affine(state,'output');out[:,h,:]=acc
    return out


def same_predictions(left,right):
    left=np.array(left,float);right=np.array(right,float)
    io.require(left.shape==right.shape and np.isfinite(left).all() and np.isfinite(right).all() and np.allclose(left,right,atol=1e-10,rtol=1e-9),'independent forward equations differ')
    return float(np.max(abs(left-right))) if left.size else 0.


def weighted_stats(arrays,weights):
    total=fsum(weights);width=len(arrays[0]);mu=[fsum(float(w)*float(row[j]) for row,w in zip(arrays,weights))/total for j in range(width)]
    scale=[sqrt(fsum(float(w)*(float(row[j])-mu[j])**2 for row,w in zip(arrays,weights))/total) for j in range(width)]
    return np.array(mu),np.array([s if s>1e-6 else 1. for s in scale])


def regress(x,y,weights):
    x=np.asarray(x,float);y=np.asarray(y,float);w=np.asarray(weights,float);matrix=np.einsum('ni,n,nj->ij',x,w,x,optimize=True);right=np.einsum('ni,n,nj->ij',x,w,y,optimize=True)
    matrix+=np.diag([0.]+[.001]*(x.shape[1]-1));return np.linalg.solve(matrix,right)


def audit(path):
    start=perf_counter_ns();m=a.checked(path);out=Path(path).parent/'training';done=io.read(out/'completion.json');bank=io.read(out/'models.json')['by_task'];bundle=io.read(out/'public_train_bundle.json')
    io.require(done['status']=='TWENTY_ONE_MODELS_SAVED_TRAIN_ONLY' and done['models_sha256']==io.sha(out/'models.json') and done['public_bundle_sha256']==io.sha(out/'public_train_bundle.json'),'completed TRAIN-only models')
    systems=0;predictions=0;maximum=0.
    for entry in bundle['entries']:
        task=entry['task'];normal=entry['normalization'];frame_rows=[];frame_weights=[];offs=[];off_weights=[]
        for t in entry['trajectories']:
            for value in t['windows']:
                raw=value['query'];q=ForecastQuery.from_dict(raw);n=len(q.observations);weight=1/len(t['windows'])
                for obs,u in zip(q.observations,q.previous_commands):frame_rows.append([*obs,*u]);frame_weights.append(weight/n)
                offs.append(q.nominal_offset);off_weights.append(weight)
        for rows,ws,prefix in ((frame_rows,frame_weights,'history'),(offs,off_weights,'offset')):
            mu,scale=weighted_stats(rows,ws);same_predictions(mu,np.array(normal[prefix+'_mean']));same_predictions(scale,np.array(normal[prefix+'_scale']))
        direct=bank[task]['DIRECT_RIDGE_H8']
        for h in range(8):
            xs=[];ys=[];ws=[]
            for t in entry['trajectories']:
                valid=[w for w in t['windows'] if w['mask'][h]]
                for w in valid:
                    xs.append([1.,*independent_context(w['query'],normal,'DIRECT_RIDGE_H8'),*(x/.8 for u in w['query']['planned_commands'] for x in u)])
                    ys.append(w['targets'][h]);ws.append(1/len(valid))
            computed=regress(xs,ys,ws);saved=np.array(direct['horizon_coefficients'][h]);io.require(np.allclose(computed,saved,atol=1e-7,rtol=1e-6),'independent direct coefficients')
            same_predictions(np.array(xs)@computed,np.array(xs)@saved);systems+=1
        for method in ('HISTORY_LINEAR10','QUADRATIC_STATE20'):
            xs=[];ys=[];ws=[]
            for raw in entry['one_step_trajectories']:
                s=[raw['initial'],*raw['observations']];commands=raw['commands'];count=len(commands)-2
                for k in range(2,len(commands)):
                    p=s[k];v=[*p[:3],*(p[j]-s[k-1][j] for j in range(3)),*(s[k-1][j]-s[k-2][j] for j in range(3)),*commands[k],p[3],*(p[4+j]-p[j] for j in range(3)),*(p[-3+j]-p[j] for j in range(3))]
                    xs.append(v[3:13] if method=='HISTORY_LINEAR10' else v);ys.append([s[k+1][j]-p[j] for j in range(2)]);ws.append(1/count)
            mu,scale=weighted_stats(xs,ws);model=bank[task][method];same_predictions(mu,np.array(model['mean']));same_predictions(scale,np.array(model['scale']))
            z=(np.array(xs)-mu)/scale;design=[]
            for row in z:
                values=[1.,*row]
                if method=='QUADRATIC_STATE20':values.extend(row[i]*row[j] for i in range(20) for j in range(i,20))
                design.append(values)
            coefficients=regress(design,ys,ws);saved=np.array(model['coefficients']);io.require(np.allclose(coefficients,saved,atol=1e-7,rtol=1e-6),'independent one-step coefficients')
            same_predictions(np.array(design)@coefficients,np.array(design)@saved);systems+=1
        raws=[w['query'] for t in entry['trajectories'] for w in t['windows']]
        for method,model in bank[task].items():
            if method in ('HISTORY_LINEAR10','QUADRATIC_STATE20','PERSIST_ZERO','DIRECT_RIDGE_H8'):continue
            rng=np.random.default_rng(model['sampling_seed']);h=hashlib.sha256()
            for _ in range(5000):
                ts=rng.integers(0,len(entry['trajectories']),size=32);ws=np.array([rng.integers(0,len(entry['trajectories'][i]['windows'])) for i in ts]);h.update(np.asarray([ts,ws],dtype='<i8').tobytes())
            io.require(h.hexdigest()==model['sampling_schedule_sha256'] and model['optimizer_updates']==5000,'fixed full training schedule')
            # Independent NumPy implementation here; isolated Torch-double
            # comparison is a separate source-bound receipt before promotion.
            from src.probe.latent_response_model_v1 import predict
            for k in range(0,len(raws),128):
                batch=raws[k:k+128];maximum=max(maximum,same_predictions(independent_predict(model,batch),predict(model,[ForecastQuery.from_dict(v) for v in batch])));predictions+=len(batch)
        ss=[bank[task][method] for method in ('SS_SENT','SS_NO_SENT','SS_CURRENT_SENT')]
        io.require(len({v['initial_parameters_sha256'] for v in ss})==1,'same-capacity same-initialization ablation')
        io.require(len({bank[task][method]['encoder_initial_sha256'] for method in ('SS_SENT','SS_NO_SENT','SS_CURRENT_SENT','DIRECT_MLP_H8')})==1,'same encoder initialization including direct baseline')
        io.require(len({bank[task][method]['sampling_schedule_sha256'] for method in ('SS_SENT','SS_NO_SENT','SS_CURRENT_SENT','DIRECT_MLP_H8')})==1,'same sampling across neural methods')
    io.require(systems==30,'registered independent ridge replay budget');a.checked(path)
    result={'integrity':'PASSED_PENDING_TORCH_DOUBLE','manifest_id':m['manifest_id'],'models_sha256':io.sha(out/'models.json'),'public_bundle_sha256':io.sha(out/'public_train_bundle.json'),
        'ridge_systems_recomputed':systems,'neural_optimizer_retrains':0,'independent_neural_window_forwards':predictions,'max_neural_abs_error':maximum,
        'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'online_LLM_API_calls':0,'scope':'Independent closed-form fits, scalar features, forward equations and training schedules; no independent optimizer rerun'}
    io.write(out/'numerical_audit.json',result);return result


def complete_audit(path):
    import subprocess,os
    result=audit(path);out=Path(path).parent/'training'
    command=[str(a.TRAIN_PYTHON),'-B','scripts/train_latent_response_v1.py','--bundle',str(out/'public_train_bundle.json'),
        '--audit-models',str(out/'models.json'),'--output',str(out/'torch_forward_audit.json')]
    start=perf_counter_ns()
    with (out/'torch_forward_process.log').open('x',encoding='utf-8',newline='\n') as log:
        process=subprocess.Popen(command,cwd=a.ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=0x08000000 if os.name=='nt' else 0)
        try:code=process.wait(timeout=7200)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=True)
                else:process.kill()
            process.wait(timeout=30);raise RuntimeError('Independent forward audit timed out without retry')
    io.write(out/'torch_forward_process_receipt.json',{'command':command,'returncode':code,'wall_ns':perf_counter_ns()-start,
        'log_sha256':io.sha(out/'torch_forward_process.log'),'new_model_fits':0,'new_environment_steps':0})
    io.require(code==0,'independent Torch forward process failed');torch=io.read(out/'torch_forward_audit.json')
    io.require(torch['integrity']=='PASSED' and torch['models_sha256']==result['models_sha256'] and torch['bundle_sha256']==result['public_bundle_sha256'],'bound independent forward')
    result={**result,'integrity':'PASSED','torch_forward_receipt_sha256':io.sha(out/'torch_forward_audit.json'),'torch_window_forwards_checked':torch['window_forwards_checked'],
        'actual_audit_ridge_fits':30,'neural_optimizer_retrains':0}
    io.write(out/'audit.json',result);return result
