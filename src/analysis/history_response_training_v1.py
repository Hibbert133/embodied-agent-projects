"""Train public-context response references on the fresh TRAIN population only."""
from pathlib import Path
from time import perf_counter_ns
from collections import Counter
import json
import numpy as np
from src.analysis import history_response_io_v1 as a
from src.probe.history_response_model_v1 import descriptor, METHODS, UNIT, RIDGE, NEIGHBOURS
from src.probe.paired_packet_model_v1 import design
from src.probe.paired_packet_query_v1 import validate, ROLES
io=a.io


def families(path,split):
    folder=Path(path).parent/split.lower();audit=io.read(folder/'audit.json')
    io.require(audit['integrity']=='PASSED','audited complete physical records before public reading')
    for n,h in audit['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'unchanged audited '+n)
    cases=iter(io.rows(folder/'cases.jsonl.gz'));exports=iter(io.rows(folder/'public_trajectories.jsonl.gz'));answer=[]
    for i in range(len(a.population(split))//3):
        trio=[next(cases) for _ in ROLES];traces=[next(exports) for _ in ROLES];base=trio[0]
        io.require([c['packet_kind'] for c in trio]==list(ROLES) and all(a.family_key(c)==a.family_key(base) for c in trio),'ordered actual family')
        q=base['forecast_record']['query'] if base['forecast_record'] is not None else None
        if q is not None:validate(q)
        positions={};lengths={}
        for role,c,t in zip(ROLES,trio,traces):
            io.require(c['public_trajectory_sha256']==io.digest(t),'public source hash')
            start=c['entry_at_calls'];rows=[] if start is None else t['steps'][start:start+c['packet_steps']]
            positions[role]=[r['after']['observation'][:2] for r in rows];lengths[role]=len(rows)
            io.require(lengths[role]==c['packet_steps'],'no invented endpoint or terminal continuation')
        answer.append(dict(family_index=i,group=base['group'],task=base['task'],context=base['context'],boundary=base['boundary'],
            acquisition_action=base['acquisition_action'],query=q,packet_positions_xy=positions,packet_lengths=lengths,
            complete_three_role_H16=all(n==16 for n in lengths.values()),reasons={r:c['reason'] for r,c in zip(ROLES,trio)},saved_forecast=base['forecast_record']))
    io.require(next(cases,None) is None and next(exports,None) is None,'all allocated public records registered')
    return answer


def dataset(rows,task,kind='FIR',indices=None):
    selected=[f for f in rows if f['task']==task and f['complete_three_role_H16']]
    if indices is not None:selected=[selected[int(i)] for i in indices]
    groups=Counter(f['group'] for f in selected);io.require(groups,'nonempty actual TRAIN selection')
    x=[];y=[];w=[];fi=[]
    for i,f in enumerate(selected):
        u=np.asarray(f['query']['packets']['PLUS'],float)[:,:2]
        for h in range(1,17):
            x.append(design(u,h,kind));y.append((np.asarray(f['packet_positions_xy']['PLUS'][h-1])-np.asarray(f['packet_positions_xy']['MINUS'][h-1]))/(2*UNIT))
            w.append(1/(len(groups)*groups[f['group']]*16));fi.append(i)
    return selected,np.asarray(x),np.asarray(y),np.asarray(w),np.asarray(fi,int)


def input_scale(x,w):
    scale=np.sqrt(np.sum(w[:,None]*x*x,axis=0));scale[scale==0]=1
    return scale


def linear_fit(x,y,w,scale=None):
    scale=input_scale(x,w) if scale is None else np.asarray(scale,float)
    z=x/scale
    coef=np.linalg.solve(z.T@(w[:,None]*z)+RIDGE*np.eye(x.shape[1]),z.T@(w[:,None]*y))
    return dict(input_scale=scale.tolist(),coef=coef.tolist())


def context_bank(selected,kind):
    c=np.asarray([descriptor(f['query'],kind) for f in selected]);groups=Counter(f['group'] for f in selected)
    weights=np.asarray([1/(len(groups)*groups[f['group']]) for f in selected])
    center=np.sum(weights[:,None]*c,axis=0);constant=np.ptp(c,axis=0)==0;center[constant]=c[0,constant]
    scale=np.sqrt(np.sum(weights[:,None]*(c-center)**2,axis=0));scale[constant | (scale==0)]=1
    return center,scale,(c-center)/scale


def kernel_fit(selected,x,y,w,fi,kind):
    scale=input_scale(x,w);z=x/scale;center,cs,c=context_bank(selected,kind)
    d=np.sum((c[:,None,:]-c[None,:,:])**2,axis=2)/c.shape[1];kc=np.exp(-.5*d)
    sw=np.sqrt(w);kernel=(z@z.T)*kc[fi[:,None],fi[None,:]]
    dual=np.linalg.solve(sw[:,None]*kernel*sw[None,:]+RIDGE*np.eye(len(w)),sw[:,None]*y)
    components=np.asarray([z[fi==i].T@(sw[fi==i,None]*dual[fi==i]) for i in range(len(selected))])
    return dict(input_scale=scale.tolist(),center=center.tolist(),context_scale=cs.tolist(),contexts=c.tolist(),coefficients=components.tolist())


def fit(rows,save=None):
    complete=[f for f in rows if f['complete_three_role_H16']]
    io.require(set(f['group'] for f in complete)==set(range(9)),'all nine TRAIN groups retained')
    bank=dict(protocol='HISTORY_RESPONSE_MODELS_V1',by_task={})
    def one(task,kind,entry,center=None):
        if save is not None:save('FIT_INTENT',dict(task=task,kind=kind,center_index=center))
        result=entry()
        if save is not None:save('FIT_COMPLETE',dict(task=task,kind=kind,center_index=center))
        return result
    for task in io.TASKS:
        selected,x,y,w,fi=dataset(rows,task)
        io.require(len(selected)>=12 and len(set(f['group'] for f in selected))>=3,'TRAIN task availability, no favourable task selection')
        _,xi,yi,wi,_=dataset(rows,task,'INSTANT')
        models={}
        models['INSTANT']=one(task,'INSTANT',lambda:linear_fit(xi,yi,wi))
        models['FIR']=one(task,'FIR',lambda:linear_fit(x,y,w))
        for method,kind in (('STATE_KERNEL','STATE'),('HISTORY_KERNEL','HISTORY')):
            models[method]=one(task,method,lambda kind=kind:kernel_fit(selected,x,y,w,fi,kind))
        center,cs,c=context_bank(selected,'HISTORY');distance=np.sum((c[:,None,:]-c[None,:,:])**2,axis=2)/153
        scale=np.asarray(models['FIR']['input_scale']);coefs=[]
        for i in range(len(selected)):
            ids=np.argsort(distance[i],kind='stable')[:NEIGHBOURS]
            _,xx,yy,ww,_=dataset(rows,task,indices=ids)
            fitted=one(task,'HISTORY_NN',lambda:linear_fit(xx,yy,ww,scale),i);coefs.append(fitted['coef'])
        models['HISTORY_NN']=dict(input_scale=scale.tolist(),center=center.tolist(),context_scale=cs.tolist(),contexts=c.tolist(),coefficients=coefs)
        bank['by_task'][task]=models
    return bank


def train(path):
    from src.analysis.release_learning_guard_v1 import read_only
    start=perf_counter_ns();a.checked(path);out=Path(path).parent/'training';out.mkdir(exist_ok=False);receipt={}
    try:
        with (out/'fit_journal.jsonl').open('x',encoding='utf8',newline='\n') as journal,read_only(receipt,max_solve=120):
            data=families(path,'TRAIN')
            def save(kind,payload):journal.write(json.dumps(dict(event=kind,monotonic_ns=perf_counter_ns(),**payload),allow_nan=False)+'\n');journal.flush()
            bank=fit(data,save)
    except BaseException as ex:
        io.write(out/'failure.json',dict(error=dict(type=type(ex).__name__,message=str(ex)),receipt=receipt,wall_ns=perf_counter_ns()-start));raise
    public=[{k:v for k,v in f.items() if k!='saved_forecast'} for f in data]
    io.write(out/'public_train_families.json',public)
    count=12+sum(f['complete_three_role_H16'] for f in data)
    io.require(receipt['operation_counts']['solve_attempts']==count,'exact scientific solve accounting')
    io.write(out/'models.json',dict(bank=bank,manifest_id=io.read(path)['manifest_id'],training_families_sha256=io.sha(out/'public_train_families.json'),
        classification='STANDARD_CONTEXT_MODULATED_KNOWN_COMMAND_RESPONSE_NOT_ACQUISITION_OR_INVERSE',scientific_ridge_systems=count,receipt=receipt))
    result=dict(integrity='TRAINED_FOR_INDEPENDENT_AUDIT',models_sha256=io.sha(out/'models.json'),public_train_families_sha256=io.sha(out/'public_train_families.json'),
        families=len(public),complete_families=sum(f['complete_three_role_H16'] for f in public),scientific_ridge_systems=count,receipt=receipt,wall_ns=perf_counter_ns()-start)
    io.write(out/'training_receipt.json',result);return result


def audit_training(path):
    from unittest.mock import patch
    from src.analysis import history_response_independent_math_v1 as literal
    from src.probe import history_response_model_v1 as production
    from src.analysis.release_learning_guard_v1 import read_only
    from src.analysis.response_action_audit_v1 import same
    start=perf_counter_ns();a.checked(path);root=Path(path).parent;out=root/'training';done=io.read(out/'training_receipt.json');bank=io.read(out/'models.json')['bank'];guard={};counter={}
    same(done['models_sha256'],io.sha(out/'models.json'));same(done['public_train_families_sha256'],io.sha(out/'public_train_families.json'))
    data=io.read(out/'public_train_families.json')
    def denied(*args,**kw):raise RuntimeError('production fit/features/predictor/reader disabled in independent numerical audit')
    with read_only(guard,max_lstsq=114),patch(__name__+'.fit',denied),patch(__name__+'.families',denied),patch(__name__+'.descriptor',denied),patch(__name__+'.design',denied),patch(__name__+'.linear_fit',denied),patch(__name__+'.kernel_fit',denied),patch(__name__+'.context_bank',denied),patch.object(production,'descriptor',denied),patch.object(production,'predict',denied):
        expected_data=literal.read_training(path);same(data,expected_data,'independent actual public TRAIN reader, no private labels')
        expected=literal.refit(expected_data,counter)
        maximum=literal.compare_models(bank,expected)
        literal_predictions={f['family_index']:literal.evaluate(bank,f['query']) for f in data if f['query'] is not None}
    complete=sum(f['complete_three_role_H16'] for f in data)
    same(counter,dict(augmented_lstsq=6+complete,symmetric_eigendecompositions=6),'exact independent fit accounting')
    same(guard['operation_counts']['lstsq_attempts'],6+complete)
    prediction_error=0.;verification_guard={}
    with read_only(verification_guard):
        for f in data:
            if f['query'] is None:continue
            main=production.predict(bank,f['query']);other=literal_predictions[f['family_index']]
            for kind in METHODS:
                for pair in main[kind]:
                    error=float(np.max(np.abs(np.asarray(main[kind][pair])-np.asarray(other[kind][pair]))));prediction_error=max(prediction_error,error)
                    io.require(np.allclose(main[kind][pair],other[kind][pair],atol=1e-10,rtol=1e-8),'literal saved-context forecast')
    result=dict(integrity='PASSED',models_sha256=io.sha(out/'models.json'),public_train_families_sha256=io.sha(out/'public_train_families.json'),
        independent_numerical_counts=counter,max_coefficient_difference=maximum,max_prediction_difference_m=prediction_error,
        training_bank_checks=len(literal_predictions),main_training_bank_forecast_rows=288*len(literal_predictions),literal_training_bank_forecast_rows=288*len(literal_predictions),
        receipt=guard,main_bank_verification_guard=verification_guard,wall_ns=perf_counter_ns()-start,online_LLM_API_calls=0,new_environment_steps=0)
    io.write(out/'audit.json',result);return result
