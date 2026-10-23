"""Read-only journal/command auditor. No world construction or physical replay.

The immutable historical actor is a prefix specification; numerical predictions,
float32 executor order, record causality, ledgers and state matching are checked
independently of the new collector/host. Prefix C4/C8 refits are separately costed.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
import numpy as np
from src.analysis import command_contrast_io_v1 as allocation
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.continuous import StepObservation

io=allocation.io
PHYSICAL=('logical_step','phase','command','executed_action_oracle','after','noise_cursor_after',
          'simulation_time_before','simulation_time_after')
KEYS=('cohort','case_id','unit_id','group','task','seed','context','measurement_program','target','action_id')


def same(a,b,message='record differs'):
    io.require(io.digest(normalize(a))==io.digest(normalize(b)),message)


def raw_models():
    """Load raw coefficient arrays, not the collector's model wrapper."""
    allocation.source_models()  # source hashes and complete bank contract
    result={t:{} for t in allocation.POLICIES}
    for key,entry in io.read(allocation.SOURCE/'training/models.json')['models'].items():
        if entry['kind']=='LINEAR':
            p=allocation.SOURCE/'training'/entry['file']; value=io.read(p)
            result[value['task']][key]=(value,io.sha(p))
    return result


def expected_predictions(query,models):
    a,b,o=np.asarray(query['observations'],float); out={}
    displacement=np.r_[o[:3]-b[:3],b[:3]-a[:3]]
    for key,(model,sha) in models.items():
        feature=model['feature']; predictions=[]; stats=model['stats']
        for candidate in query['candidates']:
            u=candidate['sent_command']
            x=(np.r_[o,u] if feature=='F43' else np.r_[displacement,u] if feature=='H10' else
               np.r_[o[:3],displacement,u,o[3],o[4:7]-o[:3],o[-3:]-o[:3]])
            # Saved coefficients already have physical-metre output units.
            predictions.append((np.r_[1.,(x-stats['input_mean'])/stats['input_scale']]@np.asarray(model['coefficient'])).tolist())
        out[key]={'source_sha256':sha,'predictions_m':predictions}
    return out


def audit_plan(plan,spec,history,baseline,models):
    from src.probe.command_contrast_v1 import PhysicalQuery,SavedPlan
    SavedPlan.from_dict(plan)  # strict allowlist, no evaluator/future fields
    q=plan['query']; n=len(history)-1
    same(q['task'],spec['task']); same(q['decision_step'],n)
    same(q['observation_steps'],list(range(n-2,n+1)))
    same(q['observations'],history[-3:],'query used fabricated/stale/future history')
    same(q['baseline_command'],baseline,'baseline differs from fixed source program')
    candidates=[]
    for name,delta in zip(('BASELINE','X_PLUS','X_MINUS','Y_PLUS','Y_MINUS'),
                          ((0,0),(.25,0),(-.25,0),(0,.25),(0,-.25))):
        command=np.asarray(baseline,float).copy(); command[:2]=np.clip(command[:2]+delta,-1,1)
        candidates.append({'action_id':name,'sent_command':command.astype(np.float32).tolist()})
    same(q['candidates'],candidates,'prediction must use physical float32 commands, including duplicates')
    expected=expected_predictions(q,models); same(sorted(plan['models']),sorted(expected))
    for key,value in expected.items():
        same(plan['models'][key]['source_sha256'],value['source_sha256'])
        io.require(np.allclose(plan['models'][key]['predictions_m'],value['predictions_m'],atol=1e-14,rtol=1e-12),
                   'independent physical-unit prediction differs')
    return PhysicalQuery.from_dict(q)


class QueryReached(Exception):
    def __init__(self,payload): self.payload=deepcopy(payload)


