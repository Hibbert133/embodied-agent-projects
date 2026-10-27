"""Factual, split-isolated standard forecast fitting and independent audits."""
from pathlib import Path
from time import perf_counter_ns
from itertools import groupby
from unittest.mock import patch
import numpy as np
from src.analysis import correction_scope_io_v1 as a
from src.analysis import correction_scope_independent_v1 as independent
from src.analysis.release_learning_guard_v1 import read_only
from src.probe import correction_scope_model_v1 as model
io=a.io


def examples(path,cohort):
    out=Path(path).parent/cohort.lower();audit=io.read(out/'audit.json')
    io.require(audit['integrity']=='PASSED' and io.sha(out/'examples.jsonl.gz')==audit['examples_sha256'],'audited factual examples')
    for n,h in audit['collection_sha256'].items():io.require(io.sha(out/n)==h,'audited raw bytes changed '+n)
    return list(io.rows(out/'examples.jsonl.gz'))


def train(path):
    path=Path(path).resolve();m=a.checked(path);rows=examples(path,'TRAIN');out=path.parent/'learning';out.mkdir(exist_ok=False)
    start=perf_counter_ns();io.write(out/'fit_intent.json',dict(started_ns=start,manifest_id=m['manifest_id'],source_split='TRAIN',fits_max=8))
    guard={};models={};failure=None
    try:
        with read_only(guard,max_solve=8):
            for stage in model.STAGES:
                data=[r for r in rows if r['stage']==stage and r['target'] is not None];io.require(data,'no factual TRAIN targets '+stage);models[stage]={}
                for kind in model.KINDS:
                    x=[model.features(r['view'],kind) for r in data];y=[r['target'] for r in data];g=[r['spec']['group'] for r in data]
                    models[stage][kind]=model.fit(x,y,g,kind)
                    io.write(out/(stage+'_'+kind+'.json'),models[stage][kind])
        bank=dict(schema='CORRECTION_SCOPE_BANK_V1',manifest_id=m['manifest_id'],models=models,TRAIN_examples_sha256=io.sha(path.parent/'train/examples.jsonl.gz'),
            frozen_ns=perf_counter_ns(),only_factual_public_training=True,policy_weights_unchanged=True)
        bank['bank_id']=io.digest(bank);io.write(out/'bank.json',bank)
    except BaseException as e:failure=dict(type=type(e).__name__,message=str(e))
    receipt=dict(integrity='FIT_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_PARTIAL',guard=guard,wall_ns=perf_counter_ns()-start,
        failure=failure,actual_forecast_fits=guard.get('operation_counts',{}).get('solve_attempts',0),new_response_fits=0,new_policy_training=0,online_LLM_API_calls=0)
    io.write(out/'fit_receipt.json',receipt)
    if failure:raise RuntimeError(str(failure))
    return receipt


def literal_labels(path,cohort,rows):
    """Rebuild labels from the actual journal, not the exported target columns."""
    bycase=iter(groupby(io.rows(Path(path).parent/cohort.lower()/'events.jsonl.gz'),a.case_key));index=0;fields=0
    for spec in a.population(cohort):
        key,it=next(bycase);io.require(key==a.case_key(spec),'literal label allocation')
        history=[];prior=None;returned=None;entry=None
        for e in it:
            if e['event']=='CONTROLLED_INITIAL':prior=dict(observation=e['observation'],success=False,terminated=False,truncated=False)
            elif e['event']=='STEP_COMPLETE':
                history.append(dict(at_calls=e['logical_step'],before=prior,command=e['command'],after=e['after']));prior=e['after']
            elif e['event']=='AGENT_EVENT':
                p=e['public_payload']
                if e['agent_event']=='TASK_MEMORY_RETURN':returned=p['memory']
                elif e['agent_event']=='FORECAST_INPUT' and p['value']['stage']=='POST':entry=p['at_calls']
        expected=None if entry is None else independent.target(history,entry,returned)
        for stage in model.STAGES:
            row=rows[index];index+=1;io.require(row['spec']==spec and row['stage']==stage,'literal example order')
            io.require((row['target'] is None)==(expected is None),'literal missing target')
            if expected is not None:
                io.require(np.allclose(row['target'],expected,atol=2e-12,rtol=2e-12),'literal factual successor label');fields+=len(expected)
    io.require(index==len(rows) and next(bycase,None) is None,'literal label denominator');return fields


