"""Saved prospective forecasts only; exact registered nanometre loss statistics."""
from collections import defaultdict,Counter
from decimal import Decimal,localcontext,ROUND_HALF_EVEN
from fractions import Fraction
from pathlib import Path
from time import perf_counter_ns,time_ns
import numpy as np
from src.analysis import latent_response_io_v1 as a
from src.analysis.command_target_sources_v1 import GroupedJournal
from src.probe.latent_response_query_v1 import METHODS
io=a.io
H8=METHODS[:6]


def score(prediction,truth,horizon,valid,available):
    if not available:return {'raw_m':None,'loss_nm':1000000000,'reason':'NO_MEASUREMENT_ENTRY','capped':False}
    if not valid:return {'raw_m':None,'loss_nm':1000000000,'reason':'INVALID_SAVED_FORECAST','capped':False}
    if len(truth)<horizon:return {'raw_m':None,'loss_nm':1000000000,'reason':'SHORT_ACTUAL_PACKET','capped':False}
    p=np.asarray(prediction,float);y=np.asarray(truth,float)
    io.require(p.shape[0]>=horizon and p.shape[1:]==(2,) and np.isfinite(p).all(),'saved finite prediction shape')
    with localcontext() as ctx:
        ctx.prec=80;total=Decimal(0)
        for h in range(horizon):
            for j in range(2):total+=(Decimal(str(float(p[h,j])))-Decimal(str(float(y[h,j]))))**2
        rmse=(total/Decimal(2*horizon)).sqrt();bounded=min(Decimal(1),rmse)
        nm=int((bounded*Decimal(1000000000)).to_integral_value(rounding=ROUND_HALF_EVEN))
    return {'raw_m':float(rmse),'loss_nm':nm,'reason':None,'capped':rmse>1}


def loss_rows(c,events):
    results=[e['public_payload']['result'] for e in events if e['event']=='AGENT_EVENT' and e['agent_event']=='FORECAST_RESULT']
    io.require(len(results)<=1,'one prospective forecast event');result=results[0] if results else None
    physical=[e for e in events if e['event']=='STEP_COMPLETE'];entry=c['entry_at_calls'];truth=[]
    if entry is not None:
        before=c['initial']['observation'] if entry==0 else physical[entry-1]['after']['observation']
        truth=[(np.asarray(e['after']['observation'][:2])-before[:2]).tolist() for e in physical[entry:]]
    out=[]
    for method in METHODS:
        forecast=None if result is None else result['forecasts'][method];valid=None if forecast is None else forecast['valid']
        pred=None if forecast is None or not valid else forecast['displacements'];one=score(pred,truth,1,valid,result is not None)
        multi=score(pred,truth,8,valid,result is not None) if method in H8 else {'raw_m':None,'loss_nm':None,'reason':'ONE_STEP_MODEL_ONLY','capped':False}
        out.append({**{k:c[k] for k in a.KEYS},'method':method,'query_available':result is not None,'forecast_valid':valid,
            'actual_packet_steps':c['packet_steps'],'complete_first_eight':c['complete_first_eight'],'collection_reason':c['reason'],
            'h1_raw_error_m':one['raw_m'],'h1_loss_nm':one['loss_nm'],'h1_reason':one['reason'],'h1_capped':one['capped'],
            'h8_raw_rmse_m':multi['raw_m'],'h8_loss_nm':multi['loss_nm'],'h8_reason':multi['reason'],'h8_capped':multi['capped']})
    return out


def quantile(values,num,den):
    values=sorted(int(v) for v in values);position=Fraction((len(values)-1)*num,den);lo=position.numerator//position.denominator;weight=position-lo
    return Fraction(values[lo])*(1-weight)+Fraction(values[min(lo+1,len(values)-1)])*weight


def fraction_record(v,denom=1):
    value=v/denom
    return {'numerator':value.numerator,'denominator':value.denominator,'metres':float(value/1000000000)}


