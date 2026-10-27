"""Exact binary-float rational algebra and a separately constructed source reader."""
from fractions import Fraction as F
from collections import Counter,defaultdict
from pathlib import Path
from time import perf_counter_ns
import math
import numpy as np
from src.analysis import packet_structure_sources_v1 as a
from src.analysis.command_target_sources_v1 import GroupedJournal
from src.analysis.response_action_audit_v1 import same
io=a.io
META=('split','group','task','context','boundary','acquisition_action')


def fv(x):return [F.from_float(float(v)) for v in x]
def square(x):return sum(v*v for v in x)


def observed(z,p,m,nz,np_,nm):
    z,p,m,nz,np_,nm=map(fv,(z,p,m,nz,np_,nm));e=[(p[j]+m[j])/2-z[j] for j in range(2)];o=[(p[j]-m[j])/2 for j in range(2)]
    ne=[(np_[j]+nm[j])/2-nz[j] for j in range(2)];te=[e[j]-ne[j] for j in range(2)]
    return dict(observed_even_xy_m=e,observed_odd_xy_m=o,native_even_xy_m=ne,tracking_even_xy_m=te,linear_command_class_floor_m2=square(e)/3,
        native_even_term_m2=square(ne)/3,tracking_even_term_m2=square(te)/3,native_tracking_cross_m2=sum(2*x*y for x,y in zip(ne,te))/3,even_decomposition_error_m2=F(0))


def prediction(z,p,m,forecasts):
    z,p,m=map(fv,(z,p,m));q=list(map(fv,forecasts));v=[[(p[j]-z[j]),(m[j]-z[j]),(m[j]-p[j])] for j in range(2)]
    direct=sum((q[k][j]-v[j][k])**2 for j in range(2) for k in range(3))/6
    e=[(p[j]+m[j])/2-z[j] for j in range(2)];o=[(p[j]-m[j])/2 for j in range(2)];ph=[sum(c*q[k][j] for k,c in enumerate((1,-1,-2)))/6 for j in range(2)]
    r=[[q[k][j]-c*ph[j] for j in range(2)] for k,c in enumerate((1,-1,-2))]
    odd=square([ph[j]-o[j] for j in range(2)]);floor=square(e)/3;correction=(sum(square(x) for x in r)-2*sum(e[j]*(r[0][j]+r[1][j]) for j in range(2)))/6
    assert direct==odd+floor+correction
    return dict(saved_pair_mse_m2=direct,linear_command_class_floor_m2=floor,saved_odd_component_error_m2=odd,saved_nonclass_correction_m2=correction,
        saved_class_defect_l2_m=math.sqrt(float(sum(square(x) for x in r))),decomposition_error_m2=F(0))


def numeric_match(actual,expected,name):
    if isinstance(expected,list):
        io.require(isinstance(actual,list) and len(actual)==len(expected),'same vector dimensions '+name)
        for x,y in zip(actual,expected):io.require(math.isclose(x,float(y),rel_tol=2e-11,abs_tol=2e-15),'literal vector '+name)
    else:
        atol=2e-15 if name.endswith('_command') or name.endswith('_l2_m') else 2e-18
        io.require(math.isclose(actual,float(expected),rel_tol=2e-11,abs_tol=atol),'exact rational quantity '+name)


def source_groups():
    """Use public exports for positions; never calls the main family constructor."""
    m=io.read(a.SOURCE/'manifest.json');identity={k:m[k] for k in a.original.IDENTITY};family=0
    for split in a.original.SPLITS:
        folder=a.SOURCE/split.lower();journal=GroupedJournal(io.rows(folder/'events.jsonl.gz'),a.original.KEYS,identity);native=GroupedJournal(io.rows(folder/'private_targets.jsonl.gz'),a.original.KEYS,identity)
        exports=iter(io.rows(folder/'public_trajectories.jsonl.gz'));records=iter(io.rows(folder/'cases.jsonl.gz'));specs=a.original.population(split)
        for offset in range(0,len(specs),3):
            cases=[];traces=[];physical=[];priv=[]
            for spec in specs[offset:offset+3]:
                c=next(records);same({k:c[k] for k in a.original.KEYS},spec);tr=next(exports);same(io.digest(tr),c['public_trajectory_sha256']);e=journal.take_case(c);p=native.take_case(c)
                same(e[-1]['case_record_sha256'],io.digest(c));steps={v['logical_step']:v for v in e if v['event']=='STEP_COMPLETE'};same(len(steps),c['total_steps']);same(len(tr['steps']),c['total_steps'])
                cases.append(c);traces.append(tr);physical.append(steps);priv.append({(v['label'],v['at_calls']):v for v in p})
            for c in cases[1:]:same(c['entry_at_calls'],cases[0]['entry_at_calls']);same(c['entry_witness_oracle'],cases[0]['entry_witness_oracle']);same(c['initial'],cases[0]['initial'])
            yield family,cases,traces,physical,priv;family+=1
        journal.finish();native.finish();io.require(next(records,None) is None and next(exports,None) is None,'no extra independent source rows')
    same(family,288)


