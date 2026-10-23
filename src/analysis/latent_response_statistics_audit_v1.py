"""Independent rational/Decimal losses and whole-group integer resampling."""
from collections import defaultdict,Counter
from decimal import Decimal,localcontext,ROUND_HALF_EVEN
from fractions import Fraction
from math import isclose
from math import fsum
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import latent_response_io_v1 as a
from src.analysis.command_target_sources_v1 import GroupedJournal
from src.probe.latent_response_query_v1 import METHODS
io=a.io;H8=METHODS[:6]


def compare(actual,expected,path='root'):
    if type(expected) is dict:
        io.require(type(actual) is dict and set(actual)==set(expected),'independent statistics keys '+path)
        return sum(compare(actual[k],v,path+'/'+k) for k,v in expected.items())
    if type(expected) in (tuple,list):
        io.require(type(actual) in (tuple,list) and len(actual)==len(expected),'independent statistics length '+path)
        return sum(compare(x,y,path+f'/{i}') for i,(x,y) in enumerate(zip(actual,expected)))
    if type(expected) is float:io.require(type(actual) is float and isclose(actual,expected,rel_tol=1e-10,abs_tol=1e-12),'descriptive float '+path)
    else:io.require(type(actual) is type(expected) and actual==expected,'exact statistics field '+path)
    return 1


def loss(predicted,actual,h,valid,present):
    if not present:return None,1000000000,'NO_MEASUREMENT_ENTRY',False
    if not valid:return None,1000000000,'INVALID_SAVED_FORECAST',False
    if len(actual)<h:return None,1000000000,'SHORT_ACTUAL_PACKET',False
    terms=[]
    for k in range(h):
        for j in range(2):terms.append((Fraction(str(float(predicted[k][j])))-Fraction(str(float(actual[k][j]))))**2)
    squared=sum(terms,Fraction(0))/(2*h)
    with localcontext() as ctx:
        ctx.prec=80;root=(Decimal(squared.numerator)/Decimal(squared.denominator)).sqrt();nm=int((min(Decimal(1),root)*10**9).to_integral_value(rounding=ROUND_HALF_EVEN))
    return float(root),nm,None,root>1


def case_rows(c,events):
    result=next((e['public_payload']['result'] for e in events if e['event']=='AGENT_EVENT' and e['agent_event']=='FORECAST_RESULT'),None)
    physical=[e for e in events if e['event']=='STEP_COMPLETE'];entry=c['entry_at_calls'];observed=[]
    if entry is not None:
        position=c['initial']['observation'] if entry==0 else physical[entry-1]['after']['observation']
        for e in physical[entry:]:observed.append([float(e['after']['observation'][j])-float(position[j]) for j in range(2)])
    rows=[]
    for method in METHODS:
        pred=None if result is None else result['forecasts'][method];valid=None if pred is None else pred['valid'];values=None if not valid else pred['displacements']
        r1=loss(values,observed,1,valid,result is not None);r8=loss(values,observed,8,valid,result is not None) if method in H8 else (None,None,'ONE_STEP_MODEL_ONLY',False)
        rows.append({**{k:c[k] for k in a.KEYS},'method':method,'query_available':result is not None,'forecast_valid':valid,'actual_packet_steps':c['packet_steps'],
            'complete_first_eight':c['complete_first_eight'],'collection_reason':c['reason'],'h1_raw_error_m':r1[0],'h1_loss_nm':r1[1],'h1_reason':r1[2],'h1_capped':r1[3],
            'h8_raw_rmse_m':r8[0],'h8_loss_nm':r8[1],'h8_reason':r8[2],'h8_capped':r8[3]})
    return rows


def percentile(values,numerator,denominator):
    seq=sorted(int(v) for v in values);position=(len(seq)-1)*numerator;index,remainder=divmod(position,denominator)
    return Fraction(seq[index]*(denominator-remainder)+seq[min(index+1,len(seq)-1)]*remainder,denominator)


def record(value):return {'numerator':value.numerator,'denominator':value.denominator,'metres':float(value/Fraction(1000000000))}


