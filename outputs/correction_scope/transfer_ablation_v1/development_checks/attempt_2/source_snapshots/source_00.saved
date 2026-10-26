"""TRAIN-only supervision interventions; never new physical trajectory labels."""
import numpy as np
from src.analysis import correction_transfer_learning_v1 as prior
KINDS=('FUTURE_MARGINAL_PRODUCT','FUTURE_RATE_MEAN','HISTORY_RECONSTRUCT')


def past_summary(node):
    prior.old.validate_node(node);rows=node['history'][-32:]
    if not rows:raise ValueError('no executed past window; cannot fabricate a reconstruction label')
    p=np.zeros(24);j=np.zeros(24)
    for row in rows:
        one,error,_=prior.old.public.query_vector(row);p+=one;j+=one*error
    return np.r_[p/len(rows),j/len(rows),j.sum()/len(rows),len(rows)/32]


def supervision(nodes,target,kind):
    if kind not in KINDS:raise ValueError('unknown auxiliary supervision intervention')
    y=np.asarray(target,dtype=float).copy()
    if y.shape!=(len(nodes),4,50) or not np.isfinite(y).all():raise ValueError('complete factual TRAIN targets required')
    for node in nodes:prior.old.validate_node(node)
    if kind=='FUTURE_MARGINAL_PRODUCT':y[:,:,24:48]=y[:,:,:24]*y[:,:,48:49]
    elif kind=='FUTURE_RATE_MEAN':y=np.repeat(y.mean(1,keepdims=True),4,axis=1)
    else:y=np.repeat(np.asarray([past_summary(n) for n in nodes])[:,None,:],4,axis=1)
    if np.min(y)<0 or not np.allclose(y[:,:,:24].sum(2),1,atol=2e-10,rtol=2e-10):raise ValueError('valid occupancy distribution')
    if not np.allclose(y[:,:,24:48].sum(2),y[:,:,48],atol=2e-10,rtol=2e-10):raise ValueError('consistent aggregate error mass')
    if not np.all((y[:,:,49]>0)&(y[:,:,49]<=1)):raise ValueError('bounded aggregate window fractions required')
    return y
