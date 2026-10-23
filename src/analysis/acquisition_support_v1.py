"""Descriptive action-support and complete-program room; evaluator-only labels."""
from collections import defaultdict,Counter
from copy import deepcopy
from itertools import combinations,groupby
from pathlib import Path
from time import perf_counter_ns
import csv
import numpy as np
from src.analysis import acquisition_support_sources_v1 as src
io=src.io
STAGES=('AFTER8','BEFORE_MOVE','AFTER_MOVE','RAW_PI_BEFORE_MOVE')
PHYSICAL=('logical_step','command','executed_action_oracle','after','reward','info','simulation_time_before','simulation_time_after','noise_cursor_after')
REQUESTS=('KEEP_C8','BEGIN_C8_PI_0.5_NOW','MOVE_THEN_KEEP_C8_PI_0.5','MOVE_THEN_INTEGRAL_PI_2.0',
          'REJECT_KEEP_C8_AFTER_MOVE','REJECT_KEEP_C8_PI_0.5_AFTER_MOVE','REIDENTIFY_AFTER_MOVE','SHORT_VALIDATION_RETURN_OLD',
          'CONTINUE_RAW_PI_0.5','MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY')


def physical_row(row):
    value=deepcopy({k:row[k] for k in PHYSICAL})
    if isinstance(value['info'].get('episode'),dict):value['info']['episode'].pop('t',None)
    return value


def trace(case,events,witnesses):
    initial=next(w for w in witnesses if w['label']=='INITIAL')['witness']
    start=io.digest([case['initial'],initial['native_sha256'],initial['comparison_python_sha256']])
    keys=[start];physical_count=0;public=[]
    for e in events:
        if e['event']=='STEP_COMPLETE':
            p=physical_row(e);io.require(p['logical_step']==physical_count,'consecutive original steps')
            if physical_count<128:keys.append(io.digest([keys[-1],p]))
            physical_count+=1
        elif e['event']=='AGENT_EVENT':public.append((e['agent_event'],e['public_payload']))
    io.require(physical_count==case['total_steps'],'source trace denominator')
    pi=[p['at_calls'] for k,p in public if k=='PI_PLAN'];move=[p['at_calls'] for k,p in public if k=='MOVE_ENTRY']
    post=[p['at_calls'] for k,p in public if k=='POST_MOVE_TASK_ENTRY']
    fits=[p['at_calls'] for k,p in public if k=='FIT_INTENT']
    # No source program defines a validation-and-return macro. Never infer
    # one from ordinary task steps or from an unqualified entry marker.
    io.require(not any(k in ('SHORT_VALIDATION_ENTRY','VALIDATION_ENTRY','VALIDATION_COMPLETE') for k,p in public),'unqualified validation schema needs a separate version')
    io.require(len(move)<=1 and len(post)<=1,'one original movement')
    io.require(not post or post[0]<=128,'registered movement prefix bound')
    return {'case':case,'prefix_sha256':keys,'first_pi_at':pi[0] if pi else None,
        'move_at':move[0] if move else None,'post_move_at':post[0] if post else None,'fit_at':fits,'validation_at':[],
        'initial_witness_native_sha256':initial['native_sha256'],'initial_witness_python_sha256':initial['comparison_python_sha256']}


def availability(t,n):
    c=t['case']
    if n is None:return 'CANONICAL_MOVEMENT_NOT_EXECUTED'
    if n>c['total_steps']:return 'SOURCE_TRAJECTORY_ENDED_BEFORE_NODE'
    if n==c['total_steps']:
        return 'INVALID_FIT_SOURCE_STOP' if c['stop_reason'].startswith('INVALID') else 'SOURCE_ALREADY_ENDED_AT_NODE'
    return None


