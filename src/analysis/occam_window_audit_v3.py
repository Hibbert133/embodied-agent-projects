"""Independent cost/actuator/PI/lifecycle checks and record-only actor replay.

Replay shares the actor/previous acquisition primitive, never resimulates.
Separate scalar cost and batch Gaussian conditioning do not call those formulas.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
from itertools import groupby
import math
import numpy as np
from src.analysis import occam_window_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation,check_ledger,check_observation,physical_rows_equal
from src.analysis.task_passive_audit_v1 import audit_pi
from src.analysis.occam_performance_independent_v1 import batch_posterior
from src.analysis.occam_window_envelope_v1 import bind_case
from src.analysis.continuous_state_witness_v1 import compare_witnesses
from src.probe import occam_window_program_v1 as actor
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
io=a.io


def same(x,y,message='independent record mismatch'):io.require(io.digest(normalize(x))==io.digest(normalize(y)),message)


def scalar_cost(task,initial,steps,start,stop,terminal):
    def phi(value,n):
        if n==500 or any(value[k] for k in ('success','terminated','truncated')):return 0.
        obs=value['observation'];indices=range(3) if task=='reach-v3' else range(4,7)
        return min(1.,math.sqrt(sum((obs[i]-obs[36+j])**2 for j,i in enumerate(indices))))
    before=initial if start==0 else steps[start-1]['after'];current=before;value=0.
    for index in range(start,stop):
        after=steps[index]['after'];value+=1/500.+phi(after,index+1)-phi(current,index);current=after
    penalty=0
    if terminal and not current['success']:
        penalty=500-stop;value+=penalty/500.
    return dict(cost=value,deadline_charge_steps=stop-start+penalty,potential_before=phi(before,start),potential_after=phi(current,stop))


def replay(spec,case,public,steps):
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy(spec['task']);cursor=physical=queries=0
    def fixed(observation):
        nonlocal queries
        queries+=1;return np.asarray(policy.get_action(np.array(observation,copy=True)),np.float32)
    def emit(kind,payload):
        nonlocal cursor
        io.require(cursor<len(public),'invented replay event');e=public[cursor];p=e['public_payload']
        same(kind,e['agent_event']);same(payload,{k:v for k,v in p.items() if k not in ('sequence','saved_ns')},'public replay '+kind)
        cursor+=1;return deepcopy(p)
    def step(saved):
        nonlocal physical
        io.require(physical<len(steps),'invented physical replay');r=steps[physical]
        for k in ('command','phase','raw_policy'):same(saved[k],r[k],'executed command differs')
        physical+=1;return StepReceipt(StepObservation(**r['after']),physical)
    p=actor.OccamProvider(actor.constructed_bank(spec['fixture_sign']))
    result=actor.run(spec['task'],StepObservation(**case['initial']),spec['planned_boundary'],spec['acquisition_action'],p,fixed,step,emit)
    same(cursor,len(public));same(physical,len(steps));same(queries,case['policy_queries'])
    for k,v in result['outcome'].items():same(v,case[k],'replayed outcome '+k)
    return queries


def reconstruct(spec,case,events,private,ledger):
    from src.analysis.continuous_state_witness_v1 import verify_witness,compare_witnesses
    same(case['ledger_before'],ledger);same(case['initial_fault_oracle'],a.initial_fault());same(case['destination_oracle'],a.destination(spec))
    io.require(case['completed'] and case['environment_closed'] and case['error'] is None and case['close_error'] is None,'partial case')
    same(case['captures'],0);same(case['restores'],0)
    current=clock=command=intent=reset=None;factory=0;resets=Counter();steps=[];public=[];local={};fault=a.initial_fault();boundary=None
    tape=a.noise(spec);integral=[0.,0.];pi_pending=None;pi_count=0;rate=.5;rate_plan=None;queries=[];decisions=[];costs=[];feedback=[];last_stamp=-1
    for e in events:
        io.require(e['saved_ns']>last_stamp,'outer timestamp reversed');last_stamp=e['saved_ns'];k=e['event']
        if k in ('CASE_ALLOCATION','CASE_COMPLETE'):continue
        if k=='FACTORY_INTENT':same(e['ledger'],ledger);io.require(factory==0 and current is None,'repeat factory');factory=1
        elif k=='LIFECYCLE_RESET_INTENT':
            phase=e['phase'];io.require(reset is None and current is None,'mid-task reset')
            io.require((factory==1 and phase=='GOAL_GENERATION' and resets[phase]<50) or (factory==2 and phase=='CONTROLLED_RESET' and resets[phase]==0),'unallocated reset')
            same(e['before'],ledger);ledger=ledger_add(ledger,phase,'reset_attempts',1);reset=e
        elif k=='LIFECYCLE_RESET_COMPLETE':
            io.require(reset is not None and e['intent_sequence']==reset['sequence'],'orphan reset')
            ledger=simulation(ledger,e['phase'],100,500);ledger=ledger_add(ledger,e['phase'],'reset_completed',1);same(e['after'],ledger);resets[e['phase']]+=1;reset=None
        elif k=='FACTORY_COMPLETE':io.require(factory==1 and resets['GOAL_GENERATION']==50,'factory count');same(e['ledger'],ledger);factory=2
        elif k=='CONTROLLED_INITIAL':
            io.require(current is None and factory==2 and resets['CONTROLLED_RESET']==1,'one initial reset')
            same(e['observation'],case['initial']['observation']);same(e['ledger'],ledger);current=deepcopy(case['initial']);clock=e['simulation_time'];check_observation(current)
        elif k=='NOISE_COMMITMENT':same(e['tape_sha256_oracle'],io.digest(tape.tolist()));same(e['noise_namespace_oracle'],2026102812)
        elif k=='AGENT_EVENT':
            p=e['public_payload'];io.require(current is not None and command is None and intent is None and p['sequence']==len(public)
                and p['at_calls']==len(steps) and p['saved_ns']<=e['saved_ns'],'public event chronology')
            public.append(e);local[p['sequence']]=e;name=e['agent_event']
            if name=='PI_PLAN':io.require(pi_pending is None,'duplicate plan');pi_pending=p
            elif name=='COMMAND':
                io.require(not any(current[x] for x in ('success','terminated','truncated')) and len(steps)<500,'command after end')
                same(p['before'],current);io.require(p['decision_sequence']<p['sequence'] and p['decision_sequence'] in local,'future command parent')
                if p['raw_policy'] is not None:
                    io.require(pi_pending is not None and p['decision_sequence']==pi_pending['sequence'],'saved PI consumed')
                    q=pi_pending['saved_plan']['pi_plan'];same(q['query']['time_constant_s'],rate)
                    integral,_=audit_pi(q,p['command'],integral,spec['task'],len(steps),current,p['raw_policy']);pi_count+=1
                else:io.require(p['phase'] in ('REPOSITION','WARM_PROBE'),'missing fixed policy')
                command=e
            elif name=='TASK_MEMORY_COMMIT':same(p['memory']['integral_xy'],integral);same(p['memory']['current'],current);pi_pending=None
            elif name=='WINDOW_QUERY':
                q=p['value'];same(q['initial'],case['initial']);same(q['completed_steps'],len(steps));same(q['integral_xy'],integral)
                history=[];prior=case['initial']
                for row in steps:history.append(dict(at_calls=row['logical_step'],before=prior,command=row['command'],after=row['after']));prior=row['after']
                same(q['history'],history,'future/omitted actual history');queries.append(p)
            elif name=='WINDOW_DECISION':
                io.require(queries and p['input_sequence']==queries[-1]['sequence']==p['sequence']-1,'query before decision')
                same(p['declaration']['public_query_sha256'],io.digest(queries[-1]['value']));decisions.append(p)
            elif name=='RATE_PLAN':
                io.require(decisions and p['decision_sequence']==decisions[-1]['sequence'] and rate_plan is None,'unsaved selection')
                same(p['rate'],decisions[-1]['declaration']['selected_rate']);rate_plan=p
            elif name=='RATE_COMMIT':
                io.require(rate_plan is not None and p['plan_sequence']==rate_plan['sequence'],'rate changed without decision')
                rate=rate_plan['rate'];same(p['memory']['time_constant_s'],rate);same(p['memory']['integral_xy'],integral);rate_plan=None
            elif name in ('PREFIX_COST','ACQUISITION_COST','WINDOW_RESULT'):
                m=p['measurement'];stop=len(steps);same(m['end_at'],stop)
                other=scalar_cost(spec['task'],case['initial'],steps,m['start_at'],stop,m['terminal'])
                for field in other:io.require(abs(other[field]-m[field])<1e-12,'independent scalar cost '+field)
                rows=[];prior=case['initial'] if m['start_at']==0 else steps[m['start_at']-1]['after']
                for row in steps[m['start_at']:]:rows.append(dict(at_calls=row['logical_step'],before=prior,command=row['command'],after=row['after']));prior=row['after']
                same(m['rows_sha256'],io.digest(rows));costs.append(m)
                if name=='WINDOW_RESULT':io.require(decisions and p['parent_sequence']==decisions[-1]['sequence'],'factual feedback parent')
            elif name=='WINDOW_FEEDBACK':feedback.append(p)
        elif k=='STEP_INTENT':
            io.require(command is not None and intent is None,'step without durable command');same(e['command'],command['public_payload']['command']);same(e['global_command_sequence'],command['sequence']);same(e['logical_step'],len(steps));same(e['ledger_before'],ledger);intent=e
        elif k=='STEP_COMPLETE':
            io.require(intent is not None and e['intent_sequence']==intent['sequence'] and intent['saved_ns']<=e['execution_started_ns']<=e['completed_ns']<=e['saved_ns'],'execution ordering')
            same(e['command'],intent['command']);same(e['executed_action_oracle'],applied(e['command'],fault,tape[len(steps)]),'actuator float32 chain/noise cursor')
            same(e['logical_step'],len(steps));same(e['noise_cursor_after'],len(steps)+1);same(e['simulation_time_before'],clock)
            io.require(abs(e['simulation_time_after']-clock-.0125)<1e-10,'continuous clock')
            same(e['ledger_before'],ledger);ledger=simulation(ledger,'CONTROL',1,5);same(e['ledger_after'],ledger)
            check_observation(e['after']);same(e['after']['success'],bool(e['info'].get('success',False)));steps.append(e);current=e['after'];clock=e['simulation_time_after'];command=intent=None
        elif k=='FAULT_BOUNDARY':
            io.require(boundary is None and len(steps)==spec['planned_boundary'] and command is None,'fault boundary')
            same(e['old_fault_oracle'],fault);fault=a.destination(spec);same(e['new_fault_oracle'],fault);same(e['before'],e['after']);boundary=e
        elif k=='PHYSICAL_BOUNDARY':same(e['noise_past_sha256'],io.digest(tape[:len(steps)].tolist()));same(e['simulation_time'],clock)
        else:raise ValueError('unknown host event '+k)
    io.require(command is None and intent is None and reset is None and pi_pending is None and rate_plan is None,'unfinished operation')
    same(case['final'],current);same(case['ledger_before_close'],ledger);same(case['ledger_after_close'],ledger);check_ledger(ledger)
    same(case['boundary_applied'],boundary is not None);same(case['deadline_loss'],len(steps) if current['success'] else 500)
    io.require(len(steps)==case['total_steps']==case['host_attempts']==case['host_returned']==case['physical_rows_count']<=500,'physical count')
    same(case['policy_queries'],pi_count);same(sum(m['deadline_charge_steps'] for m in costs),case['deadline_loss'])
    io.require(costs and costs[0]['start_at']==0 and costs[-1]['end_at']==len(steps) and costs[-1]['terminal'],'complete cost coverage')
    for left,right in zip(costs,costs[1:]):same(left['end_at'],right['start_at']);io.require(not left['terminal'],'continued terminal')
    refs=[];bylabel={}
    for p in private:
        io.require(p['event']=='STATE_WITNESS','unknown private event');same(p['ledger_before'],p['ledger_after'])
        anchor=next((e for e in events if e['sequence']==p['source_anchor_sequence']),None)
        io.require(anchor is not None and anchor['saved_ns']==p['source_anchor_saved_ns']<=p['started_ns']<=p['completed_ns']<=p['saved_ns'],'private chronology')
        verify_witness(p['witness'],full_sha256=p['source_witness']['python_semantic_sha256'],native_sha256=p['source_witness']['native_sha256'])
        at=p['logical_step'];io.require(0<=at<=len(steps),'witness after future');same(p['source_witness']['noise_past_sha256'],io.digest(tape[:at].tolist()))
        expected=next(e for e in events if e['event']=='CONTROLLED_INITIAL') if at==0 else steps[at-1]
        same(p['source_witness']['simulation_time'],expected['simulation_time'] if at==0 else expected['simulation_time_after'])
        same(p['ledger_before'],expected['ledger'] if at==0 else expected['ledger_after'])
        refs.append(dict(label=p['label'],sequence=p['sequence'],logical_step=at,native_sha256=p['witness']['native_sha256'],comparison_python_sha256=p['witness']['comparison_python_sha256']))
        io.require(p['label'] not in bylabel,'duplicate witness');bylabel[p['label']]=p
    same(case['state_witness_refs'],refs)
    expected=['INITIAL']+(['INTERVENTION_PRE','INTERVENTION_POST'] if boundary else [])
    if any(e['agent_event']=='TASK_MEMORY_RETURN' for e in public):expected+=['POST_ACQUISITION']
    if decisions:expected+=['FIRST_RATE_PRE','FIRST_RATE_POST']
    expected+=['FINAL'];same(list(bylabel),expected)
    for l,r in (('INTERVENTION_PRE','INTERVENTION_POST'),('FIRST_RATE_PRE','FIRST_RATE_POST')):
        if l in bylabel:io.require(compare_witnesses(bylabel[l]['witness'],bylabel[r]['witness'])['comparison_equal'],'nonphysical operation changed state')
    # Independently condition a joint Gaussian once for the completed sequence.
    H=[];Y=[];prior=actor.constructed_bank(spec['fixture_sign'])['prior'];batch=None
    for d,f in zip(decisions,feedback):
        v=f['feedback'];same(f['decision_sequence'],d['sequence']);decl=d['declaration']
        if v.get('status')=='NO_UPDATE_PARTIAL_WINDOW':continue
        H.append(decl['bases'][decl['selected_index']]);target=next(e['public_payload']['measurement']['cost'] for e in public if e['agent_event']=='WINDOW_RESULT' and e['public_payload']['parent_sequence']==d['sequence']);Y.append([target]);batch=v['posterior']
    same(len(H),case['full_feedback_windows']);same(len(decisions),case['performance_windows']);same(len(feedback),len(decisions))
    if H:
        mu,cov=batch_posterior(prior['mean'],prior['covariance'],np.asarray(H),np.asarray(Y),prior['process_covariance'],prior['measurement_covariance'])
        io.require(np.allclose(mu,batch['mean'],atol=1e-10,rtol=0) and np.allclose(cov,batch['covariance'],atol=1e-10,rtol=0),'independent full-sequence posterior')
    return ledger,steps,public,bylabel,len(H)


def audit(path):
    from src.analysis.release_learning_guard_v1 import read_only
    path=Path(path).resolve();manifest=a.checked(path);out=path.parent/'native';start=perf_counter_ns();completion=io.read(out/'completion.json')
    io.require(completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT' and completion['manifest_id']==manifest['manifest_id'],'partial/wrong allocation cannot pass')
    for n,h in completion['artifact_sha256'].items():same(io.sha(out/n),h)
    summary=io.read(out/'summary.json');cases=list(io.rows(out/'cases.jsonl.gz'));same(len(cases),36)
    outer=iter(groupby(io.rows(out/'events.jsonl.gz'),a.key));priv=iter(groupby(io.rows(out/'witnesses.jsonl.gz'),a.key))
    for field in a.IDENTITY:same(summary[field],manifest[field])
    same(summary['allocated_executions'],36);same(summary['executions'],36)
    expected_compact=[{k:c[k] for k in (*a.KEYS,'total_steps','deadline_loss','success','policy_queries','performance_windows','full_feedback_windows','boundary_applied')} for c in cases]
    same(summary['rows'],expected_compact,'complete retained summary population')
    ledger=dict(counts={},by_phase={});guard={};count=Counter();pairs={};panels=[];eseq=pseq=0;previous=(0,0,-1,-1)
    with read_only(guard,max_solve=5000):
        for spec,case in zip(a.population(),cases):
            same({k:case[k] for k in a.KEYS},spec);ek,es=next(outer);pk,ps=next(priv);same(ek,a.key(spec));same(pk,a.key(spec));es=list(es);ps=list(ps)
            previous=bind_case(manifest,spec,case,es,ps,previous)
            for e in es:same(e['sequence'],eseq);eseq+=1
            for p in ps:same(p['sequence'],pseq);pseq+=1
            ledger,steps,public,witnesses,updates=reconstruct(spec,case,es,ps,ledger)
            queries=replay(spec,case,public,steps);count.update(executions=1,control_steps=len(steps),audit_fixed_policy_queries=queries,audit_filter_updates=updates,independent_batch_solves=int(updates>0))
            first=next((e['public_payload'] for e in public if e['agent_event']=='WINDOW_DECISION'),None)
            entry=None if first is None else first['at_calls'];key=tuple(spec[k] for k in a.KEYS if k!='fixture_sign')
            if spec['fixture_sign']==-1:pairs[key]=(steps,witnesses,first)
            else:
                paired_steps,pw,pd=pairs.pop(key);same(pd is None,first is None)
                if first is not None:
                    same(pd['at_calls'],entry);io.require(physical_rows_equal(paired_steps,steps,entry),'common acquisition trajectory differs')
                    io.require(compare_witnesses(pw['POST_ACQUISITION']['witness'],witnesses['POST_ACQUISITION']['witness'])['comparison_equal'],'common post-acquisition native state differs')
                    changed=paired_steps[entry]['command']!=steps[entry]['command'];io.require(pd['declaration']['selected_rate']!=first['declaration']['selected_rate'],'fixtures did not change legal selection')
                    count.update(live_fixture_pairs=1,first_actual_command_different=int(changed))
                else:count.update(early_end_fixture_pairs=1)
            panels.append({**spec,'total_steps':len(steps),'success':case['success'],'deadline_loss':case['deadline_loss'],
                'performance_windows':case['performance_windows'],'full_feedback_windows':updates,'untrained_fixture_no_scientific_comparison':True})
    io.require(not pairs and next(outer,None) is None and next(priv,None) is None,'unconsumed allocation')
    same(ledger,summary['lifecycle']);same(eseq,summary['events']);same(pseq,summary['private_records']);same(count['control_steps'],summary['control_steps'])
    io.require(count['live_fixture_pairs']>0 and count['first_actual_command_different']>0,'no authenticated changed-choice physical chain')
    io.require(count['audit_fixed_policy_queries']<=18000 and count['audit_filter_updates']<=1116,'audit budget')
    result=dict(integrity='PASSED',manifest_id=manifest['manifest_id'],counts=dict(count),ledger=ledger,guard=guard,panels=panels,
        independent_physics_resimulation=False,shared_actor_replay_disclosed=True,scalar_cost_and_joint_gaussian_are_independent=True,
        online_LLM_API_calls=0,scientific_model_training=0,task_benefit_or_paper_qualification=False,wall_ns=perf_counter_ns()-start)
    io.write(out/'audit.json',result);a.checked(path);return {k:v for k,v in result.items() if k!='panels'}
