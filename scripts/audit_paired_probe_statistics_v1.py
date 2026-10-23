"""Independent numeric reconstruction from case outcomes; no primary stats import."""
import argparse
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scripts import run_strong_chronological_reference_v1 as io
from src.probe.cache_acquisition_evidence_v1 import digest

ARMS=('REUSE_OLD','PROBE_KEEP','PROBE_UPDATE','PROBE_UPDATE_KEEP')
NAMES=('total_keep','motion_budget','update_keep','total_strict','fallback')


def contrasts(row,j):
    expected=[(f,p) for f in range(1,j+1) for p in ARMS]
    if [(v['future'],v['program']) for v in row['evaluations']]!=expected:raise ValueError('raw ordered outcomes incomplete')
    table=[];losses=[]
    for f in range(1,j+1):
        values={v['program']:v['outcome']['deadline_loss'] for v in row['evaluations'] if v['future']==f}
        r,p,u,k=(values[name] for name in ARMS)
        if any(type(v) is not int or not 0<=v<=500 for v in (r,p,u,k)):raise ValueError('integer deadline loss required')
        c=[r-k,r-p,p-k,r-u,u-k]
        if c[0]!=c[1]+c[2]:raise ValueError('pathwise controlled-effect identity')
        table.append(c);losses.append([r,p,u,k])
    return np.asarray(table,float),np.asarray(losses,float)


def covariance(array):
    x=np.asarray(array,float);center=x-x.sum(axis=0)/len(x)
    return sum(np.outer(row,row) for row in center)/(len(x)-1)


def rebuild(m,s,phase):
    j=m['config'][phase.lower()]['fresh_futures'];pairs=[]
    for row in s['cases']:
        if row['disposition']=='WARM_ELIGIBLE':
            values,losses=contrasts(row,j);pairs.append((row,values,losses))
    methods={}
    fields=(('mean_deadline_loss','deadline_loss'),('mean_logical_steps','total_steps'),('mean_physical_suffix_steps','suffix_steps'),
            ('mean_probe_suffix_steps','fixed_probe_suffix_steps'),('mean_policy_suffix_steps','policy_suffix_steps'))
    for arm in ARMS:
        outcomes=[v['outcome'] for r,_,_ in pairs for v in r['evaluations'] if v['program']==arm];count=len(outcomes)
        methods[arm]={'cases':count,'successes':sum(int(v['success']) for v in outcomes),'stops':sum(int(v['stopped']) for v in outcomes),
            **{name:sum(v[field] for v in outcomes)/count if count else None for name,field in fields}}
    nested=None;means=[v.sum(axis=0)/j for _,v,_ in pairs]
    if len(pairs)>=2:
        covs=[covariance(v) for _,v,_ in pairs];within=sum(covs)/len(covs);observed=covariance(means);noise=within/j
        nested={'contexts':len(pairs),'fresh_futures_per_context':j,'contrast_order':list(NAMES),'mean_contrast':(sum(means)/len(means)).tolist(),
            'context_mean_contrasts':[v.tolist() for v in means],'within_future_covariance_mean':within.tolist(),
            'observed_context_mean_covariance':observed.tolist(),'mc_mean_noise_covariance':noise.tolist(),
            'noise_corrected_finite_source_covariance':(observed-noise).tolist(),
            'per_context_mc_standard_error':[np.sqrt(np.diag(v)/j).tolist() for v in covs],
            'per_context_both_strict_signs_observed':[[bool(min(v[:,k])<0 and max(v[:,k])>0) for k in range(5)] for _,v,_ in pairs]}
    groups=[]
    for key in ('task','family_oracle','schedule_oracle'):
        for value in sorted({r[key] for r,_,_ in pairs}):
            selected=[means[i] for i,(r,_,_) in enumerate(pairs) if r[key]==value]
            groups.append({'field':key,'value':value,'contexts':len(selected),'mean_contrast':(sum(selected)/len(selected)).tolist()})
    recommendations={}
    for method in ('UNCERTAINTY4','TASK_IVR4'):
        total=0;count=0;actions={}
        for r,_,loss in pairs:
            action=r['references'][method]['action'];actions[action]=actions.get(action,0)+1
            if action=='STOP_PUBLIC_CHECK':total+=500*j
            else:
                if action not in ('RUN_CACHED','REFRESH8'):raise ValueError('unknown saved reference action')
                total+=sum(loss[:,0 if action=='RUN_CACHED' else 2])
            count+=j
        recommendations[method]={'contexts':len(pairs),'actions':actions,'mean_current_state_deadline_loss':float(total/count) if count else None}
    bootstrap=None
    if phase=='MAIN' and pairs:
        streams=m['population_oracle'][phase];ids=sorted(v['stream'] for v in streams)
        strata=sorted({(v['family_oracle'],v['schedule_oracle']) for v in streams})
        cells=[[v['stream'] for v in streams if (v['family_oracle'],v['schedule_oracle'])==key] for key in strata]
        cells=[sorted(v) for v in cells]
        counts={k:0 for k in ids};sums={k:np.zeros(5) for k in ids}
        for mean,(row,_,_) in zip(means,pairs):counts[row['stream']]+=1;sums[row['stream']]+=mean
        rng=np.random.default_rng(20261021);draws=[];undefined=0
        for _ in range(10000):
            multiplicities={k:0 for k in ids}
            for cell in cells:
                for picked in rng.choice(cell,len(cell),replace=True):multiplicities[int(picked)]+=1
            denom=sum(multiplicities[k]*counts[k] for k in ids)
            if denom:draws.append(sum(multiplicities[k]*sums[k] for k in ids)/denom)
            else:undefined+=1
        bootstrap={'contrast_order':list(NAMES),'point':(sum(sums.values())/sum(counts.values())).tolist(),'samples':10000,'seed':20261021,
            'source_streams':len(ids),'strata':len(strata),'stratum_order':[list(v) for v in strata],'undefined_draws':undefined,
            'percentile_95':None if undefined else np.quantile(draws,[.025,.975],axis=0).T.tolist()}
    return {'source_units':s['source_units'],'dispositions':{k:sum(int(r['disposition']==k) for r in s['cases']) for k in ('COLD_SOURCE','WARM_PREFIX_ENDED','WARM_ELIGIBLE')},
        'contexts':len(pairs),'fresh_futures_per_context':j,'contrast_order':list(NAMES),'methods':methods,'nested':nested,'groups':groups,
        'saved_recommendations':recommendations,'stream_bootstrap':bootstrap,'universal_complete_hidden_state_qualification':False}


