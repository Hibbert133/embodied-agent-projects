"""Evaluator-only factual-input consistency, never an entry-time forecast."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from time import perf_counter_ns
import hashlib,json,subprocess
import numpy as np
from src.analysis import correction_effect_learning_v1 as previous
from src.analysis.release_learning_guard_v1 import read_only
io=previous.io;ROOT=io.ROOT;BASE=ROOT/'outputs/correction_scope/effect_horizon_v1'
CONFIG=ROOT/'configs/movement_task/correction_effect_horizon_v1.json'
EFFECT=ROOT/'outputs/correction_scope/effect_learning_v1/run_20261027T064624Z_db04aa83cabc'
HORIZONS=(1,2,4,8,16,32);METHODS=('ZERO_EFFECT','NOMINAL_SENT','FROZEN_GLOBAL_MATRIX')
PURPOSE='POST_HOC_EXECUTED_INPUTS_NOT_FORECAST'
AXES=((),('group',),('task',),('context',),('boundary',),('acquisition_action',),('rates',),('task','context','boundary'),('task','context','boundary','acquisition_action','rates'))


def window(pair,left,right,matrix,*,purpose):
    io.require(purpose==PURPOSE,'future source commands are evaluator-only; not a forecast interface')
    at=pair['first_difference'];result=[]
    if at is not None:
        io.require(type(at) is int and at>=2 and len(left)>at and len(right)>at,'actual first difference')
        io.require(left[at-1]['after']==right[at-1]['after'],'same factual starting state')
    for h in HORIZONS:
        row={k:pair[k] for k in ('pair_id','group','task','context','boundary','acquisition_action','rates','loss_difference','success_a','success_b')}
        row.update(horizon=h,first_difference=at,source_pair_status=pair['status'],analysis_semantics=PURPOSE,
            status=pair['status'] if at is None else 'COMPLETE_FACTUAL_WINDOW',mse=None,predictions=None)
        if at is not None:
            enough_a=len(left)-at>=h;enough_b=len(right)-at>=h
            if not (enough_a and enough_b):row['status']='BOTH_SOURCES_SHORT' if not enough_a and not enough_b else 'SOURCE_A_SHORT' if not enough_a else 'SOURCE_B_SHORT'
            else:
                a=left[at:at+h];b=right[at:at+h]
                ua=np.asarray([r['command'] for r in a],float);ub=np.asarray([r['command'] for r in b],float)
                io.require(ua.shape==ub.shape==(h,4) and np.isfinite(np.r_[ua.ravel(),ub.ravel()]).all() and max(abs(ua).max(),abs(ub).max())<=1,'actual bounded commands')
                du=(ub[:,:2]-ua[:,:2]).sum(axis=0)
                effect=(np.asarray(b[-1]['after']['observation'][:2])-np.asarray(a[-1]['after']['observation'][:2]))/.01
                predictions={'ZERO_EFFECT':np.zeros(2),'NOMINAL_SENT':du,'FROZEN_GLOBAL_MATRIX':du@np.asarray(matrix)}
                row.update(command_sum_difference_xy=du.tolist(),actual_endpoint_difference_xy=effect.tolist(),
                    predictions={k:v.tolist() for k,v in predictions.items()},mse={k:float(np.mean((v-effect)**2)) for k,v in predictions.items()},
                    raw_policy_difference_steps=sum(previous.bits(x['raw_policy'])!=previous.bits(y['raw_policy']) for x,y in zip(a,b)),
                    z_gripper_difference_steps=sum(previous.bits(x['command'])[8:]!=previous.bits(y['command'])[8:] for x,y in zip(a,b)),
                    future_commands_consumed_for_evaluation=h-1,no_unexecuted_states_generated=True)
        result.append(row)
    return result


def panels(rows):
    result=[]
    for axes in AXES:
        cells=defaultdict(list)
        for r in rows:cells[(r['horizon'],*(tuple(r[k]) if k=='rates' else r[k] for k in axes))].append(r)
        for key,registered in sorted(cells.items(),key=lambda x:str(x[0])):
            actual=[r for r in registered if r['status']=='COMPLETE_FACTUAL_WINDOW']
            metric={kind:None for kind in METHODS};z=None;motion=None
            if actual:
                w=previous.weights(actual)
                metric={kind:float(sum(float(q)*r['mse'][kind] for q,r in zip(w,actual))) for kind in METHODS}
                z=float(sum(float(q)*(r['z_gripper_difference_steps']>0) for q,r in zip(w,actual)))
                motion=float(sum(float(q)*10*np.linalg.norm(r['actual_endpoint_difference_xy']) for q,r in zip(w,actual)))
            result.append(dict(horizon=key[0],axes=list(axes),values=list(key[1:]),registered=len(registered),available=len(actual),
                independent_groups=len({r['group'] for r in actual}),statuses=dict(Counter(r['status'] for r in registered)),
                mse=metric,any_z_gripper_difference_weighted_fraction=z,mean_actual_endpoint_L2_mm=motion))
    return result


def bindings():
    result=previous.source_bindings();commit=io.read(CONFIG)['effect_result_commit']
    names=['manifest.json','pairs/pair_register.json','pairs/public_pairs.json','pairs/audit.json','models/predictions.json','models/audit.json','evaluation/decision.json']
    names.extend(f'models/group{g}_GLOBAL_MATRIX.json' for g in range(9))
    for n in names:
        p=EFFECT/n;name=p.relative_to(ROOT).as_posix();blob=subprocess.check_output(['git','show',commit+':'+name],cwd=ROOT)
        io.require(hashlib.sha256(blob).hexdigest()==io.sha(p),'immutable committed prior effect '+n);result[name]=io.sha(p)
    return result


def prepare(sources):
    frozen=io.read(BASE/'freeze_validation/complete.json');io.require(frozen['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean horizon freeze')
    io.require(not list(BASE.glob('run_*/manifest.json')),'one horizon audit allocation')
    for n,h in frozen['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'unchanged horizon source')
    head=io.git('rev-parse','HEAD');out=BASE/('run_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12]);out.mkdir(exist_ok=False)
    m=dict(protocol='CORRECTION_EFFECT_HORIZON_V1',classification=PURPOSE,source_git_commit=head,config=io.read(CONFIG),source_sha256={n:io.sha(ROOT/n) for n in sources},input_sha256=bindings())
    m['manifest_id']=io.digest(m);io.write(out/'manifest.json',m);return out/'manifest.json'


def checked(path):
    path=Path(path).resolve();m=io.read(path);copy=dict(m);mid=copy.pop('manifest_id')
    io.require(path.parent.parent==BASE and mid==io.digest(copy) and m['config']==io.read(CONFIG),'horizon manifest ownership')
    for n,h in {**m['source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'immutable horizon data/source '+n)
    return m


def analyse(path):
    path=Path(path);checked(path);out=path.parent/'analysis';out.mkdir(exist_ok=False);start=perf_counter_ns();guard={};result=[];models={}
    register=io.read(EFFECT/'pairs/pair_register.json');public={r['pair_id']:r for r in io.read(EFFECT/'pairs/public_pairs.json')};old={(r['pair_id'],r['kind']):r for r in io.read(EFFECT/'models/predictions.json')}
    saved={r['pair_id']:r for r in register};seen=[]
    with read_only(guard):
        for g in range(9):
            model=io.read(EFFECT/f'models/group{g}_GLOBAL_MATRIX.json');models[g]=np.asarray(model['coef'])/np.asarray(model['scale'])[:,None]
        for family in previous.source_nodes():
            for ia,ib in previous.PAIRS:
                ca,sa,_=family[ia];cb,sb,_=family[ib];pid=io.digest([previous.node_key(ca),ia,ib]);r=saved[pid]
                io.require(r['source_case_sha256']==[io.digest(ca),io.digest(cb)],'full source cases unchanged')
                at,packet,target=previous.first_difference(ca['initial'],sa,cb['initial'],sb)
                io.require(at==r['first_difference'],'unchanged first divergence')
                if at is not None:io.require(packet==public[pid]['input'] and target==public[pid]['target'],'same factual pair and true history')
                values=window(r,sa,sb,models[r['group']],purpose=PURPOSE)
                if at is not None:
                    for kind,old_kind in (('ZERO_EFFECT','ZERO_EFFECT'),('NOMINAL_SENT','NOMINAL_SENT'),('FROZEN_GLOBAL_MATRIX','GLOBAL_MATRIX')):
                        io.require(np.allclose(values[0]['predictions'][kind],old[(pid,old_kind)]['prediction'],atol=2e-11,rtol=2e-11) and np.isclose(values[0]['mse'][kind],old[(pid,old_kind)]['mse'],atol=2e-11,rtol=2e-11),'exact source one-step check')
                seen.append(pid);result.extend(values)
        io.require(len(seen)==len(set(seen))==972 and len(result)==5832,'all pairs and fixed horizons')
        previous.compact(out/'windows.json',result);io.write(out/'panels.json',panels(result))
    available=sum(r['status']=='COMPLETE_FACTUAL_WINDOW' for r in result)
    receipt=dict(integrity='FOR_INDEPENDENT_AUDIT',registered_pairs=972,registered_windows=5832,available_windows=available,
        frozen_matrix_file_reads=9,frozen_matrix_evaluations=available,deterministic_reference_evaluations=2*available,guard=guard,
        ex_post_actual_future_inputs_not_entry_forecasts=True,no_task_benefit_or_model_qualification=True,new_physics=0,new_fits=0,online_LLM_API_calls=0,
        wall_ns=perf_counter_ns()-start,artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()})
    io.write(out/'receipt.json',receipt);return receipt