def replay_prefix(spec,initial,public,steps,nominal):
    """Replay the frozen prefix on saved observations; never call an environment.

    Public fit results are compared with independent refits; wall-clock values
    are intentionally excluded from numerical/causal equality.
    """
    from src.probe import observable_history_behavior_v1 as behavior
    from src.rollout.task_registry import create_task_policy
    from src.analysis.response_qualification_audit_v1 import fit_close
    policy=create_task_policy(spec['task']); index=cursor=queries=refits=nfev=0; target=None
    def get_action(observation):
        nonlocal queries
        queries+=1; return policy.get_action(np.asarray(observation).copy())
    def emit(kind,payload):
        nonlocal index,refits,nfev
        phase=payload.get('phase')
        reached=(spec['target']=='COLD_STEP2' and payload['at_calls']==2 and phase=='FIXED_PROBE' or
                 spec['target']=='POST_MOVE_MEAS0' and phase in ('MEASURE_FEEDBACK','MEASURE_BALANCED') or
                 spec['target']=='POST_MEASURE_TASK0' and phase=='TASK_AFTER_MEASUREMENT')
        if kind=='COMMAND' and reached: raise QueryReached(payload)
        io.require(index<len(public),'missing saved prefix event')
        saved=public[index]; same(saved['agent_event'],kind)
        actual=deepcopy(saved['public_payload']); index+=1
        io.require(actual['sequence']==index-1,'public sequence gap')
        content={k:v for k,v in actual.items() if k not in ('sequence','saved_ns')}
        if kind=='FIT_RESULT':
            fit_close(content.pop('fit'),payload['fit']); payload={k:v for k,v in payload.items() if k!='fit'}
            refits+=1; nfev+=int(actual['fit'].get('nfev',0))
        same(content,payload,'frozen prefix event/numerical command differs')
        return actual
    def consume(saved):
        nonlocal cursor
        io.require(cursor<len(steps),'missing actual prefix response')
        row=steps[cursor]; same(saved['command'],row['command']); same(saved['phase'],row['phase'])
        cursor+=1; return StepObservation(**row['after'])
    outcome=None
    try:
        outcome=behavior.run(spec['task'],StepObservation(**initial),nominal,spec['planned_boundary'],
            spec['measurement_program'],allocation.measurement(spec),get_action,consume,emit)
    except QueryReached as reached: target=reached.payload
    io.require(index==len(public) and cursor==len(steps),'extra prefix events or unconsumed responses')
    return target,outcome,{'policy_queries':queries,'independent_c4_c8_refits':refits,'independent_c4_c8_nfev':nfev}


