"""Separate scalar grouping and bootstrap sums; main statistics are disabled."""
from pathlib import Path
from math import fsum
from fractions import Fraction
from time import perf_counter_ns
import numpy as np
from src.analysis import memory_reset_io_v1 as a
io=a.io
P=('RAW_CONTINUE','RAW_NOOP','RAW_RESET_I','DIRECT_C8','MOVE_INTEGRAL','LOCAL_PID_KEEP','LOCAL_PID_RESET_I',
   'LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY','LOCAL_PID_REFERENCE_RESET_NO_PROBE')


def same(got,want,label='statistics'):
    if isinstance(want,dict):
        io.require(type(got) is dict and set(got)==set(want),'fields '+label);return sum(same(got[k],v,label+'/'+k) for k,v in want.items())
    if isinstance(want,(tuple,list)):
        io.require(isinstance(got,(list,tuple)) and len(got)==len(want),'length '+label);return sum(same(x,y,label) for x,y in zip(got,want))
    if type(want) in (int,float):io.require(type(got) in (int,float) and abs(got-want)<=1e-10,'number '+label)
    else:io.require(got==want,'value '+label)
    return 1


def independently_compute(rows,draws):
    io.require(len(rows)==540 and len(draws)==10000,'full fixed population and resampling')
    programs=[];loss={};window={}
    for name in P:
        part=[r for r in rows if r['program']==name];io.require(len(part)==54,'complete program')
        for g in range(9):
            cell=[r for r in part if r['group']==g];io.require(len(cell)==6,'whole group')
            loss[g,name]=sum(r['deadline_loss'] for r in cell);window[g,name]=sum(r['complete_warm_window'] for r in cell)
        programs.append({'program':name,'assigned':54,'successes':sum(r['success'] for r in part),'mean_deadline_loss':fsum(r['deadline_loss'] for r in part)/54,
            'actual_control_steps':sum(r['total_steps'] for r in part),'movement_steps':sum(r['movement_steps'] for r in part),'probe_steps':sum(r['warm_probe_steps'] for r in part),
            'complete_windows':sum(r['complete_warm_window'] for r in part),'reference_updates':sum(r['reference_update_applied'] for r in part),
            'memory_transitions':sum(r['memory_transition_applied'] for r in part),'nonzero_integral_changes':sum(r['memory_nonzero_changed'] is True for r in part),
            'initial_C4_C8_fit_attempts':sum(r['c4_c8_fit_attempts'] for r in part)})
    def quantile(sorted_values,q):
        index=(len(sorted_values)-1)*q;lo=int(index);frac=index-lo
        return float((sorted_values[lo]+frac*(sorted_values[min(lo+1,len(sorted_values)-1)]-sorted_values[lo]))/54)
    def contrast(left,right,metric):
        values=window if metric=='WINDOW_RATE' else loss;delta=[values[g,left]-values[g,right] for g in range(9)]
        rep=sorted(sum(delta[int(g)] for g in row) for row in draws)
        return {'left':left,'right':right,'metric':metric,'mean_difference':sum(delta)/54,'group_differences':[v/6 for v in delta],
            'group_bootstrap95':[quantile(rep,Fraction(1,40)),quantile(rep,Fraction(39,40))],'independent_groups':9,'unadjusted_interval':True}
    pairs=[('RAW_RESET_I','RAW_CONTINUE'),('LOCAL_PID_RESET_I','LOCAL_PID_KEEP'),
        ('LOCAL_PID_REFERENCE_RESET','LOCAL_PID_RESET_I'),('LOCAL_PID_REFERENCE_CARRY','LOCAL_PID_REFERENCE_RESET'),
        ('LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_RESET_NO_PROBE'),('RAW_RESET_I','DIRECT_C8'),('RAW_RESET_I','MOVE_INTEGRAL')]
    pairs.extend((name,'RAW_CONTINUE') for name in P[1:] if (name,'RAW_CONTINUE') not in pairs)
    contrasts=[contrast(left,right,'DEADLINE_LOSS') for left,right in pairs]
    panels=[]
    for name in P:
        for task in ('push-v3','reach-v3','door-open-v3'):
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    part=[v for v in rows if v['program']==name and v['task']==task and v['context']==context and v['planned_boundary']==boundary]
                    io.require(len(part)==3,'independent whole panel')
                    panels.append(dict(program=name,task=task,context=context,planned_boundary=boundary,assigned=3,
                        successes=sum(v['success'] for v in part),mean_deadline_loss=float(Fraction(sum(v['deadline_loss'] for v in part),3)),
                        memory_transitions=sum(v['memory_transition_applied'] for v in part),complete_windows=sum(v['complete_warm_window'] for v in part)))
    primary=dict(primary_full_population_loss_95_upper_below_zero=contrasts[0]['group_bootstrap95'][1]<0)
    return dict(classification='STANDARD_COUNTERMECHANISM_ONLY',program_summaries=programs,registered_contrasts=contrasts,
        full_assignment_panels=panels,primary_checks=primary,primary_status='SUPPORTED_STANDARD_RESET_REFERENCE_ONLY' if primary['primary_full_population_loss_95_upper_below_zero'] else 'NOT_QUALIFIED',
        success_changes_are_reported_not_a_hidden_gate=True,secondary_cannot_replace_failed_primary=True,
        new_response_training=0,new_policy_training=0,new_online_LLM_API_calls=0,publication_goal_complete=False)


def audit(path):
    start=perf_counter_ns();path=path.resolve();a.checked(path);out=path.parent/'qual';receipt=io.read(out/'statistics_receipt.json')
    io.require(receipt['statistics_sha256']==io.sha(out/'statistics.json') and receipt['bootstrap_indices_sha256']==io.sha(out/'bootstrap_group_indices.json'),'statistics bytes')
    io.require(receipt['source_audit_sha256']==io.sha(out/'audit.json'),'statistics source audit')
    rows=io.read(out/'summary.json')['rows'];draws=io.read(out/'bootstrap_group_indices.json');rng=np.random.default_rng(202610235)
    expected=np.concatenate([np.asarray(g)[rng.integers(0,3,size=(10000,3))] for g in ((0,3,6),(1,4,7),(2,5,8))],axis=1).tolist()
    io.require(draws==expected,'registered bootstrap stream or stratification changed')
    result=independently_compute(rows,draws);fields=same(io.read(out/'statistics.json'),result)
    value={'integrity':'PASSED','fields_checked':fields,'whole_independent_groups':9,'resamples_checked':10000,'source_statistics_sha256':io.sha(out/'statistics.json'),
        'auditor_sha256':io.sha(__file__),'main_statistics_functions_not_called':True,'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0}
    io.write(out/'statistics_audit.json',value);return value
