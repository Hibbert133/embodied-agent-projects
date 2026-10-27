"""Separate public reader, augmented-LS/eigen refits and literal predictions.

Shared primitives: JSON, IEEE doubles, NumPy linear algebra and fixed records.
No production descriptor, design, fitted-bank constructor or predictor is used.
"""
from pathlib import Path
from collections import Counter
from math import exp
import numpy as np
from src.analysis import history_response_io_v1 as a
io=a.io
KINDS=('ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN','HISTORY_KERNEL')
PAIRS=(('ZERO','PLUS'),('ZERO','MINUS'),('PLUS','MINUS'))


def public_vector(q,history):
    values=[float(x) for x in q['current']['observation']]+list(q['integral_carried_xy'])
    if history:
        for transition in q['history']:
            values+=list(transition['command'])
            values += [(transition['after']['observation'][j]-transition['before']['observation'][j])/.01 for j in range(3)]
    return np.asarray(values,float)


def inputs(u,h,instant=False):
    values=[]
    for lag in range(1 if instant else 16):
        for axis in (0,1):values.append(sum(float(u[t][axis]) for t in range(max(h-lag,0))))
    return np.asarray(values,float)


def read_training(path):
    folder=Path(path).parent/'train';cases=list(io.rows(folder/'cases.jsonl.gz'));public=list(io.rows(folder/'public_trajectories.jsonl.gz'));answer=[]
    io.require(len(cases)==len(public)==324,'exact fresh TRAIN source population')
    for i in range(108):
        group=cases[3*i:3*i+3];traces=public[3*i:3*i+3];first=group[0];positions={};lengths={}
        for role,c,trace in zip(('ZERO','PLUS','MINUS'),group,traces):
            io.require(c['split']=='TRAIN' and c['packet_kind']==role and c['public_trajectory_sha256']==io.digest(trace),'literal TRAIN/public identity')
            n=c['packet_steps'];start=c['entry_at_calls'];lengths[role]=n
            positions[role]=[] if start is None else [trace['steps'][start+j]['after']['observation'][:2] for j in range(n)]
        record=first['forecast_record']
        answer.append(dict(family_index=i,group=first['group'],task=first['task'],context=first['context'],boundary=first['boundary'],
            acquisition_action=first['acquisition_action'],query=None if record is None else record['query'],packet_positions_xy=positions,packet_lengths=lengths,
            complete_three_role_H16=all(n==16 for n in lengths.values()),reasons={r:c['reason'] for r,c in zip(('ZERO','PLUS','MINUS'),group)}))
    return answer


def rows_for(families):
    count=Counter(f['group'] for f in families);xs=[];ys=[];weights=[];ids=[]
    for i,f in enumerate(families):
        for h in range(1,17):
            xs.append(inputs(f['query']['packets']['PLUS'],h))
            ys.append([(f['packet_positions_xy']['PLUS'][h-1][j]-f['packet_positions_xy']['MINUS'][h-1][j])/.02 for j in (0,1)])
            weights.append(1/(len(count)*count[f['group']]*16));ids.append(i)
    return np.asarray(xs),np.asarray(ys),np.asarray(weights),np.asarray(ids,int)


def normalizer(x,w):
    result=np.sqrt(np.einsum('n,ni,ni->i',w,x,x));result[result==0]=1
    return result


def augmented(x,y,w,counter,scale=None):
    counter['augmented_lstsq']=counter.get('augmented_lstsq',0)+1
    s=normalizer(x,w) if scale is None else np.asarray(scale)
    n=x.shape[1];matrix=np.vstack((np.sqrt(w)[:,None]*(x/s),np.sqrt(.001)*np.eye(n)))
    target=np.vstack((np.sqrt(w)[:,None]*y,np.zeros((n,2))))
    coef=np.linalg.lstsq(matrix,target,rcond=None)[0]
    return dict(input_scale=s.tolist(),coef=coef.tolist())


def contexts(families,history):
    raw=np.asarray([public_vector(f['query'],history) for f in families]);counts=Counter(f['group'] for f in families)
    weights=np.asarray([1/(len(counts)*counts[f['group']]) for f in families]);mean=np.sum(raw*weights[:,None],axis=0)
    constant=np.ptp(raw,axis=0)==0;mean[constant]=raw[0,constant]
    sd=np.sqrt(np.sum((raw-mean)**2*weights[:,None],axis=0));sd[constant | (sd==0)]=1
    return mean,sd,(raw-mean)/sd


