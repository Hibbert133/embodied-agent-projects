"""NumPy, float64 auxiliary-risk network; explicit analytic derivatives.

Ranking scores are not probabilities or safety bounds. No plant/control model
is fitted here. Training budgets are charged by the caller, not hidden in SGD.
"""
import numpy as np

VARIANTS=('DIRECT_MSE','DIRECT_SPO','EMPIRICAL_REWEIGHT_SPO','CONDITIONAL_SPO','JOINT_SPO')
PARAMS=('w1','b1','w2','b2','wr','br')


def softmax(x):
    e=np.exp(x-np.max(x,axis=-1,keepdims=True));return e/e.sum(axis=-1,keepdims=True)


def sigmoid(x):return np.exp(-np.logaddexp(0.,-x))


def initialize(dim,seed,hidden=16):
    r=np.random.default_rng(seed)
    return dict(w1=r.normal(0,.03,(dim,hidden)),b1=np.zeros(hidden),
        w2=r.normal(0,.03,(hidden,200)),b2=np.zeros(200),
        wr=r.normal(0,.03,(dim+204,4)),br=np.zeros(4))


def forward(parameters,phi,historical,known,gamma,variant):
    assert variant in VARIANTS and gamma>=.05
    a=parameters;h=np.tanh(phi@a['w1']+a['b1'])
    raw=(h@a['w2']+a['b2']).reshape(-1,4,50)
    p=softmax(raw[:,:,:24]);v=raw[:,:,24:48]
    g=np.logaddexp(0.,raw[:,:,48:49])*gamma;l=sigmoid(raw[:,:,49:50])
    if variant=='EMPIRICAL_REWEIGHT_SPO':
        j=p*historical[:,None,:];g=j.sum(2,keepdims=True);s=None
    elif variant=='CONDITIONAL_SPO':
        s=np.logaddexp(0.,v);j=g*p*s/(p*s).sum(2,keepdims=True)
    else:s=softmax(v);j=s*g
    missing=(p*(1-known[:,None,:])).sum(2,keepdims=True)
    features=np.concatenate((p,j/gamma,g/gamma,l,missing),axis=2)
    design=np.concatenate((phi,features.reshape(len(phi),204)),axis=1)
    scores=design@a['wr']+a['br']
    assert np.isfinite(scores).all()
    return dict(scores=scores,p=p,j=j,g=g,length=l,missing=missing,
        raw=raw,s=s,h=h,design=design)