def audit_models(path):
    path=Path(path).resolve();m=a.checked(path);out=path.parent/'learning';bank=io.read(out/'bank.json');rows=examples(path,'TRAIN');guard={};start=perf_counter_ns();checks=0
    io.require(bank['manifest_id']==m['manifest_id'] and bank['TRAIN_examples_sha256']==io.sha(path.parent/'train/examples.jsonl.gz'),'model source identity')
    with read_only(guard,max_lstsq=8),patch.object(model,'fit',side_effect=RuntimeError('main fit disabled')),patch.object(model,'features',side_effect=RuntimeError('main features disabled')),patch.object(model,'target',side_effect=RuntimeError('main target disabled')),patch.object(model,'predict',side_effect=RuntimeError('main predict disabled')):
        fields=literal_labels(path,'TRAIN',rows)
        for stage in model.STAGES:
            data=[r for r in rows if r['stage']==stage and r['target'] is not None]
            for kind in model.KINDS:
                coefficients=independent.refit(data,kind,bank['models'][stage][kind]);checks+=int(coefficients.size)
    result=dict(integrity='PASSED',bank_id=bank['bank_id'],bank_sha256=io.sha(out/'bank.json'),
        independent_refits=8,coefficient_fields=checks,literal_target_fields=fields,guard=guard,wall_ns=perf_counter_ns()-start,
        new_physical_interactions=0,online_LLM_API_calls=0,main_fit_features_target_predict_disabled=True)
    io.write(out/'model_audit.json',result);return result


def prediction_audit(path,cohort):
    path=Path(path).resolve();a.checked(path);io.require(cohort in ('CAL','TEST'),'independent prediction phase')
    bank=io.read(path.parent/'learning/bank.json');out=path.parent/cohort.lower();rows=examples(path,cohort);guard={};start=perf_counter_ns();count=fields=0
    with read_only(guard),patch.object(model,'predict',side_effect=RuntimeError('main predict disabled')),patch.object(model,'features',side_effect=RuntimeError('main features disabled')),patch.object(model,'target',side_effect=RuntimeError('main target disabled')),patch.object(model,'family_errors',side_effect=RuntimeError('main metrics disabled')):
        fields=literal_labels(path,cohort,rows)
        for r in rows:
            if r['view'] is None:io.require(r['prediction'] is None,'forecast without factual input');continue
            p=r['prediction'];io.require(p is not None and p['bank_id']==bank['bank_id'] and p['input_sha256']==io.digest(r['view']),'saved frozen forecast')
            io.require(np.allclose(p['predictions']['PERSISTENCE'],independent.persistence(r['view']),atol=3e-10,rtol=3e-10),'independent persistence forecast');count+=1
            for kind in model.KINDS:
                expected=independent.prediction(r['view'],bank['models'][r['stage']][kind]);actual=p['predictions'][kind]
                io.require(np.allclose(actual,expected,atol=3e-10,rtol=3e-10),'independent actual pre-outcome prediction');count+=1
                if r['target'] is not None:
                    values=independent.errors(actual,r['target']);io.require(all(v>=0 and np.isfinite(v) for v in values.values()),'literal errors finite')
    first=next(io.rows(out/'events.jsonl.gz'))['saved_ns'];io.require(first>bank['frozen_ns'],'predictions collected before model freeze')
    result=dict(integrity='PASSED',cohort=cohort,forecasts_checked=count,literal_target_fields=fields,guard=guard,wall_ns=perf_counter_ns()-start,
        bank_id=bank['bank_id'],new_physics=0,new_fits=0,online_LLM_API_calls=0,main_math_disabled=True)
    io.write(out/'prediction_audit.json',result);return result


def calibrate(path):
    path=Path(path).resolve();a.checked(path);rows=examples(path,'CAL');audit=io.read(path.parent/'cal/prediction_audit.json');io.require(audit['integrity']=='PASSED','CAL prediction audit')
    result={};guard={};start=perf_counter_ns()
    with read_only(guard):
        for stage in model.STAGES:
            result[stage]={}
            for kind in ('PERSISTENCE',*model.KINDS):
                errors=[model.family_errors(r['prediction']['predictions'][kind],r['target']) for r in rows if r['stage']==stage and r['target'] is not None]
                io.require(errors,'CAL target coverage')
                result[stage][kind]={k:float(np.quantile([np.sqrt(r[k]) for r in errors],.9)) for k in errors[0]}
    value=dict(integrity='PASSED',empirical_level=.9,radii=result,CAL_examples_sha256=io.sha(path.parent/'cal/examples.jsonl.gz'),
        bank_sha256=io.sha(path.parent/'learning/bank.json'),
        locked_ns=perf_counter_ns(),guard=guard,wall_ns=perf_counter_ns()-start,
        model_selection=False,physical_safety_guarantee=False,exchangeability_guarantee_claimed=False)
    io.write(path.parent/'learning/calibration.json',value);return value
