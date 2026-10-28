"""Independent cost/actuator/PI/lifecycle checks and record-only actor replay.

V1 checks fixed-bank own-history deployment without resimulation.
Replay shares the actor/policy; separate scalar and batch checks disable the
online providers and numerical functions. Strict feature extraction is shared.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
from itertools import groupby
import math,gzip,json
import numpy as np
from src.analysis import occam_reference_qualification_io_v1 as a
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_journal_audit_v1 import applied,ledger_add,simulation,check_ledger,check_observation,physical_rows_equal
from src.analysis.task_passive_audit_v1 import audit_pi
from src.probe.occam_qualification_program_v1 import program_spec
from src.analysis.occam_qualification_math_audit_v1 import audit_windows
from src.analysis.occam_qualification_envelope_v1 import bind_case
from src.analysis.continuous_state_witness_v1 import compare_witnesses
from src.probe import occam_qualification_program_v1 as actor
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
io=a.io


def same(x,y,message='independent record mismatch'):io.require(io.digest(normalize(x))==io.digest(normalize(y)),message)


def literal_legacy_command(controller,raw_policy):
    raw=np.clip(np.asarray(raw_policy,np.float32),-1,1).astype(float)
    manual=raw.copy();manual[:2]=np.array(controller['matrix_xy'],float)@raw[:2]+np.array(controller['offset'][:2],float)
    return np.clip(manual,-1,1).astype(np.float32)


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
    p=a.provider(spec)
    result=actor.run_program(spec['task'],StepObservation(**case['initial']),spec['planned_boundary'],spec['program'],a.nominal(spec),p,fixed,step,emit)
    same(cursor,len(public));same(physical,len(steps));same(queries,case['policy_queries'])
    for k,v in result['outcome'].items():same(v,case[k],'replayed outcome '+k)
    return queries


def reconstruct(spec,case,events,private,ledger):
    from src.analysis.continuous_state_witness_v1 import verify_witness,compare_witnesses
    legacy=program_spec(spec['program'])['kind']=='LEGACY'
    same(case['ledger_before'],ledger);same(case['initial_fault_oracle'],a.initial_fault());same(case['destination_oracle'],a.destination(spec))
    io.require(case['completed'] and case['environment_closed'] and case['error'] is None and case['close_error'] is None,'partial case')
    same(case['captures'],0);same(case['restores'],0)
    current=clock=command=intent=reset=None;factory=0;resets=Counter();steps=[];public=[];local={};fault=a.initial_fault();boundary=None
    tape=a.noise(spec);integral=[0.,0.];pi_pending=None;pi_count=0;raw_count=0;rate=program_spec(spec['program']).get('prefix_rate',.5);rate_plan=None;queries=[];decisions=[];costs=[];feedback=[];last_stamp=-1
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
        elif k=='NOISE_COMMITMENT':same(e['tape_sha256_oracle'],io.digest(tape.tolist()),'noise tape commitment');same(e['noise_namespace_oracle'],a.registry()['noise_namespace'],'frozen noise namespace')
        elif k=='AGENT_EVENT':
            p=e['public_payload'];io.require(current is not None and command is None and intent is None and p['sequence']==len(public)
                and p['at_calls']==len(steps) and p['saved_ns']<=e['saved_ns'],'public event chronology')
            public.append(e);local[p['sequence']]=e;name=e['agent_event']
            if name=='PI_PLAN':io.require(pi_pending is None,'duplicate plan');pi_pending=p
            elif name=='COMMAND':
                io.require(not any(current[x] for x in ('success','terminated','truncated')) and len(steps)<500,'command after end')
                same(p['before'],current);io.require(p['decision_sequence']<p['sequence'] and p['decision_sequence'] in local,'future command parent')
                if p['raw_policy'] is not None:
                    raw_count+=1
                    if legacy:
                        controller=local[p['decision_sequence']]['public_payload']['controller'];manual=literal_legacy_command(controller,p['raw_policy'])
                        io.require(np.allclose(manual,p['command'],atol=1e-7,rtol=0),'independent original C8 command map')
                    else:
                        io.require(pi_pending is not None and p['decision_sequence']==pi_pending['sequence'],'saved PI consumed')
                        q=pi_pending['saved_plan']['pi_plan'];same(q['query']['time_constant_s'],rate)
                        integral,_=audit_pi(q,p['command'],integral,spec['task'],len(steps),current,p['raw_policy']);pi_count+=1
                else:io.require(p['phase'] in ('REPOSITION','WARM_PROBE','FIXED_PROBE'),'missing fixed policy')
                command=e
            elif name=='TASK_MEMORY_COMMIT':same(p['memory']['integral_xy'],integral);same(p['memory']['current'],current);pi_pending=None
            elif name=='WINDOW_QUERY':
                q=p['value'];same(q['initial'],case['initial']);same(q['completed_steps'],len(steps));same(q['integral_xy'],integral)
                history=[];prior=case['initial']
                for row in steps:history.append(dict(at_calls=row['logical_step'],before=prior,command=row['command'],after=row['after']));prior=row['after']
                same(q['history'],history,'future/omitted actual history');queries.append(p)
            elif name=='WINDOW_DECISION':
                io.require(queries and p['input_sequence']==queries[-1]['sequence']==p['sequence']-1,'query before decision')
                d=p['declaration'];same(d['public_query_sha256'],io.digest(queries[-1]['value']))
                decisions.append(p)
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
    same(case['policy_queries'],raw_count)
    if not legacy:
        same(sum(m['deadline_charge_steps'] for m in costs),case['deadline_loss'])
        io.require(costs and costs[0]['start_at']==0 and costs[-1]['end_at']==len(steps) and costs[-1]['terminal'],'complete cost coverage')
        for left,right in zip(costs,costs[1:]):same(left['end_at'],right['start_at']);io.require(not left['terminal'],'continued terminal')
    else:io.require(not costs and not decisions and not feedback,'legacy references are not model-window programs')
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
    if any(e['agent_event']=='RELOCATION_EVIDENCE' for e in public):expected+=['POST_RELOCATION']
    if any(e['agent_event'] in ('TASK_MEMORY_RETURN','POST_MOVE_TASK_ENTRY') for e in public):expected+=['POST_ACQUISITION']
    if decisions:expected+=['FIRST_RATE_PRE','FIRST_RATE_POST']
    expected+=['FINAL'];same(list(bylabel),expected)
    for l,r in (('INTERVENTION_PRE','INTERVENTION_POST'),('FIRST_RATE_PRE','FIRST_RATE_POST')):
        if l in bylabel:io.require(compare_witnesses(bylabel[l]['witness'],bylabel[r]['witness'])['comparison_equal'],'nonphysical operation changed state')
    same(len(decisions),case['performance_windows']);same(len(feedback),len(decisions))
    for d,f in zip(decisions,feedback):same(f['decision_sequence'],d['sequence'])
    return ledger,steps,public,bylabel


def _literal_model_check(spec,public):
    from contextlib import ExitStack
    from unittest.mock import patch
    from src.probe import occam_qualification_provider_v1 as providers
    from src.probe import occam_performance_core_v1 as online
    settings=program_spec(spec['program']);bank=None
    if settings['kind']=='TRAINED':bank=io.read(a.TRAIN/'learning'/(settings['bank']+'_raw.json'))
    def denied(*args,**kwargs):raise AssertionError('online model/actor forbidden in independent arithmetic')
    with ExitStack() as stack:
        for obj,name in ((providers.TrainedProvider,'declare'),(providers.TrainedProvider,'feedback'),
            (providers.FixedRateProvider,'declare'),(actor,'run_program'),(online,'forecast'),(online,'update'),(online,'basis_forward')):
            stack.enter_context(patch.object(obj,name,denied))
        return audit_windows(spec['program'],public,bank,a.config()['prediction_constant'])


def model_execution_coverage(phase,panels):
    io.require(phase in a.PHASES,'registered coverage phase')
    if phase=='QUAL':return True
    for program in a.PROGRAMS:
        settings=program_spec(program)
        if settings['kind']=='TRAINED':
            io.require(any(p['program']==program and p['performance_windows'] for p in panels),'native model execution coverage '+program)
            if settings['adapt']:io.require(any(p['program']==program and p['filter_updates'] for p in panels),'actual native adaptation coverage '+program)
    return True


def audit(path,phase):
    from src.analysis.release_learning_guard_v1 import read_only
    path=Path(path).resolve();manifest=a.checked(path);out=path.parent/phase.lower();summary=io.read(out/'summary.json');done=io.read(out/'completion.json')
    io.require(summary['status']==done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','complete allocated population before qualification')
    for n,h in done['artifact_sha256'].items():same(io.sha(out/n),h,'immutable complete cohort '+n)
    start=perf_counter_ns();guard={};caps=a.limits(phase);count=Counter();panels=[];prefix={};post={};unit=None;initial_reference=None
    outer=groupby(io.rows(out/'events.jsonl.gz'),key=lambda row:tuple(row[k] for k in a.KEYS))
    priv=groupby(io.rows(out/'witnesses.jsonl.gz'),key=lambda row:tuple(row[k] for k in a.KEYS));cases=iter(io.rows(out/'cases.jsonl.gz'))
    previous=(0,0,-1,-1);ledger=dict(counts={},by_phase={})
    with read_only(guard,max_solve=caps['audit_solve_max'],max_cold_fits=caps['audit_c4_c8_refits_max']), \
        gzip.open(out/'prequential_windows.jsonl.gz','xt',encoding='utf8') as diagnostics:
        for spec in a.population(phase):
            case=next(cases);ek,ev=next(outer);pk,pv=next(priv);same(ek,a.key(spec));same(pk,ek);events=list(ev);private=list(pv)
            previous=bind_case(manifest,spec,case,events,private,previous)
            ledger,steps,public,witnesses=reconstruct(spec,case,events,private,ledger)
            queries=replay(spec,case,public,steps);math_result=_literal_model_check(spec,public)
            same(math_result['updates'],case['full_feedback_windows']);same(math_result['updates'],case['filter_update_attempts'])
            count.update(executions=1,control_steps=len(steps),audit_fixed_policy_queries=queries,
                audit_filter_updates=math_result['updates'],independent_batch_solves=math_result['batch_solves'],observed_windows=math_result['windows'],
                actual_c4_c8_fit_attempts=case.get('c4_c8_fit_attempts',0),actual_c4_c8_optimizer_nfev=case.get('c4_c8_optimizer_nfev',0))
            fits=case['legacy_fit_accounting']
            same(fits.get('fit_intents',0),case.get('c4_c8_fit_attempts',0));same(fits.get('fit_results',0),case.get('c4_c8_fit_results',0))
            same(fits.get('optimizer_nfev',0),case.get('c4_c8_optimizer_nfev',0))
            settings=program_spec(spec['program']);next_unit=(spec['group'],spec['task'],spec['context'])
            if next_unit!=unit:prefix.clear();post.clear();unit=next_unit;initial_reference=None
            if initial_reference is None:initial_reference=witnesses['INITIAL']['witness']
            else:io.require(compare_witnesses(initial_reference,witnesses['INITIAL']['witness'])['comparison_equal'],'all complete programs share controlled native/RNG initial state')
            source='C8' if settings['kind']=='LEGACY' else 'RAW_'+str(settings.get('prefix_rate',.5))
            def physical_same(left,right,n):
                from src.analysis.memory_reset_streaming_audit_v2 import compare_info
                io.require(len(left)>=n and len(right)>=n,'actual common segment length')
                for l,r in zip(left[:n],right[:n]):
                    for field in ('command','raw_policy','after','executed_action_oracle','simulation_time_before','simulation_time_after','noise_cursor_after','reward'):same(l[field],r[field],'common physical segment '+field)
                    compare_info(l,r)
            if source in prefix:
                ref=prefix[source];io.require(compare_witnesses(ref[1]['INITIAL']['witness'],witnesses['INITIAL']['witness'])['comparison_equal'],'same-source controlled initial state')
                n=min(spec['planned_boundary'],len(steps),len(ref[0]));physical_same(ref[0],steps,n);count['common_prefix_pairs']+=1
            else:prefix[source]=(steps,witnesses)
            if settings['kind']!='LEGACY':
                action=(settings.get('prefix_rate',.5),settings['action']);entry=witnesses.get('POST_ACQUISITION')
                if action in post:
                    ref_steps,ref_entry=post[action];same(entry is None,ref_entry is None,'shared acquisition availability')
                    if entry is not None:
                        same(entry['logical_step'],ref_entry['logical_step']);physical_same(ref_steps,steps,entry['logical_step'])
                        io.require(compare_witnesses(entry['witness'],ref_entry['witness'])['comparison_equal'],'common acquisition end full native/RNG state')
                        count['common_acquisition_pairs']+=1
                    else:count['early_end_acquisition_pairs']+=1
                else:post[action]=(steps,entry)
            for value in math_result['diagnostics']:diagnostics.write(json.dumps({**spec,**value},separators=(',',':'),allow_nan=False)+'\n')
            panels.append({**spec,'success':case['success'],'deadline_loss':case['deadline_loss'],'total_steps':len(steps),
                'boundary_applied':case['boundary_applied'],'performance_windows':case['performance_windows'],'filter_updates':case['full_feedback_windows'],
                'mse':math_result['mse'],'constant_mse':math_result['constant_mse'],'prediction_missing_reason':math_result['missing_reason'],
                'c4_c8_fit_attempts':case.get('c4_c8_fit_attempts',0),'c4_c8_optimizer_nfev':case.get('c4_c8_optimizer_nfev',0)})
    io.require(next(cases,None) is None and next(outer,None) is None and next(priv,None) is None,'exact allocation and all original records consumed')
    same(count['executions'],len(a.population(phase)));same(count['control_steps'],summary['control_steps']);same(ledger,summary['lifecycle'])
    same(previous[0],summary['events']);same(previous[1],summary['private_records'])
    for key,limit in (('audit_fixed_policy_queries','audit_policy_queries_max'),('audit_filter_updates','online_filter_updates_max'),
        ('actual_c4_c8_fit_attempts','c4_c8_fit_attempts_max'),('actual_c4_c8_optimizer_nfev','c4_c8_optimizer_nfev_max')):io.require(count[key]<=caps[limit],'full-population numerical/query budget '+key)
    model_execution_coverage(phase,panels)
    result=dict(integrity='PASSED',phase=phase,manifest_id=manifest['manifest_id'],counts=dict(count),ledger=ledger,guard=guard,panels=panels,
        prequential_windows_sha256=io.sha(out/'prequential_windows.jsonl.gz'),shared_actor_policy_and_strict_feature_extraction_disclosed=True,
        independent_scalar_filter_and_batch_network_arithmetic=True,independent_physics_resimulation=False,
        new_environment_interactions=0,new_neural_training=0,online_LLM_API_calls=0,
        task_benefit_or_paper_qualification=False,wall_ns=perf_counter_ns()-start)
    io.write(out/'audit.json',result);a.checked(path);return {k:v for k,v in result.items() if k!='panels'}
