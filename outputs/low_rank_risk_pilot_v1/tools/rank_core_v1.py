"""Standard weighted kernel reduced-rank ridge, not a novel robot controller."""
import numpy as np

KINDS=('LINEAR','RBF')
SPECS=(('FULL',12,'FULL'),*(('RR'+str(r),r,'CONTRAST') for r in (1,2,4)),
       *(('PCA'+str(r),r,'PCA_CONTRAST') for r in (1,2,4)),('RAW_RR2',2,'RAW'),('RAW_RR3',3,'RAW'))
NAMES=tuple(k+'_'+s[0] for k in KINDS for s in SPECS)
TASKS=('push-v3','reach-v3','door-open-v3')


def need(v,msg):
    if not v:raise ValueError(msg)


def features(node):
    need(type(node) is dict and set(node)=={'schema','stage','task','completed_steps','current','integral_xy','controller','history','acquisition_action'}
         and node['schema']=='COMPLETE_RISK_PUBLIC_NODE_V1' and node['stage']=='PRE' and node['acquisition_action'] is None,'strict public PRE only')
    n=node['completed_steps'];need(type(n) is int and n in (16,32,64) and len(node['history'])==n,'real boundary history')
    need(node['task'] in TASKS,'public task')
    def state(s):
        need(set(s)=={'observation','terminated','truncated','success'} and all(type(s[k]) is bool for k in ('terminated','truncated','success')),'strict public state')
        need(len(s['observation'])==39 and np.isfinite(s['observation']).all(),'state vector')
    state(node['current']);need(not any(node['current'][k] for k in ('terminated','truncated','success')),'no terminal decision')
    c=node['controller'];need(c==dict(source='UNCORRECTED',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.,0.,0.,0.]),'original PRE controller')
    integral=np.asarray(node['integral_xy'],float);need(integral.shape==(2,) and np.isfinite(integral).all() and max(abs(integral))<=2,'actual integral')
    x=np.zeros(41548);x[:48]=[*[float(node['task']==t) for t in TASKS],*node['current']['observation'],*integral,n/500.,0.,0.,0.]
    previous=None
    for i,row in enumerate(node['history']):
        need(set(row)=={'at_calls','before','command','after'} and row['at_calls']==i,'actual history index')
        state(row['before']);state(row['after']);u=np.asarray(row['command'],float)
        need(u.shape==(4,) and np.isfinite(u).all() and max(abs(u))<=1 and np.array_equal(u,u.astype(np.float32).astype(float)),'actual float32 sends')
        need(previous is None or row['before']==previous,'history continuity')
        need(not any(row['before'][k] for k in ('success','terminated','truncated')),'no completed terminal prefix')
        x[48+83*i:48+83*(i+1)]=[*row['before']['observation'],*u,*row['after']['observation'],1.]
        previous=row['after']
    need(previous==node['current'],'current matches actual end');return x


def weights(groups):
    groups=np.asarray(groups,int);unique=np.unique(groups)
    need(len(groups)>0,'nonempty independent-group training')
    return np.array([len(groups)/(len(unique)*np.count_nonzero(groups==g)) for g in groups])


def normalize(x,w):
    active=np.flatnonzero(np.ptp(x,axis=0)>0);mean=np.average(x[:,active],axis=0,weights=w)
    scale=np.maximum(np.sqrt(np.average((x[:,active]-mean)**2,axis=0,weights=w)),.05)
    return active,mean,scale,np.clip((x[:,active]-mean)/scale,-10,10)


def kernel(x,z,kind):
    d=max(1,x.shape[1]);dot=x@z.T/d
    if kind=='LINEAR':return dot
    need(kind=='RBF','fixed kernel')
    dist=np.maximum(np.sum(x*x,1)[:,None]/d+np.sum(z*z,1)[None,:]/d-2*dot,0)
    return np.exp(-dist/2)


