"""Public input tensors for an untrained receiver prototype.

Padding is explicitly masked, never interpreted as fabricated displacement.
Feature definitions alone are neither a trained policy nor qualification.
"""
import math
from dataclasses import asdict
import numpy as np
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.information_release_v1 import ACTIONS,REASONS,validate_view,memory,observations
from src.probe.task_passive_pi_v1 import require

TASKS=('push-v3','reach-v3','door-open-v3')
PHASES=('VALIDATION_TASK','REPOSITION','MEASUREMENT')
COMMON_SIZE=123
STEP_SIZE=86
MAX_STEPS=72


def memory_features(saved):
    m=memory(saved);c=m.current;base=m.base()
    return [m.completed_steps/500,*c.observation,float(c.terminated),float(c.truncated),float(c.success),
        *[n for row in base['matrix_xy'] for n in row],*base['offset'],*m.integral_xy,math.log2(m.time_constant_s)]


def encode(view):
    before,_=validate_view(view);c=view['common']
    common=[float(t==before.task) for t in TASKS]+memory_features(c['before_memory'])+memory_features(c['post_memory'])
    common.extend(float(a==c['action']) for a in ACTIONS)
    common.append(c['paid_acquisition_steps']/72)
    common.extend(c['phase_counts'].get(p,0)/(64 if p=='REPOSITION' else 8) for p in PHASES)
    common.extend(float(r==c['reason']) for r in REASONS)
    trace=np.zeros((MAX_STEPS,STEP_SIZE),np.float64);mask=np.zeros(MAX_STEPS,bool)
    for i,s in enumerate(view['signal'] or ()):
        trace[i]=[s['at_calls']/500,*s['command'],*s['before']['observation'],*s['after']['observation'],
            *[float(p==s['phase']) for p in PHASES]]
        mask[i]=True
    common=np.asarray(common,np.float64)
    require(common.shape==(COMMON_SIZE,) and np.isfinite(common).all() and np.isfinite(trace).all(),'finite registered public receiver tensors')
    # No record identity, exposure bit, RNG draw, receiver hash, oracle or result.
    return dict(common=common,trace=trace,trace_mask=mask)


def pre_acquisition_features(current_memory,completed_history):
    """Only already completed real history; no after-acquisition endpoint input."""
    m=memory(current_memory);require(type(completed_history) in (tuple,list),'actual prior history')
    require(len(completed_history)==m.completed_steps,'complete real prefix, no made-up oldest history')
    previous=None
    for i,s in enumerate(completed_history):
        require(type(s) is dict and set(s)=={'at_calls','command','before','after'},'no private, future or extra prefix data')
        require(type(s['at_calls']) is int and s['at_calls']==i,'prefix excludes current/future command')
        b=observations(s['before']);a=observations(s['after'])
        require(type(s['command']) in (list,tuple) and len(s['command'])==4,'actual public prefix command')
        from src.probe.information_release_v1 import numeric
        for n in s['command']:numeric(n,-1,1)
        require(previous is None or previous==b,'consecutive actual prefix observations')
        require(not any(b[k] for k in ('success','terminated','truncated')),'no prefix step after end')
        previous=a
    if previous is not None:require(previous==observations(normalize(asdict(m.current))),'prefix endpoint differs from actual current memory')
    return dict(schema='PRE_ACQUISITION_PUBLIC_HISTORY_V1',memory=normalize(m.to_dict()),completed_history=normalize(completed_history))
