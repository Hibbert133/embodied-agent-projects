"""Strict public causal training projection and mask-preserving TRAIN statistics.

Completed future rows are labels, never history inputs at an earlier decision.
Registry/oracle fields live outside this schema and are not feature columns.
"""
from copy import deepcopy
import numpy as np
from src.probe.occam_performance_core_v1 import require,digest,basis_forward,covariance
from src.probe.occam_public_history_v1 import features,state,TASKS
from src.probe.occam_window_cost_v1 import measure,ended


def project(value):
    require(type(value) is dict and set(value)=={'schema','task','initial','history','windows'}
        and value['schema']=='OCCAM_PUBLIC_TRAIN_TRAJECTORY_V1','public training fields only')
    task=value['task'];state(value['initial']);require(task in TASKS,'known task')
    rows=value['history'];require(type(rows) is list and 0<len(rows)<=500,'complete actual episode')
    current=value['initial']
    for i,row in enumerate(rows):
        require(type(row) is dict and set(row)=={'at_calls','before','command','after'} and row['at_calls']==i
            and row['before']==current and not ended(current),'complete consecutive true history')
        state(row['after']);u=np.asarray(row['command'],float)
        require(u.shape==(4,) and np.isfinite(u).all() and max(abs(u))<=1
            and np.array_equal(u,u.astype(np.float32).astype(float)),'actual float32 sends')
        current=row['after']
    require(ended(current) or len(rows)==500,'complete terminal episode, not a truncated file')
    require(type(value['windows']) is list,'actual windows')
    hs=[];xs=[];ys=[];full=[];terminal=[];previous=None
    for item in value['windows']:
        require(type(item) is dict and set(item)=={'query','selected_rate','measurement'},'public decision and observed label only')
        q=deepcopy(item['query']);n=q['completed_steps'];require(q['task']==task and q['initial']==value['initial']
            and q['history']==rows[:n] and (previous is None or n==previous),'no future/omitted/reused decision input')
        q['candidate_time_constant_s']=item['selected_rate'];h,x=features(q,8)
        m=item['measurement'];require(type(m) is dict,'actual window receipt')
        stop=m['end_at'];require(type(stop) is int and n<stop<=len(rows),'actual nonempty window label')
        before=value['initial'] if n==0 else rows[n-1]['after']
        expected=measure(task,n,before,rows[n:stop],q['evaluation_steps'])
        require(set(m)==set(expected),'strict complete observed cost fields')
        for field in expected:
            if field in ('cost','potential_before','potential_after'):
                require(type(m[field]) in (int,float) and abs(m[field]-expected[field])<=1e-12,'recomputed public scalar cost differs')
            else:require(digest(m[field])==digest(expected[field]),'recomputed public cost receipt differs '+field)
        # Preserve the immutable saved label across NumPy runtimes; only
        # recomputation tolerance, never an error/utility decision threshold.
        hs.append(h);xs.append(x);ys.append([m['cost']]);full.append(expected['full_window']);terminal.append(expected['terminal']);previous=stop
    if previous is not None:require(previous==len(rows),'all actual tail windows, no selected prefix')
    return dict(task=task,history=np.asarray(hs,float).reshape(-1,664),descriptor=np.asarray(xs,float).reshape(-1,87),
        targets=np.asarray(ys,float).reshape(-1,1),full_window=np.asarray(full,bool),terminal=np.asarray(terminal,bool),
        missing_reason='EARLY_END_BEFORE_PERFORMANCE_WINDOW' if not hs else None)


def weighted_stats(sequences):
    require(type(sequences) is list and sequences,'TRAIN public sequences, including empty episodes')
    usable=[s for s in sequences if len(s['targets'])];require(usable,'TRAIN contains no observed windows')
    # Equal episode mass, then equal observed windows; empty episodes have no
    # invented feature/target. Availability remains in the population denominator.
    xsum=np.zeros(87);x2=np.zeros(87);ysum=ysq=0.;hm=np.zeros(82);h2=np.zeros(82);mass=0.
    for s in usable:
        H=s['history'].reshape(-1,8,83);X=s['descriptor'];Y=s['targets'];n=len(Y)
        require(len(H)==len(X)==n and np.isfinite(H).all() and np.isfinite(X).all() and np.isfinite(Y).all(),'finite TRAIN arrays')
        w=1./len(usable)/n;xsum+=w*X.sum(0);x2+=w*(X*X).sum(0);ysum+=w*Y.sum();ysq+=w*(Y*Y).sum()
        for window in H:
            mask=window[:,82];require(np.isin(mask,[0.,1.]).all() and not np.any(window[mask==0]),'zero padded rows and explicit mask')
            actual=window[mask==1,:82]
            if len(actual):
                z=w/len(actual);hm+=z*actual.sum(0);h2+=z*(actual*actual).sum(0);mass+=w
    require(mass>0,'some real history, no fabricated initial displacement')
    hm/=mass;h2/=mass
    def sd(second,mean):
        var=second-mean*mean;require(var.min()>=-1e-10,'finite nonnegative TRAIN variance');return np.maximum(np.sqrt(np.maximum(var,0)),.05)
    xs=sd(x2,xsum);hs=sd(h2,hm);ys=float(sd(np.array([ysq]),np.array([ysum]))[0])
    xsum[80:83]=0.;xs[80:83]=1. # Preserve known task indicators.
    return dict(schema='OCCAM_TRAIN_NORMALIZATION_V1',history_mean=hm.tolist(),history_scale=hs.tolist(),
        descriptor_mean=xsum.tolist(),descriptor_scale=xs.tolist(),target_mean=float(ysum),target_scale=ys,
        episodes=len(sequences),nonempty_episodes=len(usable),fit_source='TRAIN_ONLY_EQUAL_EPISODE_THEN_WINDOW',scale_floor=.05)


