"""Separate causal reader, adaptive fixed selector and literal PI audit.

Two controller interpreters share immutable TaskMemory and the macro primitive;
literal PI arithmetic and byte comparisons are separately checked. No physics.
"""
from collections import defaultdict
from copy import deepcopy
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import math,struct
import numpy as np
from src.analysis import correction_policy_support_v1 as main
from src.analysis import learned_acquisition_native_io_v1 as native
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.task_passive_audit_v1 import audit_pi
from src.probe import learned_acquisition_actor_v1 as adaptive
from src.probe import correction_scope_program_v1 as legacy
from src.probe.frozen_risk_client_v1 import forced_reference
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
io=main.io


def bits(command):
    io.require(len(command)==4 and all(math.isfinite(float(x)) and abs(x)<=1 for x in command),'literal bounded command')
    return struct.pack('<4f',*command)


class Different(Exception):pass


def replay(initial,steps,task,boundary,action,rate,*,policy=None):
    from src.rollout.task_registry import create_task_policy
    current=deepcopy(initial);cursor=examined=responses=queries=events=pi_checks=0;different=None;prefix=[]
    integral=[0.,0.];pending=proposed=None
    fixed=create_task_policy(task) if policy is None else policy
    rng_before=main.random_fingerprint();policy_before=deepcopy(getattr(fixed,'__dict__',{}))
    def query(observation):
        nonlocal queries
        io.require(np.array_equal(observation,current['observation']),'independent causal fixed-policy observation')
        queries+=1;return np.asarray(fixed.get_action(np.array(observation,copy=True)),np.float32)
    def emit(kind,payload):
        nonlocal events,pending,proposed,pi_checks
        if kind=='PI_PLAN':
            io.require(pending is None,'unconsumed PI plan');pending=payload['saved_plan']['pi_plan']
        elif kind=='COMMAND' and payload['raw_policy'] is not None:
            io.require(pending is not None and proposed is None,'task command without plan')
            expected=.5 if payload['phase'] in ('PREFIX_TASK','VALIDATION_TASK') else rate
            io.require(pending['query']['time_constant_s']==expected,'registered controller rate and phase')
            proposed,_=audit_pi(pending,payload['command'],integral,task,cursor,current,payload['raw_policy']);pi_checks+=1
            c=pending['query']['controller'];io.require(c['source']=='UNCORRECTED' and c['matrix_xy']==[[1.,0.],[0.,1.]] and c['offset']==[0.]*4,'fixed RAW identity baseline')
        elif kind in ('TASK_MEMORY_COMMIT','TASK_MEMORY_RETURN','RATE_COMMIT'):
            io.require(payload['memory']['integral_xy']==integral and normalize(payload['memory']['current'])==normalize(current),'independent carried memory/current state')
        ack=dict(normalize(payload),sequence=events,saved_ns=events+1);events+=1;return ack
    def step(saved):
        nonlocal cursor,examined,responses,current,different,integral,pending,proposed
        io.require(different is None and cursor<len(steps) and saved['at_calls']==cursor,'no future source access after first difference')
        io.require(normalize(saved['before'])==normalize(current),'independent current state')
        actual=steps[cursor];examined+=1
        if bits(saved['command'])!=bits(actual['command']):
            different=dict(at_control_index=cursor,replayed_intended_command=saved['command'],factual_sent_command=actual['command']);raise Different()
        current=deepcopy(actual['after']);responses+=1;cursor+=1;prefix.append(dict(command=actual['command'],after=current))
        if saved['raw_policy'] is not None:
            io.require(proposed is not None,'unverified PI command');integral=proposed;proposed=pending=None
        return StepReceipt(StepObservation(**current),cursor)
    try:
        if not any(initial[k] for k in ('success','terminated','truncated')):
            adaptive.run(task,StepObservation(**deepcopy(initial)),boundary,query,step,emit,forced_reference(action,rate))
    except Different:pass
    io.require(main.random_fingerprint()==rng_before and policy_before==getattr(fixed,'__dict__',{}),'independent fixed-policy/RNG side effects')
    if different is None:io.require(cursor==len(steps) and (any(current[k] for k in ('success','terminated','truncated')) or cursor==500),'independent complete endpoint')
    return dict(status='SUPPORTED_FACTUAL_OUTCOME' if different is None else 'UNKNOWN_AFTER_COMMAND_DIFFERENCE',matched_prefix_steps=cursor,
        source_commands_examined=examined,source_responses_consumed=responses,first_difference=different,matched_prefix_sha256=io.digest([initial,prefix]),
        supported_loss=(cursor if current['success'] else 500) if different is None else None,
        supported_success=bool(current['success']) if different is None else None,replay_fixed_policy_queries=queries,literal_pi_checks=pi_checks)


