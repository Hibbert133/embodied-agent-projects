"""Literal causal linear algebra; does not import the production design/predictor."""
import math
import numpy as np
from src.analysis.response_qualification_io_v1 import require

KINDS=('INSTANT','FIR','CENTERED_FIR','FREE_CAUSAL')
PAIRS=(('ZERO','PLUS'),('ZERO','MINUS'),('PLUS','MINUS'))


def row(commands,h,kind):
    require(1<=h<=16 and kind in KINDS,'literal registered horizon/model')
    if kind=='INSTANT':
        return np.array([math.fsum(float(commands[t][j]) for t in range(h)) for j in range(2)])
    if kind=='FREE_CAUSAL':return np.array([float(commands[t][j]) for t in range(h) for j in range(2)])
    return np.array([math.fsum(float(commands[t][j]) for t in range(h-lag)) if lag<h else 0. for lag in range(16) for j in range(2)])


def evaluate(bank,q):
    result={}
    for kind in ('ZERO',*KINDS):
        result[kind]={}
        for left,right in PAIRS:
            commands=[[b[j]-a[j] for j in range(2)] for a,b in zip(q['packets'][left],q['packets'][right])];pred=[]
            for h in range(1,17):
                if kind=='ZERO':pred.append([0.,0.]);continue
                saved=bank['by_task'][q['task']][kind]
                if kind=='FREE_CAUSAL':saved=saved[h-1]
                x=row(commands,h,kind);scale=saved['scale'];coef=saved['coef']
                require(len(x)==len(scale)==len(coef) and all(float(s)>0 for s in scale),'literal saved dimensions')
                pred.append([.01*math.fsum(float(x[k])/float(scale[k])*float(coef[k][j]) for k in range(len(x))) for j in range(2)])
            result[kind][left+'__'+right]=pred
    return result


def systems(families,task,kind,horizon=None):
    """Independent grouping/centering/weights, public commands and positions only."""
    selected=[f for f in families if f['task']==task and f['complete_three_role_H16']]
    groups=sorted(set(f['group'] for f in selected));require(len(groups)>=3 and len(selected)>=12,'registered complete public training availability')
    xx=[];yy=[];ww=[]
    for group in groups:
        part=[f for f in selected if f['group']==group]
        for f in part:
            for h in ([horizon] if horizon is not None else range(1,17)):
                role_x={r:row(f['query']['packets'][r],h,kind) for r in ('ZERO','PLUS','MINUS')}
                role_y={r:np.array(f['packet_positions_xy'][r][h-1],float)/.01 for r in ('ZERO','PLUS','MINUS')}
                if kind=='CENTERED_FIR':
                    mx=sum(role_x.values())/3;my=sum(role_y.values())/3
                    pairs=[(role_x[r]-mx,role_y[r]-my) for r in ('ZERO','PLUS','MINUS')]
                else:pairs=[(role_x[r]-role_x[l],role_y[r]-role_y[l]) for l,r in PAIRS]
                for x,y in pairs:xx.append(x);yy.append(y);ww.append(1/(len(groups)*len(part)*3*(1 if horizon is not None else 16)))
    return np.asarray(xx),np.asarray(yy),np.asarray(ww)


def refit(families,task,kind,horizon=None):
    x,y,w=systems(families,task,kind,horizon);scale=np.sqrt(np.sum(w[:,None]*x*x,axis=0));scale[scale==0]=1
    a=x/scale*np.sqrt(w[:,None]);b=y*np.sqrt(w[:,None]);d=x.shape[1]
    coef=np.linalg.lstsq(np.vstack((a,np.sqrt(.001)*np.eye(d))),np.vstack((b,np.zeros((d,2)))),rcond=None)[0]
    return dict(scale=scale.tolist(),coef=coef.tolist())


def audit_fits(families,bank):
    maximum=0.;count=0
    for task in ('push-v3','reach-v3','door-open-v3'):
        for kind in KINDS:
            for h in (range(1,17) if kind=='FREE_CAUSAL' else [None]):
                expected=refit(families,task,kind,h);saved=bank['by_task'][task][kind]
                if h is not None:saved=saved[h-1]
                for field in ('scale','coef'):
                    delta=float(np.max(abs(np.asarray(saved[field])-np.asarray(expected[field]))));maximum=max(maximum,delta)
                    require(np.allclose(saved[field],expected[field],rtol=2e-8,atol=2e-8),'independent augmented-LS fit differs')
                count+=1
    return dict(independent_augmented_lstsq_systems=count,max_parameter_absolute_difference=maximum)
