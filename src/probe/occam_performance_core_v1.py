"""Standard recursive performance-model core; not a complete OCCAM reproduction.

Phi is (performance outputs, weight bases), the transpose of the pinned
author implementation's convention. No plant, environment, reset or API access.
"""
from copy import deepcopy
import hashlib,json,math
import numpy as np

RATES=(.125,.5,2.,8.)
EPS=1e-10


def require(ok,message):
    if not ok:raise ValueError(message)


def array(value,ndim):
    a=np.array(value,dtype=float,copy=True)
    require(a.ndim==ndim and np.isfinite(a).all(),'finite numeric array and exact dimension')
    return a


def covariance(value,n,*,positive=False):
    a=array(value,2)
    require(a.shape==(n,n) and np.allclose(a,a.T,atol=EPS,rtol=0),'symmetric covariance of exact shape')
    a=(a+a.T)/2
    values=np.linalg.eigvalsh(a)
    require(values.min()>0 if positive else values.min()>=-EPS,'positive definite R / numerically semidefinite P,Q')
    return a


def forecast(mean,cov,phi,measurement_cov):
    m=array(mean,1);p=covariance(cov,len(m));h=array(phi,2)
    require(h.shape[1]==len(m) and h.shape[0]>0,'Phi shape outputs by bases')
    r=covariance(measurement_cov,h.shape[0],positive=True)
    latent=h@p@h.T
    return dict(mean=h@m,latent_covariance=(latent+latent.T)/2,observation_covariance=(latent+latent.T)/2+r)


def update(mean,cov,phi,observed,process_cov,measurement_cov):
    """Q once per completed feedback window; no jitter, clipping or silent reset."""
    m=array(mean,1);p=covariance(cov,len(m));h=array(phi,2);y=array(observed,1)
    require(h.shape==(len(y),len(m)) and len(y)>0,'output/base orientation and observed vector')
    q=covariance(process_cov,len(m));r=covariance(measurement_cov,len(y),positive=True)
    prior=p+q;innovation=y-h@m;s=h@prior@h.T+r
    gain=np.linalg.solve(s,h@prior).T
    after=m+gain@innovation;a=np.eye(len(m))-gain@h
    # Joseph form is algebraically equivalent to the author's direct form.
    posterior=a@prior@a.T+gain@r@gain.T;posterior=(posterior+posterior.T)/2
    require(np.isfinite(after).all() and np.isfinite(posterior).all(),'finite posterior')
    return dict(mean=after,covariance=posterior,innovation=innovation,innovation_covariance=s,gain=gain)


def choose(predictions,reward_weights,beta):
    """Maximize E[J]+beta*sd[J]; signed beta is explicit, ties keep input order."""
    weights=array(reward_weights,1)
    require(predictions and type(beta) in (float,int) and math.isfinite(beta),'registered candidates and finite signed beta')
    scores=[]
    for p in predictions:
        mean=array(p['mean'],1);cov=covariance(p['latent_covariance'],len(mean))
        require(mean.shape==weights.shape,'linear performance reward weights')
        var=float(weights@cov@weights);require(var>=-EPS,'nonnegative reward variance')
        scores.append(float(weights@mean)+float(beta)*math.sqrt(max(0.,var)))
    return int(np.argmax(scores)),scores


