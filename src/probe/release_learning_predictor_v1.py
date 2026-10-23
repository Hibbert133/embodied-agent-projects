"""Frozen complete-task risk prediction; standard RBF regression, not novelty."""
import numpy as np
from src.probe.task_passive_pi_v1 import require,digest
from src.probe.information_release_v1 import ACTIONS
from src.probe import release_learning_features_v1 as features


def projection(model,x):
    require(type(model) is dict and set(model)=={'schema','mean','scale','active','centers','width','coefficients','training_groups','training_rows'}
        and model['schema']=='GROUP_WEIGHTED_RBF_RISK_V1','strict frozen public risk model')
    x=np.asarray(x,float);mean=np.asarray(model['mean'],float);scale=np.asarray(model['scale'],float);active=np.asarray(model['active'],bool)
    centers=np.asarray(model['centers'],float);beta=np.asarray(model['coefficients'],float);width=model['width']
    require(x.shape==mean.shape==scale.shape==active.shape and np.isfinite(x).all() and np.isfinite(mean).all()
        and np.isfinite(scale).all() and np.all(scale>0) and centers.ndim==2 and centers.shape[1]==x.size,'registered predictor dimensions')
    require(type(width) in (float,int) and width>0 and np.isfinite(width) and beta.shape==(len(centers)+1,)
        and np.isfinite(centers).all() and np.isfinite(beta).all(),'finite frozen risk coefficients')
    z=(x-mean)/scale;z[~active]=0.;distance=np.sum((centers-z)**2,axis=1)/max(1,int(active.sum()))
    return np.r_[1.,np.exp(-distance/(2*width**2))]


def predict(model,x):return float(projection(model,x)@np.asarray(model['coefficients']))


def receiver(bundle,view,prefix_history):
    require(bundle['schema']=='FROZEN_RELEASE_RECEIVER_V1' and bundle['receiver_version']==digest(bundle['model']),'receiver identity changed')
    common,full,present=features.after(view,prefix_history);model=bundle['model']
    base=np.array([predict(m,common) for m in model['common']]);enriched=None;masked=base.copy()
    if view['common']['paid_acquisition_steps']>0:masked+=np.array([predict(m,common) for m in model['common_residual']])
    if present:enriched=np.round(np.clip(base+np.array([predict(m,full) for m in model['signal_residual']]),0,500),6).tolist()
    return np.round(np.clip(masked,0,500),6).tolist(),enriched


def acquisition(bank,kind,memory,history):
    require(kind in ('effect','direct'),'registered learned risk contrast')
    x=features.before(memory,history);models=bank[kind];out={}
    for action in ACTIONS:
        if kind=='effect':
            masked=predict(models[action]['masked'],x);effect=0. if action=='CONTINUE' else predict(models[action]['effect'],x)
            full=masked+effect
        else:
            masked=predict(models[action]['masked'],x);full=masked if action=='CONTINUE' else predict(models[action]['full'],x)
        masked=round(float(np.clip(masked,0,500)),6);full=round(float(np.clip(full,0,500)),6)
        out[action]=dict(masked_risk=masked,information_effect=full-masked)
    return out
