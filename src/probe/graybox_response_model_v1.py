"""Same-data standard response references; never chooses physical commands."""
from copy import deepcopy
import numpy as np
from src.probe import graybox_observer_v1 as observer,graybox_arx_reference_v1 as arx
from src.probe.graybox_packet_query_v1 import validate,nominal_trace,PAIRS,ROLES,TASKS
from src.probe.paired_packet_model_v1 import design,linear
require=observer.require;Q_CHOICES=(0.,.001,.01);BASELINES=('ZERO','INSTANT','FIR','RLS_ARX','GRAY_FIXED');SELECTED='GRAY_JOINT'

def methods(bank):
    require(bank['q_choices']==list(Q_CHOICES),'declared process choices')
    j=bank['selected_q_index'];require(j is None or type(j) is int and 0<=j<3,'locked CAL choice')
    return (*BASELINES,*(['GRAY_Q0','GRAY_Q1','GRAY_Q2'] if j is None else [SELECTED]))

def gray_positions(plants,trace,packets,q_parameter,fixed=False,counter=None):
    model=observer.Observer(trace['initial_xy'],plants,q_parameter=q_parameter)
    if fixed:
        # Identity is the ablation's assumption, never a claim about unknown truth.
        for b in model.beliefs:
            p=np.array(b['covariance']);p[3:,:]=0.;p[:,3:]=0.;b['covariance']=p.tolist()
    for row in trace['steps']:
        plan=model.plan(row['command'],row['at_calls'],counter);model.consume(plan,row['after_xy'],row['at_calls']+1,counter)
    positions={role:[r['position_xy'] for r in model.forecast(packets[role],counter)] for role in ROLES}
    return positions

def contrasts(positions):
    answer={}
    for left,right in PAIRS:
        delta=np.asarray(positions[right],float)-np.asarray(positions[left],float)
        require(delta.shape==(16,2) and np.isfinite(delta).all(),'finite actual-plan contrast prediction')
        answer[left+'__'+right]=delta.tolist()
    return answer

def predict(bank,query,counter=None):
    q=validate(query);require(type(bank) is dict and set(bank)=={'protocol','by_task','q_choices','selected_q_index'} and bank['protocol']=='GRAYBOX_RESPONSE_MODELS_V1','strict standard bank')
    require(set(bank['by_task'])==set(TASKS),'all task models');models=bank['by_task'][q['task']]
    require(set(models)=={'INSTANT','FIR','RLS_ARX','PLANTS'},'all strong references and two nominal plants')
    trace=nominal_trace(q);result={};errors={}
    for method in methods(bank):
        if counter is not None:counter['method_attempts']=counter.get('method_attempts',0)+1
        try:
            if method in ('ZERO','INSTANT','FIR'):
                value={}
                for left,right in PAIRS:
                    du=np.array(q['packets'][right])[:,:2]-np.array(q['packets'][left])[:,:2];rows=[]
                    for h in range(1,17):
                        rows.append([0.,0.] if method=='ZERO' else (.01*linear(models[method],design(du,h,method))).tolist())
                        if counter is not None:
                            key='zero_rows' if method=='ZERO' else 'linear_rows';counter[key]=counter.get(key,0)+1
                    value[left+'__'+right]=rows
            elif method=='RLS_ARX':value=contrasts(arx.forecast(models['RLS_ARX'],trace,q['packets'],counter))
            else:
                fixed=method=='GRAY_FIXED';j=bank['selected_q_index'] if method==SELECTED else int(method[-1]) if not fixed else None
                value=contrasts(gray_positions(models['PLANTS'],trace,q['packets'],0. if fixed else Q_CHOICES[j],fixed,counter))
            require(set(value)=={l+'__'+r for l,r in PAIRS} and all(np.asarray(v).shape==(16,2) and np.isfinite(v).all() for v in value.values()),'complete finite saved model output')
            result[method]=deepcopy(value)
            if counter is not None:counter['methods_completed']=counter.get('methods_completed',0)+1
        except Exception as ex:errors[method]=dict(type=type(ex).__name__,message=str(ex))
    require(set(result)|set(errors)==set(methods(bank)) and not set(result)&set(errors),'every method predicted or explicitly failed')
    return result,errors