def plain(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [plain(v) for v in value]
    return value


def digest(value):return hashlib.sha256(json.dumps(plain(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class FeedbackSession:
    """Software ordering contract only; a future host must authenticate receipts.

    Predicted covariance matches current-weight scoring, without adding Q.
    Updating with the saved basis adds Q exactly once when feedback completes.
    Neither a small covariance nor this session is a task/safety certificate.
    """
    def __init__(self,mean,cov,process_cov,measurement_cov,*,completed_steps=0):
        self.mean=array(mean,1);self.cov=covariance(cov,len(self.mean));self.Q=covariance(process_cov,len(self.mean))
        r=array(measurement_cov,2);self.R=covariance(r,r.shape[0],positive=True)
        require(type(completed_steps) is int and 0<=completed_steps<500,'actual starting budget')
        self.completed_steps=completed_steps;self.version=0;self.pending=None;self.closed=False

    def declare(self,bases,*,completed_steps,evaluation_steps,reward_weights,beta,public_query_sha256):
        require(not self.closed and self.pending is None,'live session without pending feedback')
        require(type(completed_steps) is int and completed_steps==self.completed_steps and type(evaluation_steps) is int and 1<=evaluation_steps<=500-completed_steps,'actual budget before evaluation')
        require(isinstance(public_query_sha256,str) and len(public_query_sha256)==64 and all(x in '0123456789abcdef' for x in public_query_sha256),'public query digest')
        h=array(bases,3);require(h.shape==(4,len(self.R),len(self.mean)),'all four legal candidate bases in frozen order')
        predictions=[forecast(self.mean,self.cov,x,self.R) for x in h];index,scores=choose(predictions,reward_weights,beta)
        record=plain(dict(schema='OCCAM_PERFORMANCE_DECLARATION_V1',version=self.version,at_calls=completed_steps,
            evaluation_steps=evaluation_steps,public_query_sha256=public_query_sha256,rates=RATES,selected_index=index,
            selected_rate=RATES[index],predictions=predictions,bases=h,scores=scores,beta=beta,reward_weights=reward_weights,
            state_sha256=digest([self.mean,self.cov,self.Q,self.R])))
        record['declaration_sha256']=digest(record);self.pending=deepcopy(record);return deepcopy(record)

    def complete(self,declared,*,completed_steps,observed_performance,executed_rate):
        require(self.pending is not None and digest(declared)==digest(self.pending),'unchanged unconsumed declaration required')
        p=self.pending
        require(type(completed_steps) is int and completed_steps==p['at_calls']+p['evaluation_steps'] and executed_rate==p['selected_rate'],'completed factual window and actual declared gain')
        require(p['version']==self.version and p['state_sha256']==digest([self.mean,self.cov,self.Q,self.R]),'stale model state')
        result=update(self.mean,self.cov,p['bases'][p['selected_index']],observed_performance,self.Q,self.R)
        self.mean=result['mean'];self.cov=result['covariance'];self.completed_steps=completed_steps;self.version+=1;self.pending=None
        return plain(dict(schema='OCCAM_PERFORMANCE_FEEDBACK_V1',declaration_sha256=p['declaration_sha256'],completed_steps=completed_steps,
            version=self.version,posterior=result,no_physical_execution_proved_by_this_record=True))

    def end_partial(self,declared,*,completed_steps,reason):
        require(self.pending is not None and digest(declared)==digest(self.pending),'unchanged pending declaration')
        p=self.pending
        require(type(completed_steps) is int and p['at_calls']<=completed_steps<p['at_calls']+p['evaluation_steps'] and reason in ('SUCCESS','TERMINATED','TRUNCATED','HOST_FAILURE'),'explicit actual short-window stop')
        self.completed_steps=completed_steps;self.pending=None;self.closed=True
        return dict(status='NO_UPDATE_PARTIAL_WINDOW',reason=reason,completed_steps=completed_steps,model_version=self.version)


def basis_forward(saved,history,descriptor):
    require(type(saved) is dict and set(saved)=={'schema','dimensions','encoder','head','prior'}
        and saved['schema']=='OCCAM_PERFORMANCE_BASIS_V1','strict exported basis without oracle/extra fields')
    d=saved['dimensions'];require(set(d)=={'history','descriptor','outputs','bases'},'basis dimensions')
    require(all(type(v) is int and v>0 for v in d.values()) and type(saved['prior']) is dict
        and set(saved['prior'])=={'mean','covariance','process_covariance','measurement_covariance'},'strict learned prior, no private metadata')
    h=array(history,2);x=array(descriptor,2)
    require(h.shape==(len(x),d['history']) and x.shape[1]==d['descriptor'],'saved feature dimensions')
    def forward(value,layers):
        require(type(layers) is list and layers,'nonempty affine/ReLU basis')
        for i,layer in enumerate(layers):
            require(type(layer) is dict and set(layer)=={'weight','bias'},'strict affine layer')
            w=array(layer['weight'],2);b=array(layer['bias'],1)
            require(w.shape==(len(b),value.shape[1]),'affine dimensions')
            value=value@w.T+b
            if i<len(layers)-1:value=np.maximum(value,0.)
        return value
    context=forward(h,saved['encoder']);value=forward(np.c_[x,context],saved['head'])
    require(value.shape==(len(x),d['outputs']*d['bases']),'output basis shape')
    return value.reshape(len(x),d['outputs'],d['bases'])