def actuator(cases,physical,private,counts):
    base=cases[0];entry=base['entry_at_calls']
    if entry is None:return [[],[],[]],[[],[],[]],[[],[],[]]
    nonce=2026102810+a.original.SPLITS.index(base['split']);noise=np.random.default_rng(np.random.SeedSequence([base['seed'],nonce])).normal(0,.05,(500,3)).astype('<f4')
    counts['deterministic_noise_tapes_regenerated']+=1;counts['deterministic_noise_scalars_regenerated']+=1500;actions=[];limits=[];spaces=[]
    for c,events,native in zip(cases,physical,private):
        values=[];clipped=[];workspace=[];fault=c['destination_oracle'];same(fault['deadzone_xy'],[0.,0.])
        for k in range(c['packet_steps']):
            n=entry+k;e=events[n];same(e['phase'],'EXOGENOUS_PACKET');same(e['noise_cursor_after'],n+1)
            u=np.array(e['command'],dtype='<f4');v=u.copy();v[:2]=np.asarray(fault['matrix_xy'],np.float32)@u[:2]+np.asarray(fault['bias_xy'],np.float32);v[:3]=v[:3]+noise[n]
            expected=[float(min(np.float32(1),max(np.float32(-1),x))) for x in v];same(e['executed_action_oracle'],expected,'independent actuator order')
            before=native[('BEFORE_STEP',n)]['mocap_pos_oracle'][0];actual=native[('AFTER_STEP',n+1)]['mocap_pos_oracle'][0]
            requested=[float(before[j])+float(np.float32(np.float32(expected[j])*np.float32(.01))) for j in range(3)]
            wanted=[max(lo,min(hi,x)) for x,lo,hi in zip(requested,(-.5,.4,.05),(.5,1.,.5))];same(actual,wanted,'independent native box and float32 increment')
            values.append(expected);clipped.append(sum(x<np.float32(-1) or x>np.float32(1) for x in v));workspace.append(sum(x!=y for x,y in zip(requested,wanted)))
            counts['saved_packet_actions_checked']+=1;counts['native_target_updates_checked']+=1
        actions.append(values);limits.append(clipped);spaces.append(workspace)
    return actions,limits,spaces


def input_metrics(actions,limits,workspace,h):
    e=[(F.from_float(actions[1][t][j])+F.from_float(actions[2][t][j]))/2-F.from_float(actions[0][t][j]) for t in range(h) for j in range(3)]
    return dict(applied_even_max_abs_xyz_command=max(abs(x) for x in e),applied_even_l2_xyz_command=math.sqrt(float(square(e))),applied_even_nonzero_scalars=sum(x!=0 for x in e),
        actuator_final_clip_axes=sum(sum(v[:h]) for v in limits),native_workspace_clip_axes=sum(sum(v[:h]) for v in workspace))


def verify_panels(path,rows,models):
    tables=io.read(path);checked=0;indices={}
    for table in tables:
        fields=tuple(table['level'])
        if fields not in indices:
            index=defaultdict(list)
            for row in rows:index[tuple(row[k] for k in fields)+(row.get('method'),)].append(row)
            indices[fields]=index
    for t in tables:
        part=indices[tuple(t['level'])][tuple(t['strata'][k] for k in t['level'])+(t['method'],)];same(t['allocated_family_h_rows'],len(part))
        valid=[r for r in part if r['available']];same(t['available_family_h_rows'],len(valid));family=defaultdict(list)
        for r in valid:family[(r['group'],r['family_index'])].append(r)
        bygroup=defaultdict(list)
        for (g,f),rr in family.items():bygroup[g].append(rr)
        same(t['available_groups'],len(bygroup));same(t['available_families'],len(family))
        for name,value in t['mean'].items():
            if not bygroup:same(value,None);continue
            means=[]
            for group in bygroup.values():
                fm=[sum(F.from_float(float((v if models else v['response'])[name])) for v in rr)/len(rr) for rr in group];means.append(sum(fm)/len(fm))
            exact=sum(means)/len(means);numeric_match(value,exact,name);checked+=1
        if models:
            d=t['mean']['saved_pair_mse_m2'];r=t['floor_fraction_of_group_mean_mse']
            if d is None or d==0:same(r,None)
            else:numeric_match(r,F.from_float(t['mean']['linear_command_class_floor_m2'])/F.from_float(d),'ratio')
    return dict(panels=len(tables),scalar_means_reconstructed=checked)


