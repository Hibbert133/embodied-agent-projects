"""Source-derived physical ledger checks plus separate memory/PI and saved replay."""
from pathlib import Path
from copy import deepcopy
from dataclasses import asdict
from collections import Counter
from time import perf_counter_ns
import numpy as np
import math
from src.analysis import memory_acquisition_io_v1 as allocation
from src.analysis.response_action_audit_v1 import same,audit_pi
from src.analysis.capsule_record_json_v2 import normalize
from src.probe.continuous import StepObservation
from src.probe.physical_reprobe_v1 import StepReceipt
from src.probe import memory_acquisition_program_v1 as actor
io=allocation.io


def physical_audit(spec,case,events,private,ledger_before):
    from src.analysis.short_probe_journal_audit_v1 import applied,check_ledger,ledger_add,simulation,check_observation
    from src.analysis.continuous_state_witness_v1 import verify_witness,compare_witnesses
    for k,v in spec.items(): same(case[k],v,'allocation mismatch')
    io.require(case['completed'] and case['environment_closed'] and case['error'] is None and case['close_error'] is None,'incomplete execution retained but cannot pass')
    same(case['ledger_before'],ledger_before); same(case['initial_fault_oracle'],allocation.initial_fault()); same(case['destination_oracle'],allocation.destination(spec))
    same(case['captures'],0); same(case['restores'],0)
    ledger=deepcopy(ledger_before); current=initial=clock=command=intent=reset=None; first_clock=None
    steps=[]; public=[]; local={}; factories=0; resets=Counter(); tape=allocation.noise(spec['seed']); fault=allocation.initial_fault(); boundary=None
    allowed={'FACTORY_INTENT','FACTORY_COMPLETE','LIFECYCLE_RESET_INTENT','LIFECYCLE_RESET_COMPLETE','CONTROLLED_INITIAL',
        'NOISE_COMMITMENT','AGENT_EVENT','STEP_INTENT','STEP_COMPLETE','PHYSICAL_BOUNDARY','FAULT_BOUNDARY'}
    for e in events:
        kind=e['event']; io.require(kind in allowed,'unknown host mutation: '+kind)
        if kind=='FACTORY_INTENT':
            io.require(factories==0 and current is None,'repeat factory'); same(e['ledger'],ledger); factories=1
        elif kind=='LIFECYCLE_RESET_INTENT':
            phase=e['phase']; io.require(reset is None and current is None,'nested or mid-task reset')
            io.require((factories==1 and phase=='GOAL_GENERATION' and resets[phase]<50) or
                (factories==2 and phase=='CONTROLLED_RESET' and resets[phase]==0),'unallocated reset')
            same(e['before'],ledger); ledger=ledger_add(ledger,phase,'reset_attempts',1); reset=e
        elif kind=='LIFECYCLE_RESET_COMPLETE':
            io.require(reset is not None and e['intent_sequence']==reset['sequence'] and e['phase']==reset['phase'],'orphan reset')
            ledger=simulation(ledger,e['phase'],100,500); ledger=ledger_add(ledger,e['phase'],'reset_completed',1)
            same(e['after'],ledger); resets[e['phase']]+=1; reset=None
        elif kind=='FACTORY_COMPLETE':
            io.require(factories==1 and resets['GOAL_GENERATION']==50 and reset is None,'factory accounting'); same(e['ledger'],ledger); factories=2
        elif kind=='CONTROLLED_INITIAL':
            io.require(current is None and factories==2 and resets['CONTROLLED_RESET']==1,'exactly one controlled reset')
            same(e['ledger'],ledger); same(e['task'],spec['task']); same(e['observation'],case['initial']['observation'])
            initial=current=deepcopy(case['initial']); check_observation(current); first_clock=clock=e['simulation_time']
        elif kind=='NOISE_COMMITMENT':
            io.require(current is not None and not public and e['at_calls']==0,'late replacement of noise')
            same(e['noise_namespace_oracle'],140002); same(e['tape_sha256_oracle'],io.digest(tape.tolist()))
        elif kind=='AGENT_EVENT':
            io.require(current is not None and command is None and intent is None,'public event inside a pending action')
            p=e['public_payload']; io.require(p['sequence']==len(public) and p['at_calls']==len(steps) and p['saved_ns']<=e['saved_ns'],'public chronology')
            public.append(e); local[p['sequence']]=e
            if e['agent_event']=='COMMAND':
                io.require(not any(current[k] for k in ('success','terminated','truncated')) and len(steps)<500,'step after end/cap')
                same(p['before'],current); io.require(p['decision_sequence']<p['sequence'] and p['decision_sequence'] in local,'future/unsaved decision')
                sent=np.asarray(p['command'],np.float32); io.require(sent.shape==(4,) and np.isfinite(sent).all() and np.all(abs(sent)<=1),'invalid send')
                same(p['command'],sent.tolist()); command=e
        elif kind=='STEP_INTENT':
            io.require(command is not None and intent is None and e['logical_step']==len(steps),'unsaved/duplicate action')
            if len(steps)>=spec['planned_boundary']: io.require(boundary is not None,'missed hidden boundary')
            same(e['global_command_sequence'],command['sequence']); same(e['command'],command['public_payload']['command'])
            same(e['phase'],command['public_payload']['phase']); same(e['ledger_before'],ledger); intent=e
        elif kind=='STEP_COMPLETE':
            io.require(command is not None and intent is not None and e['logical_step']==len(steps) and e['noise_cursor_after']==len(steps)+1,'response/noise cursor')
            same(e['intent_sequence'],intent['sequence']); same(e['global_command_sequence'],command['sequence'])
            for k in ('command','phase','raw_policy'): same(e[k],command['public_payload'][k])
            io.require(command['saved_ns']<=intent['saved_ns']<=e['execution_started_ns']<=e['completed_ns']<=e['saved_ns'],'choice saved after physical outcome')
            same(e['ledger_before'],ledger); ledger=simulation(ledger,'CONTROL',1,5); same(e['ledger_after'],ledger)
            io.require(np.isclose(e['simulation_time_before'],clock,atol=1e-10,rtol=0) and np.isclose(e['simulation_time_after']-clock,.0125,atol=1e-10,rtol=0),'physical clock discontinuity')
            same(e['executed_action_oracle'],applied(e['command'],fault,tape[len(steps)]),'float32 transform/noise/final-clip order')
            check_observation(e['after']); same(e['after']['success'],bool(e['info'].get('success',False)))
            io.require(np.isfinite(e['reward']),'nonfinite reward'); steps.append(e); current=e['after']; clock=e['simulation_time_after']; command=intent=None
        elif kind=='PHYSICAL_BOUNDARY':
            io.require(len(steps) in (4,8) and e['logical_step']==len(steps),'invalid physical boundary')
            same(e['noise_past_sha256'],io.digest(tape[:len(steps)].tolist())); same(e['simulation_time'],clock)
        elif kind=='FAULT_BOUNDARY':
            io.require(boundary is None and command is None and intent is None and len(steps)==spec['planned_boundary']==e['logical_step']
                and not any(current[k] for k in ('success','terminated','truncated')),'repeat/late/nonlive boundary')
            same(e['old_fault_oracle'],fault); fault=allocation.destination(spec); same(e['new_fault_oracle'],fault)
            same(e['changed_oracle'],spec['context']=='CHANGED'); same(e['before'],e['after'],'boundary changed state/RNG/time'); boundary=e
    io.require(command is None and intent is None and reset is None,'unfinished physical action')
    same(case['final'],current); same(case['ledger_before_close'],ledger); same(case['ledger_after_close'],ledger); check_ledger(ledger)
    same(case['boundary_applied'],boundary is not None)
    missing=None if boundary is not None else 'EARLY_SUCCESS' if current['success'] else 'ENVIRONMENT_ENDED' if current['terminated'] or current['truncated'] else case['stop_reason']
    same(case['boundary_missing_reason'],missing)
    io.require(len(steps)==case['total_steps']==case['host_attempts']==case['host_returned']==case['physical_rows_count']<=500,'step costs differ')
    labels=['INITIAL']+(['INTERVENTION_PRE','INTERVENTION_POST'] if boundary is not None else [])
    moved=[e for e in public if e['agent_event']=='TASK_MEMORY_RETURN']
    if moved: labels+=['POST_ACQUISITION']
    labels+=['FINAL']; same([p['label'] for p in private],labels,'missing/extra private witness')
    refs=[]
    for p in private:
        io.require(p['event']=='STATE_WITNESS','unknown private event'); same(p['ledger_before'],p['ledger_after'],'witness advanced physics')
        anchor=next((e for e in events if e['sequence']==p['source_anchor_sequence']),None)
        io.require(anchor is not None and anchor['saved_ns']==p['source_anchor_saved_ns']<=p['started_ns']<=p['completed_ns']<=p['saved_ns'],'private chronology')
        verify_witness(p['witness'],full_sha256=p['source_witness']['python_semantic_sha256'],native_sha256=p['source_witness']['native_sha256'])
        at=0 if p['label']=='INITIAL' else spec['planned_boundary'] if p['label'].startswith('INTERVENTION_') else moved[0]['public_payload']['at_calls'] if p['label']=='POST_ACQUISITION' else len(steps)
        same(p['logical_step'],at); same(p['source_witness']['noise_past_sha256'],io.digest(tape[:at].tolist()))
        same(p['source_witness']['simulation_time'],first_clock if at==0 else steps[at-1]['simulation_time_after'])
        expected=next(e['ledger'] for e in events if e['event']=='CONTROLLED_INITIAL') if at==0 else steps[at-1]['ledger_after']
        same(p['ledger_before'],expected,'private physical ledger')
        refs.append({'label':p['label'],'sequence':p['sequence'],'logical_step':at,'native_sha256':p['witness']['native_sha256'],
            'comparison_python_sha256':p['witness']['comparison_python_sha256']})
    same(case['state_witness_refs'],refs)
    if boundary is not None:
        pair=[p for p in private if p['label'].startswith('INTERVENTION_')]
        io.require(compare_witnesses(pair[0]['witness'],pair[1]['witness'])['comparison_equal'],'boundary state witness mismatch')
        io.require(pair[0]['saved_ns']<boundary['saved_ns']<pair[1]['saved_ns'],'boundary witness order')
    return ledger,steps,public


