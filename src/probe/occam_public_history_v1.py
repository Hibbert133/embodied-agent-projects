"""Strict public causal features; no future performance or registry identifiers."""
from copy import deepcopy
import numpy as np
from src.probe.occam_performance_core_v1 import require,RATES

TASKS=('push-v3','reach-v3','door-open-v3')
KEYS={'schema','task','completed_steps','initial','history','integral_xy','candidate_time_constant_s','evaluation_steps'}
STATE={'observation','success','terminated','truncated'}


def state(value):
    require(type(value) is dict and set(value)==STATE,'public observation and flags only')
    x=np.asarray(value['observation'],dtype=float)
    require(x.shape==(39,) and np.isfinite(x).all() and all(type(value[k]) is bool for k in STATE-{'observation'}),'current39 and literal flags')
    return x


def features(query,history_steps):
    require(type(query) is dict and set(query)==KEYS and query['schema']=='OCCAM_PUBLIC_HISTORY_V1','unknown/private/future input fields')
    q=deepcopy(query);n=q['completed_steps'];h=history_steps
    require(q['task'] in TASKS and type(n) is int and 0<=n<500 and type(h) is int and 1<=h<=500,'registered task/history and budget')
    require(type(q['evaluation_steps']) is int and 1<=q['evaluation_steps']<=500-n,'remaining full evaluation budget')
    require(type(q['candidate_time_constant_s']) in (float,int) and q['candidate_time_constant_s'] in RATES,'registered gain')
    integral=np.asarray(q['integral_xy'],dtype=float);require(integral.shape==(2,) and np.isfinite(integral).all() and max(abs(integral))<=2,'public bounded controller memory')
    initial=state(q['initial']);current=q['initial'];rows=q['history']
    require(type(rows) is list and len(rows)==n,'all actual history, no skipped earliest steps')
    values=[]
    for i,row in enumerate(rows):
        require(type(row) is dict and set(row)=={'at_calls','before','command','after'} and row['at_calls']==i and row['before']==current,'consecutive actual public history')
        before=state(row['before']);after=state(row['after']);u=np.asarray(row['command'],dtype=float)
        require(not any(current[k] for k in STATE-{'observation'}) and u.shape==(4,) and np.isfinite(u).all() and max(abs(u))<=1
            and np.array_equal(u,u.astype(np.float32).astype(float)),'live bounded saved float32 actual command')
        values.append(np.r_[before,u,after,1.]);current=row['after']
    require(not any(current[k] for k in STATE-{'observation'}),'terminal histories cannot request another evaluation')
    matrix=np.zeros((h,83));tail=values[-h:]
    if tail:matrix[-len(tail):]=tail
    descriptor=np.r_[initial,state(current),integral,[float(q['task']==t) for t in TASKS],
        np.log(q['candidate_time_constant_s']/.5),n/500.,q['evaluation_steps']/500.,len(tail)/h]
    require(descriptor.shape==(87,) and np.isfinite(descriptor).all(),'public descriptor87')
    return matrix.reshape(-1),descriptor
