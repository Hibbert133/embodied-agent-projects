"""Fresh factual outcome learning; no simulator and no old-QUAL relabeling."""
from pathlib import Path
from time import perf_counter_ns
from collections import Counter
import traceback
import numpy as np
from src.analysis import release_learning_io_v1 as a
from src.analysis import release_learning_regression_v1 as regression
from src.probe import release_learning_features_v1 as features
from src.probe import release_learning_predictor_v1 as predictor
from src.probe import information_release_v1 as release
from src.analysis.information_release_targets_v1 import targets
io=a.io


def cases(root,cohort):
    folder=Path(root)/cohort.lower();r=io.read(folder/'audit.json');io.require(r['integrity']=='PASSED','only complete independently audited records')
    io.require(io.sha(folder/'cases.jsonl.gz')==r['artifact_sha256']['cases.jsonl.gz'],'audited factual case bytes unchanged')
    yield from io.rows(folder/'cases.jsonl.gz')


def group(row):return row['cohort']+'/'+str(row['group'])
def case_id(row):return '/'.join(str(row[k]) for k in a.KEYS)


def fit_recorded(folder,x,y,groups,width,ridge,centers,ledger,role):
    """Keep every attempt and returned candidate, including partial training."""
    destination=Path(folder)/'fit_records';destination.mkdir(exist_ok=True);index=len(ledger)
    stem=destination/(role.split('/')[0].lower()+'_'+str(index).zfill(3));started=perf_counter_ns()
    io.write(stem.with_suffix('.intent.json'),dict(role=role,x_sha256=io.digest(x),y_sha256=io.digest(y),groups=groups,width=width,ridge=ridge,centers=centers))
    try:
        model=regression.fit(x,y,groups,width,ridge,centers,ledger,role=role);io.write(stem.with_suffix('.model.json'),model);return model
    except BaseException:
        io.write(stem.with_suffix('.failure.json'),dict(role=role,traceback=traceback.format_exc()));raise
    finally:io.write(stem.with_suffix('.receipt.json'),dict(role=role,numerical_fit_attempts=len(ledger),wall_ns=perf_counter_ns()-started))


def tail_data(root,cohort):
    rows=[];registry=[]
    for c in cases(root,cohort):
        entry=c['learning'];why=None
        if entry is None:why='EARLY_END_BEFORE_BOUNDARY'
        elif entry['receiver_decision'] is None:why='ENDED_DURING_ACQUISITION'
        registry.append(dict(case_id=case_id(c),eligible=why is None,missing_reason=why,success=c['success'],deadline_loss=c['deadline_loss']))
        if why is not None:continue
        view=entry['release_receipt']['model_view'];common,full,present=features.after(view,entry['prefix_history'])
        rows.append(dict(case_id=case_id(c),group=group(c),task=c['task'],action=entry['saved_return']['record']['action'],
            rate=entry['receiver_decision']['choice']['time_constant_s'],common=common.tolist(),full=full.tolist(),present=present,y=c['deadline_loss']))
    io.require(rows and all(any(r['task']==t for r in rows) for t in io.TASKS),'all tasks represented, no favorable subset')
    return dict(schema='FACTUAL_RELEASE_TAIL_DATA_V1',cohort=cohort,rows=rows,complete_case_registry=registry)


