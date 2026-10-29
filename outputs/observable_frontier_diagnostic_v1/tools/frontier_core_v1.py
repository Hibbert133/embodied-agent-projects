"""Empirical future-label optimization, deliberately not a deployable learner."""
from collections import defaultdict
import hashlib
import json
import math

NODE_KEYS={'schema','stage','task','completed_steps','current','integral_xy','controller','history','acquisition_action'}
TASKS=('push-v3','reach-v3','door-open-v3')
NAMES=('UNIT_CLAIRVOYANT','ROOT_CONTINUE_ONLY','ROOT_STATIC','ROOT_ADAPTIVE_FULL','ROOT_ADAPTIVE_MASK','GLOBAL_FIXED_BEST',
       *('FIXED_'+str(i).zfill(2) for i in range(12)))


def need(ok,msg):
    if not ok:raise ValueError(msg)


def finite_tree(v):
    if type(v) is float:need(math.isfinite(v),'finite public scalar')
    elif type(v) is dict:
        for k,x in v.items():need(type(k) is str,'string key');finite_tree(x)
    elif type(v) is list:
        for x in v:finite_tree(x)
    else:need(v is None or type(v) in (str,bool,int),'plain public values')


def node(v,stage):
    need(type(v) is dict and set(v)==NODE_KEYS,'strict public node; reject private/future fields')
    need(v['schema']=='COMPLETE_RISK_PUBLIC_NODE_V1' and v['stage']==stage and v['task'] in TASKS,'public stage/task')
    n=v['completed_steps'];need(type(n) is int and 0<n<=500 and len(v['history'])==n,'actual full history')
    need(set(v['current'])=={'observation','terminated','truncated','success'} and len(v['current']['observation'])==39,'current public state')
    need(all(type(v['current'][k]) is bool and not v['current'][k] for k in ('terminated','truncated','success')),'nonterminal decision node')
    need(v['controller']==dict(source='UNCORRECTED',matrix_xy=[[1.,0.],[0.,1.]],offset=[0.,0.,0.,0.]),'known original controller')
    need(len(v['integral_xy'])==2,'real integral')
    need(v['acquisition_action'] is None if stage=='PRE' else v['acquisition_action'] in ('CONTINUE','VALIDATE8','MOVE_MEASURE'),'known acquisition')
    for i,r in enumerate(v['history']):
        need(set(r)=={'at_calls','before','command','after'} and r['at_calls']==i and len(r['command'])==4,'real history structure')
        for state in (r['before'],r['after']):
            need(set(state)=={'observation','terminated','truncated','success'} and len(state['observation'])==39,'history state schema')
            need(all(type(state[k]) is bool for k in ('terminated','truncated','success')),'history flags')
        need(not any(r['before'][k] for k in ('terminated','truncated','success')),'no steps after terminal')
        need(i==0 or r['before']==v['history'][i-1]['after'],'public continuity')
    need(v['history'][-1]['after']==v['current'],'actual current follows history');finite_tree(v)


