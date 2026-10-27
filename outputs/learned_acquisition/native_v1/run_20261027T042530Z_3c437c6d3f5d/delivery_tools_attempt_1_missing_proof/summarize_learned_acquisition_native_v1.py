"""Descriptive complete-population tables. No fitting, physics or API calls."""
from collections import Counter,defaultdict
from pathlib import Path
from time import perf_counter_ns
import csv,gzip,json,math,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import learned_acquisition_native_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
io=a.io;start=perf_counter_ns();manifest=Path(sys.argv[1]).resolve();m=a.checked(manifest);run=manifest.parent
out=run/'result_delivery';out.mkdir(exist_ok=False);guard={}


def mean(values):return None if not values else sum(values)/len(values)
def counts(rows):
    return dict(n=len(rows),success=sum(r['success'] for r in rows),mean_deadline_loss=mean([r['deadline_loss'] for r in rows]),
        total_deadline_loss=sum(r['deadline_loss'] for r in rows),actual_steps=sum(r['total_steps'] for r in rows),
        actual_fixed_policy_queries=sum(r['policy_queries'] for r in rows),movement_steps=sum(r['movement_steps'] for r in rows),
        measurement_steps=sum(r['measurement_steps'] for r in rows),live_model_calls=sum(r['live_model_calls'] for r in rows))


def cells(source):
    axes=[(),('task',),('context',),('planned_boundary',),('task','context'),('task','context','planned_boundary'),
        ('acquisition_action',),('time_constant_s',),('task','context','acquisition_action','time_constant_s'),
        ('task','context','planned_boundary','acquisition_action','time_constant_s')]
    result=[]
    for keys in axes:
        buckets=defaultdict(list)
        for r in source:buckets[tuple(r['spec'][k] for k in keys)].append(r)
        for identity,rows in sorted(buckets.items(),key=lambda item:str(item[0])):
            groups=[]
            for g in sorted({r['spec']['group'] for r in rows}):
                registered=[r for r in rows if r['spec']['group']==g];live=[r for r in registered if r['future'] is not None]
                groups.append(dict(group=g,registered=len(registered),available=len(live),missing_reasons=dict(Counter(r['missing_reason'] for r in registered if r['missing_reason'])),
                    means={k:mean([r['future']['means'][k] for r in live]) for k in ('error','command_energy','motion_energy','alignment')},
                    command_only_relative_l2=mean([r['future']['command_only_relative_l2'] for r in live if r['future']['command_only_relative_l2'] is not None])))
            result.append(dict(axes=list(keys),values=list(identity),registered=len(rows),available=sum(r['future'] is not None for r in rows),
                groups=groups,equal_group_means={k:mean([g['means'][k] for g in groups if g['means'][k] is not None]) for k in ('error','command_energy','motion_energy','alignment')},
                equal_group_command_only_relative_l2=mean([g['command_only_relative_l2'] for g in groups if g['command_only_relative_l2'] is not None])))
    return result


