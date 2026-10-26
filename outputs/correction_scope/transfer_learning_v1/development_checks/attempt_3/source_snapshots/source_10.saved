"""Standard complete-risk references on supported, already executed branches.

This is offline development, never an environment host or a novel robot method.
Only TRAIN/CAL from the immutable A1 source may be read by this entry point.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,json,os,subprocess,traceback
import numpy as np
from src.analysis import correction_scope_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
from src.probe import correction_scope_model_v1 as public

io=a.io;ROOT=io.ROOT
BASE=a.BASE/'risk_reference_v1';CONFIG=ROOT/'configs/movement_task/correction_scope_risk_reference_v1.json'
PROTOCOL=ROOT/'docs/protocols/correction_scope_risk_reference_v1_zh.md'
ACTIONS=('CONTINUE','VALIDATE8','MOVE_MEASURE');RATES=(.125,.5,2.,8.)
TASKS=('push-v3','reach-v3','door-open-v3');KINDS=('LINEAR','RBF');HISTORY=500
NODE_KEYS={'schema','stage','task','completed_steps','current','integral_xy','controller','history','acquisition_action'}
MODEL_NAMES=tuple(prefix+'_'+kind for prefix in ('static','post_all','receiver','sequential') for kind in KINDS)
SELECTORS=('CONTINUE_05','TASK_TIME_MEAN','STATIC_LINEAR','STATIC_RBF',
    *tuple(action+'_POST_'+kind for action in ACTIONS for kind in KINDS),'SEQUENTIAL_LINEAR','SEQUENTIAL_RBF')


def digest_array(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()


@contextmanager
def recorded_guard(receipt,failure_path,**limits):
    try:
        with read_only(receipt,**limits):yield
    except BaseException:
        io.write(failure_path,dict(integrity='FAILED',guard=receipt,traceback=traceback.format_exc(),no_automatic_retry=True))
        raise


def validate_node(node):
    io.require(type(node) is dict and set(node)==NODE_KEYS and node['schema']=='COMPLETE_RISK_PUBLIC_NODE_V1','strict public node, no registry/private/future keys')
    io.require(node['stage'] in ('PRE','RETURN'),'node stage')
    action=node['acquisition_action'];io.require(action is None if node['stage']=='PRE' else action in ACTIONS,'known acquisition only')
    memory=dict(schema='TASK_MEMORY_OPTION_V1',task=node['task'],completed_steps=node['completed_steps'],current=node['current'],
        controller=node['controller'],integral_xy=node['integral_xy'],time_constant_s=.5)
    public.validate(dict(schema='CORRECTION_SCOPE_PUBLIC_V1',stage='PRE' if node['stage']=='PRE' else 'POST',memory=memory,
        history=node['history'],acquisition_action=action or 'CONTINUE',time_constant_s=.5))
    io.require(not any(node['current'][k] for k in ('success','terminated','truncated')),'terminal node cannot request a choice')
    return node


def node_from_view(view):
    if view is None:return None
    public.validate(view);m=view['memory'];stage='PRE' if view['stage']=='PRE' else 'RETURN'
    if stage=='PRE':io.require(m['time_constant_s']==.5,'common pre-controller')
    else:io.require(m['time_constant_s']==view['time_constant_s'],'saved zero-duration rate metadata')
    node=dict(schema='COMPLETE_RISK_PUBLIC_NODE_V1',stage=stage,task=m['task'],completed_steps=m['completed_steps'],
        current=deepcopy(m['current']),integral_xy=deepcopy(m['integral_xy']),controller=deepcopy(m['controller']),
        history=deepcopy(view['history']),acquisition_action=None if stage=='PRE' else view['acquisition_action'])
    return validate_node(node)


def features(node):
    validate_node(node)
    head=[float(node['task']==t) for t in TASKS]+list(node['current']['observation'])+list(node['integral_xy'])
    head+=[node['completed_steps']/500.]+[float(node['acquisition_action']==v) for v in ACTIONS]
    x=np.zeros(len(head)+HISTORY*83);x[:len(head)]=head
    for i,r in enumerate(node['history']):
        x[len(head)+83*i:len(head)+83*(i+1)]=[*r['before']['observation'],*r['command'],*r['after']['observation'],1.]
    io.require(x.shape==(41548,) and np.isfinite(x).all(),'all public causal history features')
    return x


def source_bindings(config):
    base=ROOT/config['source_run'];a.checked(base/'manifest.json')
    commit=config['source_result_commit'];paths=[base/'manifest.json',base/'results/statistics.json',base/'results/statistics_audit.json']
    for cohort in ('train','cal'):
        paths.extend(base/cohort/n for n in ('cases.jsonl.gz','examples.jsonl.gz','audit.json','summary.json'))
        paths.extend((a.BASE/'common_state_audit_v1'/f'{cohort}.json',base/'supplemental_audit_v1'/f'{cohort}_semantic_controls.json'))
    result={}
    for p in paths:
        name=p.relative_to(ROOT).as_posix();raw=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        io.require(hashlib.sha256(raw).hexdigest()==io.sha(p),'source Git bytes changed '+name);result[name]=io.sha(p)
    for cohort in ('train','cal'):
        audit=io.read(base/cohort/'audit.json');io.require(audit['integrity']=='PASSED','completed source record audit')
        io.require(io.sha(base/cohort/'cases.jsonl.gz')==audit['collection_sha256']['cases.jsonl.gz'] and
            io.sha(base/cohort/'examples.jsonl.gz')==audit['examples_sha256'],'audited raw source')
        io.require(io.read(a.BASE/'common_state_audit_v1'/f'{cohort}.json')['integrity']=='PASSED','full common-state/memory proof')
        for name,h in audit['collection_sha256'].items():
            p=base/cohort/name;io.require(io.sha(p)==h,'current bytes of audited source '+str(p));result[p.relative_to(ROOT).as_posix()]=h
    return result


def prepare():
    v=io.read(BASE/'freeze_validation/complete.json');io.require(v['integrity']=='PASSED','checked and committed reference freeze')
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean committed sources')
    for n,h in v['source_sha256'].items():
        io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed reference source '+n)
    io.require(not list(BASE.glob('run_*/manifest.json')),'single reference allocation, do not restart')
    config=io.read(CONFIG);bindings=source_bindings(config);head=io.git('rev-parse','HEAD')
    out=BASE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(exist_ok=False)
    m=dict(protocol=config['protocol'],classification=config['classification'],source_git_commit=head,config=config,
        source_sha256=v['source_sha256'],input_sha256=bindings,source_TEST_statistics_read_as_bytes_only=True,
        old_TEST_used_for_training_or_evaluation=False,new_environment_interactions=0,new_online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);io.write(out/'manifest.json',m);return out/'manifest.json'


def checked(path):
    path=Path(path).resolve();m=io.read(path);v=dict(m);mid=v.pop('manifest_id')
    io.require(path.parent.parent==BASE.resolve() and mid==io.digest(v) and m['config']==io.read(CONFIG),'owned frozen reference manifest')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'immutable reference source '+n)
    return m


def assemble_graphs(base,cohort):
    io.require(cohort in ('TRAIN','CAL'),'NATIVE/TEST data are not allowed')
    folder=Path(base)/cohort.lower();cases=list(io.rows(folder/'cases.jsonl.gz'));examples=list(io.rows(folder/'examples.jsonl.gz'))
    expected=a.population(cohort);io.require({a.case_key(r) for r in cases}=={a.case_key(r) for r in expected},'all factual cases')
    views={(a.case_key(r['spec']),r['stage']):r['view'] for r in examples}
    io.require(len(views)==2*len(cases)==len(examples),'each logical input registered once')
    units=defaultdict(dict)
    for c in cases:
        io.require(c['completed'] and c['error'] is None and c['close_error'] is None and c['environment_closed'],'source error retained, not replaced')
        i=ACTIONS.index(c['acquisition_action'])*4+RATES.index(c['time_constant_s']);u=a.unit_key(c)
        io.require(i not in units[u],'unique factual leaf');units[u][i]=c
    graphs=[]
    for u,leaves in sorted(units.items()):
        io.require(set(leaves)==set(range(12)),'complete twelve-branch coverage')
        cs=[leaves[i] for i in range(12)]
        pre=[node_from_view(views[(a.case_key(c),'PRE')]) for c in cs]
        io.require(len({io.digest(n) for n in pre})==1,'identical actual pre history across candidate assignments')
        if pre[0] is not None:io.require(pre[0]['completed_steps']==cs[0]['planned_boundary'],'decision at actual frozen boundary')
        returns=[]
        for ai in range(3):
            values=[node_from_view(views[(a.case_key(cs[4*ai+j]),'POST')]) for j in range(4)]
            io.require(len({io.digest(n) for n in values})==1,'same actual acquisition return before rate metadata')
            if values[0] is None:
                io.require(len({(c['deadline_loss'],c['success'],c['total_steps'],io.digest(c['final_memory'])) for c in cs[4*ai:4*ai+4]})==1,'terminal acquisition cannot invent a tail')
            elif pre[0] is not None:
                node=values[0];io.require(node['history'][:len(pre[0]['history'])]==pre[0]['history'],'returned node must extend the actual prefix')
                if ai==0:io.require(node['history']==pre[0]['history'] and node['current']==pre[0]['current'] and node['integral_xy']==pre[0]['integral_xy'],'CONTINUE has zero physical acquisition')
            returns.append(values[0])
        if pre[0] is None:
            io.require(all(n is None for n in returns) and len({(c['deadline_loss'],c['success'],c['total_steps'],io.digest(c['final_memory'])) for c in cs})==1,'early terminal cannot create decision inputs')
        for c in cs:
            io.require(c['deadline_loss']==(c['total_steps'] if c['success'] else 500),'full loss includes acquisition once')
        graphs.append(dict(unit=list(u),boundary=cs[0]['planned_boundary'],pre=pre[0],returns=returns,
            leaves=[dict(loss=c['deadline_loss'],success=c['success'],steps=c['total_steps'],movement_steps=c['movement_steps'],measurement_steps=c['measurement_steps'],
                source_case_key=list(a.case_key(c)),source_case_sha256=io.digest(c)) for c in cs]))
    io.require(len(graphs)=={'TRAIN':54,'CAL':18}[cohort],'all source units retained')
    return graphs


def kernel(z,centers,kind):
    d=max(1,z.shape[1]);dot=z@centers.T/d
    if kind=='LINEAR':return dot
    io.require(kind=='RBF','registered kernel')
    squared=np.maximum((z*z).sum(1)[:,None]/d+(centers*centers).sum(1)[None,:]/d-2*dot,0.)
    return np.exp(-squared/2)


def fit_model(nodes,targets,groups,kind,path):
    x=np.stack([features(n) for n in nodes]);y=np.asarray(targets,float);g=np.asarray(groups)
    io.require(len(x)==len(y)==len(g)>0 and y.ndim==2 and y.shape[1]>0 and np.isfinite(y).all() and np.min(y)>=0 and np.max(y)<=1,'complete finite normalized supervised training set')
    w=np.array([len(g)/(len(set(groups))*sum(g==v)) for v in g]);mean=np.average(x,axis=0,weights=w)
    active=np.flatnonzero(np.ptp(x,axis=0)>0);scale=np.maximum(np.sqrt(np.average((x[:,active]-mean[active])**2,axis=0,weights=w)),.05)
    z=np.clip((x[:,active]-mean[active])/scale,-10,10);k=kernel(z,z,kind);n=len(z)
    system=np.zeros((n+1,n+1));system[:n,:n]=k+np.diag(.01/w);system[:n,n]=1;system[n,:n]=1
    rhs=np.vstack([y,np.zeros((1,y.shape[1]))]);solution=np.linalg.solve(system,rhs)
    with Path(path).open('xb') as stream:
        np.savez_compressed(stream,active=active,mean=mean[active],scale=scale,centers=z,coefficients=solution[:n],intercept=solution[n])
    return dict(kind=kind,rows=len(nodes),groups=sorted(set(groups)),output_dimensions=y.shape[1],active_features=len(active),
        file=Path(path).name,sha256=io.sha(path),input_sha256=digest_array(x),target_sha256=digest_array(y),weights_sha256=digest_array(w),
        training_group_sequence=list(map(int,groups)),raw_feature_dimensions=x.shape[1],ridge=.01,intercept_unpenalized=True)


def predict(model,folder,node):
    io.require(io.sha(Path(folder)/model['file'])==model['sha256'],'immutable learned reference')
    with np.load(Path(folder)/model['file'],allow_pickle=False) as b:
        x=features(node);z=np.clip((x[b['active']]-b['mean'])/b['scale'],-10,10)
        y=(kernel(z[None,:],b['centers'],model['kind'])@b['coefficients'])[0]+b['intercept']
    io.require(np.isfinite(y).all(),'finite risk prediction');return np.clip(y,0,1).tolist()


def training_rows(name,graphs,models,folder,*,apply_group_split=True):
    prefix,kind=name.rsplit('_',1);nodes=[];ys=[];groups=[];bindings=[]
    io.require(all(g['unit'][0]==('TRAIN' if apply_group_split else 'CAL') for g in graphs),'fixed training versus development cohort')
    for graph in graphs:
        group=graph['unit'][1]
        if apply_group_split and (prefix=='receiver' and group>5 or prefix=='sequential' and group<6):continue
        if prefix in ('post_all','receiver'):
            for ai,node in enumerate(graph['returns']):
                if node is not None:nodes.append(node);ys.append([v['loss']/500 for v in graph['leaves'][4*ai:4*ai+4]]);groups.append(group)
        elif graph['pre'] is not None:
            nodes.append(graph['pre']);groups.append(group)
            if prefix=='static':ys.append([v['loss']/500 for v in graph['leaves']])
            else:
                io.require(prefix=='sequential','registered reference training role');receiver=models['receiver_'+kind];labels=[];rates=[]
                for ai,node in enumerate(graph['returns']):
                    ri=1 if node is None else choice(predict(receiver,folder,node))
                    labels.append(graph['leaves'][4*ai+ri]['loss']/500);rates.append(RATES[ri])
                ys.append(labels);bindings.append(dict(unit=graph['unit'],receiver_sha256=receiver['sha256'],rates=rates,targets=labels))
    return nodes,ys,groups,bindings


def write_rows(path,rows):
    with gzip.open(path,'xt',encoding='utf8',newline='\n') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')


def train(path):
    path=Path(path).resolve();m=checked(path);out=path.parent;folder=out/'models';folder.mkdir(exist_ok=False)
    start=perf_counter_ns();guard={}
    with recorded_guard(guard,out/'training_failure.json',max_solve=8):
        graphs={c:assemble_graphs(ROOT/m['config']['source_run'],c) for c in ('TRAIN','CAL')}
        # CAL branches are registered here only; no CAL outcome enters any fit.
        for c,rows in graphs.items():write_rows(out/(c.lower()+'_graphs.jsonl.gz'),rows)
        models={};receiver_bindings={}
        fit_log=Journal(out/'fit_attempts.jsonl')
        try:
            for name in MODEL_NAMES:
                nodes,targets,groups,bindings=training_rows(name,graphs['TRAIN'],models,folder)
                fit_log.write('FIT_INTENT',dict(model=name,rows=len(nodes),group_sequence=groups))
                model=fit_model(nodes,targets,groups,name.rsplit('_',1)[1],folder/(name+'.npz'))
                if name.startswith('sequential_'):
                    model['fixed_receiver_sha256']=models['receiver_'+model['kind']]['sha256'];receiver_bindings[name]=bindings
                models[name]=model;fit_log.write('FIT_DONE',dict(model=name,sha256=model['sha256']))
        finally:fit_log.close()
        table=defaultdict(list)
        for graph in graphs['TRAIN']:
            if graph['pre'] is not None:table[graph['pre']['task']+'/'+str(graph['pre']['completed_steps'])].append([v['loss']/500 for v in graph['leaves']])
        table={k:np.mean(v,axis=0).tolist() for k,v in table.items()}
        all_y=[[v['loss']/500 for v in graph['leaves']] for graph in graphs['TRAIN'] if graph['pre'] is not None]
        bank=dict(schema='STANDARD_COMPLETE_RISK_BANK_V1',manifest_id=m['manifest_id'],models=models,mean_table=table,global_mean=np.mean(all_y,axis=0).tolist(),
            actual_model_fits=8,empirical_mean_tables=1,old_A1_predictors_used=False,CAL_labels_used_for_training=False,TEST_read=False)
        bank['bank_id']=io.digest(bank);io.write(out/'bank.json',bank);io.write(out/'fixed_receiver_training_labels.json',receiver_bindings)
    result=dict(integrity='TRAINED_FOR_INDEPENDENT_AUDIT',actual_model_fits=len(models),guard=guard,wall_ns=perf_counter_ns()-start,
        bank_sha256=io.sha(out/'bank.json'),source_sha256=m['input_sha256'],graphs_sha256={c:io.sha(out/(c.lower()+'_graphs.jsonl.gz')) for c in graphs},
        model_sha256={n:v['sha256'] for n,v in models.items()},new_physics=0,new_policy_queries=0,online_LLM_API_calls=0)
    io.write(out/'fit_receipt.json',result);return result


def choice(values):
    io.require(type(values) is list and values and all(type(v) in (int,float) and np.isfinite(v) for v in values),'finite declared candidates')
    low=min(values);return next(i for i,v in enumerate(values) if v<=low+1e-10)


def pre_choice(selector,bank,folder,node):
    validate_node(node);io.require(node['stage']=='PRE' and selector in SELECTORS,'pre-only public selector')
    if selector=='CONTINUE_05':return dict(action=0,rate=1,values=None,model=None)
    if '_POST_' in selector:return dict(action=ACTIONS.index(selector.split('_POST_')[0]),rate=None,values=None,model=None)
    if selector=='TASK_TIME_MEAN':
        values=bank['mean_table'].get(node['task']+'/'+str(node['completed_steps']),bank['global_mean']);i=choice(values)
        return dict(action=i//4,rate=i%4,values=values,model='empirical_mean')
    role,kind=selector.lower().split('_');model=bank['models'][role+'_'+kind.upper()];values=predict(model,folder,node);i=choice(values)
    return dict(action=i//4 if role=='static' else i,rate=i%4 if role=='static' else None,values=values,model=model['sha256'])


def post_choice(selector,bank,folder,node):
    validate_node(node);io.require(node['stage']=='RETURN','actual returned public history')
    if selector.startswith('SEQUENTIAL_'):name='receiver_'+selector.rsplit('_',1)[1]
    else:io.require('_POST_' in selector,'adaptive post selector');name='post_all_'+selector.rsplit('_',1)[1]
    model=bank['models'][name];values=predict(model,folder,node)
    return dict(rate=choice(values),values=values,model=model['sha256'])


class Journal:
    def __init__(self,path):self.stream=Path(path).open('x',encoding='utf8',newline='\n');self.sequence=0
    def write(self,kind,payload):
        record=dict(sequence=self.sequence,saved_ns=perf_counter_ns(),kind=kind,**payload)
        self.stream.write(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n');self.stream.flush();os.fsync(self.stream.fileno());self.sequence+=1
        return record['sequence']
    def close(self):self.stream.close()


def evaluate(path):
    path=Path(path).resolve();m=checked(path);out=path.parent;io.require(io.read(out/'model_audit.json')['integrity']=='PASSED','independent models before development replay')
    bank=io.read(out/'bank.json');saved=dict(bank);identity=saved.pop('bank_id');io.require(identity==io.digest(saved),'locked bank')
    io.require(io.sha(out/'bank.json')==io.read(out/'model_audit.json')['bank_sha256'],'model version changed after audit')
    start=perf_counter_ns();guard={};journal=Journal(out/'development_replay.jsonl');results=[];metrics=[]
    try:
        with recorded_guard(guard,out/'replay_failure.json'):
            graphs=list(io.rows(out/'cal_graphs.jsonl.gz'))
            for graph in graphs:
                for selector in SELECTORS:
                    info=dict(unit=graph['unit'],selector=selector);adaptive=False
                    if graph['pre'] is None:
                        journal.write('ALREADY_TERMINAL',info);ai,ri=0,1
                    else:
                        seq=journal.write('PRE_INPUT',dict(**info,node=graph['pre'],input_sha256=io.digest(graph['pre'])))
                        decision=pre_choice(selector,bank,out/'models',graph['pre']);ai,ri=decision['action'],decision['rate']
                        journal.write('PRE_DECISION',dict(**info,input_sequence=seq,decision=decision))
                        if ri is None:
                            node=graph['returns'][ai]
                            if node is None:journal.write('ACQUISITION_TERMINAL',dict(**info,action=ai));ri=1
                            else:
                                seq=journal.write('RETURN_INPUT',dict(**info,node=node,input_sha256=io.digest(node)))
                                decision=post_choice(selector,bank,out/'models',node);ri=decision['rate'];adaptive=True
                                journal.write('POST_DECISION',dict(**info,input_sequence=seq,action=ai,decision=decision))
                    leaf=deepcopy(graph['leaves'][4*ai+ri]);baseline=graph['leaves'][1];same=graph['leaves'][4*ai+1]
                    result=dict(**info,action=ACTIONS[ai],rate=RATES[ri],post_decision=adaptive,already_terminal=graph['pre'] is None,
                        loss=leaf['loss'],success=leaf['success'],actual_source_steps=leaf['steps'],source_case_key=leaf['source_case_key'],source_case_sha256=leaf['source_case_sha256'],
                        difference_to_CONTINUE_05=leaf['loss']-baseline['loss'],difference_to_same_acquisition_05=leaf['loss']-same['loss'],
                        success_to_failure=bool(same['success'] and not leaf['success']),failure_to_success=bool(not same['success'] and leaf['success']))
                    journal.write('OUTCOME',result);results.append(result)
            for name in MODEL_NAMES:
                nodes,targets,groups,_=training_rows(name,graphs,bank['models'],out/'models',apply_group_split=False)
                losses=[float(np.mean((np.asarray(predict(bank['models'][name],out/'models',node))-target)**2)) for node,target in zip(nodes,targets)]
                per_group={str(g):sum(v for v,gg in zip(losses,groups) if gg==g)/sum(gg==g for gg in groups) for g in sorted(set(groups))}
                metrics.append(dict(model=name,group_mean_normalized_MSE=sum(per_group.values())/len(per_group),group_MSE=per_group,
                    factual_nodes=len(nodes),missing_terminal_nodes=len(graphs)*(3 if name.startswith(('post_all_','receiver_')) else 1)-len(nodes)))
    finally:journal.close()
    io.require(len(results)==18*len(SELECTORS),'every development unit and selector')
    summaries=[]
    for selector in SELECTORS:
        rows=[r for r in results if r['selector']==selector];groups=sorted({r['unit'][1] for r in rows});d=[r['difference_to_same_acquisition_05'] for r in rows]
        summaries.append(dict(selector=selector,units=len(rows),success=sum(r['success'] for r in rows),mean_loss=sum(r['loss'] for r in rows)/len(rows),
            group_differences_to_CONTINUE_05={str(g):sum(r['difference_to_CONTINUE_05'] for r in rows if r['unit'][1]==g)/sum(r['unit'][1]==g for r in rows) for g in groups},
            choices=dict(Counter(r['action']+'/'+str(r['rate']) for r in rows)),same_acquisition_harm=sum(v>0 for v in d),same_acquisition_help=sum(v<0 for v in d),same_acquisition_tie=sum(v==0 for v in d),
            same_acquisition_harm_steps=sum(max(0,v) for v in d),same_acquisition_worst_harm=max([0]+d),
            same_acquisition_mean_difference=sum(d)/len(d),success_to_failure=sum(r['success_to_failure'] for r in rows),failure_to_success=sum(r['failure_to_success'] for r in rows),
            actual_source_steps=sum(r['actual_source_steps'] for r in rows),new_environment_steps=0))
    result=dict(integrity='FOR_INDEPENDENT_REPLAY_AUDIT',classification='OFFLINE_CAL_DEVELOPMENT_NOT_FINAL_DEPLOYMENT',manifest_id=m['manifest_id'],
        results=results,summaries=summaries,prediction_metrics=metrics,guard=guard,wall_ns=perf_counter_ns()-start,replay_log_sha256=io.sha(out/'development_replay.jsonl'),
        offline_replays=len(results),independent_CAL_groups=3,new_physics=0,new_policy_queries=0,online_LLM_API_calls=0,
        task_gain_qualified=False,algorithm_novelty_established=False,publication_goal_complete=False)
    io.write(out/'development_results.json',result);return result