def replay(spec,case,public,steps):
    from src.rollout.task_registry import create_task_policy
    policy=create_task_policy(spec['task']);cursor=event_cursor=0;current=deepcopy(case['initial']);counts=Counter()
    def query(observation):
        same(observation,current['observation'],'replay policy input');counts['fixed_policy_requeries']+=1
        return np.asarray(policy.get_action(np.asarray(observation).copy()),np.float32)
    def emit(kind,payload):
        nonlocal event_cursor
        e=public[event_cursor];event_cursor+=1;p=e['public_payload'];same(kind,e['agent_event'])
        same(normalize(payload),{k:v for k,v in p.items() if k not in ('sequence','saved_ns')},'saved actor transcript differs')
        return deepcopy(p)
    def step(saved):
        nonlocal cursor,current
        e=steps[cursor];same(saved['sequence'],next(x['public_payload']['sequence'] for x in public if x['sequence']==e['global_command_sequence']))
        same(saved['command'],e['command']);same(saved['before'],current);cursor+=1;current=deepcopy(e['after'])
        return StepReceipt(StepObservation(**current),cursor)
    result=actor.run(spec['task'],StepObservation(**case['initial']),spec['planned_boundary'],spec['action'],query,step,emit)
    same(cursor,len(steps));same(event_cursor,len(public))
    for k,v in result['outcome'].items():same(case[k],v,'outcome differs '+k)
    return counts