def stage_rows(bank,traces):
    result=[];units=list(dict.fromkeys(t['case']['unit_id'] for t in traces))
    for unit in units:
        members=[t for t in traces if t['case']['unit_id']==unit];reference=next(t for t in members if src.pid(t['case'])=='MOVE_KEEP_C8')
        raw_reference=next(t for t in members if src.pid(t['case'])=='RAW_TASK_PI_T0.5')
        times=(8,reference['case']['planned_boundary'],reference['post_move_at'],raw_reference['case']['planned_boundary'])
        for stage,n in zip(STAGES,times):
            reference=raw_reference if stage=='RAW_PI_BEFORE_MOVE' else next(t for t in members if src.pid(t['case'])=='MOVE_KEEP_C8')
            ref_reason=availability(reference,n)
            refkey=reference['prefix_sha256'][n] if n is not None and n<=reference['case']['total_steps'] else None
            for t in members:
                c=t['case'];reason=availability(t,n);key=t['prefix_sha256'][n] if n is not None and n<=c['total_steps'] else None
                matched=bool(reason is None and ref_reason is None and key==refkey)
                if reason is None and ref_reason is not None:reason='CANONICAL_'+ref_reason
                elif reason is None and key!=refkey:reason='DIFFERENT_PHYSICAL_PREFIX'
                result.append({'bank':bank,'unit_id':unit,'group':c['group'],'task':c['task'],'context':c['context'],'case_id':c['case_id'],
                    'program':src.pid(c),'stage':stage,'at_control_steps':n,'remaining_budget':500-n if n is not None else None,
                    'source_alive':availability(t,n) is None,'canonical_alive':ref_reason is None,'matches_canonical_prefix':matched,'missing_reason':reason,
                    'prefix_sha256':key,'canonical_prefix_sha256':refkey,'first_pi_at':t['first_pi_at'],'movement_started_at':t['move_at'],
                    'post_move_at':t['post_move_at'],'actual_fit_times':','.join(str(v) for v in t['fit_at']),
                    'deadline_loss':c['deadline_loss'],'remaining_deadline_loss':c['deadline_loss']-n if matched else None,'success':c['success']})
    return result


def supports(request,stage,row,t):
    if not row['matches_canonical_prefix']:return False
    c=t['case'];n=row['at_control_steps'];style=c['style'];ti=c.get('time_constant_s')
    if request=='CONTINUE_RAW_PI_0.5':return stage=='RAW_PI_BEFORE_MOVE' and style=='RAW_TASK_PI' and ti==.5 and t['first_pi_at']==0
    if request=='MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY':return stage=='RAW_PI_BEFORE_MOVE' and style.startswith('MOVE_') and t['first_pi_at']==0 and t['move_at']==n
    if stage=='RAW_PI_BEFORE_MOVE':return False
    if request=='KEEP_C8':return style=='DIRECT_C8' and stage!='AFTER_MOVE'
    if request=='BEGIN_C8_PI_0.5_NOW':return style=='DIRECT_TASK_PI' and ti==.5 and t['first_pi_at']==n
    if request=='MOVE_THEN_KEEP_C8_PI_0.5':return stage!='AFTER_MOVE' and style=='MOVE_KEEP_TASK_PI' and ti==.5 and t['move_at']==n
    if request=='MOVE_THEN_INTEGRAL_PI_2.0':return stage!='AFTER_MOVE' and style=='MOVE_INTEGRAL_TASK_PI' and ti==2. and t['move_at']==n
    if request=='REJECT_KEEP_C8_AFTER_MOVE':return stage=='AFTER_MOVE' and style=='MOVE_KEEP_C8'
    if request=='REJECT_KEEP_C8_PI_0.5_AFTER_MOVE':return stage=='AFTER_MOVE' and style=='MOVE_KEEP_TASK_PI' and ti==.5 and t['first_pi_at']==n
    if request=='REIDENTIFY_AFTER_MOVE':return stage=='AFTER_MOVE' and any(k>=n and k>8 for k in t['fit_at'])
    if request=='SHORT_VALIDATION_RETURN_OLD':return n in t['validation_at']
    raise ValueError('unregistered support request')


def support_rows(bank,traces,nodes):
    byid={t['case']['case_id']:t for t in traces};result=[]
    for (unit,stage),it in groupby(nodes,lambda r:(r['unit_id'],r['stage'])):
        rows=list(it);base=rows[0]
        for request in REQUESTS:
            ids=[r['case_id'] for r in rows if supports(request,stage,r,byid[r['case_id']])]
            result.append({k:base[k] for k in ('bank','unit_id','group','task','context','stage','at_control_steps','canonical_alive')}|
                {'requested_suffix':request,'supported':bool(ids),'supporting_case_ids':'|'.join(ids),
                 'missing_reason':None if ids else 'CANONICAL_NODE_UNAVAILABLE' if not base['canonical_alive'] else 'NO_EXECUTED_SUFFIX_WITH_MATCHING_PREFIX_AND_SEMANTICS'})
    return result