def remove_scope(value):
    if isinstance(value,dict):return {k:remove_scope(v) for k,v in value.items() if k!='scope'}
    if isinstance(value,list):return [remove_scope(v) for v in value]
    return value


def compare(actual,expected,path='statistics'):
    checked=0;maximum=0.
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or set(actual)!=set(expected):raise ValueError(path+' field set differs')
        for key,value in expected.items():
            n,d=compare(actual[key],value,path+'.'+key);checked+=n;maximum=max(maximum,d)
    elif isinstance(expected,list):
        if not isinstance(actual,list) or len(actual)!=len(expected):raise ValueError(path+' list size differs')
        for k,(a,e) in enumerate(zip(actual,expected)):
            n,d=compare(a,e,path+'.'+str(k));checked+=n;maximum=max(maximum,d)
    elif type(expected) in (int,float):
        if type(actual) not in (int,float) or not np.isfinite(actual) or not np.isclose(actual,expected,atol=1e-8,rtol=1e-12):raise ValueError(path+' numeric mismatch')
        checked=1;maximum=abs(float(actual)-float(expected))
    elif actual!=expected or type(actual)!=type(expected):raise ValueError(path+' nonnumeric value differs')
    return checked,maximum


def audit(path,phase):
    started=perf_counter_ns();m=io.read(path);identity={k:m[k] for k in io.IDENTITY};folder=path.parent/phase.lower();output=path.parent/(phase.lower()+'_analysis_v1')
    if digest({k:v for k,v in m.items() if k!='manifest_id'})!=m['manifest_id'] or any(io.sha(ROOT/n)!=h for n,h in m['input_sha256'].items()):raise ValueError('frozen source/manifest differs')
    s=io.read(folder/'summary.json');record=io.read(path.parent/(phase.lower()+'_audit.json'));saved=io.read(output/'statistics.json');cost=io.read(output/'costs.json')
    completion=io.read(output/'completion.json')
    if record['integrity']!='PASSED' or any(v['summary_sha256']!=io.sha(folder/'summary.json') for v in (record,saved,completion)):raise ValueError('matching source record/analysis required')
    if any(io.sha(output/n)!=h for n,h in completion['artifact_sha256'].items()):raise ValueError('analysis artifact bytes changed')
    if any(v[k]!=expected for v in (saved,cost,completion) for k,expected in identity.items()):raise ValueError('analysis identity')
    fields,error=compare(remove_scope(saved['statistics']),rebuild(m,s,phase))
    source=sum(r['source']['outcome']['total_steps'] for r in s['cases'])
    evaluator=sum(v['outcome']['suffix_steps'] for r in s['cases'] for v in r['evaluations'])
    sentinel=sum(v['outcome']['suffix_steps'] for r in s['cases'] for v in r['sentinels'])
    if source+evaluator+sentinel!=s['controlled_steps']:raise ValueError('source/evaluator physical cost identity')
    expected={'actual_controlled_steps':source+evaluator+sentinel,'actual_controlled_resets':s['source_units'],'actual_source_steps':source,
        'actual_evaluator_suffix_steps':evaluator,'actual_sentinel_suffix_steps':sentinel,'physical_lifecycle':record['lifecycle'],'recorded_computation':record['recorded_computation'],
        'collection_body_wall_ns':s['collection_body_wall_ns'],'audit_policy_queries':record['audit_policy_queries'],
        'audit_shared_fitter_attempts':record['audit_shared_fitter_attempts'],'audit_shared_optimizer_nfev':record['audit_shared_optimizer_nfev'],
        'audit_wall_ns':record['audit_wall_ns'],'modern_nominal_steps_full':3840,'modern_nominal_controlled_resets_full':480,
        'nominal_steps_per_source_unit':3840/s['source_units'],'restore_qualification_prior_steps':4032,'restore_qualification_prior_controlled_resets':13,
        'restore_qualification_prior_all_resets':663,'restore_qualification_prior_requested_frames':351660,
        'nominal_model_fits':0,'selector_fits':0,'policy_weight_updates':0,'api_calls':0}
    strong=io.read(ROOT/m['config']['strong_source_manifest']);previous=io.read(ROOT/strong['config']['source_costs'])
    expected['modern_nominal_lifecycle_full']=previous['joint_source_full_lifecycle']
    if phase=='MAIN':
        smoke=io.read(path.parent/'smoke/summary.json')
        expected['separate_smoke']={'actual_controlled_steps':smoke['controlled_steps'],'actual_controlled_resets':smoke['controlled_resets'],
            'physical_lifecycle':smoke['lifecycle'],'recorded_computation':smoke['counters'],'collection_body_wall_ns':smoke['collection_body_wall_ns']}
    subset={k:cost[k] for k in expected};n,d=compare(subset,expected,'costs');fields+=n;error=max(error,d)
    if type(cost['analysis_body_wall_ns']) is not int or cost['analysis_body_wall_ns']<0:raise ValueError('analysis timing metadata')
    return {**identity,'phase':phase,'integrity':'PASSED','numeric_fields_checked':fields,'max_absolute_difference':error,
        'summary_sha256':io.sha(folder/'summary.json'),'statistics_sha256':io.sha(output/'statistics.json'),'costs_sha256':io.sha(output/'costs.json'),
        'audit_body_wall_ns':perf_counter_ns()-started,'new_environment_steps':0,'new_api_calls':0,
        'scope':'Independent raw-outcome covariance, negative retained noise subtraction, grouped effects and whole-stream ratio bootstrap. Physical/computational costs cross-checked with record replay. Timing copied from bound sources is metadata, not independent performance replication.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--phase',choices=['SMOKE','MAIN'],required=True);args=parser.parse_args()
    result=audit(args.manifest.resolve(),args.phase);io.write(args.manifest.resolve().parent/(args.phase.lower()+'_statistics_audit.json'),result,exclusive=True)
    print(result['integrity'],result['numeric_fields_checked'],result['max_absolute_difference'],flush=True)
