"""Independent raw-feature, chronological query and unregularized SVD replay."""
from collections import defaultdict
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import numpy as np
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.analysis import linear_command_preflight_io_v1 as allocation
from src.analysis import observable_history_io_v1 as io

SLICES={'H10':(6,10),'F20':(9,13),'F43':(39,43)}


def same(a,b):
    if isinstance(b,dict):
        io.require(type(a) is dict and set(a)==set(b),'audit dictionary schema')
        for k in b: same(a[k],b[k])
    elif isinstance(b,(list,tuple)):
        io.require(isinstance(a,(list,tuple)) and len(a)==len(b),'audit sequence schema')
        for x,y in zip(a,b): same(x,y)
    elif isinstance(b,float):
        io.require(isinstance(a,(int,float)) and not isinstance(a,bool) and np.isclose(a,b,rtol=1e-8,atol=1e-12),'audit numeric mismatch')
    else: io.require(a==b,'audit metadata mismatch')


def candidates(baseline):
    result=[]
    for name,axis,delta in (('X_PLUS',0,.25),('X_MINUS',0,-.25),('Y_PLUS',1,.25),('Y_MINUS',1,-.25)):
        u=list(baseline); u[axis]=min(1.,max(-1.,u[axis]+delta))
        result.append({'action_id':name,'command':u})
    return result


def current_query(raw,t,step):
    state=np.asarray([t['initial'],*t['observations']],dtype=float)
    expected={'schema':'CAUSAL_COMMAND_QUERY_V1','task':t['task'],'decision_step':step,
              'observation_steps':[step-2,step-1,step],'observations':state[step-2:step+1].tolist(),
              'baseline_command':t['commands'][step],'candidates':candidates(t['commands'][step])}
    io.require(set(raw)==set(expected),'query schema includes forbidden fields')
    for key in ('schema','task','decision_step','observation_steps'): io.require(raw[key]==expected[key],'query chronology metadata')
    for key in ('observations','baseline_command'): io.require(np.array_equal(raw[key],expected[key]),'actual history/command mismatch or future observation')
    same(raw['candidates'],expected['candidates'])
    return expected


def feature(history,command,kind):
    h=np.asarray(history,dtype=float); now=h[2]; previous=h[1]; earlier=h[0]
    if kind=='F43': return np.concatenate([now,np.asarray(command)])
    d=np.concatenate([now[:3]-previous[:3],previous[:3]-earlier[:3]])
    if kind=='H10': return np.concatenate([d,command])
    return np.concatenate([now[:3],d,command,[now[3]],now[4:7]-now[:3],now[-3:]-now[:3]])


def geometry(a,xy_columns):
    _,s,v=np.linalg.svd(a,full_matrices=False); tol=max(a.shape)*np.finfo(float).eps*s[0]; rank=int(sum(s>tol))
    z=a[:,[i for i in range(a.shape[1]) if i not in xy_columns]]
    left,sz,_=np.linalg.svd(z,full_matrices=False); zr=int(sum(sz>max(z.shape)*np.finfo(float).eps*sz[0]))
    xy=a[:,xy_columns]; remainder=xy-left[:,:zr]@(left[:,:zr].T@xy)
    cs=np.linalg.svd(remainder,compute_uv=False)
    return {'s':s,'v':v[:rank],'rank':rank,'tolerance':tol,'nuisance_rank':zr,'conditional':cs,
            'conditional_rank':int(sum(cs>tol)),'condition':None if rank<a.shape[1] else float(s[0]/s[-1])}