def pairs(nodes):
    result=[]
    for _,it in groupby(nodes,lambda r:(r['unit_id'],r['stage'])):
        rows=list(it)
        for left,right in combinations(rows,2):
            same=bool(left['source_alive'] and right['source_alive'] and left['prefix_sha256']==right['prefix_sha256'])
            eligible=left['matches_canonical_prefix'] and right['matches_canonical_prefix']
            result.append({k:left[k] for k in ('bank','unit_id','group','task','context','stage','at_control_steps')}|
                {'left':left['program'],'right':right['program'],'same_physical_prefix_between_pair':same,'both_match_canonical':eligible,
                 'actual_full_loss_difference':left['deadline_loss']-right['deadline_loss'] if eligible else None,
                 'remaining_loss_difference':left['remaining_deadline_loss']-right['remaining_deadline_loss'] if eligible else None,
                 'missing_reason':None if eligible else 'LEFT:'+str(left['missing_reason'])+';RIGHT:'+str(right['missing_reason'])})
    return result


def portfolio(bank,cases,groups):
    rows=[]
    for unit,it in groupby(cases,lambda c:c['unit_id']):
        members=list(it);base=next(c for c in members if src.pid(c)=='RAW_TASK_PI_T0.5');best=min(c['deadline_loss'] for c in members)
        moving=[c for c in members if c['style'].startswith('MOVE_')];best_move=min(c['deadline_loss'] for c in moving)
        rows.append({'bank':bank,'unit_id':unit,'group':base['group'],'task':base['task'],'context':base['context'],
            'RAW_PI_loss':base['deadline_loss'],'RAW_PI_success':base['success'],'all_program_minimum_realized_loss':best,
            'all_minimum_labels':'|'.join(src.pid(c) for c in members if c['deadline_loss']==best),
            'MOVE_minimum_realized_loss':best_move,'MOVE_minimum_labels':'|'.join(src.pid(c) for c in moving if c['deadline_loss']==best_move),
            'clairvoyant_gap_vs_RAW_PI':base['deadline_loss']-best,'best_MOVE_minus_RAW_PI':best_move-base['deadline_loss'],
            'uses_future_outcomes':True,'deployable_method':False,'population_value_bound':False})
    io.require(len(rows)==6*groups,'complete room denominator')
    return rows


