"""Isolated CPU training; only the strict public TRAIN bundle is read."""
from pathlib import Path
from time import perf_counter_ns
import argparse,hashlib,json,sys,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from src.analysis.response_qualification_io_v1 import read,write,sha,digest,require,forbid_online_calls
from src.probe.latent_response_query_v1 import assert_public_training_window,context

METHODS=('SS_SENT','SS_NO_SENT','SS_CURRENT_SENT','DIRECT_MLP_H8')


def configure():
    import torch
    require(torch.__version__.startswith('2.2.2') and np.__version__=='1.26.4','pinned isolated numerical runtime')
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True);torch.backends.mkldnn.enabled=False
    return torch


def network(torch,method):
    class Net(torch.nn.Module):
        def __init__(self):
            super().__init__();self.encoder1=torch.nn.Linear(723,32);self.encoder2=torch.nn.Linear(32,8)
            if method=='DIRECT_MLP_H8':self.direct1=torch.nn.Linear(40,32);self.direct2=torch.nn.Linear(32,16)
            else:self.transition1=torch.nn.Linear(12,32);self.transition2=torch.nn.Linear(32,8);self.output=torch.nn.Linear(8,2)
        def forward(self,x,u):
            h=torch.tanh(self.encoder2(torch.tanh(self.encoder1(x))))
            if method=='DIRECT_MLP_H8':return self.direct2(torch.tanh(self.direct1(torch.cat((h,u.reshape(-1,32)),1)))).reshape(-1,8,2)
            positions=[];p=torch.zeros((len(x),2),dtype=x.dtype,device=x.device)
            for k in range(8):
                h=torch.tanh(h+self.transition2(torch.tanh(self.transition1(torch.cat((h,u[:,k]),1)))))
                p=p+self.output(h);positions.append(p)
            return torch.stack(positions,1)
    return Net()


def serialized(net):
    result={}
    for name,module in net.named_children():result[name]={'weight':module.weight.detach().cpu().numpy().tolist(),'bias':module.bias.detach().cpu().numpy().tolist()}
    return result


def schedule(rng,trajectories):
    ts=rng.integers(0,len(trajectories),size=32);ws=np.asarray([rng.integers(0,len(trajectories[i]['windows'])) for i in ts])
    return ts,ws


def arrays(entry,method):
    result=[]
    for trajectory in entry['trajectories']:
        rows=[]
        for value in trajectory['windows']:
            q,y,mask=assert_public_training_window(value)
            require(q.task==entry['task'],'matching public task block')
            rows.append((context(q,entry['normalization'],method).astype(np.float32),np.array(q.planned_commands,np.float32)/np.float32(.8),
                np.asarray(y/.01,np.float32),mask.astype(np.float32)))
        result.append(rows)
    return result


def fit(torch,entry,method,out,log):
    start=perf_counter_ns();torch.manual_seed(entry['initialization_seed']);net=network(torch,method);initial=serialized(net)
    count=sum(p.numel() for p in net.parameters());require(count==(25272 if method=='DIRECT_MLP_H8' else 24130),'frozen parameter count')
    optimizer=torch.optim.Adam(net.parameters(),lr=.001,betas=(.9,.999),eps=1e-8,weight_decay=0.)
    cache=arrays(entry,method);rng=np.random.default_rng(entry['sampling_seed']);schedule_hash=hashlib.sha256();step=0
    for step in range(1,5001):
        ts,ws=schedule(rng,entry['trajectories']);schedule_hash.update(np.asarray([ts,ws],dtype='<i8').tobytes())
        selected=[cache[i][j] for i,j in zip(ts,ws)];x,u,y,mask=(torch.tensor(np.stack([v[k] for v in selected])) for k in range(4))
        optimizer.zero_grad(set_to_none=True);prediction=net(x,u);loss=(((prediction-y)**2*mask[:,:,None]).sum((1,2))/(2*mask.sum(1))).mean()
        require(torch.isfinite(loss).item(),'finite masked multi-step loss');loss.backward();optimizer.step()
        if step==1 or step%100==0:
            log({'task':entry['task'],'method':method,'update':step,'normalized_masked_loss':float(loss.detach())})
            write(out/'progress.json',{'task':entry['task'],'method':method,'completed_optimizer_updates':step},exclusive=False)
        if step%1000==0:write(out/(entry['task']+'_'+method+f'_checkpoint_{step}.json'),{'task':entry['task'],'method':method,'updates':step,'parameters':serialized(net)})
    return {'task':entry['task'],'method':method,'normalization':entry['normalization'],**serialized(net),
        'initial_parameters_sha256':digest(initial),'encoder_initial_sha256':digest({k:v for k,v in initial.items() if k.startswith('encoder')}),
        'initialization_seed':entry['initialization_seed'],'sampling_seed':entry['sampling_seed'],'sampling_schedule_sha256':schedule_hash.hexdigest(),
        'optimizer_updates':5000,'parameters':count,'dtype':'float32','wall_ns':perf_counter_ns()-start,'probability_or_safety_guarantee':False}