def eigen_fit(families,x,y,w,ids,history,counter):
    mean,sd,c=contexts(families,history);scale=normalizer(x,w);z=x/scale;sw=np.sqrt(w)
    similarities=np.asarray([[exp(-.5*float(np.mean((l-r)**2))) for r in c] for l in c])
    gram=np.dot(z,z.T)*similarities[ids[:,None],ids[None,:]]
    regularized=sw[:,None]*gram*sw[None,:]+.001*np.eye(len(w))
    counter['symmetric_eigendecompositions']=counter.get('symmetric_eigendecompositions',0)+1
    eigenvalues,vectors=np.linalg.eigh(regularized)
    io.require(np.min(eigenvalues)>0,'positive independently reconstructed ridge system')
    dual=vectors@((vectors.T@(sw[:,None]*y))/eigenvalues[:,None])
    pieces=[]
    for i in range(len(families)):
        positions=np.where(ids==i)[0]
        pieces.append(np.sum(z[positions,:,None]*(sw[positions,None]*dual[positions])[:,None,:],axis=0))
    return dict(input_scale=scale.tolist(),center=mean.tolist(),context_scale=sd.tolist(),contexts=c.tolist(),coefficients=np.asarray(pieces).tolist())


def refit(rows,counter):
    result=dict(protocol='HISTORY_RESPONSE_MODELS_V1',by_task={})
    for task in io.TASKS:
        families=[f for f in rows if f['task']==task and f['complete_three_role_H16']]
        x,y,w,ids=rows_for(families);model={}
        model['INSTANT']=augmented(x[:,:2],y,w,counter)
        model['FIR']=augmented(x,y,w,counter)
        model['STATE_KERNEL']=eigen_fit(families,x,y,w,ids,False,counter)
        model['HISTORY_KERNEL']=eigen_fit(families,x,y,w,ids,True,counter)
        mean,sd,c=contexts(families,True);coefs=[];scale=np.asarray(model['FIR']['input_scale'])
        for value in c:
            distance=[float(np.sum((other-value)**2)/153) for other in c]
            nearest=sorted(range(len(c)),key=lambda j:(distance[j],j))[:8]
            xx,yy,ww,_=rows_for([families[j] for j in nearest])
            coefs.append(augmented(xx,yy,ww,counter,scale)['coef'])
        model['HISTORY_NN']=dict(input_scale=scale.tolist(),center=mean.tolist(),context_scale=sd.tolist(),contexts=c.tolist(),coefficients=coefs)
        result['by_task'][task]=model
    return result


def compare_models(main,other):
    maximum=0.
    def compare(left,right):
        nonlocal maximum
        if isinstance(left,dict):
            io.require(set(left)==set(right),'independent bank keys')
            for k in left:compare(left[k],right[k])
        elif isinstance(left,str):io.require(left==right,'independent bank version')
        else:
            l=np.asarray(left,float);r=np.asarray(right,float);io.require(l.shape==r.shape,'independent fitted dimensions')
            maximum=max(maximum,float(np.max(np.abs(l-r))))
            io.require(np.allclose(l,r,atol=1e-8,rtol=1e-6),'separate augmented-LS/eigen coefficient check')
    compare(main,other);return maximum


def evaluate(bank,q):
    task=bank['by_task'][q['task']];effective={}
    for method in KINDS[1:]:
        saved=task[method];scale=np.asarray(saved['input_scale'])
        if method in ('INSTANT','FIR'):coef=np.asarray(saved['coef'])
        else:
            raw=public_vector(q,method!='STATE_KERNEL');z=(raw-np.asarray(saved['center']))/np.asarray(saved['context_scale'])
            distances=[float(np.sum((z-np.asarray(row))**2)/len(raw)) for row in saved['contexts']]
            if method=='HISTORY_NN':coef=np.asarray(saved['coefficients'][min(range(len(distances)),key=lambda j:(distances[j],j))])
            else:
                coef=np.zeros((32,2))
                for d,piece in zip(distances,saved['coefficients']):coef+=exp(-.5*d)*np.asarray(piece)
        effective[method]=(scale,coef)
    result={}
    for method in KINDS:
        result[method]={}
        for left,right in PAIRS:
            delta=[[q['packets'][right][t][j]-q['packets'][left][t][j] for j in (0,1)] for t in range(16)];trajectory=[]
            for h in range(1,17):
                value=[0.,0.]
                if method!='ZERO':
                    x=inputs(delta,h,method=='INSTANT');scale,coef=effective[method]
                    value=[.01*sum(float(x[i]/scale[i]*coef[i,j]) for i in range(len(x))) for j in (0,1)]
                trajectory.append(value)
            result[method]['__'.join((left,right))]=trajectory
    return result