def prepare(index,public):
    trajectories={}; data={}; cache={}; details=[]
    for e in public['entries']:
        data[e['source_bank'],e['task']]=e['trajectories']
        for t in e['trajectories']:
            io.require(t['trajectory_id'] not in trajectories,'duplicate FIT trajectory')
            trajectories[t['trajectory_id']]=t
    for key,e in index.items():
        m=io.read(allocation.SOURCE/'training'/e['file']); ts=data[e['source'],e['task']]
        xx=[]; weights=[]; sent=[]
        for t in ts:
            h=np.asarray([t['initial'],*t['observations']]); n=len(t['commands'])-2
            xx.extend(feature(h[i-2:i+1],t['commands'][i],e['feature']) for i in range(2,n+2))
            weights.extend([1/n]*n); sent.extend(t['commands'][2:])
        x=np.asarray(xx); mean=np.asarray(m['stats']['input_mean']); scale=np.asarray(m['stats']['input_scale']); coef=np.asarray(m['coefficient'])
        a=np.column_stack([np.ones(len(x)),(x-mean)/scale])*np.sqrt(np.asarray(weights)[:,None])
        start,stop=SLICES[e['feature']]; g=geometry(a,[start+1,start+2]); j=coef[start+1:stop+1].T/scale[start:stop]
        js=np.linalg.svd(j[:,:2],compute_uv=False); low=np.min(sent,axis=0); high=np.max(sent,axis=0)
        cache[key]=(m,mean,scale,coef,g,j,low,high)
        details.append({'model_key':key,'source':e['source'],'task':e['task'],'feature':e['feature'],'source_model_sha256':e['sha256'],
            'state_independent_command_matrix_m':j.tolist(),'xy_singular_values_m':js.tolist(),'xy_condition':None if js[-1]==0 else float(js[0]/js[-1]),
            'xy_determinant_m2':float(np.linalg.det(j[:,:2])),'training_trajectories':len(ts),'training_query_positions':len(x),
            'rank':g['rank'],'columns':a.shape[1],'design_singular_values':g['s'].tolist(),'rank_tolerance':g['tolerance'],
            'design_condition':g['condition'],'nuisance_rank':g['nuisance_rank'],'conditional_xy_rank':g['conditional_rank'],
            'conditional_xy_singular_values':g['conditional'].tolist(),'command_axis_min':low.tolist(),'command_axis_max':high.tolist(),
            'physical_qualification':False,'probability_guarantee':False})
    return trajectories,cache,details


