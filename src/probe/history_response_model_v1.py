"""Standard public-context linear response kernels; no inverse or controller.

Only the *known future command* part is linear. Context kernels use completed
observations/commands. This is a component reference, not a novel acquisition rule.
"""
import numpy as np
from src.probe.paired_packet_query_v1 import validate, contrast, PAIRS
from src.probe.paired_packet_model_v1 import design
from src.probe.task_passive_pi_v1 import require

METHODS=('ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN','HISTORY_KERNEL')
BASELINES=METHODS[:-1]
SELECTED='HISTORY_KERNEL'
UNIT=.01
RIDGE=.001
NEIGHBOURS=8


def descriptor(query,kind):
    q=validate(query)
    require(kind in ('STATE','HISTORY'),'registered public descriptor')
    values=list(q['current']['observation'])+list(q['integral_carried_xy'])
    if kind=='HISTORY':
        for row in q['history']:
            delta=(np.asarray(row['after']['observation'][:3])-np.asarray(row['before']['observation'][:3]))/UNIT
            values.extend(row['command']);values.extend(delta.tolist())
    result=np.asarray(values,float)
    require(result.shape==((41,) if kind=='STATE' else (153,)) and np.isfinite(result).all(),'finite public history only')
    return result


def context_weights(model,value):
    require(set(model)=={'input_scale','center','context_scale','contexts','coefficients'},'strict context bank, no evaluator metadata')
    center=np.asarray(model['center'],float);scale=np.asarray(model['context_scale'],float)
    contexts=np.asarray(model['contexts'],float);coef=np.asarray(model['coefficients'],float)
    require(center.shape==scale.shape==value.shape and contexts.ndim==2 and contexts.shape[1]==len(value),'descriptor dimensions')
    require(coef.shape==(len(contexts),32,2) and len(contexts)>=1,'saved context kernels')
    require(all(np.isfinite(x).all() for x in (center,scale,contexts,coef)) and np.min(scale)>0,'finite fitted context bank')
    z=(value-center)/scale
    distance=np.sum((contexts-z)**2,axis=1)/len(value)
    return np.exp(-.5*distance),distance,coef


def coefficients(bank,query):
    q=validate(query)
    require(type(bank) is dict and set(bank)=={'protocol','by_task'} and bank['protocol']=='HISTORY_RESPONSE_MODELS_V1','versioned immutable public predictor bank')
    task=bank['by_task'][q['task']]
    require(set(task)==set(METHODS)-{'ZERO'},'all same-data strong references')
    public={kind:descriptor(q,kind) for kind in ('STATE','HISTORY')}
    answer={}
    for method in METHODS[1:]:
        model=task[method];scale=np.asarray(model['input_scale'],float)
        n=2 if method=='INSTANT' else 32
        require(scale.shape==(n,) and np.isfinite(scale).all() and np.min(scale)>0,'TRAIN-only input normalization')
        if method in ('INSTANT','FIR'):
            require(set(model)=={'input_scale','coef'},'strict global model')
            coef=np.asarray(model['coef'],float)
        else:
            kind='STATE' if method=='STATE_KERNEL' else 'HISTORY'
            weights,distance,saved=context_weights(model,public[kind])
            if method=='HISTORY_NN':
                # np.argmin returns the first immutable TRAIN center on a tie.
                coef=saved[int(np.argmin(distance))]
            else:coef=np.einsum('n,nij->ij',weights,saved)
        require(coef.shape==(n,2) and np.isfinite(coef).all(),'finite current effective response, never inverted')
        answer[method]=(scale,coef)
    return answer


def predict(bank,query,counter=None):
    q=validate(query);effective=coefficients(bank,q);result={}
    for method in METHODS:
        result[method]={}
        for pair in PAIRS:
            if counter is not None:counter['trajectories_started']=counter.get('trajectories_started',0)+1
            delta=contrast(q,pair);trajectory=[]
            for h in range(1,17):
                if method=='ZERO':
                    y=np.zeros(2)
                    if counter is not None:counter['zero_rows']=counter.get('zero_rows',0)+1
                else:
                    x=design(delta,h,'INSTANT' if method=='INSTANT' else 'FIR')
                    scale,coef=effective[method];y=UNIT*(x/scale)@coef
                    if counter is not None:counter['linear_rows']=counter.get('linear_rows',0)+1
                require(y.shape==(2,) and np.isfinite(y).all(),'finite saved forecast, no output clipping')
                trajectory.append(y.tolist())
            result[method]['__'.join(pair)]=trajectory
            if counter is not None:counter['trajectories_completed']=counter.get('trajectories_completed',0)+1
    return result
