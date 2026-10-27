"""Strict current public history and three fully declared future command packets."""
from copy import deepcopy
import numpy as np
from src.probe.correction_scope_model_v1 import public_state
from src.probe.task_passive_pi_v1 import require
ROLES=('ZERO','PLUS','MINUS');PAIRS=(('ZERO','PLUS'),('ZERO','MINUS'),('PLUS','MINUS'))
KEYS={'schema','task','at_calls','acquisition_action','current','history','integral_carried_xy','packets'}
TASKS=('push-v3','reach-v3','door-open-v3')

def command(value):
    require(type(value) is list and len(value)==4 and all(type(x) in (int,float) for x in value),'four ordinary command values')
    u=np.asarray(value,np.float32);require(np.isfinite(u).all() and np.max(abs(u))<=1 and u.astype(float).tolist()==value,'exact bounded saved float32 command')
    return u.astype(float)

def validate(value):
    require(type(value) is dict and set(value)==KEYS and value['schema']=='PAIRED_PACKET_QUERY_V1','strict public paired query; no identity/oracle/future response fields')
    require(value['task'] in TASKS and type(value['at_calls']) is int and 24<=value['at_calls']<=136 and value['acquisition_action'] in ('IN_TASK','MOVE'),'registered actual entry')
    current=public_state(value['current']);require(not any(current[k] for k in ('success','terminated','truncated')),'live measured current state')
    history=value['history'];require(type(history) is list and len(history)==16,'sixteen actually completed public transitions')
    previous=None
    for j,row in enumerate(history):
        require(type(row) is dict and set(row)=={'at_calls','before','command','after'} and row['at_calls']==value['at_calls']-16+j,'no invented/omitted/future history')
        public_state(row['before']);public_state(row['after']);command(row['command'])
        require(not any(row['before'][k] or row['after'][k] for k in ('success','terminated','truncated')),'no terminal or future history at a live entry')
        if previous is not None:require(previous==row['before'],'contiguous actual history')
        previous=row['after']
    require(previous==current,'history must end at actual forecast state')
    integral=value['integral_carried_xy'];require(type(integral) is list and len(integral)==2 and all(type(x) in (int,float) and np.isfinite(x) and abs(x)<=2 for x in integral),'public carried task integral')
    packets=value['packets'];require(type(packets) is dict and set(packets)==set(ROLES),'all three future programs declared')
    arrays={}
    for role in ROLES:
        require(type(packets[role]) is list and len(packets[role])==16,'complete known sixteen-step packet')
        arrays[role]=np.asarray([command(u) for u in packets[role]])
        require(np.array_equal(arrays[role][:,2:],np.zeros((16,2))),'preserve zero Z and gripper packet inputs')
    require(np.array_equal(arrays['ZERO'],np.zeros((16,4))) and np.array_equal(arrays['PLUS'][:,:2],-arrays['MINUS'][:,:2]),'symmetric independently declared input family')
    require(np.max(abs(arrays['PLUS'][:,:2]))<=float(np.float32(.4)),'frozen packet amplitude')
    return deepcopy(value)

def make(task,at_calls,action,current,rows,integral,packets):
    return validate(dict(schema='PAIRED_PACKET_QUERY_V1',task=task,at_calls=at_calls,acquisition_action=action,current=deepcopy(current),history=deepcopy(rows[-16:]),
        integral_carried_xy=list(integral),packets=deepcopy(packets)))

def contrast(query,pair):
    value=validate(query);require(pair in PAIRS,'registered directed command pair')
    return np.asarray(value['packets'][pair[1]],float)[:,:2]-np.asarray(value['packets'][pair[0]],float)[:,:2]