def objective(parameters,data,variant,*,ridge=.01,gradient=True):
    phi,hist,known,cost,y,w,gamma=(data[k] for k in ('phi','historical','known','cost','target','weights','gamma'))
    z=forward(parameters,phi,hist,known,gamma,variant);score=z['scores'];n=len(phi)
    if variant=='DIRECT_MSE':
        risk=((score-cost)**2).mean(1);ds=(score-cost)*w[:,None]/2
    else:
        best=np.argmin(cost,axis=1);worst=np.argmax(cost-2*score,axis=1);ix=np.arange(n)
        risk=(cost-2*score)[ix,worst]+2*score[ix,best]-cost[ix,best]
        ds=np.zeros_like(score);ds[ix,best]+=2*w;ds[ix,worst]-=2*w
    loss=float(w@risk);dp=np.zeros_like(z['p']);dj=np.zeros_like(z['j'])
    dg=np.zeros_like(z['g']);dl=np.zeros_like(z['length']);de=None
    if variant not in ('DIRECT_MSE','DIRECT_SPO'):
        factor=w[:,None,None]/4;pt,jt,gt,lt=y[:,:,:24],y[:,:,24:48],y[:,:,48:49],y[:,:,49:50]
        loss+=float(np.sum(factor*(z['p']-pt)**2)+np.sum(factor*(z['length']-lt)**2))
        dp+=2*factor*(z['p']-pt);dl+=2*factor*(z['length']-lt)
        if variant!='EMPIRICAL_REWEIGHT_SPO':
            loss+=float(np.sum(factor*((z['g']-gt)/gamma)**2));dg+=2*factor*(z['g']-gt)/gamma**2
            if variant=='JOINT_SPO':
                loss+=float(np.sum(factor*((z['j']-jt)/gamma)**2));dj+=2*factor*(z['j']-jt)/gamma**2
            else:
                # A never-visited bin has no conditional-error label. The
                # numeric zero in this temporary array is always masked by pt.
                true=np.divide(jt,pt,out=np.zeros_like(jt),where=pt>0)
                conditional=z['g']*z['s']/(z['p']*z['s']).sum(2,keepdims=True)
                loss+=float(np.sum(factor*pt*((conditional-true)/gamma)**2))
                de=2*factor*pt*(conditional-true)/gamma**2
    loss+=ridge/2*sum(float(np.sum(parameters[k]**2)) for k in PARAMS)
    assert np.isfinite(loss)
    if not gradient:return loss,z
    grads=dict(wr=z['design'].T@ds,br=ds.sum(0))
    df=(ds@parameters['wr'].T)[:,phi.shape[1]:].reshape(n,4,51)
    dp+=df[:,:,:24];dj+=df[:,:,24:48]/gamma;dg+=df[:,:,48:49]/gamma;dl+=df[:,:,49:50]
    dp+=df[:,:,50:51]*(1-known[:,None,:])
    draw=np.zeros_like(z['raw'])
    if variant=='EMPIRICAL_REWEIGHT_SPO':dp+=(dj+dg)*hist[:,None,:]
    elif variant=='CONDITIONAL_SPO':
        p,s,g=z['p'],z['s'],z['g'];t=(p*s).sum(2,keepdims=True);q=p*s/t
        dv=g/t*(dj-(dj*q).sum(2,keepdims=True));dg+=(dj*q).sum(2,keepdims=True)
        dpos=dv*p;dp+=dv*s
        if de is not None:
            dg+=(de*s/t).sum(2,keepdims=True);dpos+=de*g/t
            dt=-(de*g*s).sum(2,keepdims=True)/t**2;dpos+=dt*p;dp+=dt*s
        draw[:,:,24:48]=dpos*sigmoid(z['raw'][:,:,24:48])
        draw[:,:,48:49]=dg*gamma*sigmoid(z['raw'][:,:,48:49])
    else:
        dsj=dj*z['g'];draw[:,:,24:48]=z['s']*(dsj-(dsj*z['s']).sum(2,keepdims=True))
        dg+=(dj*z['s']).sum(2,keepdims=True);draw[:,:,48:49]=dg*gamma*sigmoid(z['raw'][:,:,48:49])
    draw[:,:,:24]=z['p']*(dp-(dp*z['p']).sum(2,keepdims=True))
    draw[:,:,49:50]=dl*z['length']*(1-z['length']);flat=draw.reshape(n,200)
    grads['w2']=z['h'].T@flat;grads['b2']=flat.sum(0)
    dh=(flat@parameters['w2'].T)*(1-z['h']**2)
    grads['w1']=phi.T@dh;grads['b1']=dh.sum(0)
    grads={k:grads[k]+ridge*parameters[k] for k in PARAMS}
    assert all(np.isfinite(g).all() for g in grads.values())
    return loss,grads,z


def fit(data,variant,seed,steps,*,learning_rate=.01,clip=10.,ridge=.01,ledger=None):
    if ledger is None:raise ValueError('explicit neural fit/update ledger required')
    ledger['fit_attempts']=ledger.get('fit_attempts',0)+1
    a=initialize(data['phi'].shape[1],seed);trace=[];clipped=0
    for step in range(steps):
        value,g,_=objective(a,data,variant,ridge=ridge)
        norm=np.sqrt(sum(float(np.sum(x*x)) for x in g.values()));scale=min(1.,clip/max(norm,1e-300))
        clipped+=int(scale<1)
        for k in PARAMS:a[k]-=learning_rate*scale*g[k]
        ledger['optimizer_steps']=ledger.get('optimizer_steps',0)+1
        if step%100==0 or step==steps-1:trace.append(dict(before_update=step,loss=value,gradient_norm=float(norm),gradient_clipped=bool(scale<1)))
    final,_=objective(a,data,variant,ridge=ridge,gradient=False)
    return a,dict(trace=trace,final_loss=final,clipped_updates=clipped,optimizer_steps=steps)