def write_csv(folder,name,rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with (folder/name).open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def analyze(manifest_path):
    started=perf_counter_ns();manifest_path=Path(manifest_path).resolve();m=src.load_manifest(manifest_path);out=manifest_path.parent
    for name,h in m['source_sha256'].items():io.require(io.sha(src.ROOT/name)==h,'frozen analysis/source changed')
    all_nodes=[];all_support=[];all_pairs=[];all_room=[];all_cases=[];banks=[]
    for bank,root,cohort,n,groups,programs in src.SOURCES:
        folder=root/cohort.lower();cases=list(io.rows(folder/'cases.jsonl.gz'));ids,units=src.validate_cases(cases,bank,n,groups,programs)
        journals=iter(groupby(io.rows(folder/'events.jsonl.gz'),lambda e:e['case_id']));private=iter(groupby(io.rows(folder/'witnesses.jsonl.gz'),lambda e:e['case_id']));traces=[]
        for case in cases:
            cid,events=next(journals);wid,witnesses=next(private);io.require(cid==wid==case['case_id'],'source journal ordering')
            t=trace(case,list(events),list(witnesses));traces.append(t)
            all_cases.append({'bank':bank,**{k:case[k] for k in ('case_id','unit_id','group','task','context','style','time_constant_s','total_steps','deadline_loss','success','stop_reason','planned_boundary')},
                'program':src.pid(case),'first_pi_at':t['first_pi_at'],'move_at':t['move_at'],'post_move_at':t['post_move_at'],
                'actual_fit_times':','.join(str(v) for v in t['fit_at']),
                'initial_witness_native_sha256':t['initial_witness_native_sha256'],'initial_witness_python_sha256':t['initial_witness_python_sha256']})
        io.require(next(journals,None) is None and next(private,None) is None,'extra unallocated journal cases')
        nodes=stage_rows(bank,traces);support=support_rows(bank,traces,nodes);pair=pairs(nodes);room=portfolio(bank,cases,groups)
        all_nodes+=nodes;all_support+=support;all_pairs+=pair;all_room+=room
        summary={'bank':bank,'executions':n,'groups':groups,'units':len(units),'programs':programs,'actual_saved_control_steps':sum(c['total_steps'] for c in cases),
            'full_program_results':[],'all_task_context_cells':[],'complete_group_room':[],
            'node_missing_counts':dict(Counter(r['missing_reason'] for r in nodes if r['missing_reason'])),
            'support_counts':[{'stage':stage,'requested_suffix':request,'complete_denominator':len(units),'canonical_live_units':sum(r['canonical_alive'] for r in support if r['stage']==stage and r['requested_suffix']==request),
                'supported_units':sum(r['supported'] for r in support if r['stage']==stage and r['requested_suffix']==request)} for stage in STAGES for request in REQUESTS]}
        for pid in ids:
            actual=[c for c in cases if src.pid(c)==pid];summary['full_program_results'].append({'program':pid,'n':len(actual),'successes':sum(c['success'] for c in actual),'mean_deadline_loss':sum(c['deadline_loss'] for c in actual)/len(actual)})
        for task in io.TASKS:
            for context in ('UNCHANGED','CHANGED'):
                cell=[r for r in room if r['task']==task and r['context']==context]
                summary['all_task_context_cells'].append({'task':task,'context':context,'n':len(cell),'RAW_PI_mean_loss':sum(r['RAW_PI_loss'] for r in cell)/len(cell),
                    'all_program_clairvoyant_min_mean':sum(r['all_program_minimum_realized_loss'] for r in cell)/len(cell),
                    'best_MOVE_mean_loss':sum(r['MOVE_minimum_realized_loss'] for r in cell)/len(cell),
                    'MOVE_better_than_RAW_PI':sum(r['best_MOVE_minus_RAW_PI']<0 for r in cell),'MOVE_worse_than_RAW_PI':sum(r['best_MOVE_minus_RAW_PI']>0 for r in cell)})
        for g in range(groups):
            cell=[r for r in room if r['group']==g]
            summary['complete_group_room'].append({'group':g,'n':len(cell),'mean_clairvoyant_gap_vs_RAW_PI':sum(r['clairvoyant_gap_vs_RAW_PI'] for r in cell)/6,
                'mean_best_MOVE_minus_RAW_PI':sum(r['best_MOVE_minus_RAW_PI'] for r in cell)/6})
        banks.append(summary)
    for name,rows in (('all_cases.csv',all_cases),('all_nodes.csv',all_nodes),('all_requested_suffix_support.csv',all_support),('all_node_program_pairs.csv',all_pairs),('all_unit_portfolio_room.csv',all_room)):write_csv(out,name,rows)
    io.require(len(all_cases)==1584 and sum(c['total_steps'] for c in all_cases)==204824,'full source denominator')
    for name,h in m['source_sha256'].items():io.require(io.sha(src.ROOT/name)==h,'source changed during analysis')
    io.write(out/'results.json',{'classification':'POST_HOC_DESCRIPTIVE_ACTION_SUPPORT_ONLY','banks':banks,'new_environment_steps':0,'new_resets':0,'new_model_fits':0,'new_online_LLM_API_calls':0,
        'uses_future_outcomes_only_in_evaluation':True,'clairvoyant_realized_minimum_is_a_population_bound':False,'new_method_or_gate_promoted':False})
    artifact={p.name:io.sha(p) for p in out.iterdir() if p.suffix=='.csv' or p.name=='results.json'}
    io.write(out/'completion.json',{'status':'ANALYZED_PENDING_INDEPENDENT_AUDIT','manifest_id':m['manifest_id'],'artifact_sha256':artifact,
        'rows':{'cases':len(all_cases),'nodes':len(all_nodes),'requested_suffixes':len(all_support),'program_pairs':len(all_pairs),'unit_room':len(all_room)},'wall_ns':perf_counter_ns()-started,
        'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0})
    return {'source_cases':len(all_cases),'source_steps':204824,'rows':len(all_nodes),'classification':'POST_HOC_DESCRIPTIVE_ONLY'}
