"""Frozen nine-group statistics; acquisition and reference utility are distinct."""
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import memory_reset_io_v1 as a
from src.probe.memory_reset_program_v1 import PROGRAMS
io=a.io


def indices():
    rng=np.random.default_rng(202610235)
    return np.concatenate([np.asarray(g)[rng.integers(0,3,size=(10000,3))] for g in ((0,3,6),(1,4,7),(2,5,8))],axis=1)


def compute(rows,draws):
    specs=a.population('QUAL');io.require(len(rows)==len(specs)==540,'complete independent qualification population')
    for r,s in zip(rows,specs):
        io.require(all(r[k]==v for k,v in s.items()),'qualification order or allocation changed')
        io.require(type(r['success']) is bool and r['deadline_loss']==(r['total_steps'] if r['success'] else 500) and 0<=r['total_steps']<=500,'full observed cutoff loss')
    io.require(np.asarray(draws).shape==(10000,9),'registered group resampling')
    loss=np.empty((9,10),dtype=np.int64);window=np.empty((9,10),dtype=np.int64);programs=[]
    for j,name in enumerate(PROGRAMS):
        selected=[r for r in rows if r['program']==name]
        for g in range(9):
            part=[r for r in selected if r['group']==g];io.require(len(part)==6,'six paired task/context units per group')
            loss[g,j]=sum(r['deadline_loss'] for r in part);window[g,j]=sum(r['complete_warm_window'] for r in part)
        programs.append({'program':name,'assigned':54,'successes':sum(r['success'] for r in selected),'mean_deadline_loss':float(np.sum(loss[:,j])/54),
            'actual_control_steps':sum(r['total_steps'] for r in selected),'movement_steps':sum(r['movement_steps'] for r in selected),'probe_steps':sum(r['warm_probe_steps'] for r in selected),
            'complete_windows':sum(r['complete_warm_window'] for r in selected),'reference_updates':sum(r['reference_update_applied'] for r in selected),
            'memory_transitions':sum(r['memory_transition_applied'] for r in selected),'nonzero_integral_changes':sum(r['memory_nonzero_changed'] is True for r in selected),
            'initial_C4_C8_fit_attempts':sum(r['c4_c8_fit_attempts'] for r in selected)})
    def contrast(left,right,kind):
        matrix=window if kind=='WINDOW_RATE' else loss;delta=matrix[:,PROGRAMS.index(left)]-matrix[:,PROGRAMS.index(right)]
        totals=np.sort(np.sum(delta[draws],axis=1));ci=[]
        for numerator in (1,39):
            lo,remainder=divmod((len(totals)-1)*numerator,40)
            ci.append(float((int(totals[lo])*(40-remainder)+int(totals[min(lo+1,len(totals)-1)])*remainder)/(54*40)))
        return {'left':left,'right':right,'metric':kind,'mean_difference':float(np.sum(delta)/54),'group_differences':(delta.astype(float)/6).tolist(),
            'group_bootstrap95':ci,'independent_groups':9,'unadjusted_interval':True}
    pairs=[('RAW_RESET_I','RAW_CONTINUE'),('LOCAL_PID_RESET_I','LOCAL_PID_KEEP'),
        ('LOCAL_PID_REFERENCE_RESET','LOCAL_PID_RESET_I'),('LOCAL_PID_REFERENCE_CARRY','LOCAL_PID_REFERENCE_RESET'),
        ('LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_RESET_NO_PROBE'),('RAW_RESET_I','DIRECT_C8'),('RAW_RESET_I','MOVE_INTEGRAL')]
    pairs += [(name,'RAW_CONTINUE') for name in PROGRAMS[1:] if (name,'RAW_CONTINUE') not in pairs]
    contrasts=[contrast(left,right,'DEADLINE_LOSS') for left,right in pairs]
    cells=[]
    for name in PROGRAMS:
        for task in io.TASKS:
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    part=[r for r in rows if (r['program'],r['task'],r['context'],r['planned_boundary'])==(name,task,context,boundary)]
                    io.require(len(part)==3,'complete task/context/boundary panel')
                    cells.append(dict(program=name,task=task,context=context,planned_boundary=boundary,assigned=3,
                        successes=sum(r['success'] for r in part),mean_deadline_loss=sum(r['deadline_loss'] for r in part)/3,
                        memory_transitions=sum(r['memory_transition_applied'] for r in part),complete_windows=sum(r['complete_warm_window'] for r in part)))
    checks=dict(primary_full_population_loss_95_upper_below_zero=contrasts[0]['group_bootstrap95'][1]<0)
    return dict(classification='STANDARD_COUNTERMECHANISM_ONLY',program_summaries=programs,registered_contrasts=contrasts,
        full_assignment_panels=cells,primary_checks=checks,primary_status='SUPPORTED_STANDARD_RESET_REFERENCE_ONLY' if all(checks.values()) else 'NOT_QUALIFIED',
        success_changes_are_reported_not_a_hidden_gate=True,secondary_cannot_replace_failed_primary=True,
        new_response_training=0,new_policy_training=0,new_online_LLM_API_calls=0,publication_goal_complete=False)


def run(path):
    path=Path(path).resolve();a.checked(path);out=path.parent/'qual';start=perf_counter_ns();audit=io.read(out/'audit.json')
    io.require(audit['integrity']=='PASSED' and audit['collection_completion_sha256']==io.sha(out/'completion.json'),'independently audited QUAL data')
    for n,h in audit['artifact_sha256'].items():io.require(io.sha(out/n)==h,'audited data changed')
    rows=io.read(out/'summary.json')['rows'];draws=indices();result=compute(rows,draws)
    io.write(out/'bootstrap_group_indices.json',draws.tolist());io.write(out/'statistics.json',result)
    io.write(out/'statistics_receipt.json',{'integrity':'COMPUTED_REQUIRES_INDEPENDENT_AUDIT','statistics_sha256':io.sha(out/'statistics.json'),
        'bootstrap_indices_sha256':io.sha(out/'bootstrap_group_indices.json'),'source_audit_sha256':io.sha(out/'audit.json'),'wall_ns':perf_counter_ns()-start,
        'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0});return result