def audit(path):
    from src.analysis.release_learning_guard_v1 import read_only
    from unittest.mock import patch
    from src.analysis import packet_structure_math_v1 as disabled
    def denied(*args,**kw):raise RuntimeError('main structure algebra disabled in rational audit')
    start=perf_counter_ns();a.checked(path);root=Path(path).parent;out=root/'analysis';done=io.read(out/'completion.json');guard={};counts=Counter();registered=io.read(out/'case_register.json')
    for name,h in done['artifact_sha256'].items():same(io.sha(out/name),h)
    observed_rows=list(a.plain_rows(out/'family_horizon_rows.jsonl'));prediction_rows=list(a.plain_rows(out/'saved_prediction_rows.jsonl'));oi=pi=ci=0;exact_checks=0
    with read_only(guard),patch.object(disabled,'response',denied),patch.object(disabled,'saved_error',denied),patch.object(disabled,'actuator_parity',denied):
        for number,cases,traces,physical,native in source_groups():
            base=cases[0];entry=base['entry_at_calls'];lengths=[c['packet_steps'] for c in cases];meta={k:base[k] for k in META};meta['family_index']=number
            for c in cases:
                expected={k:c[k] for k in (*a.original.KEYS,'total_steps','entry_at_calls','packet_steps','reason','success_at_response_horizon')}|dict(family_index=number);same(registered[ci],expected);ci+=1
            acts,limits,spaces=actuator(cases,physical,native,counts);rec=base['forecast_record'];numeric=rec is not None and bool(rec['forecasts']) and rec['forecast_error'] is None
            for h in range(1,17):
                row=observed_rows[oi];oi+=1;available=min(lengths)>=h;reason=None if available else 'NO_COMMON_PACKET_ENTRY' if entry is None else 'AT_LEAST_ONE_ROLE_ENDED_BEFORE_H'
                for k,v in meta.items():same(row[k],v)
                same(row['horizon'],h);same(row['horizon_band'],(h+3)//4);same(row['available'],available);same(row['missing_reason'],reason);same(row['packet_lengths'],dict(zip(a.ROLES,lengths)))
                same(row['original_case_reasons'],dict(zip(a.ROLES,[c['reason'] for c in cases])))
                positions=None
                if available:
                    positions=[tr['steps'][entry+h-1]['after']['observation'][:2] for tr in traces];targets=[ns[('AFTER_STEP',entry+h)]['mocap_pos_oracle'][0][:2] for ns in native]
                    expected=observed(*positions,*targets)
                    for key,v in expected.items():numeric_match(row['response'][key],v,key);exact_checks+=1
                    ip=input_metrics(acts,limits,spaces,h)
                    for key,v in ip.items():
                        if type(v) is int:same(row['actuator'][key],v)
                        else:numeric_match(row['actuator'][key],v,key)
                    counts['observed_three_role_decompositions']+=1
                else:same(row['response'],None);same(row['actuator'],None)
                for method in a.METHODS:
                    p=prediction_rows[pi];pi+=1
                    for k,v in meta.items():same(p[k],v)
                    same(p['horizon'],h);same(p['method'],method);same(p['available'],available and numeric);same(p['missing_reason'],reason if not available else None if numeric else 'NO_SAVED_NUMERIC_PREDICTION')
                    if available and numeric:
                        forecasts=[rec['forecasts'][method][key][h-1] for key in ('ZERO__PLUS','ZERO__MINUS','PLUS__MINUS')];expected=prediction(*positions,forecasts)
                        for key,v in expected.items():numeric_match(p[key],v,key);exact_checks+=1
                        counts['saved_prediction_arithmetic_decompositions']+=1
                    else:
                        for key in ('saved_pair_mse_m2','linear_command_class_floor_m2','saved_odd_component_error_m2','saved_nonclass_correction_m2','saved_class_defect_l2_m','decomposition_error_m2'):same(p[key],None)
                    counts['registered_saved_prediction_slots']+=1
        same((ci,oi,pi),(864,4608,23040));same(dict(counts),done['counters']);stats=dict(observed=verify_panels(out/'observed_panels.json',observed_rows,False),saved=verify_panels(out/'prediction_panels.json',prediction_rows,True))
    a.checked(path)
    result=dict(integrity='PASSED',exact_rational_quantity_checks=exact_checks,cases=ci,family_horizon_rows=oi,registered_prediction_slots=pi,counters=dict(counts),panels=stats,
        main_numeric_implementation_disabled=True,guard=guard,analysis_completion_sha256=io.sha(out/'completion.json'),wall_ns=perf_counter_ns()-start,new_physics=0,new_model_fits=0,new_model_predictions=0,online_LLM_API_calls=0)
    io.write(out/'audit.json',result);return result
