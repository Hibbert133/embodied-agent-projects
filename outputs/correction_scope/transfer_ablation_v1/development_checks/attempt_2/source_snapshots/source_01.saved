"""Matched auxiliary-label ablations; fixed candidate, TRAIN-only development."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess
import numpy as np
from src.analysis import correction_transfer_learning_v1 as prior
from src.analysis import correction_auxiliary_targets_v1 as labels

io=prior.io;ROOT=io.ROOT;BASE=ROOT/'outputs/correction_scope/transfer_ablation_v1'
CONFIG=ROOT/'configs/movement_task/correction_transfer_ablation_v1.json'
KINDS=labels.KINDS;ACTIONS=prior.ACTIONS;RATES=prior.RATES
NEW_SELECTORS=tuple(k+'/'+a for k in KINDS for a in (*ACTIONS,'TWO_STAGE'))
SELECTORS=(*prior.SELECTORS,*NEW_SELECTORS)
DEPENDENCIES=tuple(dict.fromkeys((*prior.DEPENDENCIES,'src/analysis/correction_transfer_learning_v1.py',
    'src/analysis/correction_transfer_independent_v1.py','src/analysis/transfer_risk_math_v1.py','src/analysis/transfer_risk_independent_math_v1.py')))
SOURCES=('src/analysis/correction_auxiliary_targets_v1.py','src/analysis/correction_transfer_ablation_v1.py',
    'src/analysis/correction_transfer_ablation_independent_v1.py','scripts/run_correction_transfer_ablation_v1.py',
    'tests/test_correction_transfer_ablation_v1.py','configs/movement_task/correction_transfer_ablation_v1.json',
    'docs/protocols/correction_transfer_ablation_v1_zh.md','docs/research/correction_transfer_ablation_decision_v1_zh.md',
    'outputs/correction_scope/transfer_ablation_v1/validate_freeze.py',*DEPENDENCIES)


def source_bindings(c):
    result=prior.source_bindings(c);base=ROOT/c['source_learning_run'];bank=io.read(base/'bank.json')
    paths=[base/name for name in ('manifest.json','bank.json','model_audit.json','replay_audit.json','fit_receipt.json',
        'results.json','selected_rows.json','replay.jsonl','development_decision.json')]
    paths.extend(base/'models'/model[role]['file'] for fold in bank['models'].values() for model in fold.values() for role in ('receiver','precritic'))
    paths.extend((ROOT/'configs/movement_task/correction_transfer_learning_v1.json',prior.BASE/'freeze_validation/complete.json'))
    for p in paths:
        name=p.relative_to(ROOT).as_posix();data=subprocess.check_output(['git','show',c['source_result_commit']+':'+name],cwd=ROOT)
        assert hashlib.sha256(data).hexdigest()==io.sha(p),'immutable source Git bytes '+name;result[name]=io.sha(p)
    assert io.read(base/'model_audit.json')['integrity']==io.read(base/'replay_audit.json')['integrity']=='PASSED'
    return result


def prepare():
    v=io.read(BASE/'freeze_validation/complete.json');assert v['integrity']=='PASSED'
    assert not io.git('status','--porcelain','--untracked-files=no') and not list(BASE.glob('run_*/manifest.json'))
    for n,h in v['source_sha256'].items():assert io.sha(ROOT/n)==h
    c=io.read(CONFIG);inputs=source_bindings(c);head=io.git('rev-parse','HEAD')
    out=BASE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(exist_ok=False)
    m=dict(protocol=c['protocol'],source_git_commit=head,config=c,source_sha256=v['source_sha256'],input_sha256=inputs,
        classification='TRAIN_ONLY_POSTHOC_MATCHED_SUPERVISION_ABLATION',source_candidate_unchanged=True,
        CAL_TEST_training_or_evaluation=False,new_physics=0,online_LLM_API_calls=0)
    m['manifest_id']=io.digest(m);io.write(out/'manifest.json',m);return out/'manifest.json'


def checked(path):
    path=Path(path).resolve();m=io.read(path);copy=dict(m);mid=copy.pop('manifest_id')
    assert path.parent.parent==BASE.resolve() and mid==io.digest(copy) and m['config']==io.read(CONFIG)
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():assert io.sha(ROOT/n)==h,'frozen source '+n
    return m


def fit(path):
    path=Path(path).resolve();m=checked(path);out=path.parent;folder=out/'models';folder.mkdir(exist_ok=False)
    start=perf_counter_ns();guard={};ledger={};journal=prior.old.Journal(out/'fit_attempts.jsonl');models={};bindings={}
    (out/'training_labels').mkdir(exist_ok=False)
    graphs=list(io.rows(ROOT/m['config']['source_graph']));examples=list(io.rows(ROOT/m['config']['source_run']/'train/examples.jsonl.gz'))
    io.write(out/'source_availability.json',[dict(unit=g['unit'],pre_available=g['pre'] is not None,
        returns=[dict(action=ACTIONS[i],available=n is not None,history_length=None if n is None else len(n['history']),
            missing_reason=None if n is not None else 'ALREADY_TERMINAL' if g['pre'] is None else 'ACQUISITION_TERMINAL') for i,n in enumerate(g['returns'])]) for g in graphs])
    source_bank=io.read(ROOT/m['config']['source_learning_run']/'bank.json')
    try:
        with prior.old.recorded_guard(guard,out/'fit_failure.json',max_solve=9):
            for fold in range(3):
                allocation=prior.split(fold);nodes,cost,factual,groups,ids=prior.receiver_rows(graphs,examples,allocation['receiver'])
                basis=prior.make_basis(nodes,groups);gamma=max(.05,float(prior.weights(groups)@factual[:,:,48].mean(1)))
                source=source_bank['models'][str(fold)]['JOINT_SPO']['receiver']
                assert gamma==source['gamma'] and prior.old.digest_array(factual)==source['target_sha256']
                models[str(fold)]={}
                for kind in KINDS:
                    target=labels.supervision(nodes,factual,kind);data=prior.dataset(nodes,cost,target,groups,basis,gamma)
                    assert prior.old.digest_array(cost)==source['cost_sha256'] and prior.old.digest_array(data['phi'])==source['feature_sha256']
                    key=str(fold)+'/'+kind;journal.write('NEURAL_FIT_INTENT',dict(key=key,allocation=allocation,steps=1000,
                        target_sha256=prior.old.digest_array(target),factual_target_sha256=source['target_sha256'],source_candidate_sha256=source['sha256']))
                    label_file='target_'+str(fold)+'_'+kind+'.json';io.write(out/'training_labels'/label_file,target.tolist())
                    params,receipt=prior.network.fit(data,'JOINT_SPO',m['config']['model_rng_seed']+fold,1000,ledger=ledger)
                    filename='receiver_'+str(fold)+'_'+kind+'.npz';prior.save_npz(folder/filename,{**params,**basis,'gamma':gamma})
                    model=dict(file=filename,sha256=io.sha(folder/filename),variant='JOINT_SPO',auxiliary_kind=kind,fold=fold,
                        training_groups=list(allocation['receiver']),training_nodes=ids,feature_sha256=prior.old.digest_array(data['phi']),
                        factual_target_sha256=source['target_sha256'],target_sha256=prior.old.digest_array(target),cost_sha256=prior.old.digest_array(cost),
                        weights_sha256=prior.old.digest_array(data['weights']),gamma=gamma,seed=m['config']['model_rng_seed']+fold,training=receipt,
                        source_unmodified_candidate_sha256=source['sha256'],saved_parameter_count=sum(a.size for a in params.values()),
                        training_label_file=label_file,training_label_file_sha256=io.sha(out/'training_labels'/label_file))
                    journal.write('NEURAL_FIT_SAVED',dict(key=key,model_sha256=model['sha256']))
                    ns,y,gs,records=prior.pre_rows(graphs,allocation['precritic'],model,folder);bindings[key]=records
                    journal.write('PRECRITIC_FIT_INTENT',dict(key=key,fixed_receiver_sha256=model['sha256']))
                    pre=prior.old.fit_model(ns,y,gs,'RBF',folder/('pre_'+str(fold)+'_'+kind+'.npz'));pre['fixed_receiver_sha256']=model['sha256']
                    models[str(fold)][kind]=dict(receiver=model,precritic=pre);journal.write('PRECRITIC_FIT_SAVED',dict(key=key,model_sha256=pre['sha256']))
        assert ledger==dict(fit_attempts=9,optimizer_steps=9000)
        bank=dict(manifest_id=m['manifest_id'],models=models,neural_ledger=ledger,source_split='TRAIN',source_candidate_refitted=False,
            frozen_ns=perf_counter_ns());bank['bank_id']=io.digest(bank);io.write(out/'bank.json',bank);io.write(out/'fixed_receiver_labels.json',bindings)
        receipt=dict(integrity='FOR_INDEPENDENT_REFIT',neural_ledger=ledger,ridge_fits=9,guard=guard,wall_ns=perf_counter_ns()-start,
            bank_sha256=io.sha(out/'bank.json'),new_physics=0,new_policy_queries=0,online_LLM_API_calls=0)
        io.write(out/'fit_receipt.json',receipt);return receipt
    finally:journal.close()


def summarize(rows):
    summaries={}
    for selector in SELECTORS:
        r=[v for v in rows if v['selector']==selector];assert len(r)==54
        d=[v['leaf']['loss']-v['baseline']['loss'] for v in r];panels={}
        for task in prior.old.TASKS:
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    rr=[v for v in r if v['unit'][2]==task and v['unit'][3]==context and v['boundary']==boundary]
                    assert len(rr)==3;panels[f'{task}/{context}/{boundary}']=dict(n=3,success=sum(v['leaf']['success'] for v in rr),mean_loss=float(np.mean([v['leaf']['loss'] for v in rr])))
        summaries[selector]=dict(n=54,success=sum(v['leaf']['success'] for v in r),mean_loss=float(np.mean([v['leaf']['loss'] for v in r])),
            total_executed_steps=sum(v['leaf']['steps'] for v in r),acquisition_steps=sum(v['leaf']['movement_steps']+v['leaf']['measurement_steps'] for v in r),
            harm=sum(v>0 for v in d),help=sum(v<0 for v in d),tie=sum(v==0 for v in d),harm_severity=sum(v for v in d if v>0),
            success_to_failure=sum(v['baseline']['success'] and not v['leaf']['success'] for v in r),failure_to_success=sum(not v['baseline']['success'] and v['leaf']['success'] for v in r),
            same_acquisition_harm=sum(v['leaf']['loss']>v['same_acquisition']['loss'] for v in r),same_acquisition_help=sum(v['leaf']['loss']<v['same_acquisition']['loss'] for v in r),
            groups={str(g):float(np.mean([v['leaf']['loss'] for v in r if v['unit'][1]==g])) for g in range(9)},panels=panels,
            chosen_actions=dict(Counter(v['action'] for v in r)),chosen_rates=dict(Counter(str(v['rate']) for v in r)))
    return summaries


def evaluate(path):
    path=Path(path).resolve();m=checked(path);out=path.parent;bank=io.read(out/'bank.json');audit=io.read(out/'model_audit.json')
    assert audit['integrity']=='PASSED' and audit['bank_sha256']==io.sha(out/'bank.json')
    start=perf_counter_ns();guard={};journal=prior.old.Journal(out/'replay.jsonl')
    source_rows=io.read(ROOT/m['config']['source_learning_run']/'selected_rows.json');rows=deepcopy(source_rows)
    graphs=list(io.rows(ROOT/m['config']['source_graph']))
    try:
        with prior.old.recorded_guard(guard,out/'replay_failure.json'):
            for i,row in enumerate(source_rows):journal.write('SOURCE_ROW_REUSED',dict(source_row_index=i,source_row_sha256=io.digest(row),source_replay_sha256=m['input_sha256'][m['config']['source_learning_run']+'/replay.jsonl']))
            for graph in graphs:
                fold=graph['unit'][1]//3
                for selector in NEW_SELECTORS:
                    kind,action=selector.split('/');models=bank['models'][str(fold)][kind];info=dict(unit=graph['unit'],selector=selector,fold=fold)
                    if graph['pre'] is None:ai,ri=0,1;journal.write('ALREADY_TERMINAL',info)
                    else:
                        if action=='TWO_STAGE':
                            values=prior.old.predict(models['precritic'],out/'models',graph['pre']);ai=prior.old.choice(values)
                            journal.write('PRE_DECISION',dict(**info,query_sha256=io.digest(graph['pre']),scores=values,action=ai,model_sha256=models['precritic']['sha256']))
                        else:ai=ACTIONS.index(action);journal.write('PRE_FIXED_ACTION',dict(**info,action=ai,query_sha256=io.digest(graph['pre'])))
                        node=graph['returns'][ai]
                        if node is None:ri=1;journal.write('ACQUISITION_TERMINAL',dict(**info,action=ai))
                        else:
                            choice=prior.receiver_decision(models['receiver'],out/'models',node);ri=choice['rate'];journal.write('RETURN_DECISION',dict(**info,action=ai,decision=choice))
                    row=dict(**info,boundary=graph['boundary'],action=ACTIONS[ai],rate=RATES[ri],already_terminal=graph['pre'] is None,
                        return_terminal=graph['returns'][ai] is None,leaf=deepcopy(graph['leaves'][4*ai+ri]),baseline=deepcopy(graph['leaves'][1]),same_acquisition=deepcopy(graph['leaves'][4*ai+1]))
                    journal.write('FACTUAL_OUTCOME',row);rows.append(row)
        assert len(rows)==2376
        io.write(out/'selected_rows.json',rows);io.write(out/'results.json',dict(classification=m['classification'],selectors=summarize(rows),
            source_selections_reused=1728,new_offline_selections=648,n_units=54,n_selectors=44,n_selections=2376,
            nominal_CI_or_significance=False,fold_training_overlap=True,new_physics=0,online_LLM_API_calls=0))
        receipt=dict(integrity='FOR_INDEPENDENT_REPLAY_AUDIT',guard=guard,wall_ns=perf_counter_ns()-start,
            selected_sha256=io.sha(out/'selected_rows.json'),results_sha256=io.sha(out/'results.json'),replay_sha256=io.sha(out/'replay.jsonl'))
        io.write(out/'replay_receipt.json',receipt);return receipt
    finally:journal.close()