def independent_memory(spec,case,public,steps):
    """PI arithmetic is independently reconstructed; memory never calls the actor."""
    current=deepcopy(case['initial']);at=0;integral=[0.,0.];plan=None;expected_integral=None;suspended=False
    choice=returned=None;counts=Counter();controller={'source':'UNCORRECTED','matrix_xy':[[1.,0.],[0.,1.]],'offset':[0.,0.,0.,0.]}
    move_history=[];lifted=False;probe_count=0;probe_entered=False
    def memory():return {'schema':'TASK_MEMORY_OPTION_V1','task':spec['task'],'completed_steps':at,'current':current,
        'controller':controller,'integral_xy':integral,'time_constant_s':.5}
    for e in public:
        kind=e['agent_event'];p=e['public_payload'];same(p['at_calls'],at,'memory clock differs')
        if kind=='PI_PLAN':
            io.require(not suspended and plan is None,'plan during suspended/pending state');plan=p['saved_plan']
            same(plan['schema'],'TASK_MEMORY_COMMAND_V1');same(plan['before_memory_sha256'],io.digest(memory()))
            same(plan['pi_plan_sha256'],io.digest(plan['pi_plan']))
            same(plan['pi_plan']['query']['controller'],controller)
        elif kind=='COMMAND':
            step=steps[at];same(p['before'],current)
            if p['raw_policy'] is not None:
                io.require(plan is not None and not suspended,'task command missing memory plan')
                expected_integral,c=audit_pi(plan['pi_plan'],p['command'],integral,spec['task'],at,current,p['raw_policy']);counts.update(c)
            else:
                io.require(suspended and plan is None,'non-task command outside actual suspension')
                if p['phase']=='REPOSITION':
                    io.require(not probe_entered and len(move_history)<=64,'relocation after probe or beyond cap')
                    xyz=np.asarray(current['observation'][:3]);target=np.asarray((0.,.6,.25) if lifted else (*move_history[0][:2],.25))
                    velocity=xyz-np.asarray(move_history[-2][:3]) if len(move_history)>=2 else np.zeros(3)
                    desired=np.r_[np.clip(8.*(target-xyz)-16.*velocity,-.5,.5),-1.]
                    same(p['command'],np.clip(desired,-1,1).astype(np.float32).tolist(),'independent relocation command')
                else:
                    io.require(p['phase']=='WARM_PROBE' and probe_entered and probe_count<8,'unavailable probe action')
                    directions=((.4,0,0,0),(0,.4,0,0),(-.4,0,0,0),(0,-.4,0,0))
                    same(p['command'],np.asarray(directions[probe_count%4],np.float32).tolist(),'independent probe command');probe_count+=1
                move_history.append(step['after']['observation']);lifted=lifted or step['after']['observation'][2]>=.235
            current=deepcopy(step['after']);at+=1
        elif kind=='TASK_MEMORY_COMMIT':
            io.require(plan is not None and expected_integral is not None,'commit without actual task receipt')
            integral=expected_integral;same(p['memory'],memory(),'task integral/reset mismatch');plan=expected_integral=None
        elif kind=='ACQUISITION_CHOICE':
            io.require(choice is None and at==spec['planned_boundary'],'repeat/late acquisition');choice=p
            same(p['before_memory'],memory());same(p['action'],spec['action'])
            same(p['behavior_probabilities'],[float(a==spec['action']) for a in actor.ACTIONS])
        elif kind=='TASK_MEMORY_SUSPEND':
            io.require(choice is not None and spec['action']=='MOVE_MEASURE8' and not suspended,'invalid suspension')
            same(p['memory'],memory());same(p['token'],{'schema':'TASK_MEMORY_SUSPEND_V1','memory_sha256':io.digest(memory()),'at_completed_steps':at});suspended=True
            move_history=[list(current['observation'])];lifted=current['observation'][2]>=.235
        elif kind=='PROBE_ENTRY':
            io.require(suspended and not probe_entered and len(move_history)>=4,'probe before settled anchor')
            h=move_history[-4:];xyz=h[-1][:3]
            io.require(max(abs(a-b) for a,b in zip(xyz,(0.,.6,.25)))<=.015 and math.dist(xyz,h[-1][4:7])>=.10
                and all(max(abs(a-b) for a,b in zip(u[:3],v[:3]))<=.003 for u,v in zip(h[:-1],h[1:])),'independent anchor entry')
            same(p['entry_history'],h);probe_entered=True
        elif kind=='TASK_MEMORY_RETURN':
            io.require(choice is not None and returned is None and plan is None,'repeat/unplanned return')
            same(p['memory'],memory(),'acquisition changed controller/integral or restored old observation')
            same(p['before_memory_sha256'],io.digest(choice['before_memory']));same(p['new_steps'],at-choice['at_calls'])
            returned=p;suspended=False;counts['returns']+=1
        elif kind=='TAIL_CHOICE':
            io.require(returned is not None and not suspended and not any(current[k] for k in ('success','terminated','truncated')),'tail after terminal option')
            same(p['parent_return_sequence'],returned['sequence']);same(p['action'],'KEEP');same(p['memory_sha256'],io.digest(memory()))
            same(p['new_correction_applied'],False);same(p['behavior_probabilities'],[1.0]);same(p['available_actions'],['KEEP'])
            counts['tail_choices']+=1
    io.require(plan is None and not suspended,'unfinished task memory');same(case['final_memory'],memory())
    same(at,len(steps));same(counts['pi_plans'],case['policy_queries'])
    return counts


