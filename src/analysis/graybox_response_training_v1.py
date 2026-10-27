"""Fit declared standard references only on new audited NOMINAL and TRAIN."""
from pathlib import Path
from time import perf_counter_ns
from collections import Counter
import json
import numpy as np
from src.analysis import graybox_response_io_v1 as a
from src.probe import graybox_observer_v1 as observer,graybox_arx_reference_v1 as arx
from src.probe.graybox_packet_query_v1 import validate
from src.probe.paired_packet_model_v1 import design
io=a.io

def families(path,split):
    folder=Path(path).parent/split.lower();audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED','audited public paired sources')
    for n,h in audit['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'unchanged public source '+n)
    cases=iter(io.rows(folder/'cases.jsonl.gz'));exports=iter(io.rows(folder/'public_trajectories.jsonl.gz'));rows=[]
    for i in range(len(a.population(split))//3):
        trio=[next(cases) for _ in a.ROLES];tt=[next(exports) for _ in a.ROLES];base=trio[0]
        io.require([c['packet_kind'] for c in trio]==list(a.ROLES) and all(a.family_key(c)==a.family_key(base) for c in trio),'actual ordered matched family')
        q=None if base['forecast_record'] is None else base['forecast_record']['query']
        if q is not None:validate(q)
        positions={};lengths={}
        for role,c,t in zip(a.ROLES,trio,tt):
            io.require(io.digest(t)==c['public_trajectory_sha256'],'actual public source hash');start=c['entry_at_calls']
            part=[] if start is None else t['steps'][start:start+c['packet_steps']]
            positions[role]=[r['after']['observation'][:2] for r in part];lengths[role]=len(part);io.require(len(part)==c['packet_steps'],'actual endpoints only')
        rows.append(dict(family_index=i,group=base['group'],task=base['task'],context=base['context'],boundary=base['boundary'],acquisition_action=base['acquisition_action'],
            query=q,packet_positions_xy=positions,packet_lengths=lengths,complete_three_role_H16=all(n==16 for n in lengths.values()),
            reasons={r:c['reason'] for r,c in zip(a.ROLES,trio)},saved_forecast=base['forecast_record']))
    io.require(next(cases,None) is None and next(exports,None) is None,'complete allocated paired sources');return rows

def nominal(path):
    root=Path(path).parent/'nominal';audit=io.read(root/'audit.json');io.require(audit['integrity']=='PASSED' and audit['nominal_contract']=='PASSED','nominal source availability gate')
    for n,h in audit['artifact_sha256'].items():io.require(io.sha(root/n)==h,'unchanged nominal source '+n)
    cases=list(io.rows(root/'cases.jsonl.gz'));exports=list(io.rows(root/'public_trajectories.jsonl.gz'));io.require(len(cases)==len(exports)==27,'all27 nominal records')
    data=[]
    for c,t,spec in zip(cases,exports,a.population('NOMINAL')):
        io.require(all(c[k]==v for k,v in spec.items()) and io.digest(t)==c['public_trajectory_sha256'],'nominal source ownership')
        trace=dict(initial_xy=t['initial']['observation'][:2],steps=[dict(at_calls=r['at_calls'],command=r['command'],after_xy=r['after']['observation'][:2]) for r in t['steps']])
        if trace['steps']:observer.validate_trace(trace)
        data.append(dict(group=spec['group'],task=spec['task'],trace=trace))
    return data

def systems(rows,task,kind):
    selected=[f for f in rows if f['task']==task and f['complete_three_role_H16']];groups=Counter(f['group'] for f in selected)
    io.require(len(selected)>=12 and len(groups)>=3,'paired TRAIN task availability')
    x=[];y=[];w=[]
    for f in selected:
        for left,right in (('ZERO','PLUS'),('ZERO','MINUS'),('PLUS','MINUS')):
            delta=np.array(f['query']['packets'][right])[:,:2]-np.array(f['query']['packets'][left])[:,:2]
            for h in range(1,17):
                x.append(design(delta,h,kind));y.append((np.array(f['packet_positions_xy'][right][h-1])-f['packet_positions_xy'][left][h-1])/.01)
                w.append(1/(len(groups)*groups[f['group']]*3*16))
    return np.array(x),np.array(y),np.array(w)

def linear_fit(x,y,w,counter):
    scale=np.sqrt(np.sum(w[:,None]*x*x,axis=0));scale[scale==0]=1.;z=x/scale
    counter['ridge_solve_attempts']=counter.get('ridge_solve_attempts',0)+1
    coef=np.linalg.solve(z.T@(w[:,None]*z)+.001*np.eye(x.shape[1]),z.T@(w[:,None]*y))
    return dict(scale=scale.tolist(),coef=coef.tolist())

def fit_data(nominal_rows,paired_rows,save=None,counter=None):
    counter={} if counter is None else counter;complete=[r for r in paired_rows if r['complete_three_role_H16']]
    io.require(set(r['group'] for r in complete)==set(range(9)),'all9 actual TRAIN groups retained')
    bank=dict(protocol='GRAYBOX_RESPONSE_MODELS_V1',by_task={},q_choices=list(a.Q_CHOICES),selected_q_index=None);metadata={}
    def event(kind,task,model):
        if save is not None:save(kind,dict(task=task,model=model))
    for task in io.TASKS:
        nn=[r for r in nominal_rows if r['task']==task];io.require(len(nn)==9 and {r['group'] for r in nn}==set(range(9)) and sum(len(r['trace']['steps'])>=40 for r in nn)>=6,'all nominal groups, minimum long traces')
        traces=[r['trace'] for r in nn if r['trace']['steps']];event('FIT_INTENT',task,'NOMINAL_GRID');fitted=observer.fit_nominal_grid(traces,ledger=counter);event('FIT_COMPLETE',task,'NOMINAL_GRID')
        fitted['zero_length_source_groups']=[r['group'] for r in nn if not r['trace']['steps']]
        fitted['RLS_short_history_source_groups']=[r['group'] for r in nn if len(r['trace']['steps'])<3]
        models=dict(PLANTS=fitted['plants']);metadata[task]=fitted
        event('FIT_INTENT',task,'RLS_ARX');models['RLS_ARX']=arx.fit([t for t in traces if len(t['steps'])>=3],ledger=counter);event('FIT_COMPLETE',task,'RLS_ARX')
        for kind in ('INSTANT','FIR'):
            event('FIT_INTENT',task,kind);models[kind]=linear_fit(*systems(paired_rows,task,kind),counter);event('FIT_COMPLETE',task,kind)
        bank['by_task'][task]=models
    return bank,metadata

def training_family_export(rows):
    # FIR labels need actual role positions and known input plans, not public state histories.
    return [{k:v for k,v in f.items() if k not in ('query','saved_forecast')}|dict(query=None if f['query'] is None else {'packets':f['query']['packets']}) for f in rows]

def train(path):
    from src.analysis.release_learning_guard_v1 import read_only
    a.checked(path);out=Path(path).parent/'training';out.mkdir(exist_ok=False);start=perf_counter_ns();guard={};counter={}
    try:
        with read_only(guard,max_solve=9),(out/'fit_journal.jsonl').open('x',encoding='utf8',newline='\n') as journal:
            nominal_rows=nominal(path);paired=families(path,'TRAIN');io.write(out/'public_nominal_traces.json',nominal_rows);io.write(out/'public_train_families.json',training_family_export(paired))
            def save(kind,payload):journal.write(json.dumps(dict(event=kind,monotonic_ns=perf_counter_ns(),**payload))+'\n');journal.flush()
            bank,metadata=fit_data(nominal_rows,paired,save,counter)
            io.require(counter['nominal_grid_candidate_evaluations']==27 and counter['ridge_solve_attempts']==9,'declared finite training systems')
            io.write(out/'models.json',dict(bank=bank,nominal_fit_metadata=metadata,training_counts=counter,manifest_id=io.read(path)['manifest_id']))
        value=dict(integrity='TRAINED_FOR_INDEPENDENT_AUDIT',models_sha256=io.sha(out/'models.json'),actual_counts=counter,guard=guard,wall_ns=perf_counter_ns()-start,
            primary_ridge_systems=9,nominal_grid_candidates=27,neural_updates=0,online_LLM_API_calls=0,physical_or_control_qualification=False)
        io.write(out/'completion.json',value);return value
    except BaseException as ex:
        io.write(out/'failure.json',dict(integrity='FAILED',type=type(ex).__name__,message=str(ex),actual_counts=counter,guard=guard,wall_ns=perf_counter_ns()-start));raise

def audit_training(path):
    from src.analysis.graybox_response_training_audit_v1 import audit
    return audit(path)
