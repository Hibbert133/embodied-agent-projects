"""Public paired one-step command-effect features. Not a plant inverse."""
from copy import deepcopy
import numpy as np
from src.probe.correction_scope_model_v1 import public_state
from src.probe.task_passive_pi_v1 import require

KINDS=('GLOBAL_SCALAR','GLOBAL_MATRIX','ABSOLUTE_CONTEXT','PAIRED_CONTEXT')
COMPARATORS=('ZERO_EFFECT','NOMINAL_SENT',*KINDS)
INPUT_KEYS={'completed_steps','current','history2','command_a','command_b'}


def command(value):
    u=np.asarray(value,np.float32)
    require(u.shape==(4,) and np.isfinite(u).all() and np.max(abs(u))<=1,'bounded public sent command')
    require(u.astype(float).tolist()==list(value),'saved float32 command values');return u.astype(float)


def features(packet):
    require(type(packet) is dict and set(packet)==INPUT_KEYS,'strict public paired input, no identity/private/future fields')
    current=public_state(packet['current']);require(not any(current[k] for k in ('success','terminated','truncated')),'live common state')
    require(type(packet['completed_steps']) is int and 2<=packet['completed_steps']<500,'two actually completed history steps')
    h=packet['history2'];require(type(h) is list and len(h)==2,'two actually observed transitions, no invented initial displacement')
    deltas=[];previous=None
    for index,row in enumerate(h):
        require(type(row) is dict and set(row)=={'at_calls','before','command','after'} and row['at_calls']==packet['completed_steps']-2+index,'strict chronological public history row')
        public_state(row['before']);public_state(row['after']);command(row['command'])
        require(not any(row['before'][k] for k in ('success','terminated','truncated')),'history after task end')
        if previous is not None:require(previous==row['before'],'history continuity')
        previous=row['after'];deltas.extend((np.asarray(row['after']['observation'][:3])-np.asarray(row['before']['observation'][:3]))/.01)
    require(previous==current,'history includes future or stale current')
    ua,ub=command(packet['command_a']),command(packet['command_b'])
    require(ua[2:].tobytes()==ub[2:].tobytes(),'rate interventions change XY only')
    o=np.asarray(current['observation'],float)
    phi=np.r_[1.,o[:3],o[4:7]-o[:3],o[3],deltas,ua[2:]]
    require(phi.shape==(16,) and np.isfinite(phi).all(),'fixed16 public physical-context features')
    return phi,ua[:2],ub[:2]


def design(packet,kind):
    phi,a,b=features(packet)
    if kind=='GLOBAL_MATRIX':return b-a
    if kind=='PAIRED_CONTEXT':return np.outer(phi,b-a).ravel()
    if kind=='ABSOLUTE_CONTEXT':return np.stack([np.r_[phi,np.outer(phi,u).ravel()] for u in (a,b)])
    require(kind=='GLOBAL_SCALAR','registered effect model');return b-a


def predict(saved,packet):
    kind=saved['kind'];require(kind in COMPARATORS,'known effect model')
    phi,a,b=features(packet)
    if kind=='ZERO_EFFECT':return [0.,0.]
    if kind=='NOMINAL_SENT':return (b-a).tolist()
    x=design(packet,kind);scale=np.asarray(saved['scale'],float);coef=np.asarray(saved['coef'],float)
    if kind=='GLOBAL_SCALAR':return ((b-a)*float(coef[0][0])/float(scale[0])).tolist()
    if kind=='ABSOLUTE_CONTEXT':x=x[1]-x[0]
    answer=x/scale@coef;require(answer.shape==(2,) and np.isfinite(answer).all(),'finite effect only')
    return answer.tolist()