def train(bundle_path,out):
    torch=configure();bundle=read(bundle_path);require(set(bundle)=={'schema','entries'} and bundle['schema']=='PUBLIC_LATENT_TRAIN_BUNDLE_V1','public TRAIN bundle only')
    out.mkdir(exist_ok=False);start=perf_counter_ns();attempts=[];failure=None;network_guard={}
    with (out/'training_log.jsonl').open('x',encoding='utf-8',newline='\n') as f:
        def log(v):f.write(json.dumps(v)+'\n');f.flush()
        try:
            with forbid_online_calls(network_guard):
                for entry in bundle['entries']:
                    require(set(entry)=={'task','trajectories','one_step_trajectories','normalization','initialization_seed','sampling_seed'},'no private extra task entry')
                    from src.analysis.latent_response_training_v1 import statistics
                    expected=statistics(entry['trajectories'])
                    for k in ('history_mean','history_scale','offset_mean','offset_scale'):require(np.allclose(expected[k],entry['normalization'][k],atol=1e-12,rtol=1e-9),'TRAIN-only normalization')
                    for method in METHODS:
                        attempt={'task':entry['task'],'method':method,'status':'ATTEMPTED'};attempts.append(attempt);log(attempt)
                        model=fit(torch,entry,method,out,log);write(out/(entry['task']+'_'+method+'.json'),model);attempt['status']='SAVED';log(attempt)
        except BaseException as error:failure={'type':type(error).__name__,'message':str(error),'traceback':traceback.format_exc()}
    result={'status':'TWELVE_NEURAL_MODELS_SAVED' if failure is None else 'FAILED_NO_RETRY','attempts':attempts,'fits_attempted':len(attempts),
        'fits_saved':sum(v['status']=='SAVED' for v in attempts),'source_bundle_sha256':sha(bundle_path),'failure':failure,
        'network_guard':network_guard,'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'online_LLM_API_calls':0}
    write(out/'completion.json',result);print(result,flush=True)
    if failure is not None:raise SystemExit(1)


def audit_forward(bundle_path,models_path,output):
    from src.analysis.latent_response_model_audit_v1 import independent_context,independent_predict
    torch=configure();start=perf_counter_ns();bundle=read(bundle_path);bank=read(models_path)['by_task'];count=0;maximum=0.;network_guard={}
    with forbid_online_calls(network_guard):
        for entry in bundle['entries']:
            raws=[w['query'] for t in entry['trajectories'] for w in t['windows']]
            for method in METHODS:
                model=bank[entry['task']][method];torch.manual_seed(model['initialization_seed']);net=network(torch,method)
                require(digest(serialized(net))==model['initial_parameters_sha256'],'independent initial tensor state')
                net=net.double()
                with torch.no_grad():
                    for name,module in net.named_children():
                        module.weight.copy_(torch.tensor(model[name]['weight'],dtype=torch.float64));module.bias.copy_(torch.tensor(model[name]['bias'],dtype=torch.float64))
                    for k in range(0,len(raws),128):
                        batch=raws[k:k+128];x=np.array([independent_context(q,model['normalization'],method) for q in batch]);u=np.array([q['planned_commands'] for q in batch])/.8
                        actual=.01*net(torch.tensor(x,dtype=torch.float64),torch.tensor(u,dtype=torch.float64)).numpy();expected=independent_predict(model,batch)
                        error=float(np.max(abs(actual-expected)));require(np.allclose(actual,expected,atol=1e-10,rtol=1e-9),'Torch double independent forward differs');maximum=max(maximum,error);count+=len(batch)
    result={'integrity':'PASSED','models_sha256':sha(models_path),'bundle_sha256':sha(bundle_path),'window_forwards_checked':count,'maximum_absolute_error_m':maximum,
        'network_guard':network_guard,'optimizer_updates':0,'new_model_fits':0,'new_environment_steps':0,'online_LLM_API_calls':0,'wall_ns':perf_counter_ns()-start}
    write(output,result);print(result,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--audit-models',type=Path);v=p.parse_args()
    if v.audit_models:audit_forward(v.bundle.resolve(),v.audit_models.resolve(),v.output.resolve())
    else:train(v.bundle.resolve(),v.output.resolve())
