"""Public, causal forecasts of actual successor queries; never a plant inverse.

All learning uses factual public observations and sent commands. The explicit
working model dXY=.01*sentXY is not qualified physics or a noise-free model.
"""
from copy import deepcopy
import numpy as np
from src.probe.task_memory_option_v1 import TaskMemory
from src.probe.task_passive_pi_v1 import require, digest, vector
from src.analysis.capsule_record_json_v2 import normalize

ACTIONS=('CONTINUE','VALIDATE8','MOVE_MEASURE')
RATES=(.125,.5,2.,8.)
STAGES=('PRE','POST')
TASKS=('push-v3','reach-v3','door-open-v3')
KINDS=('COMMAND_RBF','RATE_BLIND_RBF','FULL_LINEAR','FULL_RBF')
HORIZONS=(8,32)
BINS=24
BLOCK=50
TARGETS=2*BLOCK+42


def public_state(v):
    require(type(v) is dict and set(v)=={'observation','success','terminated','truncated'},'strict public step observation')
    vector(v['observation'],39)
    require(all(type(v[k]) is bool for k in ('success','terminated','truncated')),'public terminal booleans')
    return v


def validate(v):
    require(type(v) is dict and set(v)=={'schema','stage','memory','history','acquisition_action','time_constant_s'}
            and v['schema']=='CORRECTION_SCOPE_PUBLIC_V1','unknown/private/future forecast input')
    require(v['stage'] in STAGES and v['acquisition_action'] in ACTIONS and v['time_constant_s'] in RATES,'registered forecast query')
    m=TaskMemory.from_dict(v['memory']);h=v['history']
    require(m.saved_controller[0]=='UNCORRECTED','A1 uses only the fixed RAW identity base')
    require(type(h) is list and len(h)==m.completed_steps,'complete causal public history from actual initial state')
    previous=None
    for i,r in enumerate(h):
        require(type(r) is dict and set(r)=={'at_calls','before','command','after'} and type(r['at_calls']) is int and r['at_calls']==i,'consecutive strict public row')
        public_state(r['before']);public_state(r['after']);u=vector(r['command'],4)
        require(max(abs(x) for x in u)<=1 and tuple(np.asarray(u,np.float32).astype(float))==u,'saved bounded float32 command')
        require(not any(r['before'][k] for k in ('success','terminated','truncated')),'history after terminal')
        if previous is not None:require(previous==r['before'],'public history discontinuity')
        previous=r['after']
    if h:require(h[-1]['after']==v['memory']['current'],'history includes future or stale memory')
    return m


def view(stage,memory,history,action,rate):
    v=normalize(dict(schema='CORRECTION_SCOPE_PUBLIC_V1',stage=stage,memory=memory.to_dict(),
        history=deepcopy(history),acquisition_action=action,time_constant_s=rate))
    validate(v);return v


def query_vector(row):
    b=np.asarray(row['before']['observation'],float);a=np.asarray(row['after']['observation'],float);u=np.asarray(row['command'],float)
    d=(a[:3]-b[:3])/.01;err=float(np.sum((d[:2]-u[:2])**2))
    dist=float(np.linalg.norm(b[4:7]-b[:3]))
    quadrant=int(u[0]>=0)+2*int(u[1]>=0)
    level=min(2,int(float(np.max(np.abs(u[:2])))*3))
    index=(quadrant*3+level)*2+int(dist<=.1)
    one=np.zeros(BINS);one[index]=1.
    return one,err,np.r_[u[:3],d,b[3],dist/.5,err]


def summary(history):
    if not history:return np.zeros(28)
    a=np.asarray([query_vector(r)[2] for r in history[-8:]])
    return np.r_[a.mean(0),a.std(0),a[-1],len(a)/8.]


def features(v,kind):
    m=validate(v);require(kind in KINDS,'registered forecast feature set')
    s=summary(v['history'])
    categorical=np.r_[[float(m.task==t) for t in TASKS],[float(v['stage']==t) for t in STAGES],
        [float(v['acquisition_action']==a) for a in ACTIONS],
        [float(v['time_constant_s']==r) if kind!='RATE_BLIND_RBF' else 0. for r in RATES]]
    if kind=='COMMAND_RBF':return np.r_[categorical,s]
    return np.r_[categorical,np.asarray(m.current.observation),np.asarray(m.integral_xy),m.completed_steps/500.,s]


def target(history,entry,returned):
    """Evaluation-side labels only; never called by an online forecast."""
    require(type(entry) is int and 0<=entry<=len(history),'actual tail boundary')
    tail=history[entry:];out=[]
    if not tail:return None,'NO_EXECUTED_TAIL'
    for horizon in HORIZONS:
        rows=tail[:horizon];n=len(rows);hist=np.zeros(BINS);joint=np.zeros(BINS);error=0.
        for row in rows:
            q,e,_=query_vector(row);hist+=q;joint+=q*e;error+=e
        # Normalization is by executed length. Short/terminal windows retain
        # their real length; no virtual observations, zero padding or rollouts.
        out.extend(np.r_[hist/n,joint/n,error/n,n/horizon])
    m=TaskMemory.from_dict(returned)
    out.extend(np.r_[m.current.observation,m.integral_xy,m.completed_steps/500.])
    y=np.asarray(out,float);require(y.shape==(TARGETS,) and np.isfinite(y).all(),'finite complete factual target')
    return y.tolist(),None


