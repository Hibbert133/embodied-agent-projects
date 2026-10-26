"""Independent reverse-mode array engine and functional training audit.

Does not call the main network, loss, gradients, initialization or SGD. NumPy
is a shared numerical dependency, not an independent framework/institution.
"""
import numpy as np


def unbroadcast(g,shape):
    while g.ndim>len(shape):g=g.sum(axis=0)
    for i,d in enumerate(shape):
        if d==1:g=g.sum(axis=i,keepdims=True)
    return g.reshape(shape)


class Array:
    __array_priority__=1000
    def __init__(self,value,edges=()):self.v=np.asarray(value,dtype=np.float64);self.edges=edges;self.g=np.zeros_like(self.v)
    def __add__(self,other):
        b=asarray(other);return Array(self.v+b.v,((self,lambda g:unbroadcast(g,self.v.shape)),(b,lambda g:unbroadcast(g,b.v.shape))))
    __radd__=__add__
    def __neg__(self):return self*-1
    def __sub__(self,other):return self+-asarray(other)
    def __rsub__(self,other):return asarray(other)+-self
    def __mul__(self,other):
        b=asarray(other);return Array(self.v*b.v,((self,lambda g:unbroadcast(g*b.v,self.v.shape)),(b,lambda g:unbroadcast(g*self.v,b.v.shape))))
    __rmul__=__mul__
    def __truediv__(self,other):
        b=asarray(other);return Array(self.v/b.v,((self,lambda g:unbroadcast(g/b.v,self.v.shape)),(b,lambda g:unbroadcast(-g*self.v/b.v**2,b.v.shape))))
    def __matmul__(self,other):
        b=asarray(other);return Array(self.v@b.v,((self,lambda g:g@b.v.T),(b,lambda g:self.v.T@g)))
    def __getitem__(self,key):
        def pull(g):
            a=np.zeros_like(self.v);np.add.at(a,key,g);return a
        return Array(self.v[key],((self,pull),))
    def reshape(self,*shape):return Array(self.v.reshape(*shape),((self,lambda g:g.reshape(self.v.shape)),))
    def sum(self,axis=None,keepdims=False):
        def pull(g):return np.broadcast_to(np.expand_dims(g,axis) if axis is not None and not keepdims else g,self.v.shape)
        return Array(self.v.sum(axis=axis,keepdims=keepdims),((self,pull),))
    def tanh(self):
        v=np.tanh(self.v);return Array(v,((self,lambda g:g*(1-v*v)),))
    def positive(self):
        v=np.logaddexp(self.v,0);s=np.exp(-np.logaddexp(-self.v,0))
        return Array(v,((self,lambda g:g*s),))
    def logistic(self):
        v=np.exp(-np.logaddexp(-self.v,0));return Array(v,((self,lambda g:g*v*(1-v)),))
    def probabilities(self):
        e=np.exp(self.v-self.v.max(-1,keepdims=True));p=e/e.sum(-1,keepdims=True)
        return Array(p,((self,lambda g:p*(g-(g*p).sum(-1,keepdims=True))),))
    def backward(self):
        order=[];seen=set()
        def visit(a):
            if id(a) in seen:return
            seen.add(id(a))
            for parent,_ in a.edges:visit(parent)
            order.append(a)
        visit(self)
        for a in order:a.g=np.zeros_like(a.v)
        self.g=np.ones_like(self.v)
        for a in reversed(order):
            for parent,pull in a.edges:parent.g+=pull(a.g)


def asarray(x):return x if isinstance(x,Array) else Array(x)


def concat(arrays,axis):
    shapes=[a.v.shape[axis] for a in arrays];end=np.cumsum([0,*shapes]);edges=[]
    for i,a in enumerate(arrays):
        key=[slice(None)]*a.v.ndim;key[axis]=slice(end[i],end[i+1]);key=tuple(key)
        edges.append((a,lambda g,key=key:g[key]))
    return Array(np.concatenate([a.v for a in arrays],axis=axis),tuple(edges))


def initial(dim,seed):
    rng=np.random.default_rng(seed)
    return dict(w1=rng.normal(0,.03,(dim,16)),b1=np.zeros(16),w2=rng.normal(0,.03,(16,200)),b2=np.zeros(200),
        wr=rng.normal(0,.03,(dim+204,4)),br=np.zeros(4))


def evaluate(parameters,data,variant,*,ridge=.01,derivatives=True):
    a={k:Array(v) for k,v in parameters.items()};phi=Array(data['phi']);y=data['target'];cost=data['cost'];gamma=data['gamma']
    raw=((phi@a['w1']+a['b1']).tanh()@a['w2']+a['b2']).reshape(-1,4,50)
    p=raw[:,:,:24].probabilities();length=raw[:,:,49:50].logistic();g=raw[:,:,48:49].positive()*gamma
    if variant=='EMPIRICAL_REWEIGHT_SPO':j=p*data['historical'][:,None,:];g=j.sum(2,True)
    elif variant=='CONDITIONAL_SPO':
        positive=raw[:,:,24:48].positive();den=(p*positive).sum(2,True);j=p*positive*g/den
    else:j=raw[:,:,24:48].probabilities()*g
    missing=(p*(1-data['known'][:,None,:])).sum(2,True)
    projected=concat([p,j/gamma,g/gamma,length,missing],2)
    design=concat([phi,projected.reshape(len(y),204)],1);score=design@a['wr']+a['br']
    if variant=='DIRECT_MSE':risk=((score-cost)*(score-cost)).sum(1)/4
    else:
        idx=np.arange(len(y));best=np.argmin(cost,axis=1);worst=np.argmax(cost-2*score.v,axis=1)
        risk=(cost-2*score)[idx,worst]+2*score[idx,best]-cost[idx,best]
    loss=(risk*data['weights']).sum()
    if variant not in ('DIRECT_MSE','DIRECT_SPO'):
        weights=data['weights'][:,None,None]/4
        loss=loss+((p-y[:,:,:24])*(p-y[:,:,:24])*weights).sum()+((length-y[:,:,49:50])*(length-y[:,:,49:50])*weights).sum()
        if variant!='EMPIRICAL_REWEIGHT_SPO':
            e=(g-y[:,:,48:49])/gamma;loss=loss+(e*e*weights).sum()
            if variant=='JOINT_SPO':e=(j-y[:,:,24:48])/gamma;loss=loss+(e*e*weights).sum()
            else:
                t=np.zeros_like(y[:,:,24:48]);np.divide(y[:,:,24:48],y[:,:,:24],out=t,where=y[:,:,:24]>0)
                e=(g*positive/den-t)/gamma;loss=loss+(e*e*y[:,:,:24]*weights).sum()
    for v in a.values():loss=loss+(v*v).sum()*(ridge/2)
    if derivatives:loss.backward()
    return float(loss.v),{k:v.g for k,v in a.items()},dict(scores=score.v,p=p.v,j=j.v,g=g.v,length=length.v,missing=missing.v)


def refit(data,variant,seed,steps,ledger):
    ledger['fit_attempts']=ledger.get('fit_attempts',0)+1;values=initial(data['phi'].shape[1],seed)
    for _ in range(steps):
        _,derivatives,_=evaluate(values,data,variant)
        norm=float(np.sqrt(sum(np.dot(d.ravel(),d.ravel()) for d in derivatives.values())))
        rate=.01*min(1.,10./max(1e-300,norm))
        values={k:v-rate*derivatives[k] for k,v in values.items()};ledger['optimizer_steps']=ledger.get('optimizer_steps',0)+1
    return values