def audit_case(spec,case,events,private,nominal,models,ledger_before):
    from src.analysis.short_probe_journal_audit_v1 import applied,check_ledger,ledger_add,simulation,check_observation
    from src.analysis.continuous_state_witness_v1 import verify_witness
    for key,value in spec.items(): same(case[key],value,'allocation differs')
    io.require(case['completed'] and case['environment_closed'] and case['error'] is None and case['close_error'] is None,
               'incomplete execution cannot pass; retain its raw records')
    same(case['ledger_before'],ledger_before); same(case['fault_oracle'],allocation.fault(spec))
    io.require(not case['captures'] and not case['restores'],'snapshot/restore prohibited')
    ledger=deepcopy(ledger_before); initial=current=clock=command=intent=reset=None
    steps=[]; public=[]; global_public={}; plans=[]; factories=0; resets=Counter(); tape=allocation.noise(spec['seed'],spec['noise_namespace'])
    allowed={'FACTORY_INTENT','FACTORY_COMPLETE','LIFECYCLE_RESET_INTENT','LIFECYCLE_RESET_COMPLETE','CONTROLLED_INITIAL',
             'NOISE_COMMITMENT','AGENT_EVENT','STEP_INTENT','STEP_COMPLETE','PHYSICAL_BOUNDARY','UNIT_PLAN_COMMITTED','UNIT_PLAN_REUSED'}
    for e in events:
        kind=e['event']; io.require(kind in allowed,'unknown physical or evaluator mutation: '+kind)
        if kind=='FACTORY_INTENT':
            io.require(factories==0 and current is None,'repeated factory'); same(e['ledger'],ledger); factories=1
        elif kind=='LIFECYCLE_RESET_INTENT':
            phase=e['phase']; io.require(reset is None and current is None,'mid-run/nested reset')
            io.require((factories==1 and phase=='GOAL_GENERATION' and resets[phase]<50) or
                       (factories==2 and phase=='CONTROLLED_RESET' and resets[phase]==0),'unregistered reset')
            same(e['before'],ledger); ledger=ledger_add(ledger,phase,'reset_attempts',1); reset=e
        elif kind=='LIFECYCLE_RESET_COMPLETE':
            io.require(reset is not None and e['intent_sequence']==reset['sequence'] and e['phase']==reset['phase'],'orphan reset')
            ledger=simulation(ledger,e['phase'],100,500); ledger=ledger_add(ledger,e['phase'],'reset_completed',1)
            same(e['after'],ledger); resets[e['phase']]+=1; reset=None
        elif kind=='FACTORY_COMPLETE':
            io.require(factories==1 and resets['GOAL_GENERATION']==50 and reset is None,'factory reset count'); same(e['ledger'],ledger); factories=2
        elif kind=='CONTROLLED_INITIAL':
            io.require(current is None and factories==2 and resets['CONTROLLED_RESET']==1,'one controlled initial reset')
            same(e['ledger'],ledger); same(e['task'],spec['task']); same(e['observation'],case['initial']['observation'])
            current=initial=deepcopy(case['initial']); check_observation(current); clock=e['simulation_time']
        elif kind=='NOISE_COMMITMENT':
            io.require(current is not None and not public and e['at_calls']==0,'noise installed after execution')
            same(e['noise_namespace_oracle'],spec['noise_namespace']); same(e['tape_sha256_oracle'],io.digest(tape.tolist()))
        elif kind=='AGENT_EVENT':
            io.require(current is not None and command is None and intent is None,'public event during pending step')
            p=e['public_payload']; io.require(p['sequence']==len(public) and p['at_calls']==len(steps) and p['saved_ns']<=e['saved_ns'],'public chronology')
            public.append(e); global_public[p['sequence']]=e['sequence']
            if e['agent_event']=='COMMAND':
                io.require(not any(current[k] for k in ('success','terminated','truncated')) and len(steps)<spec['maximum_steps'],'step after end/cap')
                same(p['before'],current); io.require(p['decision_sequence']<p['sequence'] and p['decision_sequence'] in global_public,'future/unsaved choice')
                sent=np.asarray(p['command'],np.float32); io.require(sent.shape==(4,) and np.isfinite(sent).all() and np.all(abs(sent)<=1),'invalid sent command')
                same(p['command'],sent.tolist()); command=e
        elif kind=='STEP_INTENT':
            io.require(command is not None and intent is None and e['logical_step']==len(steps),'unsaved/duplicate step')
            same(e['global_command_sequence'],command['sequence']); same(e['command'],command['public_payload']['command'])
            same(e['phase'],command['public_payload']['phase']); same(e['ledger_before'],ledger); intent=e
        elif kind=='STEP_COMPLETE':
            io.require(command is not None and intent is not None and e['logical_step']==len(steps) and e['noise_cursor_after']==len(steps)+1,'response/noise cursor')
            same(e['intent_sequence'],intent['sequence']); same(e['global_command_sequence'],command['sequence'])
            for k in ('command','phase','raw_policy'): same(e[k],command['public_payload'][k])
            io.require(command['saved_ns']<=intent['saved_ns']<=e['execution_started_ns']<=e['completed_ns']<=e['saved_ns'],'choice saved after physical outcome')
            same(e['ledger_before'],ledger); ledger=simulation(ledger,'CONTROL',1,5); same(e['ledger_after'],ledger)
            io.require(np.isclose(e['simulation_time_before'],clock,atol=1e-10,rtol=0) and
                       np.isclose(e['simulation_time_after']-clock,.0125,atol=1e-10,rtol=0),'clock rewind/discontinuity')
            same(e['executed_action_oracle'],applied(e['command'],case['fault_oracle'],tape[len(steps)]),'transform/noise/final-clip order')
            check_observation(e['after']); same(e['after']['success'],bool(e['info'].get('success',False)))
            io.require(np.isfinite(e['reward']),'nonfinite reward'); steps.append(e); current=e['after']; clock=e['simulation_time_after']; command=intent=None
        elif kind=='PHYSICAL_BOUNDARY':
            io.require(len(steps) in (4,8) and e['logical_step']==len(steps),'invalid physical boundary')
            same(e['noise_past_sha256'],io.digest(tape[:len(steps)].tolist())); same(e['simulation_time'],clock)
        elif kind in ('UNIT_PLAN_COMMITTED','UNIT_PLAN_REUSED'):
            io.require(command is None and len(steps)==e['at_calls'] and not plans,'duplicate/late plan'); plans.append(e)
    io.require(command is None and intent is None and reset is None,'incomplete pending action')
    same(case['final'],current); same(case['ledger_before_close'],ledger); same(case['ledger_after_close'],ledger); check_ledger(ledger)
    io.require(len(steps)==case['total_steps']==case['host_attempts']==case['host_returned']==case['physical_rows_count']<=spec['maximum_steps'],'actual count differs')
    labels=['INITIAL','QUERY_PRE','FINAL'] if case['query_available'] else ['INITIAL','NO_QUERY_END']
    same([w['label'] for w in private],labels,'missing/extra private witness')
    refs=[]; states=[initial,*[s['after'] for s in steps]]
    for p in private:
        io.require(p['event']=='STATE_WITNESS','unknown private event'); same(p['ledger_before'],p['ledger_after'],'witness advanced physics')
        anchor=next((e for e in events if e['sequence']==p['source_anchor_sequence']),None)
        io.require(anchor is not None and anchor['saved_ns']==p['source_anchor_saved_ns']<=p['started_ns']<=p['completed_ns']<=p['saved_ns'],'private witness chronology')
        verify_witness(p['witness'],full_sha256=p['source_witness']['python_semantic_sha256'],native_sha256=p['source_witness']['native_sha256'])
        at=0 if p['label']=='INITIAL' else len(steps)-int(p['label']=='QUERY_PRE'); same(p['logical_step'],at)
        same(p['source_witness']['noise_past_sha256'],io.digest(tape[:at].tolist()))
        witness_clock=events[next(i for i,e in enumerate(events) if e['event']=='CONTROLLED_INITIAL')]['simulation_time'] if at==0 else steps[at-1]['simulation_time_after']
        same(p['source_witness']['simulation_time'],witness_clock)
        expected_ledger=next(e['ledger'] for e in events if e['event']=='CONTROLLED_INITIAL') if at==0 else steps[at-1]['ledger_after']
        same(p['ledger_before'],expected_ledger,'private witness has wrong physical ledger')
        refs.append({'label':p['label'],'sequence':p['sequence'],'native_sha256':p['witness']['native_sha256'],
            'comparison_python_sha256':p['witness']['comparison_python_sha256'],'logical_step':at})
    same(case['state_witness_refs'],refs)
    prefix_public=public[:case['prefix_event_count']]; prefix_steps=steps[:-1] if case['query_available'] else steps
    target,outcome,cost=replay_prefix(spec,initial,prefix_public,prefix_steps,nominal)
    fits=sum(e['agent_event']=='FIT_INTENT' for e in prefix_public)
    io.require(fits==cost['independent_c4_c8_refits']==case['c4_c8_fit_attempts']==case['c4_c8_fit_results'],'fit accounting')
    same(case['c4_c8_optimizer_nfev'],cost['independent_c4_c8_nfev']); same(case['policy_queries'],cost['policy_queries'])
    plan=None
    if case['query_available']:
        io.require(target is not None and len(plans)==1 and len(public)==len(prefix_public)+2,'unexplained query/extra events')
        choice,cmd=public[-2:]; same(choice['agent_event'],'CONTRAST_CHOICE'); same(cmd['agent_event'],'COMMAND')
        p=choice['public_payload']; c=cmd['public_payload']; pe=plans[0]
        same(sorted(p),sorted(('sequence','saved_ns','at_calls','selection','plan_sequence')))
        same(sorted(p['selection']),sorted(('plan_sha256','action_id','sent_command','decision_step')))
        io.require(pe['sequence']<choice['sequence']<cmd['sequence']<steps[-1]['intent_sequence'],'plan/choice not before execution')
        io.require(pe['event']==('UNIT_PLAN_COMMITTED' if spec['action_id']=='BASELINE' else 'UNIT_PLAN_REUSED'),'plan generated after baseline outcome')
        io.require(c['phase']=='CONTRAST_QUERY' and c['decision_sequence']==p['sequence'],'saved choice consumption')
        same(c['raw_policy'],target['raw_policy']); same(c['source_phase'],target['phase']); same(case['source_phase'],target['phase'])
        same(case['query_step'],len(prefix_steps)); same(case['before_observation'],states[-2]['observation']); same(case['after_observation'],states[-1]['observation'])
        same(case['selection_sequence'],p['sequence']); same(case['command_sequence'],c['sequence']); same(case['selected_action'],spec['action_id'])
        same(case['plan_sha256'],p['selection']['plan_sha256']); same(case['plan_sha256'],c['plan_sha256']); same(case['plan_sha256'],pe['plan_sha256'])
        same(p['plan_sequence'],case['plan_sequence']); same(p['selection']['action_id'],spec['action_id']); same(p['selection']['sent_command'],c['command'])
        same(p['selection']['decision_step'],len(prefix_steps)); same(case['missing_reason'],None)
        io.require(private[1]['saved_ns']<pe['saved_ns']<steps[-1]['execution_started_ns'],'prediction did not follow observed state before action')
        if spec['action_id']=='BASELINE':
            same(case['plan_sequence'],pe['sequence']); plan=pe['plan']; same(io.digest(plan),case['plan_sha256'])
            audit_plan(plan,spec,[s['observation'] for s in states[:-1]],target['command'],models)
            same(c['command'],plan['query']['baseline_command'],'reference branch did not consume saved baseline')
            same(pe['target'],spec['target']); same(pe['source_phase'],target['phase'])
        else: same(pe['plan_sequence'],case['plan_sequence'])
    else:
        io.require(target is None and not plans and len(public)==len(prefix_public),'missing point fabricated')
        value=outcome['outcome']; reason='EARLY_SUCCESS' if value['success'] else 'ENVIRONMENT_ENDED' if value['terminated'] or value['truncated'] else value['stop_reason']
        same(case['missing_reason'],reason); same(case['prefix_outcome'],value)
        for k in ('plan_sequence','plan_sha256','selected_action'): same(case[k],None)
    return ledger,{'steps':steps,'prefix':[{k:r[k] for k in PHYSICAL} for r in prefix_steps],
        'plan':plan,'target':target,'private':private,'costs':cost}


