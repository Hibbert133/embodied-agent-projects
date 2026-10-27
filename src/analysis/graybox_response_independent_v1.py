"""Separate literal forecast reconstruction and augmented least-squares checks.

No production feature, predictor or observer import. Shares the declared model,
JSON/floats, scalar quadrature implementation and linear algebra primitives.
"""
from copy import deepcopy
import math
import numpy as np
from src.analysis import graybox_observer_independent_v1 as scalar
from src.analysis.response_qualification_io_v1 import require
PAIRS=(('ZERO','PLUS'),('ZERO','MINUS'),('PLUS','MINUS'));ROLES=('ZERO','PLUS','MINUS');Q=(0.,.001,.01)

def input_row(commands,h,kind):
    if kind=='INSTANT':return np.array([math.fsum(float(commands[t][j]) for t in range(h)) for j in range(2)])
    require(kind=='FIR','literal finite impulse kind')
    return np.array([math.fsum(float(commands[t][j]) for t in range(h-lag)) if lag<h else 0. for lag in range(16) for j in range(2)])

def arx_row(pos,cmd,i):
    require(i>=2,'real two-displacement history')
    return np.array([*cmd[i][:2],*cmd[i-1][:2],*((pos[i][j]-pos[i-1][j])/.01 for j in range(2)),
        *((pos[i-1][j]-pos[i-2][j])/.01 for j in range(2)),1.])

def initial(axis,y,fixed):
    means=[(0.,.6)[axis],float(y),0.,float(axis==0),float(axis==1),0.]
    diag=[0.,1e-10,1e-4,*([0.]*3 if fixed else [(.25 if axis==0 else .2)**2/3,(.25 if axis==1 else .2)**2/3,.2**2/3])]
    return dict(mean=means,covariance=[[diag[i] if i==j else 0. for j in range(6)] for i in range(6)])

def gray(plants,trace,packets,q,fixed=False,counter=None):
    beliefs=[initial(i,trace['initial_xy'][i],fixed) for i in range(2)]
    def one(axis,b,u):
        if counter is not None:counter['independent_axis_predictions']=counter.get('independent_axis_predictions',0)+1
        return scalar.predict(axis,b,u,plants[axis],q)
    for row in trace['steps']:
        for i in range(2):
            beliefs[i]=one(i,beliefs[i],row['command']);beliefs[i],_=scalar.update(beliefs[i],row['after_xy'][i],plants[i])
            if counter is not None:counter['independent_axis_observations']=counter.get('independent_axis_observations',0)+1
    out={}
    for role in ROLES:
        branch=deepcopy(beliefs);values=[]
        for command in packets[role]:
            branch=[one(i,branch[i],command) for i in range(2)];values.append([b['mean'][1] for b in branch])
        out[role]=values
    return out

def rls(bank,trace,packets,counter=None):
    pos=[trace['initial_xy']]+[r['after_xy'] for r in trace['steps']];cmd=[r['command'] for r in trace['steps']];n=len(cmd)-2
    scale=np.array(bank['input_scale']);prior=np.linalg.solve(np.array(bank['covariance']),np.eye(9));precision=.98**n*prior;rhs=precision@np.array(bank['coef'])
    for i in range(2,len(cmd)):
        z=arx_row(pos,cmd,i)/scale;y=(np.array(pos[i+1])-pos[i])/.01;w=.98**(len(cmd)-1-i)
        precision+=w*np.outer(z,z);rhs+=w*np.outer(z,y)
    coef=np.linalg.solve(precision,rhs)
    if counter is not None:counter['independent_RLS_batch_solves']=counter.get('independent_RLS_batch_solves',0)+2
    out={}
    for role in ROLES:
        pp=deepcopy(pos);cc=deepcopy(cmd);values=[]
        for command in packets[role]:
            cc.append(list(command));z=arx_row(pp,cc,len(cc)-1)/scale;after=np.array(pp[-1])+.01*(z@coef);pp.append(after.tolist());values.append(after.tolist())
        out[role]=values
    return out

def differences(positions):
    return {l+'__'+r:[[float(positions[r][h][j])-float(positions[l][h][j]) for j in range(2)] for h in range(16)] for l,r in PAIRS}

def evaluate(bank,q,counter=None):
    models=bank['by_task'][q['task']];trace=dict(initial_xy=q['initial']['observation'][:2],steps=[dict(at_calls=r['at_calls'],command=r['command'],after_xy=r['after']['observation'][:2]) for r in q['history']])
    names=['ZERO','INSTANT','FIR','RLS_ARX','GRAY_FIXED']+(['GRAY_Q0','GRAY_Q1','GRAY_Q2'] if bank['selected_q_index'] is None else ['GRAY_JOINT'])
    out={};errors={}
    for name in names:
        try:
            if name in ('ZERO','INSTANT','FIR'):
                result={}
                for left,right in PAIRS:
                    commands=[[b[j]-a[j] for j in range(2)] for a,b in zip(q['packets'][left],q['packets'][right])];values=[]
                    for h in range(1,17):
                        if name=='ZERO':values.append([0.,0.]);continue
                        x=input_row(commands,h,name);scale=models[name]['scale'];coef=models[name]['coef']
                        values.append([.01*math.fsum(float(x[k])/float(scale[k])*float(coef[k][j]) for k in range(len(x))) for j in range(2)])
                    result[left+'__'+right]=values
            elif name=='RLS_ARX':result=differences(rls(models[name],trace,q['packets'],counter))
            else:
                fixed=name=='GRAY_FIXED';index=bank['selected_q_index'] if name=='GRAY_JOINT' else int(name[-1]) if not fixed else None
                result=differences(gray(models['PLANTS'],trace,q['packets'],0. if fixed else Q[index],fixed,counter))
            require(all(np.array(v).shape==(16,2) and np.isfinite(v).all() for v in result.values()),'finite independent predictions');out[name]=result
        except Exception as ex:errors[name]=dict(type=type(ex).__name__,message=str(ex))
    return out,errors

def nominal_scores(traces,counter=None):
    scores=[]
    for rho in (0.,.5,.9):
        for kappa in (.05,.2,.8):
            plants=[dict(rho=rho,kappa=kappa,observation_variance=1e-6,acceleration_variance=6.25e-8)]*2;total=[0.,0.]
            for trace in traces:
                beliefs=[initial(i,trace['initial_xy'][i],True) for i in range(2)]
                for row in trace['steps']:
                    for i in range(2):
                        p=scalar.predict(i,beliefs[i],row['command'],plants[i],0.);beliefs[i],nll=scalar.update(p,row['after_xy'][i],plants[i]);total[i]+=nll/(len(traces)*len(trace['steps']))
                        if counter is not None:counter['independent_nominal_axis_predictions']=counter.get('independent_nominal_axis_predictions',0)+1
            scores.append(total)
            if counter is not None:counter['independent_nominal_grid_passes']=counter.get('independent_nominal_grid_passes',0)+1
    return scores

def augmented_linear(x,y,w,ridge=.001):
    x=np.array(x,float);y=np.array(y,float);w=np.array(w,float);d=x.shape[1];scale=np.sqrt(np.sum(w[:,None]*x*x,axis=0));scale[scale==0]=1.
    a=x/scale*np.sqrt(w[:,None]);b=y*np.sqrt(w[:,None])
    coef=np.linalg.lstsq(np.r_[a,np.sqrt(ridge)*np.eye(d)],np.r_[b,np.zeros((d,2))],rcond=None)[0]
    return dict(scale=scale.tolist(),coef=coef.tolist())
