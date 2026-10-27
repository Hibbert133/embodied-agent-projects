"""Read-only v2 orchestration repair. Never changes v1 qualification or physics.

V1 reconstructed all54 cases then failed because JSON normalization rejects sets.
Only compare dictionary keys as sorted lists; outputs are in a fresh v2 folder.
The numerical inference, PI, actuator and witness reconstructors remain v1.
"""
from collections import Counter
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import gzip,json
import numpy as np
from src.analysis.learned_acquisition_native_audit_v1 import a,io,same,reconstruct,command_replay
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis.short_probe_journal_audit_v1 import physical_rows_equal
from src.analysis.capsule_record_json_v2 import normalize


def check_program_membership(programs):
    io.require(type(programs) is dict,'program records indexed by unique dictionary keys')
    same(sorted(programs),sorted(a.PROGRAMS),'missing or unregistered program in native unit')


def audit(path):
    from src.probe import learned_acquisition_actor_v1 as deployed
    from src.probe.frozen_risk_client_v1 import FrozenRiskClient
    from src.analysis import correction_scope_risk_reference_v1 as main_risk
    from src.analysis import transfer_risk_math_v1 as main_network
    path=Path(path).resolve();m=a.checked(path);original=path.parent/'native';out=path.parent/'native_audit_repair_v2';out.mkdir(exist_ok=False);start=perf_counter_ns();completion=io.read(original/'completion.json')
    io.require(completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial allocation cannot qualify')
    for name,digest in completion['artifact_sha256'].items():io.require(io.sha(original/name)==digest,'native collection immutable '+name)
    summary=io.read(original/'summary.json');cases=list(io.rows(original/'cases.jsonl.gz'));specs=a.population();same(len(cases),54)
    outer=iter(groupby(io.rows(original/'events.jsonl.gz'),a.case_key));priv=iter(groupby(io.rows(original/'witnesses.jsonl.gz'),a.case_key))
    sequence=psequence=stamp=pstamp=replay_queries=total_steps=0;ledger=dict(counts={},by_phase={});guard={};units={};contexts={};counts=Counter();chains=[];divergences=[]
    def denied(*args,**kwargs):raise RuntimeError('deployed actor/client/main risk inference disabled during independent native audit')
    with read_only(guard),patch.object(deployed,'run',denied),patch.object(FrozenRiskClient,'__call__',denied),patch.object(main_risk,'predict',denied),patch.object(main_network,'forward',denied),gzip.open(out/'decision_queries.jsonl.gz','xt',encoding='utf8') as stream:
        for spec,case in zip(specs,cases):
            a.validate_spec(spec)
            for name in a.KEYS:same(case[name],spec[name])
            key,it=next(outer);events=list(it);pk,pit=next(priv);private=list(pit);same(key,a.case_key(spec));same(pk,key)
            for rows,is_private in ((events,False),(private,True)):
                for e in rows:
                    for k in (*a.KEYS,*a.IDENTITY):same(e[k],spec[k] if k in spec else m[k])
                    if is_private:io.require(e['sequence']==psequence and e['saved_ns']>=pstamp,'private native chronology');psequence+=1;pstamp=e['saved_ns']
                    else:io.require(e['sequence']==sequence and e['saved_ns']>=stamp,'public native chronology');sequence+=1;stamp=e['saved_ns']
            same(events[0]['event'],'CASE_ALLOCATION');last=events.pop();same(last['event'],'CASE_COMPLETE');same(last['case_record_sha256'],io.digest(case))
            same(case['event_start_sequence'],events[0]['sequence']);same(case['event_end_sequence_exclusive'],last['sequence'])
            ledger,steps,witnesses,public,queries=reconstruct(spec,case,events[1:],private,ledger)
            replay_queries+=command_replay(spec,case,steps);total_steps+=len(steps)
            same(sum(e['agent_event']=='ACQUISITION_CHOICE' for e in public),int(case['pre_forecast'] is not None))
            same(sum(e['agent_event']=='RATE_PLAN' for e in public),int(case['post_forecast'] is not None))
            live=sum(e['agent_event']=='FORECAST' and e['public_payload']['forecast'] is not None and e['public_payload']['forecast']['kind']=='FROZEN_MODEL' for e in public)
            same(case['live_model_calls'],live);counts['actual_neural_decision_calls']+=live
            u=a.unit_key(spec);units.setdefault(u,{})[spec['program']]=(steps,witnesses,case)
            for q in queries:stream.write(json.dumps(normalize(q),separators=(',',':'),allow_nan=False)+'\n')
            if spec['program']=='LEARNED_JOINT_BANK0':
                pre=case['pre_forecast'];contexts[(spec['group'],spec['task'],spec['context'])]=None if pre is None else next(e['public_payload'] for e in public if e['agent_event']=='FORECAST' and e['public_payload']['sequence']==pre['forecast_sequence'])['forecast']
                counts['nondefault_neural_programs']+=int(case['selected_action'] not in (None,'CONTINUE') or case['selected_rate'] not in (None,.5))
                tails=[r for r in steps if r['phase']=='TAIL_TASK']
                if case['selected_action']=='MOVE_MEASURE' and case['measurement_steps']>0 and case['post_forecast'] is not None and tails:
                    chains.append(dict(spec=spec,actual_movement_steps=case['movement_steps'],actual_measurement_steps=case['measurement_steps'],actual_tail_steps=len(tails),
                        selected_rate=case['selected_rate'],saved_postdecision_sequence=case['post_forecast']['forecast_sequence']))
        io.require(next(outer,None) is None and next(priv,None) is None,'no unallocated native records')
        for unit,programs in units.items():
            check_program_membership(programs);left,lw,lc=programs['LEGACY_REFERENCE'];right,rw,rc=programs['DYNAMIC_FORCED_REFERENCE']
            same(len(left),len(right));io.require(physical_rows_equal(left,right,len(left)),'new forced interface changed actual physical execution')
            for label in ('INITIAL','FINAL'):
                same(lw[label]['witness']['native_sha256'],rw[label]['witness']['native_sha256'],'forced native state match')
                same(lw[label]['witness']['comparison_python_sha256'],rw[label]['witness']['comparison_python_sha256'],'forced RNG/python state match')
            counts['forced_full_physical_pairs']+=1
            for program in ('DYNAMIC_FORCED_REFERENCE','LEARNED_JOINT_BANK0'):
                candidate,_,c=programs[program];n=min(lc['planned_boundary'],len(left));io.require(physical_rows_equal(left,candidate,n),'common native prefix changed');counts['common_prefix_pairs']+=1
            learned,_,lcase=programs['LEARNED_JOINT_BANK0']
            different=next((i for i,(x,y) in enumerate(zip(left,learned)) if np.asarray(x['command'],np.float32).tobytes()!=np.asarray(y['command'],np.float32).tobytes()),None)
            if different is not None:
                io.require(different>=lc['planned_boundary'],'model altered the common prefix')
                divergences.append(dict(unit=list(unit),first_actual_command_difference=different,reference_command=left[different]['command'],learned_command=learned[different]['command']))
        for group in range(3):
            for task in ('push-v3','reach-v3','door-open-v3'):
                left=contexts[(group,task,'UNCHANGED')];right=contexts[(group,task,'CHANGED')]
                same(left,right,'hidden condition changed pre-observation model decision');counts['hidden_context_prequery_pairs']+=1
                counts['live_hidden_context_prequery_pairs']+=int(left is not None)
    same(summary['control_steps'],total_steps);same(summary['events'],sequence);same(summary['private_records'],psequence);same(summary['lifecycle'],ledger)
    same(summary['network_guard']['attempted_network_calls'],0);same(summary['forbidden_fit_guard']['attempts'],0)
    same(summary['live_model_calls'],counts['actual_neural_decision_calls']);same(ledger['counts']['reset_attempts'],2754)
    io.require(total_steps<=27000 and ledger['counts']['simulation_frames_completed']<=1512000 and replay_queries<=27000,'native full budgets')
    same(counts['forced_full_physical_pairs'],18);same(counts['common_prefix_pairs'],36);same(counts['hidden_context_prequery_pairs'],9)
    software_complete=True;behavior=bool(counts['nondefault_neural_programs'] and divergences and chains)
    gate=dict(original_frozen_audit_status='FAILED_RETAINED',repair_not_retroactive_frozen_qualification=True,status='SUPPLEMENTAL_NATIVE_CHAIN_RECONSTRUCTED_ORIGINAL_QUAL_FAILED' if software_complete and behavior else 'SUPPLEMENTAL_BEHAVIOR_CHAIN_NOT_ESTABLISHED_ORIGINAL_QUAL_FAILED',
        all54_records_checked=True,forced_full_physical_pairs=18,common_prefix_pairs=36,hidden_context_prequery_pairs=9,
        nondefault_neural_programs=counts['nondefault_neural_programs'],actual_command_divergence_cases=len(divergences),complete_neural_MOVE_measure_correct_tail_chains=len(chains),
        zero_budget_continuity_leakage_weight_change_violations=True,task_gain_qualified=False,algorithm_novelty_established=False,publication_goal_complete=False)
    io.write(out/'native_gate.json',gate);io.write(out/'actual_closed_loop_chains.json',chains);io.write(out/'actual_command_divergences.json',divergences)
    result=dict(integrity='PASSED',original_frozen_audit_status='FAILED_RETAINED',repair_not_retroactive_frozen_qualification=True,repair_source_git_commit=io.git('rev-parse','HEAD'),manifest_id=m['manifest_id'],executions=54,control_steps=total_steps,lifecycle=ledger,counters=dict(counts),
        independent_literal_PI_commands=replay_queries,audit_fixed_policy_queries=replay_queries,source_macro_and_legacy_actor_shared=True,
        main_actor_and_main_risk_inference_disabled=True,guard=guard,wall_ns=perf_counter_ns()-start,collection_sha256=completion['artifact_sha256'],
        query_sha256=io.sha(out/'decision_queries.jsonl.gz'),native_gate_sha256=io.sha(out/'native_gate.json'),
        new_physics=0,new_model_fits=0,online_LLM_API_calls=0,limitations='Recorded-feedback command specification replay, no independent physics; native qualification is not task-gain qualification')
    io.write(out/'audit.json',result);return result