with read_only(guard):
    sa=io.read(run/'training_signal/audit.json');na=io.read(run/'native_audit_repair_v2/audit.json');gate=io.read(run/'native_audit_repair_v2/native_gate.json')
    assert sa['integrity']==na['integrity']=='PASSED'
    source=io.read(run/'training_signal/case_signal.json');past=io.read(run/'training_signal/shared_past_signal.json')
    native=list(io.rows(run/'native/cases.jsonl.gz'));summary=io.read(run/'native/summary.json')
    assert len(source)==648 and len(native)==54 and summary['executions']==54
    source_cells=cells(source);io.write(out/'source_future_cells.json',source_cells)
    compact=[{k:r[k] for k in (*a.KEYS,'selected_action','selected_rate','success','deadline_loss','total_steps','policy_queries','movement_steps','measurement_steps','live_model_calls','stop_reason','wall_ns')} for r in native]
    io.write(out/'all_native_cases.json',compact);io.write(out/'all_native_failures.json',[r for r in compact if not r['success']])
    programs={p:counts([r for r in native if r['program']==p]) for p in a.PROGRAMS}
    native_cells=[]
    for g in range(3):
        for task in ('push-v3','reach-v3','door-open-v3'):
            for context in ('UNCHANGED','CHANGED'):
                rows=[r for r in native if (r['group'],r['task'],r['context'])==(g,task,context)]
                native_cells.extend(dict(group=g,task=task,context=context,program=p,**counts([r for r in rows if r['program']==p])) for p in a.PROGRAMS)
    io.write(out/'native_group_task_context_cells.json',native_cells)
    grouped=[];pairs=[]
    for g in range(3):
        grouped.append(dict(group=g,boundary=(16,32,64)[g],programs={p:counts([r for r in native if r['group']==g and r['program']==p]) for p in a.PROGRAMS}))
    units=defaultdict(dict)
    for r in native:units[a.unit_key(r)][r['program']]=r
    for key,rows in units.items():
        ref=rows['LEGACY_REFERENCE'];learned=rows['LEARNED_JOINT_BANK0'];forced=rows['DYNAMIC_FORCED_REFERENCE']
        assert ref['deadline_loss']==forced['deadline_loss'] and ref['success']==forced['success']
        pairs.append(dict(unit=list(key),reference_loss=ref['deadline_loss'],learned_loss=learned['deadline_loss'],
            loss_difference=learned['deadline_loss']-ref['deadline_loss'],reference_success=ref['success'],learned_success=learned['success'],
            learned_action=learned['selected_action'],learned_rate=learned['selected_rate']))
    paired=dict(n=18,mean_difference=mean([r['loss_difference'] for r in pairs]),total_difference=sum(r['loss_difference'] for r in pairs),
        worse=sum(r['loss_difference']>0 for r in pairs),better=sum(r['loss_difference']<0 for r in pairs),tie=sum(r['loss_difference']==0 for r in pairs),
        success_to_failure=sum(r['reference_success'] and not r['learned_success'] for r in pairs),failure_to_success=sum(not r['reference_success'] and r['learned_success'] for r in pairs),
        total_harm=sum(max(0,r['loss_difference']) for r in pairs),total_help=sum(max(0,-r['loss_difference']) for r in pairs))
    io.write(out/'all_paired_differences.json',pairs)
    latencies=[];pending={}
    for e in io.rows(run/'native/events.jsonl.gz'):
        if e['event']!='AGENT_EVENT' or e['program']!='LEARNED_JOINT_BANK0':continue
        p=e['public_payload']
        if e['agent_event']=='FORECAST_INPUT':pending[a.case_key(e)]=p
        elif e['agent_event']=='FORECAST':
            q=pending.pop(a.case_key(e));assert p['input_sequence']==q['sequence']
            latencies.append(dict(spec={k:e[k] for k in a.KEYS},stage=q['value']['stage'],saved_query_to_saved_choice_ns=p['saved_ns']-q['saved_ns']))
    assert not pending and len(latencies)==summary['live_model_calls']
    io.write(out/'all_live_decision_wall_intervals.json',latencies)
    live=[r for r in native if r['program']=='LEARNED_JOINT_BANK0']
    signals=dict(registered=648,available_future=536,missing_reasons=dict(Counter(r['missing_reason'] for r in source if r['missing_reason'])),
        past_windows=134,past_length_counts=dict(Counter(str(r['signal']['n']) for r in past.values())),
        future_length_counts=dict(Counter(str(r['future']['n']) for r in source if r['future'] is not None)),
        maximum_identity_gap=max(r['future']['max_identity_gap'] for r in source if r['future'] is not None),overall=source_cells[0])
    results=dict(classification=m['classification'],native_gate=gate,programs=programs,groups=grouped,paired_descriptive=paired,
        neural_actions=dict(Counter(str(r['selected_action']) for r in live)),neural_rates=dict(Counter(str(r['selected_rate']) for r in live)),
        signal=signals,actual_native_cost={k:summary[k] for k in ('control_steps','lifecycle','live_model_calls','wall_ns')},
        independent_replay_policy_queries=na['audit_fixed_policy_queries'],wall_interval_definition='saved public query to saved neural choice; includes host/serialization, not isolated inference or hardware real-time guarantee',
        live_interval_mean_ms=mean([r['saved_query_to_saved_choice_ns']/1e6 for r in latencies]),
        live_interval_max_ms=max([r['saved_query_to_saved_choice_ns']/1e6 for r in latencies],default=None),
        new_model_fits=0,online_LLM_API_calls=0,task_gain_qualification=False,algorithm_novelty_established=False,publication_goal_complete=False)
    io.write(out/'results.json',results)
io.write(out/'descriptive_analysis_receipt.json',dict(integrity='PASSED',guard=guard,wall_ns=perf_counter_ns()-start,source_manifest_sha256=io.sha(manifest),
    source_signal_audit_sha256=io.sha(run/'training_signal/audit.json'),native_audit_sha256=io.sha(run/'native_audit_repair_v2/audit.json'),
    analysis_new_physics=0,new_model_fits=0,online_LLM_API_calls=0,artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()}))
print(json.dumps({k:results[k] for k in ('programs','paired_descriptive','neural_actions','neural_rates','signal')},ensure_ascii=False))
