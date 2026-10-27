"""Separate Decimal endpoint/group accounting, reading actual saved forecasts."""
from pathlib import Path
from collections import defaultdict
from decimal import Decimal,localcontext,ROUND_HALF_EVEN
from fractions import Fraction
from time import perf_counter_ns
import numpy as np
from src.analysis import history_response_io_v1 as a
from src.analysis.response_action_audit_v1 import same
io=a.io


def endpoint(pred,left,right):
    with localcontext() as ctx:
        ctx.prec=80
        square=Decimal(0)
        for j in range(2):
            e=Decimal(str(right[j]))-Decimal(str(left[j]))-Decimal(str(pred[j]));square+=e*e
        rmse=(square/Decimal(2)).sqrt();rmse=min(rmse,Decimal(1))
        return int((rmse*Decimal(1000000000)).quantize(Decimal(1),rounding=ROUND_HALF_EVEN))


def reconstructed(path,split):
    folder=Path(path).parent/split.lower();cases=list(io.rows(folder/'cases.jsonl.gz'));traces=list(io.rows(folder/'public_trajectories.jsonl.gz'));rows=[]
    for i in range(len(cases)//3):
        trio=cases[i*3:i*3+3];tt=traces[i*3:i*3+3];base=trio[0];record=base['forecast_record'];lengths=[c['packet_steps'] for c in trio]
        for li,ri in ((0,1),(0,2),(1,2)):
            pair=trio[li]['packet_kind']+'__'+trio[ri]['packet_kind']
            for h in (8,16):
                available=min(lengths[li],lengths[ri])>=h;valid=record is not None and record['forecast_error'] is None
                reason='ENTRY_UNAVAILABLE' if record is None else 'INVALID_FORECAST' if not valid else 'SHORT_OR_TERMINAL_PAIR' if not available else 'AVAILABLE'
                for method in ('ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN','HISTORY_KERNEL'):
                    value=1000000000
                    if reason=='AVAILABLE':
                        positions=[tt[k]['steps'][trio[k]['entry_at_calls']+h-1]['after']['observation'][:2] for k in (li,ri)]
                        value=endpoint(record['forecasts'][method][pair][h-1],*positions)
                    rows.append({k:base[k] for k in ('group','task','context','boundary','acquisition_action')}|dict(family_index=i,pair=pair,horizon=h,method=method,loss_nm=value,availability=reason))
    return rows


def audit(path,split):
    from src.analysis.release_learning_guard_v1 import read_only
    a.checked(path);root=Path(path).parent;out=root/(split.lower()+'_evaluation');r=io.read(out/'result.json');start=perf_counter_ns();guard={}
    for n,h in r['artifact_sha256'].items():same(io.sha(out/n),h)
    with read_only(guard):
        actual=io.read(out/'endpoint_scores.json');expected=reconstructed(path,split);same(actual,expected,'independent saved-outcome decimal scores')
        tables=io.read(out/'panels.json');maximum=0.
        for t in tables:
            group=defaultdict(list)
            for row in expected:
                if row['method']==t['method'] and all(row[k]==v for k,v in t['strata'].items()):group[row['group']].append(row)
            value=sum(Fraction(sum(r['loss_nm'] for r in rr),len(rr)) for rr in group.values())/len(group)/1000000000
            maximum=max(maximum,abs(float(value)-t['mean_endpoint_loss_m']));io.require(abs(float(value)-t['mean_endpoint_loss_m'])<=1e-15,'independent equal-group mean')
            same(t['allocated_endpoints'],sum(len(v) for v in group.values()));same(t['available_endpoints'],sum(r['availability']=='AVAILABLE' for rr in group.values() for r in rr))
            available={g:[r['loss_nm'] for r in rr if r['availability']=='AVAILABLE'] for g,rr in group.items()};available={g:v for g,v in available.items() if v};same(t['available_groups'],len(available))
            if not available:same(t['available_only_mean_endpoint_loss_m'],None)
            else:
                only=sum(Fraction(sum(v),len(v)) for v in available.values())/len(available)/10**9
                io.require(abs(float(only)-t['available_only_mean_endpoint_loss_m'])<=1e-15,'independent observed-only descriptive mean')
        if split=='CAL':
            same(r['selected_model'],'HISTORY_KERNEL')
        else:
            rng=np.random.default_rng(2026102960);draws=np.concatenate([rng.choice([j,j+3,j+6],size=(10000,3),replace=True) for j in range(3)],axis=1);selected=r['selected_model'];indexed=defaultdict(dict)
            for x in expected:indexed[(x['group'],x['family_index'],x['pair'],x['horizon'])][x['method']]=x['loss_nm']
            for baseline in ('ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN'):
                values=[]
                for g in range(9):
                    d=[v[selected]-v[baseline] for k,v in indexed.items() if k[0]==g];same(len(d),72);values.append(float(Fraction(sum(d),72*10**9)))
                saved=r['co_primary'][baseline];io.require(np.allclose(values,saved['group_mean_selected_minus_baseline_m'],atol=1e-15,rtol=0),'independent paired group differences')
                samples=sorted(float(sum(values[int(j)] for j in draw)/9) for draw in draws);ci=[]
                for p in (.025,.975):
                    position=(len(samples)-1)*p;lo=int(position);fraction=position-lo;ci.append(samples[lo]+fraction*(samples[min(lo+1,len(samples)-1)]-samples[lo]))
                io.require(np.allclose(ci,saved['bootstrap95_m'],atol=1e-15,rtol=0),'independent stratified whole-group bootstrap')
            same(r['gates']['all_five_primary_CI_upper_negative'],all(v['bootstrap95_m'][1]<0 for v in r['co_primary'].values()))
            cases=list(io.rows(root/'qual/cases.jsonl.gz'));complete_groups=set();availability={t+'__'+c+'__'+p:0 for t in io.TASKS for c in ('UNCHANGED','CHANGED') for p in ('IN_TASK','MOVE')}
            for i in range(0,len(cases),3):
                trio=cases[i:i+3];base=trio[0]
                if all(c['packet_steps']==16 for c in trio):complete_groups.add(base['group'])
                key=base['task']+'__'+base['context']+'__'+base['acquisition_action']
                availability[key]+=sum(min(trio[l]['packet_steps'],trio[rr]['packet_steps'])>=16 for l,rr in ((0,1),(0,2),(1,2)))
            same(r['complete_pairs_by_task_context_anchor'],availability);same(r['gates']['minimum_complete_pairs_per_cell'],min(availability.values())>=3)
            same(r['gates']['all9_groups_have_complete_family'],len(complete_groups)==9)
            same(r['gates']['zero_invalid_forecasts'],io.read(root/'qual/audit.json')['invalid_forecasts']==0)
            below=[]
            for field,values in (('task',io.TASKS),('horizon',(8,16))):
                for v in values:
                    means={method:Fraction(sum(x['loss_nm'] for x in expected if x[field]==v and x['method']==method),sum(x[field]==v and x['method']==method for x in expected)) for method in (selected,'ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN')}
                    good=all(means[selected]<means[b] for b in ('ZERO','INSTANT','FIR','STATE_KERNEL','HISTORY_NN'));below.append(good);same(r['points'][field+'__'+str(v)]['below_all_references'],good)
            same(r['gates']['all_task_and_horizon_points_below_all'],all(below))
            same(r['status'],'QUALIFIED_RESPONSE_CONTRAST_COMPONENT_ONLY' if all(r['gates'].values()) else 'CLOSED_NEGATIVE')
    result=dict(integrity='PASSED',split=split,endpoint_rows=len(expected),panels=len(tables),max_group_mean_difference_m=maximum,
        result_sha256=io.sha(out/'result.json'),score_sha256=io.sha(out/'endpoint_scores.json'),read_only_guard=guard,shared_primitive='RNG_DRAW_ALLOCATION_AND_SAVED_RECORDS_ONLY_NO_SHARED_SCORING_OR_AGGREGATION',
        wall_ns=perf_counter_ns()-start,new_environment_steps=0,new_model_fits=0,online_LLM_API_calls=0)
    io.write(out/'audit.json',result);return result