def literal_bounds(rows,traces,learned):
    result=[]
    for unit in sorted(traces):
        for action,rate in main.CANDIDATES:
            selected=[r for r in rows if tuple(r['unit'])==unit and r['action']==action and r['rate']==rate]
            io.require(len(selected)==3 and sorted(r['source_program'] for r in selected)==sorted(native.PROGRAMS),'all source programs per independent bound')
            for i,x in enumerate(selected):
                for y in selected[i+1:]:
                    xi,xs=traces[unit][x['source_program']];yi,ys=traces[unit][y['source_program']]
                    io.require(xi==yi,'independent same initial state')
                    for j in range(min(x['matched_prefix_steps'],y['matched_prefix_steps'])):
                        io.require(bits(xs[j]['command'])==bits(ys[j]['command']) and xs[j]['after']==ys[j]['after'],'independent coupling failure')
            known=[r for r in selected if r['status']=='SUPPORTED_FACTUAL_OUTCOME']
            low=high=None;success=None
            if known:
                low=high=known[0]['supported_loss'];success=known[0]['supported_success']
                io.require(all(r['supported_loss']==low and r['supported_success']==success for r in known),'independent supported outcome contradiction')
            else:low=max(r['matched_prefix_steps'] for r in selected)+1;high=500
            result.append(dict(unit=list(unit),action=action,rate=rate,status='SUPPORTED_FACTUAL_OUTCOME' if known else 'PARTIALLY_IDENTIFIED',
                lower=low,upper=high,success=success,source_programs=[r['source_program'] for r in known],longest_supported_prefix=max(r['matched_prefix_steps'] for r in selected)))
    summaries=[]
    for action,rate in main.CANDIDATES:
        records=[r for r in result if (r['action'],r['rate'])==(action,rate)];low=sum(r['lower'] for r in records);high=sum(r['upper'] for r in records)
        n=len(records);target=sum(learned[tuple(r['unit'])] for r in records)
        groups=[]
        for g in range(3):
            subset=[r for r in records if r['unit'][1]==g]
            groups.append(dict(group=g,n=len(subset),supported=sum(r['status']=='SUPPORTED_FACTUAL_OUTCOME' for r in subset),
                lower_mean=sum(r['lower'] for r in subset)/len(subset),upper_mean=sum(r['upper'] for r in subset)/len(subset)))
        summaries.append(dict(action=action,rate=rate,n=n,supported=sum(r['status']=='SUPPORTED_FACTUAL_OUTCOME' for r in records),
            unknown=sum(r['status']=='PARTIALLY_IDENTIFIED' for r in records),lower_total=low,upper_total=high,lower_mean=low/n,upper_mean=high/n,
            fixed_minus_learned_lower_mean=(low-target)/n,fixed_minus_learned_upper_mean=(high-target)/n,groups=groups))
    return result,summaries


