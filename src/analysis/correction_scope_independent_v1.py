"""Literal feature/label/moment reconstruction, independent of the main math."""
import math
import numpy as np
from src.analysis.response_qualification_io_v1 import require


def row_values(row):
    b=row['before']['observation'];a=row['after']['observation'];u=row['command']
    d=[(a[i]-b[i])/.01 for i in range(3)];e=sum((d[i]-u[i])**2 for i in range(2))
    dist=math.sqrt(sum((b[4+i]-b[i])**2 for i in range(3)))
    level=0 if max(abs(u[0]),abs(u[1]))<1/3 else 1 if max(abs(u[0]),abs(u[1]))<2/3 else 2
    index=((int(u[0]>=0)+2*int(u[1]>=0))*3+level)*2+int(dist<=.1)
    return index,e,list(u[:3])+d+[b[3],dist/.5,e]


def summary(history):
    rows=[row_values(r)[2] for r in history[-8:]]
    if not rows:return [0.]*28
    n=len(rows);mean=[sum(r[i] for r in rows)/n for i in range(9)]
    sd=[math.sqrt(sum((r[i]-mean[i])**2 for r in rows)/n) for i in range(9)]
    return mean+sd+rows[-1]+[n/8.]


def features(v,kind):
    m=v['memory'];categorical=[float(m['task']==t) for t in ('push-v3','reach-v3','door-open-v3')]
    categorical += [float(v['stage']==t) for t in ('PRE','POST')]
    categorical += [float(v['acquisition_action']==t) for t in ('CONTINUE','VALIDATE8','MOVE_MEASURE')]
    categorical += [float(v['time_constant_s']==r) if kind!='RATE_BLIND_RBF' else 0. for r in (.125,.5,2.,8.)]
    extra=[] if kind=='COMMAND_RBF' else list(m['current']['observation'])+list(m['integral_xy'])+[m['completed_steps']/500.]
    return categorical+extra+summary(v['history'])


def target(history,entry,returned):
    tail=history[entry:]
    if not tail:return None
    result=[]
    for h in (8,32):
        rows=tail[:h];n=len(rows);p=[0.]*24;j=[0.]*24;e=0.
        for row in rows:
            b,v,_=row_values(row);p[b]+=1;j[b]+=v;e+=v
        result += [x/n for x in p]+[x/n for x in j]+[e/n,n/h]
    return result+list(returned['current']['observation'])+list(returned['integral_xy'])+[returned['completed_steps']/500.]


def design(x,model):
    z=[]
    for row in x:z.append([min(10.,max(-10.,(v-m)/s)) for v,m,s in zip(row,model['mean'],model['scale'])])
    if model['kind']=='FULL_LINEAR':return np.asarray([[1.]+row for row in z])
    return np.asarray([[1.]+row+[math.exp(-sum((a-b)**2 for a,b in zip(row,c))/len(row)/2) for c in model['centers']] for row in z])


def project(values):
    y=list(map(float,values))
    for o in (0,50):
        p=[max(v,0.) for v in y[o:o+24]];s=sum(p);p=[v/s for v in p] if s else [1/24.]*24
        e=max(y[o+48],0.);j=[max(v,0.) for v in y[o+24:o+48]];s=sum(j);j=[v*e/s for v in j] if s else [v*e for v in p]
        y[o:o+24]=p;y[o+24:o+48]=j;y[o+48]=e;y[o+49]=min(1.,max(0.,y[o+49]))
    return y


def refit(examples,kind,model):
    x=np.asarray([features(e['view'],kind) for e in examples]);y=np.asarray([e['target'] for e in examples]);groups=[e['spec']['group'] for e in examples]
    w=np.asarray([len(groups)/len(set(groups))/groups.count(g) for g in groups]);mean=np.average(x,axis=0,weights=w)
    sd=np.maximum(.05,np.sqrt(np.average((x-mean)**2,axis=0,weights=w)))
    require(np.allclose(mean,model['mean'],atol=1e-13,rtol=1e-12) and np.allclose(sd,model['scale'],atol=1e-13,rtol=1e-12),'independent TRAIN normalization')
    z=np.clip((x-mean)/sd,-10,10);indices=np.linspace(0,len(x)-1,min(64,len(x))).round().astype(int)
    require(np.allclose(z[indices],model['centers'],atol=1e-12,rtol=1e-12),'independent label-blind centers')
    phi=design(x,model);penalty=np.eye(phi.shape[1])*.1;penalty[0,0]=1e-5
    coefficients=np.linalg.lstsq(np.r_[np.sqrt(w)[:,None]*phi,penalty],np.r_[np.sqrt(w)[:,None]*y,np.zeros((phi.shape[1],y.shape[1]))],rcond=None)[0]
    require(np.allclose(coefficients,model['coefficients'],atol=3e-7,rtol=2e-7),'independent augmented least-squares coefficients')
    return coefficients


def prediction(v,model):
    phi=design([features(v,model['kind'])],model)
    return project((phi@np.asarray(model['coefficients']))[0])


def persistence(v):
    rows=v['history'][-8:];n=max(1,len(rows));p=[0.]*24;j=[0.]*24;error=0.
    for row in rows:
        b,e,_=row_values(row);p[b]+=1;j[b]+=e;error+=e
    block=[x/n for x in p]+[x/n for x in j]+[error/n,1.];m=v['memory']
    return project(block+block+list(m['current']['observation'])+list(m['integral_xy'])+[m['completed_steps']/500.])


def errors(p,y):
    result={}
    for o,h in ((0,8),(50,32)):
        result['occupancy_'+str(h)]=sum((p[o+i]-y[o+i])**2 for i in range(24))/24
        result['joint_'+str(h)]=sum((p[o+24+i]-y[o+24+i])**2 for i in range(24))/24
        result['error_'+str(h)]=(p[o+48]-y[o+48])**2
        result['count_'+str(h)]=(p[o+49]-y[o+49])**2
        result['factorized_joint_'+str(h)]=sum((p[o+i]*p[o+48]-y[o+24+i])**2 for i in range(24))/24
    result['return_state']=sum((p[100+i]-y[100+i])**2 for i in range(39))/39
    return result
