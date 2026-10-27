"""Exact fixed-policy leaf arithmetic for descriptive functional attribution.

Overriding a leaf evaluates a function at a saved observation. It does not
create a feasible physical state, a command receipt, or a task counterfactual.
"""
import numpy as np

TASKS=('push-v3','reach-v3','door-open-v3')


def require(ok,message):
    if not ok:raise ValueError(message)


def observation(value):
    require(type(value) in (list,tuple,np.ndarray),'ordinary public observation')
    x=np.array(value,dtype=float,copy=True)
    require(x.shape==(39,) and np.isfinite(x).all(),'finite current39 only')
    return x


def signature(task,value):
    x=observation(value);require(task in TASKS,'registered fixed policy')
    hand=x[:3];obj=x[4:7].copy()
    if task=='reach-v3':return (0,0)
    if task=='push-v3':
        target=obj+[-.005,0.,0.]
        position=0 if np.linalg.norm(hand[:2]-target[:2])>.02 else 1 if abs(hand[2]-target[2])>.04 else 2
        grip=int(not (np.linalg.norm(hand[:2]-obj[:2])>.02 or abs(hand[2]-obj[2])>.10))
        return (position,grip)
    obj[0]-=.05
    return (0 if np.linalg.norm(hand[:2]-obj[:2])>.12 else 1 if abs(hand[2]-obj[2])>.04 else 2,1)


def leaf(task,value,mode):
    x=observation(value)
    require(type(mode) in (tuple,list) and len(mode)==2 and all(type(v) is int for v in mode),'literal policy leaf only')
    if task=='reach-v3':
        require(tuple(mode)==(0,0),'reach has no guard');target=x[-3:];gain=5.;grip=0.
    elif task=='push-v3':
        require(mode[0] in (0,1,2) and mode[1] in (0,1),'push leaf')
        obj=x[4:7]+[-.005,0.,0.]
        target=obj+[0.,0.,.2] if mode[0]==0 else obj+[0.,0.,.03] if mode[0]==1 else x[-3:]
        gain=10.;grip=.6*mode[1]
    elif task=='door-open-v3':
        require(mode[0] in (0,1,2) and mode[1]==1,'door leaf')
        obj=x[4:7].copy();obj[0]-=.05
        target=obj+[.06,.02,.2] if mode[0]==0 else obj+[.06,.02,0.] if mode[0]==1 else obj
        gain=25.;grip=1.
    else:raise ValueError('registered task')
    return np.r_[gain*(target-x[:3]),grip].astype(np.float32).astype(float).tolist()


def decompose(task,a,b):
    """Symmetric two-factor decomposition, separately before/after send clipping."""
    ma,mb=signature(task,a),signature(task,b)
    aa=np.asarray(leaf(task,a,ma));ab=np.asarray(leaf(task,b,ma))
    ba=np.asarray(leaf(task,a,mb));bb=np.asarray(leaf(task,b,mb))
    result=dict(mode_a=list(ma),mode_b=list(mb),mode_changed=ma!=mb)
    for name,values in (('raw',(aa,ab,ba,bb)),('sent',(np.clip(v,-1,1) for v in (aa,ab,ba,bb)))):
        fa,ga,fb,gb=values
        delta=gb-fa;mode=.5*((fb-fa)+(gb-ga));state=.5*((ga-fa)+(gb-fb))
        require(np.array_equal(delta,mode+state),'exact rounded-functional decomposition')
        delta,mode,state=(v[2:] for v in (delta,mode,state))
        result[name]=dict(delta_zg=delta.tolist(),mode_zg=mode.tolist(),state_zg=state.tolist(),
            total_energy=float(np.mean(delta**2)),mode_energy=float(np.mean(mode**2)),state_energy=float(np.mean(state**2)),
            cross_energy=float(np.mean(2*mode*state)),total_L1=float(np.mean(abs(delta))),mode_L1=float(np.mean(abs(mode))),state_L1=float(np.mean(abs(state))),
            any_difference=bool(np.any(delta!=0)),mode_nonzero=bool(np.any(mode!=0)),state_nonzero=bool(np.any(state!=0)))
    return result


def summarize(records):
    require(records,'nonempty actual paired window')
    n=len(records);result={'mode_changed_fraction':sum(r['mode_changed'] for r in records)/n}
    for stage in ('raw','sent'):
        for metric in ('total_energy','mode_energy','state_energy','cross_energy','total_L1','mode_L1','state_L1'):
            result[stage+'_'+metric]=sum(r[stage][metric] for r in records)/n
        for metric in ('any_difference','mode_nonzero','state_nonzero'):
            result[stage+'_'+metric+'_fraction']=sum(r[stage][metric] for r in records)/n
        result[stage+'_any_difference_in_window']=any(r[stage]['any_difference'] for r in records)
        require(abs(result[stage+'_total_energy']-sum(result[stage+'_'+m] for m in ('mode_energy','state_energy','cross_energy')))<1e-12,'energy identity')
    return result
