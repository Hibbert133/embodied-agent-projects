"""Frozen public sequence summaries; no fitted physics model or private context."""
import numpy as np
from src.probe.information_release_features_v1 import encode,pre_acquisition_features,memory_features
from src.probe.task_passive_pi_v1 import require


def summarize(rows):
    if not rows:return [0.]*18
    u=np.asarray([r['command'] for r in rows],float)
    d=np.asarray([np.asarray(r['after']['observation'][:3])-np.asarray(r['before']['observation'][:3]) for r in rows],float)
    cross=np.asarray([[x[i]*y[j] for i in range(2) for j in range(2)] for x,y in zip(u,d)])
    return [*u.mean(0),*u.std(0),*d.mean(0),*d.std(0),*cross.mean(0)]


def before(memory,history):
    checked=pre_acquisition_features(memory,history);task=checked['memory']['task']
    values=[float(t==task) for t in ('push-v3','reach-v3','door-open-v3')]+memory_features(checked['memory'])+summarize(history)+summarize(history[-8:])
    a=np.asarray(values,float);require(a.shape==(93,) and np.isfinite(a).all(),'93 finite pre-acquisition features from actual past only');return a


def after(view,prefix_history):
    prior=before(view['common']['before_memory'],prefix_history)
    common=np.r_[encode(view)['common'],prior[57:]];trace=view['signal'] or []
    signal=[v for p in ('VALIDATION_TASK','REPOSITION','MEASUREMENT') for v in summarize([r for r in trace if r['phase']==p])]
    full=np.concatenate((common,signal));require(common.shape==(159,) and full.shape==(213,) and np.isfinite(full).all(),'159/213 finite public features, equal prior history in both views')
    return common,full,bool(trace)