def audit(path):
    path=Path(path).resolve();m=allocation.checked(path);out=path.parent/'native';start=perf_counter_ns()
    done=io.read(out/'completion.json');io.require(done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial native run cannot pass')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'collection changed '+n)
    cases=list(io.rows(out/'cases.jsonl.gz'));events=list(io.rows(out/'events.jsonl.gz'));private=list(io.rows(out/'witnesses.jsonl.gz'))
    specs=allocation.population();same(len(cases),54)
    for stream in (events,private):
        last=-1
        for i,e in enumerate(stream):
            same(e['sequence'],i);io.require(e['saved_ns']>=last,'nonmonotonic outer journal');last=e['saved_ns']
            for k in allocation.IDENTITY:same(e[k],m[k])
    ledger={'counts':{},'by_phase':{}};counts=Counter();coverage={t:{'movement':0,'post_move_task':0} for t in io.TASKS};previous={};windows=0;end=0
    for spec,case in zip(specs,cases):
        chunk=events[case['event_start_sequence']:case['event_end_sequence_exclusive']]
        io.require(case['event_start_sequence']==end,'missing/overlapping case range');marker=events[case['event_end_sequence_exclusive']]
        same(marker['event'],'CASE_COMPLETE');same(marker['case_record_sha256'],io.digest(case));end=marker['sequence']+1
        same({k:marker[k] for k in allocation.KEYS},spec)
        same(len(chunk),case['event_end_sequence_exclusive']-case['event_start_sequence'])
        for e in chunk:same({k:e[k] for k in allocation.KEYS},spec,'cross-case event')
        priv=[p for p in private if all(p[k]==v for k,v in spec.items())]
        ledger,steps,public=physical_audit(spec,case,chunk,priv,ledger)
        counts.update(replay(spec,case,public,steps));counts.update(independent_memory(spec,case,public,steps));counts['control_steps']+=len(steps)
        key=(spec['group'],spec['task'],spec['context']);n=min(spec['planned_boundary'],len(steps))
        if key in previous:
            ref=previous[key];same(case['initial'],ref['initial'],'same-seed initial state')
            from src.analysis.continuous_state_witness_v1 import compare_witnesses
            io.require(compare_witnesses(priv[0]['witness'],ref['witness'])['comparison_equal'],'initial private state differs')
            same(len(steps[:n]),len(ref['steps'][:n]))
            for a,b in zip(steps[:n],ref['steps'][:n]):
                for k in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(a[k],b[k],'shared actual PI prefix differs')
            counts['common_prefix_pairs']+=1
        else:previous[key]={'initial':case['initial'],'steps':steps,'witness':priv[0]['witness']}
        if spec['action']=='MOVE_MEASURE8':
            coverage[spec['task']]['movement']+=int(case['movement_steps']>0)
            returns=[e['public_payload']['at_calls'] for e in public if e['agent_event']=='TASK_MEMORY_RETURN']
            coverage[spec['task']]['post_move_task']+=int(bool(returns) and any(s['logical_step']>=returns[0] and s['raw_policy'] is not None for s in steps))
        windows+=int(case['complete_warm_window'])
    same(end,len(events));same(sum(len([p for p in private if all(p[k]==s[k] for k in allocation.KEYS)]) for s in specs),len(private))
    summary=io.read(out/'summary.json');same(summary['lifecycle'],ledger);same(summary['control_steps'],counts['control_steps']);same(summary['executions'],54)
    same(summary['events'],len(events));same(summary['private_records'],len(private));same(summary['network_guard'],{'attempted_network_calls':0})
    for k in ('new_parameter_fits','new_response_training','new_policy_training','online_LLM_API_calls'):same(summary[k],0)
    limits=allocation.limits();io.require(counts['control_steps']<=limits['control_steps'] and ledger['counts']['reset_attempts']==limits['all_resets'] and ledger['counts']['simulation_frames_attempted']<=limits['physical_frames'],'complete cost budget')
    gate=windows>=1 and all(v['movement']>=1 and v['post_move_task']>=1 for v in coverage.values())
    result={'integrity':'PASSED','native_software_contract':'PASSED' if gate else 'FAILED_COVERAGE','executions':54,'counts':dict(counts),
        'complete_warm_windows':windows,'coverage':coverage,'collection_completion_sha256':io.sha(out/'completion.json'),
        'artifact_sha256':done['artifact_sha256'],'wall_ns':perf_counter_ns()-start,'new_environment_steps':0,'new_parameter_fits':0,
        'new_model_fits':0,'new_online_LLM_API_calls':0,'not_robot_safety_or_task_gain_qualification':True,'publication_goal_complete':False}
    io.write(out/'audit.json',result);return result
