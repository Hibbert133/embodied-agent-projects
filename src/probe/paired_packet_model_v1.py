"""Standard causal finite-impulse response comparators; no plant inversion."""
import numpy as np
from src.probe.paired_packet_query_v1 import validate,contrast,PAIRS
from src.probe.task_passive_pi_v1 import require
METHODS=('ZERO','INSTANT','FIR','CENTERED_FIR','FREE_CAUSAL');UNIT=.01

def design(delta,horizon,kind):
    u=np.asarray(delta,float);require(u.shape==(16,2) and np.isfinite(u).all() and type(horizon) is int and 1<=horizon<=16,'known causal command contrast and output horizon')
    if kind=='INSTANT':return u[:horizon].sum(axis=0)
    if kind=='FREE_CAUSAL':return u[:horizon].ravel()
    require(kind in ('FIR','CENTERED_FIR'),'registered causal linear predictor')
    return np.asarray([u[:horizon-lag].sum(axis=0) if lag<horizon else np.zeros(2) for lag in range(16)]).ravel()

def linear(saved,x):
    require(type(saved) is dict and set(saved)=={'scale','coef'},'pure saved predictor parameters, no private fields')
    scale=np.asarray(saved['scale'],float);coef=np.asarray(saved['coef'],float)
    require(scale.shape==x.shape and coef.shape==(len(x),2) and np.isfinite(scale).all() and np.isfinite(coef).all() and np.min(scale)>0,'finite saved model dimensions')
    return (x/scale)@coef

def predict(bank,query,counter=None):
    q=validate(query);require(type(bank) is dict and set(bank)=={'protocol','by_task'} and bank['protocol']=='PAIRED_PACKET_MODELS_V1','versioned predictor bank')
    models=bank['by_task'][q['task']];require(set(models)==set(METHODS)-{'ZERO'},'all fitted standard references')
    result={}
    for kind in METHODS:
        result[kind]={}
        for pair in PAIRS:
            if counter is not None:counter['trajectories_started']=counter.get('trajectories_started',0)+1
            du=contrast(q,pair);trajectory=[]
            for h in range(1,17):
                if kind=='ZERO':
                    if counter is not None:counter['zero_rows']=counter.get('zero_rows',0)+1
                    answer=np.zeros(2)
                else:
                    if counter is not None:counter['linear_rows']=counter.get('linear_rows',0)+1
                    saved=models[kind][h-1] if kind=='FREE_CAUSAL' else models[kind]
                    answer=UNIT*linear(saved,design(du,h,kind))
                require(answer.shape==(2,) and np.isfinite(answer).all(),'valid finite sixteen-step contrast, no output clipping')
                trajectory.append(answer.tolist())
            result[kind]['__'.join(pair)]=trajectory
            if counter is not None:counter['trajectories_completed']=counter.get('trajectories_completed',0)+1
    return result
