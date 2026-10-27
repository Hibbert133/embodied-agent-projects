"""Complete causal public history for the joint-observer reference collector.

No environment or model fitting; future packets contain commands, never states.
"""
from copy import deepcopy
import numpy as np
from src.probe.correction_scope_model_v1 import public_state
from src.probe.paired_packet_query_v1 import command,ROLES,PAIRS,TASKS
from src.probe.graybox_observer_v1 import require
KEYS={'schema','task','at_calls','acquisition_action','initial','current','history','integral_carried_xy','packets'}

def validate(value):
    require(type(value) is dict and set(value)==KEYS and value['schema']=='GRAYBOX_PACKET_QUERY_V1','strict complete public query')
    require(value['task'] in TASKS and type(value['at_calls']) is int and 24<=value['at_calls']<=136,'registered physical forecast entry')
    require(value['acquisition_action'] in ('IN_TASK','MOVE'),'registered acquisition')
    initial=public_state(value['initial']);current=public_state(value['current'])
    require(not any(current[k] for k in ('success','terminated','truncated')),'live actual forecast state')
    require(type(value['history']) is list and len(value['history'])==value['at_calls'],'all actual history from the one initial reset')
    previous=initial
    for i,row in enumerate(value['history']):
        require(type(row) is dict and set(row)=={'at_calls','before','command','after'} and type(row['at_calls']) is int and row['at_calls']==i,'no missing, invented or future transition')
        before=public_state(row['before']);after=public_state(row['after']);command(row['command'])
        require(before==previous and not any(before[k] or after[k] for k in ('success','terminated','truncated')),'continuous live actual history')
        previous=after
    require(previous==current,'causal history ends at actual current observation')
    integral=value['integral_carried_xy'];require(type(integral) is list and len(integral)==2 and all(type(v) in (int,float) and np.isfinite(v) and abs(v)<=2 for v in integral),'public carried integral')
    plans=value['packets'];require(type(plans) is dict and set(plans)==set(ROLES),'all three fixed future command plans')
    arrays={}
    for role in ROLES:
        require(type(plans[role]) is list and len(plans[role])==16,'complete known command packet')
        arrays[role]=np.array([command(u) for u in plans[role]])
        require(np.array_equal(arrays[role][:,2:],np.zeros((16,2))),'known XY-only response packet')
    require(np.array_equal(arrays['ZERO'],np.zeros((16,4))) and np.array_equal(arrays['PLUS'][:,:2],-arrays['MINUS'][:,:2]) and np.max(abs(arrays['PLUS'][:,:2]))<=float(np.float32(.4)),'symmetric bounded known packet plans')
    return deepcopy(value)

def make(task,at_calls,action,initial,current,rows,integral,packets):
    return validate(dict(schema='GRAYBOX_PACKET_QUERY_V1',task=task,at_calls=at_calls,acquisition_action=action,
        initial=deepcopy(initial),current=deepcopy(current),history=deepcopy(rows),integral_carried_xy=list(integral),packets=deepcopy(packets)))

def nominal_trace(value):
    q=validate(value)
    return dict(initial_xy=q['initial']['observation'][:2],steps=[dict(at_calls=r['at_calls'],command=r['command'],after_xy=r['after']['observation'][:2]) for r in q['history']])

def project_last16(value):
    """Same information access for unchanged INSTANT/FIR reference code."""
    q=validate(value)
    from src.probe.paired_packet_query_v1 import validate as old_validate
    return old_validate({k:v for k,v in dict(q,schema='PAIRED_PACKET_QUERY_V1',history=q['history'][-16:]).items() if k!='initial'})
