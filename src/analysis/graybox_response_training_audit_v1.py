"""Rebuild public training inputs and numerical fits without production readers."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
import numpy as np
from src.analysis import graybox_response_io_v1 as a,graybox_response_independent_v1 as math
io=a.io

def sources(path):
    root=Path(path).parent;nominal=[];families=[]
    for split in ('NOMINAL','TRAIN'):
        folder=root/split.lower();r=io.read(folder/'audit.json');io.require(r['integrity']=='PASSED','audited physical sources')
        for n,h in r['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'unchanged audited source '+n)
        cc=list(io.rows(folder/'cases.jsonl.gz'));tt=list(io.rows(folder/'public_trajectories.jsonl.gz'));io.require(len(cc)==len(tt)==len(a.population(split)),'all source records')
        for c,t,s in zip(cc,tt,a.population(split)):
            io.require(all(c[k]==v for k,v in s.items()) and c['public_trajectory_sha256']==io.digest(t),'source ownership and public bytes')
        if split=='NOMINAL':
            for c,t in zip(cc,tt):
                nominal.append(dict(group=c['group'],task=c['task'],trace=dict(initial_xy=t['initial']['observation'][:2],
                    steps=[dict(at_calls=i,command=r['command'],after_xy=r['after']['observation'][:2]) for i,r in enumerate(t['steps'])])))
        else:
            for i in range(0,len(cc),3):
                trio=cc[i:i+3];base=trio[0];lengths={c['packet_kind']:c['packet_steps'] for c in trio};positions={}
                io.require([c['packet_kind'] for c in trio]==['ZERO','PLUS','MINUS'],'ordered factual role triple')
                for c,t in zip(trio,tt[i:i+3]):
                    start=c['entry_at_calls'];positions[c['packet_kind']]=[] if start is None else [t['steps'][start+j]['after']['observation'][:2] for j in range(c['packet_steps'])]
                families.append({k:base[k] for k in ('group','task','context','boundary','acquisition_action')}|dict(family_index=i//3,
                    query=None if base['entry_at_calls'] is None else {'packets':base['preallocated_packets']},packet_positions_xy=positions,packet_lengths=lengths,
                    complete_three_role_H16=all(v==16 for v in lengths.values()),reasons={c['packet_kind']:c['reason'] for c in trio}))
    return nominal,families

def linear_data(rows,task,kind):
    selected=[r for r in rows if r['task']==task and r['complete_three_role_H16']];groups=Counter(r['group'] for r in selected);xx=[];yy=[];ww=[]
    for f in selected:
        for l,r in math.PAIRS:
            commands=[[b[j]-c[j] for j in range(2)] for c,b in zip(f['query']['packets'][l],f['query']['packets'][r])]
            for h in range(1,17):
                xx.append(math.input_row(commands,h,kind));yy.append([(f['packet_positions_xy'][r][h-1][j]-f['packet_positions_xy'][l][h-1][j])/.01 for j in range(2)])
                ww.append(1/(len(groups)*groups[f['group']]*3*16))
    return np.array(xx),np.array(yy),np.array(ww)

def rls_fit(traces):
    xx=[];yy=[];ww=[]
    traces=[t for t in traces if len(t['steps'])>=3]
    for t in traces:
        pos=[t['initial_xy']]+[r['after_xy'] for r in t['steps']];cmd=[r['command'] for r in t['steps']];io.require(len(cmd)>=3,'genuine ARX history')
        for i in range(2,len(cmd)):
            xx.append(math.arx_row(pos,cmd,i));yy.append([(pos[i+1][j]-pos[i][j])/.01 for j in range(2)]);ww.append(1/(len(traces)*(len(cmd)-2)))
    x=np.array(xx);w=np.array(ww);y=np.array(yy);scale=np.sqrt(np.sum(w[:,None]*x*x,axis=0));scale[scale==0]=1.
    aa=np.r_[x/scale*np.sqrt(w[:,None]),np.sqrt(.001)*np.eye(9)];bb=np.r_[y*np.sqrt(w[:,None]),np.zeros((9,2))]
    result=np.linalg.lstsq(aa,np.c_[bb,np.eye(len(aa))],rcond=None)[0];pinv=result[:,2:]
    return dict(input_scale=scale.tolist(),coef=result[:,:2].tolist(),covariance=(pinv@pinv.T).tolist())

def audit(path):
    from src.analysis.release_learning_guard_v1 import read_only
    a.checked(path);root=Path(path).parent;out=root/'training';main=io.read(out/'models.json');done=io.read(out/'completion.json');start=perf_counter_ns();guard={};counter={};maximum={}
    io.require(done['integrity']=='TRAINED_FOR_INDEPENDENT_AUDIT' and done['models_sha256']==io.sha(out/'models.json'),'complete immutable bank before audit')
    def compare(name,left,right,atol=2e-7):
        ll=np.asarray(left,float);rr=np.asarray(right,float);delta=float(np.max(abs(ll-rr)));maximum[name]=max(maximum.get(name,0.),delta)
        io.require(ll.shape==rr.shape and np.allclose(ll,rr,atol=atol,rtol=2e-8),'independent numerical reconstruction '+name)
    with read_only(guard,max_lstsq=9):
        nominal,paired=sources(path);io.require(nominal==io.read(out/'public_nominal_traces.json') and paired==io.read(out/'public_train_families.json'),'independent public source reconstruction')
        for task in io.TASKS:
            source=[r for r in nominal if r['task']==task];traces=[r['trace'] for r in source if r['trace']['steps']];saved=main['bank']['by_task'][task];scores=math.nominal_scores(traces,counter);metadata=main['nominal_fit_metadata'][task]
            io.require(metadata['zero_length_source_groups']==[r['group'] for r in source if not r['trace']['steps']] and metadata['RLS_short_history_source_groups']==[r['group'] for r in source if len(r['trace']['steps'])<3],'explicit per-model missing training history')
            compare('nominal_NLL',scores,metadata['per_candidate_per_axis_nll'],1e-6);chosen=np.argmin(np.array(scores),axis=0).tolist()
            io.require(chosen==metadata['selected_grid_indices'],'independent finite-grid choices')
            grid=[(r,k) for r in (0.,.5,.9) for k in (.05,.2,.8)]
            for i,index in enumerate(chosen):io.require((saved['PLANTS'][i]['rho'],saved['PLANTS'][i]['kappa'])==grid[index],'saved selected plant')
            expected=rls_fit(traces)
            for field in expected:compare('RLS_'+field,expected[field],saved['RLS_ARX'][field],2e-6)
            for kind in ('INSTANT','FIR'):
                expected=math.augmented_linear(*linear_data(paired,task,kind))
                for field in expected:compare(kind+'_'+field,expected[field],saved[kind][field])
        io.require(counter['independent_nominal_grid_passes']==27 and guard['operation_counts']['lstsq_attempts']==9,'declared independent fitting budget')
    result=dict(integrity='PASSED',models_sha256=io.sha(out/'models.json'),public_sources_reconstructed=True,independent_augmented_LS=9,
        independent_counts=counter,maximum_absolute_parameter_differences=maximum,guard=guard,wall_ns=perf_counter_ns()-start,
        new_physics=0,primary_training_repeated=False,online_LLM_API_calls=0,source_sha256={n:io.sha(out/n) for n in ('models.json','public_nominal_traces.json','public_train_families.json')})
    io.write(out/'audit.json',result);return result