def fit_receiver(path):
    m=a.checked(path);root=Path(path).parent;io.require(not (root/'tail_select').exists(),'fit before any SELECT outcomes')
    folder=root/'models';folder.mkdir(exist_ok=False);start=perf_counter_ns();data=tail_data(root,'TAIL_TRAIN');ledger=[];bank=[]
    io.write(folder/'receiver_training_data.json',data)
    for j,(width,ridge) in enumerate(a.GRID):
        common=[];common_residual=[];signal=[]
        for k,rate in enumerate(release.RATES):
            rows=[r for r in data['rows'] if r['rate']==rate];io.require(rows,'registered gain has no factual support')
            base=fit_recorded(folder,[r['common'] for r in rows],[r['y'] for r in rows],[r['group'] for r in rows],width,ridge,64,ledger,f'RECEIVER/{j}/COMMON/{k}')
            common.append(base);rows=[r for r in rows if r['present']];io.require(rows,'nonempty trace has no factual gain support')
            residual=[r['y']-predictor.predict(base,r['common']) for r in rows]
            common_residual.append(fit_recorded(folder,[r['common'] for r in rows],residual,[r['group'] for r in rows],width,ridge,64,ledger,f'RECEIVER/{j}/MATCHED_COMMON/{k}'))
            signal.append(fit_recorded(folder,[r['full'] for r in rows],residual,[r['group'] for r in rows],width,ridge,64,ledger,f'RECEIVER/{j}/SIGNAL/{k}'))
        model=dict(feature_spec='PUBLIC_COMPLETE_PREFIX_AND_RETURN_V1',common=common,common_residual=common_residual,signal_residual=signal,grid_index=j,width=width,ridge=ridge)
        bank.append(dict(schema='FROZEN_RELEASE_RECEIVER_V1',model=model,receiver_version=io.digest(model)))
    io.require(len(ledger)==108,'exact registered receiver fit count')
    v=dict(schema='RELEASE_RECEIVER_BANK_V1',**{k:m[k] for k in a.IDENTITY},banks=bank,fit_ledger=ledger,
        data_sha256=io.sha(folder/'receiver_training_data.json'),scientific_risk_model_fits=108,new_response_model_fits=0,
        optimizer_updates=0,new_environment_steps=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    io.write(folder/'receiver_bank.json',v);return dict(integrity='FITTED_PENDING_INDEPENDENT_AUDIT',fits=108)


def select_receiver(path):
    a.checked(path);root=Path(path).parent;folder=root/'models';io.require(not (root/'gate_train').exists(),'receiver frozen before GATE histories')
    io.require(io.read(folder/'receiver_bank_audit.json')['integrity']=='PASSED','independently audited trained bank')
    bank=io.read(folder/'receiver_bank.json');data=tail_data(root,'TAIL_SELECT');io.write(folder/'receiver_select_data.json',data);scores=[]
    for model in bank['banks']:
        errors=[];groups=[]
        for r in data['rows']:
            k=release.RATES.index(r['rate']);base=predictor.predict(model['model']['common'][k],r['common'])
            masked=base+predictor.predict(model['model']['common_residual'][k],r['common']) if r['present'] else base
            full=base+predictor.predict(model['model']['signal_residual'][k],r['full']) if r['present'] else base
            errors.append(.5*((float(np.clip(masked,0,500))-r['y'])**2+(float(np.clip(full,0,500))-r['y'])**2));groups.append(r['group'])
        scores.append(float(np.dot(regression.weights(groups),errors)))
    best=next(j for j,v in enumerate(scores) if v<=min(scores)+1e-6);chosen=bank['banks'][best]
    all_cases=list(cases(root,'TAIL_SELECT'));fixed=[]
    for program in a.programs('TAIL_SELECT'):
        rows=[r for r in all_cases if r['program']==program];fixed.append(float(np.mean([r['deadline_loss'] for r in rows])))
    j=min(range(len(fixed)),key=lambda i:(fixed[i],a.programs('TAIL_SELECT')[i]!='TAIL_CONTINUE_1',i))
    from src.probe.release_learning_programs_v1 import fixed as assignment
    action,rate,_=assignment(a.programs('TAIL_SELECT')[j])
    chosen={**chosen,'integrity':'PASSED','selection_scores':scores,'selected_index':best,'selection_data_sha256':io.sha(folder/'receiver_select_data.json'),
        'development_groups_used':sorted({g for b in chosen['model']['common'] for g in b['training_groups']}|{r['group'] for r in data['rows']}),
        'best_fixed_program':dict(program=a.programs('TAIL_SELECT')[j],action=action,rate=rate,all_mean_cutoff_losses=fixed),
        'receiver_bank_sha256':io.sha(folder/'receiver_bank.json'),'no_model_refit_on_SELECT':True,'scientific_model_fits_from_selection':0}
    io.write(folder/'receiver_freeze.json',chosen);return dict(integrity='SELECTED_PENDING_INDEPENDENT_AUDIT',grid_index=best,receiver_version=chosen['receiver_version'])


def gate_data(root):
    receiver=io.read(Path(root)/'models/receiver_freeze.json');rows=[];registry=[]
    nuisance_groups=receiver['development_groups_used']
    for c in cases(root,'GATE_TRAIN'):
        l=c['learning'];registry.append(dict(case_id=case_id(c),eligible=l is not None,missing_reason=None if l is not None else 'EARLY_END_BEFORE_BOUNDARY',deadline_loss=c['deadline_loss']))
        if l is None:continue
        saved=l['saved_return'];receipt=l['release_receipt'];prefix=l['prefix_history'];binding=receipt['binding']
        common_view=release.release(saved,expose=False,release_sequence=binding['release_sequence'],receiver_version=receiver['receiver_version'])['model_view']
        full_view=release.release(saved,expose=True,release_sequence=binding['release_sequence'],receiver_version=receiver['receiver_version'])['model_view']
        base,_=predictor.receiver(receiver,common_view,prefix);_,enriched=predictor.receiver(receiver,full_view,prefix)
        mu0=min(base);mu1=min(base if enriched is None else enriched)
        t=targets(saved_return=saved,release_receipt=receipt,cutoff_loss=c['deadline_loss'],mu_masked=mu0,mu_full=mu1,
            expected_receiver_version=receiver['receiver_version'],independent_group=group(c),nuisance_training_groups=nuisance_groups,expected_probability=.5)
        rows.append(dict(case_id=case_id(c),group=group(c),task=c['task'],action=saved['record']['action'],x=features.before(l['pre_memory'],prefix).tolist(),
            release=binding['assigned_exposure'],y=c['deadline_loss'],mu0=mu0,mu1=mu1,target=t))
    return dict(schema='ACTUAL_RANDOMIZED_RELEASE_TARGET_DATA_V1',rows=rows,complete_case_registry=registry,
        receiver_version=receiver['receiver_version'],nuisance_training_groups=nuisance_groups,receiver_sha256=io.sha(Path(root)/'models/receiver_freeze.json'))


def fit_pre(path):
    m=a.checked(path);root=Path(path).parent;folder=root/'models';io.require(not (root/'cal').exists(),'pre-risk fitting before any CAL outcome')
    start=perf_counter_ns();data=gate_data(root);io.write(folder/'gate_training_data.json',data);ledger=[];banks=[]
    for j,(width,ridge) in enumerate(a.GRID):
        effect={};direct={}
        def fit(rows,y,role):
            io.require(rows,'complete registered action/exposure training support')
            return fit_recorded(folder,[r['x'] for r in rows],y,[r['group'] for r in rows],width,ridge,32,ledger,f'PRE/{j}/'+role)
        for action in release.ACTIONS:
            rows=[r for r in data['rows'] if r['action']==action]
            masked=fit(rows,[r['target']['masked_full_program_risk'] for r in rows],action+'/M')
            delta=None if action=='CONTINUE' else fit(rows,[r['target']['supplemental_information_effect'] for r in rows],action+'/D')
            effect[action]=dict(masked=masked,effect=delta)
            if action=='CONTINUE':direct[action]=dict(masked=fit(rows,[r['y'] for r in rows],action+'/DIRECT'))
            else:
                direct[action]={}
                for expose,key in ((False,'masked'),(True,'full')):
                    observed=[r for r in rows if r['release']==expose]
                    direct[action][key]=fit(observed,[r['y'] for r in observed],action+'/DIRECT/'+key)
        body=dict(effect=effect,direct=direct,grid_index=j,width=width,ridge=ridge)
        banks.append({**body,'policy_version':io.digest(body)})
    io.require(len(ledger)==90,'exact registered pre-risk fit count')
    v=dict(schema='RELEASE_PRE_BANK_V1',**{k:m[k] for k in a.IDENTITY},banks=banks,fit_ledger=ledger,
        gate_data_sha256=io.sha(folder/'gate_training_data.json'),receiver_sha256=data['receiver_sha256'],scientific_risk_model_fits=90,
        new_response_model_fits=0,optimizer_updates=0,new_environment_steps=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
    io.write(folder/'pre_bank.json',v);return dict(integrity='FITTED_PENDING_INDEPENDENT_AUDIT',fits=90)


def calibration_scores(rows):
    """Complete actually executed CAL arms, never an imputed policy outcome."""
    units={}
    for c in rows:
        unit=units.setdefault((c['group'],c['task'],c['context']),{});io.require(c['program'] not in unit,'duplicate CAL arm');unit[c['program']]=c
    scores={'effect':[[] for _ in a.GRID],'direct':[[] for _ in a.GRID]};selected=[]
    for key,arms in sorted(units.items()):
        io.require(set(arms)==set(a.programs('CAL')),'complete five-arm calibration unit')
        exemplar=arms['CAL_CONTINUE_MASK'];l=exemplar['learning']
        if l is None:
            io.require(all(c['learning'] is None and c['deadline_loss']==exemplar['deadline_loss'] for c in arms.values()),'early terminal CAL prefix equivalence')
            for kind in scores:
                for j in range(len(a.GRID)):scores[kind][j].append(exemplar['deadline_loss'])
            continue
        for other in arms.values():
            io.require(other['learning'] is not None and other['learning']['cal_predictions']==l['cal_predictions']
                and other['learning']['pre_memory']==l['pre_memory'],'CAL forecasts or public prehistory changed across arms')
        for j,recommendation in enumerate(l['cal_predictions']):
            io.require(recommendation['bank_index']==j,'prospective registered bank order')
            for kind in scores:
                p=recommendation[kind];name='CAL_'+p['action']+('_FULL' if p['expose'] and p['action']!='CONTINUE' else '_MASK')
                scores[kind][j].append(arms[name]['deadline_loss']);selected.append(dict(unit=list(key),kind=kind,bank=j,actual_arm=name,loss=arms[name]['deadline_loss']))
    io.require(len(units)==a.GROUPS['CAL']*6,'full independent calibration population')
    return {kind:[float(np.mean(v)) for v in grid] for kind,grid in scores.items()},selected


def lock_policy(path):
    a.checked(path);root=Path(path).parent;folder=root/'models';io.require(not (root/'dev').exists(),'lock before own-history DEV')
    io.require(io.read(folder/'pre_bank_audit.json')['integrity']=='PASSED','independent pre-risk bank audit')
    bank=io.read(folder/'pre_bank.json');scores,rows=calibration_scores(list(cases(root,'CAL')))
    choices={kind:min(range(len(v)),key=lambda j:(v[j],j)) for kind,v in scores.items()}
    body=dict(effect=bank['banks'][choices['effect']]['effect'],direct=bank['banks'][choices['direct']]['direct'],
        receiver_version=io.read(folder/'receiver_freeze.json')['receiver_version'],selected_grid_indices=choices,
        CAL_mean_full_cutoff_losses=scores,CAL_actual_arm_selection=rows,pre_bank_sha256=io.sha(folder/'pre_bank.json'))
    result=dict(schema='LOCKED_RELEASE_LEARNING_POLICY_V1',integrity='PASSED',**body,policy_version=io.digest(body),
        new_fits_from_calibration=0,CAL_is_evaluator_only_not_own_history_qualification=True)
    io.write(folder/'policy_lock.json',result);return dict(integrity='PASSED',selected=choices,policy_version=result['policy_version'])