def canonical_eigenspace(c):
    """Only roundoff-scale degeneracies use a fixed coordinate basis, never loss."""
    vals,vec=np.linalg.eigh((c+c.T)/2);order=np.argsort(-vals,kind='stable');vals=vals[order];vec=vec[:,order]
    tol=1e-10*max(1.,float(max(abs(vals))));j=0
    while j<len(vals):
        end=j+1
        while end<len(vals) and abs(vals[end]-vals[j])<=tol:end+=1
        if end-j>1:
            projector=vec[:,j:end]@vec[:,j:end].T;basis=[]
            for k in range(len(vals)):
                v=projector[:,k].copy()
                for b in basis:v-=b*np.dot(b,v)
                if np.linalg.norm(v)>1e-8:
                    v/=np.linalg.norm(v);basis.append(v)
                if len(basis)==end-j:break
            need(len(basis)==end-j,'canonical tied subspace');vec[:,j:end]=np.column_stack(basis)
        j=end
    return vals,vec


def contrast_basis():
    basis=[]
    for i in range(11):
        v=np.zeros(12);v[i]=1;v[-1]=-1
        for b in basis:v-=b*np.dot(b,v)
        basis.append(v/np.linalg.norm(v))
    return np.column_stack(basis)


def fit_base(x,y,groups,kind,ledger):
    need(y.shape==(len(x),12) and np.isfinite(y).all() and y.min()>=0 and y.max()<=1,'12 actual complete-program labels')
    w=weights(groups);a,mean,scale,z=normalize(x,w);k=kernel(z,z,kind);p=w/w.sum()
    h=np.eye(len(x))-np.ones((len(x),1))*p[None,:];kc=h@k@h.T
    target_mean=p@y;yc=y-target_mean;sw=np.sqrt(w);kw=sw[:,None]*kc*sw[None,:];yw=sw[:,None]*yc
    ledger['linear_solves']+=1
    solve=np.linalg.solve(kw+.01*np.eye(len(x)),yw);alpha=sw[:,None]*solve
    fitted=kw@solve;gram=(yw.T@fitted+fitted.T@yw)/2
    d=contrast_basis()
    raw_eig,raw_v=canonical_eigenspace(gram);rr_eig,rr_v=canonical_eigenspace(d.T@gram@d);rr_v=d@rr_v
    ledger['symmetric_eigendecompositions']+=2
    return dict(active=a,mean=mean,scale=scale,centers=z,weights=w,k=k,kc=kc,alpha=alpha,target_mean=target_mean,
        kernel_mean=p@k,kernel_grand=float(p@k@p),raw_eigenvalues=raw_eig,raw_basis=raw_v,
        rr_eigenvalues=rr_eig,rr_basis=rr_v,kind=kind,training_rows=len(x))


def target_pca(y,groups,ledger):
    w=weights(groups);yc=y-np.average(y,axis=0,weights=w);d=contrast_basis()
    covariance=d.T@(yc.T@(w[:,None]*yc))@d
    ledger['symmetric_eigendecompositions']+=1
    vals,v=canonical_eigenspace(covariance);return vals,d@v


def projection(base,pca,spec):
    name,rank,mode=spec
    if mode=='FULL':return np.eye(12)
    basis=base['raw_basis'] if mode=='RAW' else pca[1] if mode=='PCA_CONTRAST' else base['rr_basis']
    project=basis[:,:rank]@basis[:,:rank].T
    if mode!='RAW':project+=np.ones((12,12))/12
    return (project+project.T)/2


def predict(base,x,project):
    z=np.clip((x[:,base['active']]-base['mean'])/base['scale'],-10,10)
    k=kernel(z,base['centers'],base['kind']);p=base['weights']/sum(base['weights'])
    centered=k-base['kernel_mean'][None,:]-(k@p)[:,None]+base['kernel_grand']
    return centered@(base['alpha']@project)+base['target_mean']


def choice(scores):
    need(np.shape(scores)==(12,) and np.isfinite(scores).all(),'all 12 predicted risks')
    clipped=np.clip(scores,0,1);return int(np.flatnonzero(clipped<=clipped.min()+1e-10)[0])


def fit_models(x,y,groups,ledger):
    pca=target_pca(y,groups,ledger);models={}
    for kind in KINDS:
        base=fit_base(x,y,groups,kind,ledger)
        for spec in SPECS:
            project=projection(base,pca,spec);ledger['projected_model_solutions']+=1
            models[kind+'_'+spec[0]]=(base,project)
    return models,pca