def independently_summarize(rows,split):
    n=len(a.population(split));by={m:[r for r in rows if r['method']==m] for m in METHODS};summaries={}
    for method,rs in by.items():
        io.require(len(rs)==n,'whole allocation denominator')
        raw1=[r['h1_raw_error_m'] for r in rs if r['h1_raw_error_m'] is not None];raw8=[r['h8_raw_rmse_m'] for r in rs if r['h8_raw_rmse_m'] is not None]
        summaries[method]={'allocated':n,'complete_actual_packets':sum(r['complete_first_eight'] for r in rs),'invalid_saved_forecasts':sum(r['forecast_valid'] is False for r in rs),
            'mean_h1_loss_m':sum(r['h1_loss_nm'] for r in rs)/n/1e9,'mean_h8_loss_m':sum(r['h8_loss_nm'] for r in rs)/n/1e9 if method in H8 else None,
            'valid_h1_count':len(raw1),'mean_valid_h1_raw_error_m':fsum(raw1)/len(raw1) if raw1 else None,'h1_capped_count':sum(r['h1_capped'] for r in rs),
            'valid_h8_count':len(raw8),'mean_valid_h8_raw_rmse_m':fsum(raw8)/len(raw8) if raw8 else None,'h8_capped_count':sum(r['h8_capped'] for r in rs),
            'h8_missing_reasons':dict(Counter(r['h8_reason'] for r in rs if r['h8_reason']))}
    result={'classification':'PREDICTION_COMPONENT_NOT_TASK_LOSS','split':split,'summaries':summaries,'qualification':'NOT_APPLICABLE_CAL'}
    if split=='CAL':
        empirical={}
        for method in METHODS:
            if method not in H8:empirical[method]=None;continue
            values=sorted(r['h8_raw_rmse_m'] for r in by[method] if r['h8_raw_rmse_m'] is not None)
            def raw_quantile(num,den):
                if not values:return None
                index,remainder=divmod((len(values)-1)*num,den)
                return float(Fraction.from_float(values[index])*(1-Fraction(remainder,den))+Fraction.from_float(values[min(index+1,len(values)-1)])*Fraction(remainder,den))
            empirical[method]={'complete_valid_count':len(values),'raw_rmse_quantiles_m':{str(q):raw_quantile(num,den) for q,num,den in ((.5,1,2),(.9,9,10),(.95,19,20))},
                'full_allocated_loss_quantiles_nm':{str(q):float(percentile([r['h8_loss_nm'] for r in by[method]],num,den)) for q,num,den in ((.5,1,2),(.9,9,10),(.95,19,20))}}
        result['empirical_only_not_probability_guarantee']=empirical;return result
    rng=np.random.default_rng(2026102440);columns=[]
    for s in range(3):columns.append(rng.choice(np.arange(s,18,3),size=(10000,6),replace=True))
    draws=np.column_stack(columns);principal=by['SS_SENT'];comparisons={}
    for method in ('SS_NO_SENT','DIRECT_MLP_H8'):
        group=[]
        for g in range(18):group.append(sum(r['h8_loss_nm'] for r in principal if r['group']==g)-sum(r['h8_loss_nm'] for r in by[method] if r['group']==g))
        samples=np.asarray(group,dtype=np.int64)[draws].sum(axis=1);lo=percentile(samples,1,40);hi=percentile(samples,39,40)
        comparisons[method]={'mean':record(Fraction(sum(group),n)),'ci95_low':record(lo/n),'ci95_high':record(hi/n),
            'upper_strictly_below_zero':hi<0,'independent_groups':18,'group_totals_difference_nm':group}
    coverage={}
    for t in io.TASKS:
        for i in ('NOMINAL','BIASED'):
            for c in ('UNCHANGED','CHANGED'):
                for p in ('FIXED8','RANDOM8'):coverage['/'.join((t,i,c,p))]=sum(r['complete_first_eight'] for r in principal if (r['task'],r['initial_kind'],r['context'],r['packet_kind'])==(t,i,c,p))
    def total(method,key):return sum(r[key] for r in by[method])
    gates={'both_co_primary_intervals_pass':all(v['upper_strictly_below_zero'] for v in comparisons.values()),
        'H8_all_point_controls_pass':all(total('SS_SENT','h8_loss_nm')<total(m,'h8_loss_nm') for m in ('DIRECT_RIDGE_H8','PERSIST_ZERO','SS_CURRENT_SENT')),
        'H1_both_strong_controls_pass':all(total('SS_SENT','h1_loss_nm')<total(m,'h1_loss_nm') for m in ('HISTORY_LINEAR10','QUADRATIC_STATE20')),
        'all_24_cells_at_least_three_complete':all(v>=3 for v in coverage.values()),'all_18_groups_have_complete':all(any(r['group']==g and r['complete_first_eight'] for r in principal) for g in range(18)),
        'no_invalid_saved_forecast':not any(r['forecast_valid'] is False for r in rows)}
    result.update({'co_primary_comparisons':comparisons,'bootstrap_draws_sha256':io.digest(draws.tolist()),'coverage':coverage,'gates':gates,
        'qualification':'QUALIFIED_FORWARD_COMPONENT_ONLY' if all(gates.values()) else 'NOT_QUALIFIED','task_gain_or_safety_or_publication_qualified':False})
    return result


def audit(path,split):
    start=perf_counter_ns();m=a.checked(path);root=Path(path).parent;out=root/(split.lower()+'_evaluation');done=io.read(out/'completion.json')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'evaluation bytes')
    identity={k:m[k] for k in a.IDENTITY};journal=GroupedJournal(io.rows(root/split.lower()/'events.jsonl.gz'),a.KEYS,identity);rows=[]
    for c in io.rows(root/split.lower()/'cases.jsonl.gz'):rows.extend(case_rows(c,journal.take_case(c)))
    journal.finish();fields=compare(io.read(out/'case_losses.json'),rows);fields+=compare(io.read(out/'statistics.json'),independently_summarize(rows,split))
    a.checked(path);result={'integrity':'PASSED','manifest_id':m['manifest_id'],'split':split,'independently_checked_fields':fields,
        'artifact_sha256':done['artifact_sha256'],'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0,
        'main_loss_and_statistics_disabled':True,'integer_nanometre_gates_and_rational_intervals_exact':True}
    io.write(out/'audit.json',result);return result