def persistence(v):
    m=validate(v);h=v['history'][-8:];out=[]
    hist=np.zeros(BINS);joint=np.zeros(BINS);error=0.
    for row in h:
        q,e,_=query_vector(row);hist+=q;joint+=q*e;error+=e
    n=max(1,len(h))
    for _ in HORIZONS:out.extend(np.r_[hist/n,joint/n,error/n,1.])
    out.extend(np.r_[m.current.observation,m.integral_xy,m.completed_steps/500.])
    return list(map(float,out))


def design(x,model):
    x=np.asarray(x,float);z=np.clip((x-np.asarray(model['mean']))/np.asarray(model['scale']),-10,10)
    if model['kind']=='FULL_LINEAR':return np.c_[np.ones(len(z)),z]
    centers=np.asarray(model['centers']);d=((z[:,None,:]-centers[None,:,:])**2).mean(2)
    return np.c_[np.ones(len(z)),z,np.exp(-d/2)]


def fit(x,y,groups,kind):
    x=np.asarray(x,float);y=np.asarray(y,float);g=np.asarray(groups)
    require(len(x)==len(y)==len(g)>0 and y.shape[1]==TARGETS,'complete training factual rows')
    unique=np.unique(g);weights=np.asarray([1./sum(g==v) for v in g]);weights*=len(g)/len(unique)
    mean=np.average(x,axis=0,weights=weights);scale=np.sqrt(np.average((x-mean)**2,axis=0,weights=weights));scale=np.maximum(scale,.05)
    z=np.clip((x-mean)/scale,-10,10)
    # Deterministic, label-independent centers; no CAL/TEST selection.
    indices=np.linspace(0,len(x)-1,min(64,len(x))).round().astype(int)
    model=dict(kind=kind,mean=mean.tolist(),scale=scale.tolist(),centers=z[indices].tolist(),ridge=.01)
    phi=design(x,model);penalty=np.eye(phi.shape[1])*.01;penalty[0,0]=1e-10
    coefficients=np.linalg.solve(phi.T@(weights[:,None]*phi)+penalty,phi.T@(weights[:,None]*y))
    model.update(coefficients=coefficients.tolist(),training_rows=len(x),independent_groups=len(unique),
        x_sha256=digest(x.tolist()),y_sha256=digest(y.tolist()),groups_sha256=digest(g.tolist()))
    return model


def predict(bank,v):
    validate(v);require(bank['schema']=='CORRECTION_SCOPE_BANK_V1' and bank['bank_id']==digest({k:w for k,w in bank.items() if k!='bank_id'}),'frozen forecast bank')
    stage=v['stage'];results={'PERSISTENCE':project(persistence(v))}
    for kind in KINDS:
        model=bank['models'][stage][kind]
        y=(design([features(v,kind)],model)@np.asarray(model['coefficients']))[0]
        require(y.shape==(TARGETS,) and np.isfinite(y).all(),'nonfinite forecast')
        results[kind]=project(y)
    return dict(schema='CORRECTION_SCOPE_FORECAST_V1',bank_id=bank['bank_id'],
        input_sha256=digest(v),stage=stage,predictions=results)


def project(value):
    """Identical moment constraints for every comparator, no learned thresholds."""
    y=np.array(value,dtype=float,copy=True);require(y.shape==(TARGETS,) and np.isfinite(y).all(),'finite moment vector')
    for o in (0,BLOCK):
        p=np.maximum(y[o:o+24],0);s=p.sum();p=p/s if s>0 else np.ones(24)/24
        e=max(0.,y[o+48]);j=np.maximum(y[o+24:o+48],0);s=j.sum();j=j*(e/s) if s>0 else p*e
        y[o:o+24]=p;y[o+24:o+48]=j;y[o+48]=e;y[o+49]=np.clip(y[o+49],0,1)
    return y.tolist()


def family_errors(predicted,actual):
    p=np.asarray(predicted);y=np.asarray(actual);require(p.shape==y.shape==(TARGETS,),'one complete forecast and factual target')
    result={}
    for j,horizon in enumerate(HORIZONS):
        o=j*BLOCK
        result['occupancy_'+str(horizon)]=float(np.mean((p[o:o+24]-y[o:o+24])**2))
        result['joint_'+str(horizon)]=float(np.mean((p[o+24:o+48]-y[o+24:o+48])**2))
        result['error_'+str(horizon)]=float((p[o+48]-y[o+48])**2)
        result['count_'+str(horizon)]=float((p[o+49]-y[o+49])**2)
        factor=p[o:o+24]*p[o+48]
        result['factorized_joint_'+str(horizon)]=float(np.mean((factor-y[o+24:o+48])**2))
    result['return_state']=float(np.mean((p[100:139]-y[100:139])**2))
    return result
