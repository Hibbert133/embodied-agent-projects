"""Frozen standard linear response-contrast training, with separate LS audit."""
from pathlib import Path
from time import perf_counter_ns
from collections import Counter
import json
import numpy as np
from src.analysis import paired_packet_io_v1 as a
from src.probe.paired_packet_model_v1 import design,METHODS,UNIT
from src.probe.paired_packet_query_v1 import validate,PAIRS,ROLES
io=a.io


def families(path,split):
    root=Path(path).parent;folder=root/split.lower();audit=io.read(folder/'audit.json');require=io.require
    require(audit['integrity']=='PASSED','audited complete physical records before public training/evaluation')
    for n,h in audit['artifact_sha256'].items():require(io.sha(folder/n)==h,'unchanged audited '+n)
    cases=iter(io.rows(folder/'cases.jsonl.gz'));public=iter(io.rows(folder/'public_trajectories.jsonl.gz'));answer=[]
    for i in range(len(a.population(split))//3):
        trio=[next(cases) for _ in ROLES];traces=[next(public) for _ in ROLES];base=trio[0]
        require([c['packet_kind'] for c in trio]==list(ROLES) and all(a.family_key(c)==a.family_key(base) for c in trio),'ordered public family')
        q=base['forecast_record']['query'] if base['forecast_record'] is not None else None
        if q is not None:validate(q)
        positions={};available={}
        for role,c,t in zip(ROLES,trio,traces):
            require(c['public_trajectory_sha256']==io.digest(t),'public data SHA')
            start=c['entry_at_calls'];rows=[] if start is None else t['steps'][start:start+c['packet_steps']]
            positions[role]=[r['after']['observation'][:2] for r in rows];available[role]=len(rows)
            require(available[role]==c['packet_steps'],'actual packet length; no invented terminal extension')
        answer.append(dict(family_index=i,group=base['group'],task=base['task'],context=base['context'],boundary=base['boundary'],
            acquisition_action=base['acquisition_action'],query=q,packet_positions_xy=positions,packet_lengths=available,
            complete_three_role_H16=all(n==16 for n in available.values()),reasons={r:c['reason'] for r,c in zip(ROLES,trio)},
            saved_forecast=base['forecast_record']))
    require(next(cases,None) is None and next(public,None) is None,'complete public family population')
    return answer


def arrays(family_rows,task,kind,horizon=None):
    selected=[f for f in family_rows if f['task']==task and f['complete_three_role_H16']]
    groups=Counter(f['group'] for f in selected);io.require(len(groups)>=3 and len(selected)>=12,'registered TRAIN complete family availability')
    xs=[];ys=[];ws=[]
    for f in selected:
        for h in (range(1,17) if horizon is None else [horizon]):
            x={r:design(np.asarray(f['query']['packets'][r])[:,:2],h,kind) for r in ROLES}
            y={r:np.asarray(f['packet_positions_xy'][r][h-1])/UNIT for r in ROLES}
            if kind=='CENTERED_FIR':
                mx=np.mean(list(x.values()),axis=0);my=np.mean(list(y.values()),axis=0);rows=[(x[r]-mx,y[r]-my) for r in ROLES]
            else:rows=[(x[r]-x[l],y[r]-y[l]) for l,r in PAIRS]
            for xx,yy in rows:
                xs.append(xx);ys.append(yy);ws.append(1/(len(groups)*groups[f['group']]*3*(16 if horizon is None else 1)))
    return np.asarray(xs),np.asarray(ys),np.asarray(ws)


def ridge(x,y,w):
    io.require(np.isfinite(x).all() and np.isfinite(y).all() and np.isfinite(w).all() and np.all(w>0),'public finite weighted samples')
    scale=np.sqrt((w[:,None]*x*x).sum(axis=0));scale[scale==0]=1;xx=x/scale
    coef=np.linalg.solve(xx.T@(w[:,None]*xx)+.001*np.eye(x.shape[1]),xx.T@(w[:,None]*y))
    return dict(scale=scale.tolist(),coef=coef.tolist())


def fit(family_rows,save=None):
    io.require(len(set(f['group'] for f in family_rows if f['complete_three_role_H16']))==9,'all nine TRAIN groups represented globally')
    bank=dict(protocol='PAIRED_PACKET_MODELS_V1',by_task={})
    def one(task,kind,h=None):
        if save is not None:save('FIT_INTENT',dict(task=task,kind=kind,horizon=h))
        result=ridge(*arrays(family_rows,task,kind,h))
        if save is not None:save('FIT_COMPLETE',dict(task=task,kind=kind,horizon=h,parameters=result))
        return result
    for task in io.TASKS:
        bank['by_task'][task]={}
        for kind in METHODS[1:]:
            bank['by_task'][task][kind]=[one(task,kind,h) for h in range(1,17)] if kind=='FREE_CAUSAL' else one(task,kind)
    return bank


def train(path):
    start=perf_counter_ns();m=a.checked(path);out=Path(path).parent/'training';out.mkdir(exist_ok=False)
    receipt={}
    from src.analysis.release_learning_guard_v1 import read_only
    try:
        data=families(path,'TRAIN')
        with (out/'fit_journal.jsonl').open('x',encoding='utf8',newline='\n') as log,read_only(receipt,max_solve=57):
            def save(kind,value):log.write(json.dumps(dict(event=kind,**value),allow_nan=False)+'\n');log.flush()
            bank=fit(data,save)
    except BaseException as ex:
        io.write(out/'failure.json',dict(error=dict(type=type(ex).__name__,message=str(ex)),receipt=receipt,wall_ns=perf_counter_ns()-start));raise
    public=[{k:v for k,v in f.items() if k!='saved_forecast'} for f in data]
    io.write(out/'public_train_families.json',public);io.write(out/'models.json',dict(bank=bank,manifest_id=m['manifest_id'],training_families_sha256=io.sha(out/'public_train_families.json'),
        model_classification='STANDARD_RESPONSE_CONTRAST_NOT_ABSOLUTE_PLANT_OR_TASK_UTILITY',scientific_ridge_systems=57,receipt=receipt))
    io.write(out/'training_receipt.json',dict(integrity='TRAINED_FOR_INDEPENDENT_AUDIT',models_sha256=io.sha(out/'models.json'),families=len(public),
        complete_families=sum(f['complete_three_role_H16'] for f in public),public_train_families_sha256=io.sha(out/'public_train_families.json'),wall_ns=perf_counter_ns()-start,receipt=receipt))
    return io.read(out/'training_receipt.json')


def audit_training(path):
    from src.analysis.paired_packet_independent_math_v1 import audit_fits,evaluate
    from src.probe.paired_packet_model_v1 import predict
    from src.analysis.release_learning_guard_v1 import read_only
    start=perf_counter_ns();a.checked(path);out=Path(path).parent/'training';done=io.read(out/'training_receipt.json');bank=io.read(out/'models.json')['bank']
    io.require(done['models_sha256']==io.sha(out/'models.json') and done['public_train_families_sha256']==io.sha(out/'public_train_families.json'),'immutable training artifacts')
    data=io.read(out/'public_train_families.json');expected=[{k:v for k,v in f.items() if k!='saved_forecast'} for f in families(path,'TRAIN')]
    io.require(data==expected,'training dataset contains only actual audited public measurements and commands')
    receipt={};maximum=equivalence=0.;calls=0
    with read_only(receipt,max_lstsq=57):
        numerical=audit_fits(data,bank)
        for f in data:
            if f['query'] is None:continue
            main=predict(bank,f['query']);literal=evaluate(bank,f['query']);calls+=1
            for k in main:
                for pair in main[k]:
                    x=np.asarray(main[k][pair]);y=np.asarray(literal[k][pair]);maximum=max(maximum,float(np.max(abs(x-y))))
                    io.require(np.allclose(x,y,atol=1e-12,rtol=1e-10),'independent literal saved-bank prediction')
                    if k=='FIR':
                        d=float(np.max(abs(x-np.asarray(main['CENTERED_FIR'][pair]))));equivalence=max(equivalence,d)
                        io.require(np.allclose(x,main['CENTERED_FIR'][pair],atol=2e-10,rtol=2e-8),'same-data centered FIR is algebraically equivalent')
    result=dict(integrity='PASSED',models_sha256=io.sha(out/'models.json'),training_families_sha256=io.sha(out/'public_train_families.json'),
        numerical_audit=numerical,training_bank_checks=calls,max_prediction_difference_m=maximum,max_centered_equivalence_difference_m=equivalence,
        receipt=receipt,wall_ns=perf_counter_ns()-start,online_LLM_API_calls=0)
    io.write(out/'audit.json',result);return result
