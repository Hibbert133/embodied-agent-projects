"""Offline group-weighted standard RBF risk fitting, with explicit solve ledger."""
import hashlib
import numpy as np
from src.probe.task_passive_pi_v1 import require


def weights(groups):
    require(type(groups) in (list,tuple) and groups and all(type(g) is str and g for g in groups),'actual independent group registry')
    counts={g:groups.count(g) for g in set(groups)}
    return np.asarray([1/(len(counts)*counts[g]) for g in groups],float)


def fit(x,y,groups,width,ridge,centers,ledger,*,role):
    x=np.asarray(x,float);y=np.asarray(y,float);w=weights(groups)
    require(x.ndim==2 and y.shape==w.shape==(len(x),) and np.isfinite(x).all() and np.isfinite(y).all(),'finite factual risk-training arrays')
    require(type(ledger) is list and type(role) is str and role and width>0 and ridge>0 and type(centers) is int and centers>0,'registered numerical fit budget')
    mean=np.sum(x*w[:,None],axis=0);std=np.sqrt(np.sum((x-mean)**2*w[:,None],axis=0));active=std>=1e-6;scale=np.where(active,std,1.)
    z=(x-mean)/scale;z[:,~active]=0.;unique=[];seen=set()
    for i,row in enumerate(z):
        key=hashlib.sha256(row.astype('<f8').tobytes()).digest()
        if key not in seen:seen.add(key);unique.append(i)
    take=[unique[i] for i in np.linspace(0,len(unique)-1,min(centers,len(unique)),dtype=int)]
    anchor=z[take];distance=np.sum((z[:,None,:]-anchor[None,:,:])**2,axis=2)/max(1,int(active.sum()))
    phi=np.c_[np.ones(len(x)),np.exp(-distance/(2*width**2))];penalty=np.diag([0.]+[ridge]*len(anchor))
    lhs=phi.T@(w[:,None]*phi)+penalty;rhs=phi.T@(w*y)
    ledger.append(dict(role=role,training_rows=len(x),independent_groups=sorted(set(groups)),system_dimension=len(lhs),solver='numpy.linalg.solve'))
    beta=np.linalg.solve(lhs,rhs)
    require(np.isfinite(beta).all(),'finite risk fit, no silent fallback')
    return dict(schema='GROUP_WEIGHTED_RBF_RISK_V1',mean=mean.tolist(),scale=scale.tolist(),active=active.tolist(),centers=anchor.tolist(),
        width=float(width),coefficients=beta.tolist(),training_groups=sorted(set(groups)),training_rows=len(x))


def independent_refit(model,x,y,groups,ridge,ledger,*,role,expected_centers=None):
    """Different centering sums and augmented least squares; no main fit/predict."""
    import math
    x=np.asarray(x,float);y=np.asarray(y,float);counts={g:groups.count(g) for g in set(groups)}
    w=np.asarray([1/(len(counts)*counts[g]) for g in groups]);mean=np.array([math.fsum(float(v)*float(t) for v,t in zip(x[:,i],w)) for i in range(x.shape[1])])
    std=np.array([math.sqrt(math.fsum(float(t)*(float(v)-float(mean[i]))**2 for v,t in zip(x[:,i],w))) for i in range(x.shape[1])])
    active=std>=1e-6;scale=np.where(active,std,1.)
    require(np.allclose(mean,model['mean'],atol=2e-12,rtol=2e-12) and np.allclose(scale,model['scale'],atol=2e-12,rtol=2e-12)
        and np.array_equal(active,model['active']),'independent weighted preprocessing')
    z=(x-mean)/scale;z[:,~active]=0.;centers=np.asarray(model['centers']);width=model['width'];a=[]
    reference=(x-np.asarray(model['mean']))/np.asarray(model['scale']);reference[:,~active]=0.;seen=set();unique=[]
    for i,row in enumerate(reference):
        key=hashlib.sha256(row.astype('<f8').tobytes()).digest()
        if key not in seen:seen.add(key);unique.append(i)
    if expected_centers is not None:require(len(centers)==min(expected_centers,len(unique)),'registered center-count capacity')
    indices=[unique[int(i)] for i in np.linspace(0,len(unique)-1,len(centers),dtype=int)]
    require(np.allclose(centers,reference[indices],rtol=0,atol=2e-12),'independent registered factual center locations')
    require(model['training_groups']==sorted(set(groups)) and model['training_rows']==len(x),'independent factual fit provenance')
    for row in z:
        a.append([1.]+[math.exp(-math.fsum(float(v)**2 for v in row-anchor)/(2*width**2*max(1,int(active.sum())))) for anchor in centers])
    phi=np.asarray(a);reg=np.diag([0.]+[math.sqrt(ridge)]*len(centers));aug=np.r_[np.sqrt(w)[:,None]*phi,reg];target=np.r_[np.sqrt(w)*y,np.zeros(len(reg))]
    ledger.append(dict(role=role,training_rows=len(x),independent_groups=sorted(set(groups)),system_dimension=aug.shape[1],solver='numpy.linalg.lstsq_augmented'))
    beta=np.linalg.lstsq(aug,target,rcond=None)[0]
    require(np.allclose(beta,model['coefficients'],rtol=3e-6,atol=3e-6),'independent augmented risk coefficients')
    return dict(integrity='PASSED',max_coefficient_error=float(np.max(np.abs(beta-np.asarray(model['coefficients'])))),independent_coefficients=beta.tolist())