def normalize(stats,H,X,Y=None):
    require(type(stats) is dict and set(stats)=={'schema','history_mean','history_scale','descriptor_mean','descriptor_scale',
        'target_mean','target_scale','episodes','nonempty_episodes','fit_source','scale_floor'}
        and stats['schema']=='OCCAM_TRAIN_NORMALIZATION_V1' and stats['fit_source']=='TRAIN_ONLY_EQUAL_EPISODE_THEN_WINDOW','strict TRAIN normalization')
    h=np.array(H,float,copy=True);x=np.array(X,float,copy=True);require(h.ndim==x.ndim==2 and h.shape==(len(x),664) and x.shape[1]==87
        and np.isfinite(h).all() and np.isfinite(x).all(),'finite raw public feature dimensions')
    hm=np.asarray(stats['history_mean']);hs=np.asarray(stats['history_scale']);xm=np.asarray(stats['descriptor_mean']);xs=np.asarray(stats['descriptor_scale'])
    require(hm.shape==hs.shape==(82,) and xm.shape==xs.shape==(87,) and np.isfinite(np.r_[hm,hs,xm,xs,stats['target_mean'],stats['target_scale']]).all()
        and min(hs)>=.05 and min(xs)>=.05 and stats['target_scale']>=.05,'finite TRAIN location/positive scales')
    z=h.reshape(-1,8,83);mask=z[:,:,82:83].copy();require(np.isin(mask,[0,1]).all() and not np.any(z[mask[:,:,0]==0]),'actual mask with zero padding')
    z[:,:,:82]=(z[:,:,:82]-mask*hm)/hs;x=(x-xm)/xs
    y=None if Y is None else (np.asarray(Y,float)-stats['target_mean'])/stats['target_scale']
    if y is not None:require(y.shape==(len(h),1) and np.isfinite(y).all(),'finite scalar measured targets')
    return h,x,y


def export_raw(normalized_bank,stats):
    """Fold affine feature normalization and scalar output units into strict JSON.

    A zero-variance constant basis restores the target mean without stochastic
    drift. No actor schema change, hidden jitter or runtime training statistics.
    """
    bank=deepcopy(normalized_bank);d=bank['dimensions'];require(d['history']==664 and d['descriptor']==87 and d['outputs']==1,'one public scalar performance output')
    basis_forward(bank,np.zeros((1,664)),np.zeros((1,87)))
    covariance(bank['prior']['covariance'],d['bases']);covariance(bank['prior']['process_covariance'],d['bases'])
    covariance(bank['prior']['measurement_covariance'],1,positive=True)
    normalize(stats,np.zeros((1,664)),np.zeros((1,87)))
    layer=bank['encoder'][0];W=np.asarray(layer['weight'],float);folded=W.copy();hm=np.asarray(stats['history_mean']);hs=np.asarray(stats['history_scale'])
    for r in range(8):
        indices=np.arange(83*r,83*r+82);mask=83*r+82
        folded[:,indices]=W[:,indices]/hs;folded[:,mask]=W[:,mask]-(W[:,indices]/hs)@hm
    layer['weight']=folded.tolist()
    layer=bank['head'][0];W=np.asarray(layer['weight'],float);bias=np.asarray(layer['bias'],float)
    W[:,:87]/=np.asarray(stats['descriptor_scale']);bias-=W[:,:87]@np.asarray(stats['descriptor_mean']);layer['weight']=W.tolist();layer['bias']=bias.tolist()
    last=bank['head'][-1];W=np.asarray(last['weight'],float)*stats['target_scale'];bias=np.asarray(last['bias'],float)*stats['target_scale']
    last['weight']=np.vstack([W,np.zeros((1,W.shape[1]))]).tolist();last['bias']=np.r_[bias,stats['target_mean']].tolist()
    p=bank['prior'];p['mean']=list(p['mean'])+[1.]
    for key in ('covariance','process_covariance'):
        value=np.asarray(p[key],float);p[key]=np.pad(value,((0,1),(0,1))).tolist()
    p['measurement_covariance']=(np.asarray(p['measurement_covariance'])*stats['target_scale']**2).tolist();d['bases']+=1
    return bank
