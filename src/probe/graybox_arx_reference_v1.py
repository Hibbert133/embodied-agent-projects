"""Standard normalized ridge/RLS ARX reference, all real public history allowed.

No inverse or controller. The linear unbounded graybox mean has an ARX2
realization, so a latent state alone does not add a new mean-model class.
"""
from copy import deepcopy
import numpy as np
from src.probe.graybox_observer_v1 import require,validate_trace,sent
UNIT=.01;DIM=9;RIDGE=.001;FORGET=.98

def features(positions,commands,i):
    require(type(i) is int and i>=2 and len(positions)>=i+1 and len(commands)>=i+1,'two actually available earlier displacements, current known command')
    return np.r_[sent(commands[i])[:2],sent(commands[i-1])[:2],
        (np.asarray(positions[i])-positions[i-1])/UNIT,(np.asarray(positions[i-1])-positions[i-2])/UNIT,1.]

def fit(traces,weights=None,ledger=None):
    require(type(traces) is list and bool(traces),'nominal TRAIN public trajectories')
    for trace in traces:validate_trace(trace)
    require(all(len(t['steps'])>=3 for t in traces),'all source traces need genuine ARX history; otherwise registration/gate must fail')
    weights=np.ones(len(traces))/len(traces) if weights is None else np.asarray(weights,float)
    require(weights.shape==(len(traces),) and np.isfinite(weights).all() and np.min(weights)>0 and abs(weights.sum()-1)<1e-10,'normalized positive trajectory weights')
    xx=[];yy=[];ww=[]
    for trace,w in zip(traces,weights):
        pos=[trace['initial_xy']]+[r['after_xy'] for r in trace['steps']];cmd=[r['command'] for r in trace['steps']]
        for i in range(2,len(cmd)):
            xx.append(features(pos,cmd,i));yy.append((np.asarray(pos[i+1])-pos[i])/UNIT);ww.append(w/(len(cmd)-2))
    x=np.asarray(xx);y=np.asarray(yy);w=np.asarray(ww);scale=np.sqrt(np.sum(w[:,None]*x*x,axis=0));scale[scale==0]=1.
    z=x/scale;gram=z.T@(w[:,None]*z)+RIDGE*np.eye(DIM);rhs=np.c_[z.T@(w[:,None]*y),np.eye(DIM)]
    if ledger is not None:ledger['ridge_solve_attempts']=ledger.get('ridge_solve_attempts',0)+1
    solution=np.linalg.solve(gram,rhs)
    return dict(schema='GRAYBOX_RLS_ARX_V1',input_scale=scale.tolist(),coef=solution[:,:2].tolist(),covariance=solution[:,2:].tolist(),
        forgetting=FORGET,unit=UNIT)

def validate(bank):
    require(type(bank) is dict and set(bank)=={'schema','input_scale','coef','covariance','forgetting','unit'} and bank['schema']=='GRAYBOX_RLS_ARX_V1','strict ARX bank')
    scale=np.asarray(bank['input_scale'],float);coef=np.asarray(bank['coef'],float);p=np.asarray(bank['covariance'],float)
    require(scale.shape==(DIM,) and np.isfinite(scale).all() and np.min(scale)>0 and coef.shape==(DIM,2) and np.isfinite(coef).all(),'finite ARX scaling/coefficients')
    require(p.shape==(DIM,DIM) and np.isfinite(p).all() and np.max(abs(p-p.T))<1e-8 and np.linalg.eigvalsh((p+p.T)/2).min()>0,'positive ARX information covariance')
    require(bank['forgetting']==FORGET and bank['unit']==UNIT,'frozen ARX normalization');return scale,coef,p

def forecast(bank,trace,packets,ledger=None):
    validate_trace(trace);scale,coef,p=validate(bank);require(len(trace['steps'])>=3,'actual ARX history available')
    pos=[trace['initial_xy']]+[r['after_xy'] for r in trace['steps']];cmd=[r['command'] for r in trace['steps']]
    for i in range(2,len(cmd)):
        z=features(pos,cmd,i)/scale;y=(np.asarray(pos[i+1])-pos[i])/UNIT
        prior=p/FORGET;gain=prior@z/(1+z@prior@z);coef=coef+np.outer(gain,y-z@coef);p=prior-np.outer(gain,z@prior);p=(p+p.T)/2
        if ledger is not None:ledger['rls_updates']=ledger.get('rls_updates',0)+1
    out={}
    require(type(packets) is dict and bool(packets),'declared packet branches')
    for role,future in packets.items():
        require(type(future) is list and 0<len(future)<=500-len(cmd),'finite future known command plan')
        positions=deepcopy(pos);commands=deepcopy(cmd);predictions=[]
        for u in future:
            sent(u);commands.append(list(u));i=len(commands)-1;z=features(positions,commands,i)/scale
            after=np.asarray(positions[-1])+UNIT*(z@coef);require(np.isfinite(after).all(),'finite ARX forecast')
            positions.append(after.tolist());predictions.append(after.tolist())
            if ledger is not None:ledger['rls_forecast_steps']=ledger.get('rls_forecast_steps',0)+1
        out[role]=predictions
    return out