def audit(path):
    path=Path(path).resolve();m=main.checked(path);out=path.parent/'analysis';receipt=io.read(out/'receipt.json');start=perf_counter_ns();guard={};model_guard={}
    for n,h in receipt['artifact_sha256'].items():io.require(io.sha(out/n)==h,'main support artifact unchanged')
    saved=io.read(out/'attempts.json');rows=[];traces=defaultdict(dict);learned={};witness=defaultdict(list);pi_checks=queries=0
    def denied(*args,**kwargs):raise RuntimeError('main compatibility/controller/bounds disabled during independent audit')
    try:
        with read_only(guard),main.no_model_activity(model_guard),patch.object(main,'replay',denied),patch.object(main.CausalReader,'consume',denied),patch.object(main,'aggregate',denied),patch.object(main,'one_bound',denied),patch.object(legacy,'run',denied):
            # A separate event reader, not main.source_traces/project.
            outer=iter(groupby(io.rows(main.SOURCE/'native/events.jsonl.gz'),native.case_key));cases=list(io.rows(main.SOURCE/'native/cases.jsonl.gz'))
            for source_index,(spec,case) in enumerate(zip(native.population(),cases)):
                key,it=next(outer);io.require(key==native.case_key(spec),'independent source order');initial=deepcopy(case['initial']);steps=[]
                for e in it:
                    if e['event']=='STEP_COMPLETE':
                        io.require(e['logical_step']==len(steps),'independent consecutive public responses');steps.append(dict(command=e['command'],after=e['after']))
                unit=native.unit_key(spec);program=spec['program'];traces[unit][program]=(initial,steps)
                w=case['state_witness_refs'][0];witness[unit].append((w['native_sha256'],w['comparison_python_sha256']))
                if program=='LEARNED_JOINT_BANK0':learned[unit]=case['deadline_loss']
                for action,rate in main.CANDIDATES:
                    expected=replay(initial,steps,spec['task'],spec['planned_boundary'],action,rate);index=len(rows);row=saved[index]
                    for k in ('status','matched_prefix_steps','source_commands_examined','source_responses_consumed','first_difference','matched_prefix_sha256','supported_loss','supported_success','replay_fixed_policy_queries'):
                        io.require(expected[k]==row[k],'independent fixed-program result '+str(index)+' '+k)
                    io.require(row['source_spec']==spec and row['source_case_sha256']==io.digest(case) and row['unit']==list(unit) and row['action']==action and row['rate']==rate,'independent full attempt identity')
                    rows.append(row);queries+=expected['replay_fixed_policy_queries'];pi_checks+=expected['literal_pi_checks']
            io.require(next(outer,None) is None and len(rows)==len(saved)==648 and all(len(v)==3 and v[0]==v[1]==v[2] for v in witness.values()),'complete independent source and coupling')
            expected_bounds,summaries=literal_bounds(rows,traces,learned)
            key=lambda r:(str(r['unit']),r['action'],r['rate'])
            io.require(sorted(expected_bounds,key=key)==sorted(io.read(out/'unit_bounds.json'),key=key),'all independent unit bounds')
            io.require(summaries==io.read(out/'fixed_program_bounds.json'),'all independent full-program bounds')
            io.require(queries==receipt['replay_fixed_policy_queries'] and queries<=324000 and queries+receipt['replay_fixed_policy_queries']<=648000,'full new CPU query budget')
        result=dict(integrity='PASSED',manifest_id=m['manifest_id'],source_cases=54,attempts=648,unit_programs=216,
            independent_replay_fixed_policy_queries=queries,literal_pi_checks=pi_checks,guard=guard,model_guard=model_guard,
            main_actor_reader_bounds_disabled=True,shared_TaskMemory_and_macro_disclosed=True,no_independent_physics=True,
            original_native_qualification_remains_failed=True,main_receipt_sha256=io.sha(out/'receipt.json'),
            new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start)
        io.write(out/'audit.json',result);return result
    except BaseException:
        import traceback
        io.write(out/'audit_failure.json',dict(integrity='FAILED',exception=traceback.format_exc(),guard=guard,independent_attempts_completed=len(rows),
            independent_policy_queries=queries,wall_ns=perf_counter_ns()-start,no_automatic_retry=True));raise