def audit():
    started=perf_counter_ns(); folder=allocation.OUTPUT; manifest=allocation.load_manifest()
    allowed=[ROOT/n for n in manifest['input_sha256']]
    io.require(not (folder/'audit.json').exists(),'do not repeat a completed independent audit')
    completion=io.read(folder/'completion.json')
    for name,digest in completion['artifact_sha256'].items(): io.require(io.sha(folder/name)==digest,'analysis artifact changed')
    with allocation.numeric_guard(allowed) as guard:
        index,_=allocation.source_files(); public=io.read(allocation.SOURCE/'fit_public.json')
        trajectories,cache,details=prepare(index,public)
        same(io.read(folder/'model_geometry.json'),details)
        expected=[(t['trajectory_id'],i) for e in public['entries'] for t in e['trajectories'] for i in range(2,len(t['commands']))]
        cells=defaultdict(list); checked=0; records=0
        with gzip.open(folder/'queries.jsonl.gz','rt',encoding='utf-8') as handle:
            for record_number,line in enumerate(handle):
                row=json.loads(line); case,step=expected[record_number]; t=trajectories[case]; parts=case.split('/')
                io.require(set(row)=={'case_id','source','group','context','query','models'} and
                    (row['case_id'],row['source'],row['group'],row['context'])==(case,parts[4],int(parts[1]),parts[3]),'complete ordered query ownership')
                q=current_query(row['query'],t,step)
                keys=[k for k,e in index.items() if e['source']==parts[4] and e['task']==t['task']]
                io.require(set(row['models'])==set(keys) and len(keys)==3,'every linear reference per query')
                for key in keys:
                    m,mean,scale,coef,g,j,low,high=cache[key]
                    bx=feature(q['observations'],q['baseline_command'],m['feature'])
                    base=np.r_[1.,(bx-mean)/scale]@coef
                    predictions=[]
                    for candidate in q['candidates']:
                        u=np.asarray(candidate['command']); v=np.r_[0.,(feature(q['observations'],u,m['feature'])-bx)/scale]
                        coordinates=g['v']@v; norm=float(np.linalg.norm(v))
                        relative=None if norm==0 else float(np.linalg.norm(v-g['v'].T@coordinates))/norm
                        leverage=float(np.sum((coordinates/g['s'][:g['rank']])**2))
                        zero=bool(np.array_equal(u,q['baseline_command']))
                        outside=bool(np.any(u<low-1e-12) or np.any(u>high+1e-12))
                        delta=j@(u-q['baseline_command']); pred=np.r_[1.,(feature(q['observations'],u,m['feature'])-mean)/scale]@coef
                        diagnostic={'zero_command_difference':norm==0,'row_span_relative_residual':relative,'weighted_design_leverage':leverage,
                            'interpretation':'Numerical linear-design geometry only; neither conditional causal support nor physical validity nor confidence.',
                            'outside_command_axis_box':outside}
                        predictions.append({'action_id':candidate['action_id'],'sent_command':candidate['command'],'prediction_m':pred.tolist(),
                            'predicted_difference_m':delta.tolist(),'same_as_baseline':zero,'design_geometry':diagnostic})
                        cells[case,key].append((zero,outside,relative,leverage,float(np.linalg.norm(delta))))
                        checked+=1
                    same(row['models'][key],{'baseline_prediction_m':base.tolist(),'candidates':predictions,
                        'state_independent_command_matrix_m':j.tolist(),'executed_counterfactuals':False,
                        'physical_qualification':False,'probability_guarantee':False,'task_benefit':False})
                records+=1
        io.require(records==len(expected)==13402 and checked==160824,'complete fixed query population without truncation')
        summaries=[]
        for e in public['entries']:
            keys=[k for k,v in index.items() if (v['source'],v['task'])==(e['source_bank'],e['task'])]
            for t in e['trajectories']:
                case=t['trajectory_id']; parts=case.split('/')
                for key in keys:
                    values=cells[case,key]; nonzero=[v for v in values if v[2] is not None]
                    summaries.append({'case_id':case,'source':parts[4],'task':t['task'],'group':int(parts[1]),'context':parts[3],
                        'model_key':key,'query_positions':len(t['commands'])-2,'candidates':len(values),'zero_candidates':sum(v[0] for v in values),
                        'outside_command_axis_box':sum(v[1] for v in values),'nonzero_candidates':len(nonzero),
                        'mean_row_span_relative_residual':None if not nonzero else float(np.mean([v[2] for v in nonzero])),
                        'max_row_span_relative_residual':None if not nonzero else max(v[2] for v in nonzero),
                        'mean_weighted_design_leverage':None if not nonzero else float(np.mean([v[3] for v in nonzero])),
                        'max_weighted_design_leverage':None if not nonzero else max(v[3] for v in nonzero),
                        'mean_predicted_contrast_norm_m':float(np.mean([v[4] for v in values])),
                        'max_predicted_contrast_norm_m':max(v[4] for v in values)})
        same(io.read(folder/'trajectory_summaries.json'),summaries)
        same(completion['counts'],{'query_positions':13402,'model_query_pairs':40206,'candidate_model_pairs':160824,
                                  'unique_trajectories':144,'model_trajectory_pairs':432})
        io.require(not any(guard.values()) and not any(completion['guard'].values()),'forbidden numeric operation')
        allocation.load_manifest()
        io.write(folder/'audit.json',{'integrity':'PASSED','models_checked':18,'query_positions_checked':records,
            'candidate_model_pairs_checked':checked,'trajectory_summaries_checked':432,'independent_design_svds':54,'independent_xy_matrix_svds':18,
            'model_refits':0,'new_environment_steps':0,'new_api_calls':0,'guard':guard,'wall_ns':perf_counter_ns()-started,
            'source_sha256':io.sha(__file__),'artifact_sha256':completion['artifact_sha256'],'physical_qualification':False,'task_benefit':False})
    print({'integrity':'PASSED','query_positions':records,'candidate_model_pairs':checked})


if __name__=='__main__':
    try: audit()
    except BaseException as error:
        if allocation.OUTPUT.exists(): io.write(allocation.OUTPUT/'audit_failure.json',{'type':type(error).__name__,'message':str(error),'no_automatic_retry':True})
        raise