def statistics(rows,split):
    count=len(a.population(split));by=defaultdict(list)
    for row in rows:by[row['method']].append(row)
    io.require(set(by)==set(METHODS) and all(len(v)==count for v in by.values()),'complete equal model denominators')
    summaries={}
    for method,rs in by.items():
        raw1=[r['h1_raw_error_m'] for r in rs if r['h1_raw_error_m'] is not None];raw8=[r['h8_raw_rmse_m'] for r in rs if r['h8_raw_rmse_m'] is not None]
        summaries[method]={'allocated':count,'complete_actual_packets':sum(r['complete_first_eight'] for r in rs),'invalid_saved_forecasts':sum(r['forecast_valid'] is False for r in rs),
            'mean_h1_loss_m':sum(r['h1_loss_nm'] for r in rs)/count/1e9,'mean_h8_loss_m':sum(r['h8_loss_nm'] for r in rs)/count/1e9 if method in H8 else None,
            'valid_h1_count':len(raw1),'mean_valid_h1_raw_error_m':sum(raw1)/len(raw1) if raw1 else None,'h1_capped_count':sum(r['h1_capped'] for r in rs),
            'valid_h8_count':len(raw8),'mean_valid_h8_raw_rmse_m':sum(raw8)/len(raw8) if raw8 else None,'h8_capped_count':sum(r['h8_capped'] for r in rs),
            'h8_missing_reasons':dict(Counter(r['h8_reason'] for r in rs if r['h8_reason']))}
    result={'classification':'PREDICTION_COMPONENT_NOT_TASK_LOSS','split':split,'summaries':summaries,'qualification':'NOT_APPLICABLE_CAL'}
    if split=='CAL':
        empirical={}
        for method in METHODS:
            if method not in H8:empirical[method]=None;continue
            values=[r['h8_raw_rmse_m'] for r in by[method] if r['h8_raw_rmse_m'] is not None]
            empirical[method]={'complete_valid_count':len(values),'raw_rmse_quantiles_m':{str(q):float(np.quantile(values,q)) if values else None for q in (.5,.9,.95)},
                'full_allocated_loss_quantiles_nm':{str(q):float(quantile([r['h8_loss_nm'] for r in by[method]],int(q*100),100)) for q in (.5,.9,.95)}}
        result['empirical_only_not_probability_guarantee']=empirical;return result
    io.require(split=='QUAL','independent QUAL only');rng=np.random.default_rng(2026102440)
    draws=np.concatenate([rng.choice(np.array([g for g in range(18) if g%3==s]),size=(10000,6),replace=True) for s in range(3)],axis=1)
    draws_sha=io.digest(draws.tolist());comparisons={};principal=by['SS_SENT']
    def totals(rs,key):
        return np.array([sum(r[key] for r in rs if r['group']==g) for g in range(18)],dtype=np.int64)
    for method in ('SS_NO_SENT','DIRECT_MLP_H8'):
        differences=totals(principal,'h8_loss_nm')-totals(by[method],'h8_loss_nm');samples=differences[draws].sum(1)
        lo=quantile(samples,1,40);hi=quantile(samples,39,40)
        comparisons[method]={'mean':fraction_record(Fraction(int(differences.sum())),count),'ci95_low':fraction_record(lo,count),'ci95_high':fraction_record(hi,count),
            'upper_strictly_below_zero':hi<0,'independent_groups':18,'group_totals_difference_nm':differences.tolist()}
    coverage={}
    for task in io.TASKS:
        for initial in ('NOMINAL','BIASED'):
            for condition in ('UNCHANGED','CHANGED'):
                for packet in ('FIXED8','RANDOM8'):
                    key='/'.join((task,initial,condition,packet));coverage[key]=sum(r['complete_first_eight'] for r in principal if (r['task'],r['initial_kind'],r['context'],r['packet_kind'])==(task,initial,condition,packet))
    gates={'both_co_primary_intervals_pass':all(v['upper_strictly_below_zero'] for v in comparisons.values()),
        'H8_all_point_controls_pass':all(sum(r['h8_loss_nm'] for r in principal)<sum(r['h8_loss_nm'] for r in by[method]) for method in ('DIRECT_RIDGE_H8','PERSIST_ZERO','SS_CURRENT_SENT')),
        'H1_both_strong_controls_pass':all(sum(r['h1_loss_nm'] for r in principal)<sum(r['h1_loss_nm'] for r in by[method]) for method in ('HISTORY_LINEAR10','QUADRATIC_STATE20')),
        'all_24_cells_at_least_three_complete':all(v>=3 for v in coverage.values()),
        'all_18_groups_have_complete':all(any(r['group']==g and r['complete_first_eight'] for r in principal) for g in range(18)),
        'no_invalid_saved_forecast':all(r['forecast_valid'] is not False for r in rows)}
    result.update({'co_primary_comparisons':comparisons,'bootstrap_draws_sha256':draws_sha,'coverage':coverage,'gates':gates,
        'qualification':'QUALIFIED_FORWARD_COMPONENT_ONLY' if all(gates.values()) else 'NOT_QUALIFIED','task_gain_or_safety_or_publication_qualified':False})
    return result


def evaluate(path,split):
    start=perf_counter_ns();m=a.checked(path);root=Path(path).parent;out=root/split.lower();audit=io.read(out/'audit.json')
    io.require(audit['integrity']=='PASSED' and audit['native_target_updates_bit_exact'] and split in ('CAL','QUAL'),'audited prediction/native phase')
    for n,h in audit['artifact_sha256'].items():io.require(io.sha(out/n)==h,'audited prediction source changed')
    identity={k:m[k] for k in a.IDENTITY};journal=GroupedJournal(io.rows(out/'events.jsonl.gz'),a.KEYS,identity);rows=[]
    for c in io.rows(out/'cases.jsonl.gz'):rows.extend(loss_rows(c,journal.take_case(c)))
    journal.finish();result=statistics(rows,split);folder=root/(split.lower()+'_evaluation');folder.mkdir(exist_ok=False)
    io.write(folder/'case_losses.json',rows);io.write(folder/'statistics.json',result)
    io.write(folder/'completion.json',{'status':'EVALUATED_PENDING_INDEPENDENT_STATISTICS','manifest_id':m['manifest_id'],
        'artifact_sha256':{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()},'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0})
    return result


def lock(path):
    m=a.checked(path);root=Path(path).parent;io.require(not (root/'qual').exists(),'lock before any QUAL data')
    for p in (root/'training/audit.json',root/'cal/audit.json',root/'cal_evaluation/audit.json'):io.require(io.read(p)['integrity']=='PASSED','independent TRAIN/CAL prerequisites')
    rows=io.read(root/'cal/trajectory_audit.json');io.require(all(any(r['task']==t and r['complete_first_eight'] for r in rows) for t in io.TASKS),'CAL task support')
    names=['training/models.json','training/completion.json','training/audit.json','cal/completion.json','cal/audit.json','cal_evaluation/statistics.json','cal_evaluation/case_losses.json','cal_evaluation/audit.json']
    value={'status':'FROZEN_BEFORE_QUAL','manifest_id':m['manifest_id'],'artifact_sha256':{n:io.sha(root/n) for n in names},'locked_unix_ns':time_ns(),
        'selection_or_threshold_fitting':False,'no_extra_models_or_hyperparameters_selected':True}
    io.write(root/'model_lock.json',value);return value