def serialize(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
def first(values):return min(range(len(values)),key=lambda j:(values[j],j))


def validate(graphs):
    seen=set()
    for i,g in enumerate(graphs):
        u=g['unit'];need(len(u)==4 and u[0]=='TRAIN' and tuple(u) not in seen,'unique TRAIN unit');seen.add(tuple(u))
        need(len(g['leaves'])==12 and len(g['returns'])==3,'all factual branches')
        for q in g['leaves']:
            need(type(q['loss']) is int and type(q['steps']) is int and type(q['success']) is bool and q['loss']==(q['steps'] if q['success'] else 500),'actual full loss')
        if g['pre'] is None:
            need(all(v is None for v in g['returns']) and len({(q['loss'],q['steps'],q['success']) for q in g['leaves']})==1,'early completion has no decisions')
        else:
            node(g['pre'],'PRE');need(g['pre']['task']==u[2] and g['pre']['completed_steps']==g['boundary'],'root source')
            for a,v in enumerate(g['returns']):
                if v is None:need(len({(q['loss'],q['steps'],q['success']) for q in g['leaves'][4*a:4*a+4]})==1,'terminal acquisition no tail')
                else:
                    node(v,'RETURN');need(v['task']==u[2] and v['acquisition_action']==('CONTINUE','VALIDATE8','MOVE_MEASURE')[a],'actual return action')
                    n=g['pre']['completed_steps'];need(v['history'][:n]==g['pre']['history'],'real prefix preserved')
                    if a==0:need(v['history']==g['pre']['history'] and v['current']==g['pre']['current'] and v['integral_xy']==g['pre']['integral_xy'],'zero-cost CONTINUE')


def return_key(g,a,mode):
    v=g['returns'][a]
    if v is None:return None
    payload=v if mode=='FULL' else {k:v[k] for k in NODE_KEYS-{'history'}}
    return serialize(dict(root=g['pre'],returned=payload))


def solve(graphs):
    validate(graphs);roots=defaultdict(list)
    choices={n:{} for n in NAMES};panels=[];classes=[];argmin_tables=0;candidate_values=0
    for i,g in enumerate(graphs):
        if g['pre'] is not None:roots[serialize(g['pre'])].append(i)
    def assign(name,indices,a,r):
        for i in indices:choices[name][i]=(a,r)
    global_index=first([sum(g['leaves'][j]['loss'] for g in graphs) for j in range(12)])
    argmin_tables+=1;candidate_values+=12
    for i,g in enumerate(graphs):
        if g['pre'] is None:
            for n in NAMES:choices[n][i]=(None,None)
        else:
            j=first([q['loss'] for q in g['leaves']]);choices['UNIT_CLAIRVOYANT'][i]=(j//4,None if g['returns'][j//4] is None else j%4)
            choices['GLOBAL_FIXED_BEST'][i]=(global_index//4,None if g['returns'][global_index//4] is None else global_index%4)
            for j in range(12):choices['FIXED_'+str(j).zfill(2)][i]=(j//4,None if g['returns'][j//4] is None else j%4)
            argmin_tables+=1;candidate_values+=12
    for root_bytes,indices in roots.items():
        identity=hashlib.sha256(root_bytes).hexdigest();classes.append(dict(root_sha256=identity,members=indices,public_bytes=len(root_bytes)))
        totals=[sum(graphs[i]['leaves'][j]['loss'] for i in indices) for j in range(12)]
        for name,allowed in [('ROOT_CONTINUE_ONLY',range(4)),('ROOT_STATIC',range(12))]:
            j=min(allowed,key=lambda j:(totals[j],j));argmin_tables+=1;candidate_values+=len(allowed)
            for i in indices:choices[name][i]=(j//4,None if graphs[i]['returns'][j//4] is None else j%4)
        for mode in ('FULL','MASK'):
            plans=[]
            for a in range(3):
                parts=defaultdict(list);mapping={};terminal=[];total=0
                for i in indices:
                    key=return_key(graphs[i],a,mode)
                    if key is None:terminal.append(i);mapping[i]=(a,None);total+=graphs[i]['leaves'][4*a]['loss']
                    else:parts[key].append(i)
                return_classes=[]
                for b,members in parts.items():
                    costs=[sum(graphs[i]['leaves'][4*a+r]['loss'] for i in members) for r in range(4)]
                    r=first(costs);argmin_tables+=1;candidate_values+=4;total+=costs[r]
                    for i in members:mapping[i]=(a,r)
                    return_classes.append(dict(return_sha256=hashlib.sha256(b).hexdigest(),members=members,selected_rate_index=r,cost_sums=costs))
                plans.append((total,mapping));panels.append(dict(root_sha256=identity,mode=mode,acquisition_index=a,
                    members=indices,terminal_members=terminal,return_classes=return_classes,total_loss=total))
            a=first([q[0] for q in plans]);choices['ROOT_ADAPTIVE_'+mode].update(plans[a][1]);argmin_tables+=1;candidate_values+=3
    records=[];totals={}
    for name in NAMES:
        total=0
        for i,g in enumerate(graphs):
            a,rate=choices[name][i];leaf=0 if a is None else 4*a+(rate or 0);q=g['leaves'][leaf];total+=q['loss']
            records.append(dict(functional=name,unit_index=i,chosen_acquisition_index=a,rate_index=rate,
                factual_leaf_index=leaf,loss=q['loss'],success=q['success'],source_case_key=q['source_case_key'],source_case_sha256=q['source_case_sha256'],
                uses_future_labels=True,deployable=False,new_robot_execution=False))
        totals[name]=total
    need(totals['UNIT_CLAIRVOYANT']<=totals['ROOT_ADAPTIVE_FULL']<=totals['ROOT_ADAPTIVE_MASK']<=totals['ROOT_STATIC']<=totals['GLOBAL_FIXED_BEST'],'finite empirical information ordering')
    need(totals['ROOT_STATIC']<=totals['ROOT_CONTINUE_ONLY'],'static menu contains CONTINUE')
    return dict(records=records,root_classes=classes,return_panels=panels,totals=totals,global_fixed_index=global_index,
        optimization_ledger=dict(argmin_tables=argmin_tables,candidate_cost_values=candidate_values),all_optimizations_use_future_labels=True)