def audit(path,cohort):
    path=Path(path).resolve(); manifest=allocation.load_manifest(path); started=perf_counter_ns()
    io.require(cohort in ('SOFTWARE_NATIVE','QUAL'),'registered audit phase')
    folder=path.parent/('software_native' if cohort=='SOFTWARE_NATIVE' else 'collection'); completion=io.read(folder/'completion.json')
    io.require(completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial collection retained, cannot pass')
    for n,h in completion['artifact_sha256'].items(): io.require(io.sha(folder/n)==h,'collection bytes changed: '+n)
    specs=manifest['config']['native_software_population' if cohort=='SOFTWARE_NATIVE' else 'population']
    cases=list(io.rows(folder/'cases.jsonl.gz')); io.require(len(cases)==len(specs),'complete registered population')
    outer=iter(groupby(io.rows(folder/'events.jsonl.gz'),lambda e:e['case_id'])); private=iter(groupby(io.rows(folder/'witnesses.jsonl.gz'),lambda e:e['case_id']))
    models=raw_models(); nominal=io.read(allocation.ROOT/io.C8)['joint']; ledger={'counts':{},'by_phase':{}}
    sequence=psequence=stamp=pstamp=0; counts=Counter(); reference=None; checks=0; units=[]
    from src.analysis.continuous_state_witness_v1 import compare_witnesses
    for spec,case in zip(specs,cases):
        key,it=next(outer); events=list(it); pk,pit=next(private); ps=list(pit); io.require(key==pk==spec['case_id'],'journal allocation order')
        for rows,is_private in ((events,False),(ps,True)):
            for e in rows:
                for k in (*io.IDENTITY,*KEYS): same(e[k],manifest[k] if k in io.IDENTITY else spec[k])
                if is_private:
                    io.require(e['sequence']==psequence and e['saved_ns']>=pstamp,'private journal sequence/time'); psequence+=1; pstamp=e['saved_ns']
                else:
                    io.require(e['sequence']==sequence and e['saved_ns']>=stamp,'journal sequence/time'); sequence+=1; stamp=e['saved_ns']
        for k in io.IDENTITY: same(case[k],manifest[k])
        io.require(events[-1]['event']=='CASE_COMPLETE','missing complete receipt'); receipt=events.pop()
        same(receipt['case_record_sha256'],io.digest(case)); same(case['event_start_sequence'],events[0]['sequence'])
        same(case['event_end_sequence_exclusive'],receipt['sequence']); same(receipt['total_steps'],case['total_steps'])
        same(receipt['query_available'],case['query_available']); same(receipt['missing_reason'],case['missing_reason'])
        ledger,result=audit_case(spec,case,events,ps,nominal[spec['task']],models[spec['task']],ledger)
        counts.update(result['costs']); counts['control_steps']+=len(result['steps']); counts['query_available']+=int(case['query_available'])
        if spec['action_id']=='BASELINE':
            reference=(case,result,events); units.append(spec['unit_id'])
        else:
            io.require(reference is not None and reference[0]['unit_id']==spec['unit_id'],'no reference for actual branch')
            first,base,firstevents=reference; same(case['query_available'],first['query_available']); same(case['missing_reason'],first['missing_reason'])
            same(result['prefix'],base['prefix'],'physical prefix differs'); same(case['initial'],first['initial'])
            for i in (0,1): io.require(compare_witnesses(ps[i]['witness'],base['private'][i]['witness'])['comparison_equal'],'real prefix witness mismatch')
            if case['query_available']:
                same(case['plan_sequence'],first['plan_sequence']); same(case['plan_sha256'],first['plan_sha256'])
                target=result['target']; states=[case['initial']['observation'],*[r['after']['observation'] for r in result['steps'][:-1]]]
                audit_plan(base['plan'],spec,states,target['command'],models[spec['task']])
                same(result['steps'][-1]['command'],next(c['sent_command'] for c in base['plan']['query']['candidates'] if c['action_id']==spec['action_id']))
                plan_event=next(e for e in firstevents if e['event']=='UNIT_PLAN_COMMITTED')
                io.require(plan_event['saved_ns']<result['steps'][-1]['execution_started_ns'],'plan postdates branch outcome')
            checks+=1
    io.require(next(outer,None) is None and next(private,None) is None,'unallocated extra records')
    summary=io.read(folder/'summary.json'); same(summary['lifecycle'],ledger); same(summary['control_steps'],counts['control_steps'])
    same(summary['events'],sequence); same(summary['private_records'],psequence); same(summary['executions'],len(specs))
    same(summary['online_c4_c8_fit_attempts'],counts['independent_c4_c8_refits']); same(summary['new_api_calls'],0)
    same(summary['network_guard'],{'attempted_network_calls':0})
    limits=manifest['config']['native_software_limits' if cohort=='SOFTWARE_NATIVE' else 'limits']
    io.require(counts['control_steps']<=limits['control_steps'] and ledger['counts']['reset_completed']<=limits['all_resets']
               and ledger['counts']['simulation_frames_completed']<=limits['physical_frames'],'study budget exceeded')
    contract='PASSED' if cohort=='SOFTWARE_NATIVE' and counts['query_available']==15 else 'INCOMPLETE' if cohort=='SOFTWARE_NATIVE' else 'NOT_APPLICABLE'
    result={**{k:manifest[k] for k in io.IDENTITY},'cohort':cohort,'integrity':'PASSED','native_software_contract':contract,
        'executions':len(cases),'units':len(units),'paired_branch_checks':checks,'costs':dict(counts),'lifecycle':ledger,
        'new_environment_steps':0,'new_api_calls':0,'new_response_predictor_training':0,'completion_sha256':io.sha(folder/'completion.json'),
        'auditor_sha256':io.sha(__file__),'wall_ns':perf_counter_ns()-started,
        'scope':'Saved-record and source-generated-state audit, not independent reproduction of physical dynamics or task utility'}
    io.write(folder/'audit.json',result); return result
