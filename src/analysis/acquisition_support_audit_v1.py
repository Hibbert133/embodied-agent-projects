"""Independent direct-record comparison; no rolling-digest support decisions."""
from collections import Counter
from itertools import groupby,combinations
from pathlib import Path
from time import perf_counter_ns
import csv
import math
from src.analysis import acquisition_support_sources_v1 as src
io=src.io
STAGES=('AFTER8','BEFORE_MOVE','AFTER_MOVE','RAW_PI_BEFORE_MOVE')
REQUESTS=('KEEP_C8','BEGIN_C8_PI_0.5_NOW','MOVE_THEN_KEEP_C8_PI_0.5','MOVE_THEN_INTEGRAL_PI_2.0',
    'REJECT_KEEP_C8_AFTER_MOVE','REJECT_KEEP_C8_PI_0.5_AFTER_MOVE','REIDENTIFY_AFTER_MOVE','SHORT_VALIDATION_RETURN_OLD',
    'CONTINUE_RAW_PI_0.5','MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY')


def project(e):
    # Independently build just the physical tuple. Phase/raw-policy are kept
    # outside this equality because they are not the applied physical input.
    info={k:v for k,v in e['info'].items()}
    if isinstance(info.get('episode'),dict):info['episode']={k:v for k,v in info['episode'].items() if k!='t'}
    return {'logical_step':e['logical_step'],'command':e['command'],'executed_action_oracle':e['executed_action_oracle'],
        'after':e['after'],'reward':e['reward'],'info':info,'simulation_time_before':e['simulation_time_before'],
        'simulation_time_after':e['simulation_time_after'],'noise_cursor_after':e['noise_cursor_after']}


def parse(c,events,private):
    initials=[r['witness'] for r in private if r['label']=='INITIAL'];io.require(len(initials)==1,'one actual initial witness')
    initial=initials[0];s=[project(e) for e in events if e['event']=='STEP_COMPLETE'];io.require(len(s)==c['total_steps'],'all original steps')
    pub=[(e['agent_event'],e['public_payload']) for e in events if e['event']=='AGENT_EVENT']
    def at(kind):return [p['at_calls'] for k,p in pub if k==kind]
    pi=at('PI_PLAN');move=at('MOVE_ENTRY');post=at('POST_MOVE_TASK_ENTRY')
    io.require(not any(at(k) for k in ('SHORT_VALIDATION_ENTRY','VALIDATION_ENTRY','VALIDATION_COMPLETE')),'no source validation macro')
    # Digests are re-created only to audit the exported identity columns;
    # actual equality below always uses direct structures and list prefixes.
    keys=[io.digest([c['initial'],initial['native_sha256'],initial['comparison_python_sha256']])]
    for e in s[:128]:keys.append(io.digest([keys[-1],e]))
    return {'case':c,'steps':s[:128],'keys':keys,'initial':(c['initial'],initial['native_sha256'],initial['comparison_python_sha256']),
        'pi':pi[0] if pi else None,'move':move[0] if move else None,'post':post[0] if post else None,'fits':at('FIT_INTENT')}


def reason(t,n):
    if n is None:return 'CANONICAL_MOVEMENT_NOT_EXECUTED'
    c=t['case']
    if c['total_steps']<n:return 'SOURCE_TRAJECTORY_ENDED_BEFORE_NODE'
    if c['total_steps']==n:return 'INVALID_FIT_SOURCE_STOP' if c['stop_reason'][:7]=='INVALID' else 'SOURCE_ALREADY_ENDED_AT_NODE'
    return None


def equal(a,b,n):return n is not None and a['initial']==b['initial'] and a['steps'][:n]==b['steps'][:n] and len(a['steps'])>=n and len(b['steps'])>=n


def candidates(request,stage,n,t):
    c=t['case'];s=c['style'];ti=c.get('time_constant_s')
    if stage=='RAW_PI_BEFORE_MOVE':
        return (request=='CONTINUE_RAW_PI_0.5' and s=='RAW_TASK_PI' and ti==.5 and t['pi']==0) or (
            request=='MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY' and s.startswith('MOVE_') and t['pi']==0 and t['move']==n)
    tests={
        'KEEP_C8':s=='DIRECT_C8' and stage!='AFTER_MOVE',
        'BEGIN_C8_PI_0.5_NOW':s=='DIRECT_TASK_PI' and ti==.5 and t['pi']==n,
        'MOVE_THEN_KEEP_C8_PI_0.5':stage!='AFTER_MOVE' and s=='MOVE_KEEP_TASK_PI' and ti==.5 and t['move']==n,
        'MOVE_THEN_INTEGRAL_PI_2.0':stage!='AFTER_MOVE' and s=='MOVE_INTEGRAL_TASK_PI' and ti==2. and t['move']==n,
        'REJECT_KEEP_C8_AFTER_MOVE':stage=='AFTER_MOVE' and s=='MOVE_KEEP_C8',
        'REJECT_KEEP_C8_PI_0.5_AFTER_MOVE':stage=='AFTER_MOVE' and s=='MOVE_KEEP_TASK_PI' and ti==.5 and t['pi']==n,
        'REIDENTIFY_AFTER_MOVE':stage=='AFTER_MOVE' and any(k>8 and k>=n for k in t['fits']),
        'SHORT_VALIDATION_RETURN_OLD':False,'CONTINUE_RAW_PI_0.5':False,'MOVE_FROM_RAW_PI_PREFIX_KEEP_PI_MEMORY':False}
    return tests[request]


def check_csv(folder,name,expected):
    with (folder/name).open(encoding='utf-8-sig',newline='') as f:actual=list(csv.DictReader(f))
    io.require(len(actual)==len(expected),'complete CSV denominator '+name);count=0
    for a,e in zip(actual,expected):
        io.require(set(a)==set(e),'CSV columns '+name)
        for k,v in e.items():
            if v is None:io.require(a[k]=='','missing is not zero '+name+'/'+k)
            elif isinstance(v,bool):io.require(a[k]==str(v),'boolean '+name+'/'+k)
            elif isinstance(v,(float,int)):io.require(math.isclose(float(a[k]),v,rel_tol=1e-12,abs_tol=1e-14),'number '+name+'/'+k)
            else:io.require(a[k]==v,'identity '+name+'/'+k)
            count+=1
    return count


def audit(path):
    start=perf_counter_ns();path=Path(path).resolve();folder=path.parent;m=src.load_manifest(path);done=io.read(folder/'completion.json')
    io.require(done['manifest_id']==m['manifest_id'] and done['status']=='ANALYZED_PENDING_INDEPENDENT_AUDIT','closed main analysis')
    for n,h in m['source_sha256'].items():io.require(io.sha(src.ROOT/n)==h,'source unchanged before audit')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'analysis artifact unchanged')
    case_rows=[];nodes=[];support=[];pair_rows=[];room=[];summaries=[]
    for bank,root,cohort,n,groups,programs in src.SOURCES:
        actual=list(io.rows(root/cohort.lower()/'cases.jsonl.gz'));ids,units=src.validate_cases(actual,bank,n,groups,programs)
        events=iter(groupby(io.rows(root/cohort.lower()/'events.jsonl.gz'),lambda e:e['case_id']))
        witnesses=iter(groupby(io.rows(root/cohort.lower()/'witnesses.jsonl.gz'),lambda e:e['case_id']));traces=[]
        for c in actual:
            cid,e=next(events);wid,w=next(witnesses);io.require(cid==wid==c['case_id'],'source case sequence')
            t=parse(c,list(e),list(w));traces.append(t)
            case_rows.append({'bank':bank,**{k:c[k] for k in ('case_id','unit_id','group','task','context','style','time_constant_s','total_steps','deadline_loss','success','stop_reason','planned_boundary')},
                'program':src.pid(c),'first_pi_at':t['pi'],'move_at':t['move'],'post_move_at':t['post'],'actual_fit_times':','.join(str(k) for k in t['fits']),
                'initial_witness_native_sha256':t['initial'][1],'initial_witness_python_sha256':t['initial'][2]})
        io.require(next(events,None) is None and next(witnesses,None) is None,'extra source journal')
        bank_nodes=[];bank_support=[];bank_room=[]
        for unit in units:
            members=[t for t in traces if t['case']['unit_id']==unit];c8=next(t for t in members if src.pid(t['case'])=='MOVE_KEEP_C8')
            raw=next(t for t in members if src.pid(t['case'])=='RAW_TASK_PI_T0.5')
            times=[8,c8['case']['planned_boundary'],c8['post'],raw['case']['planned_boundary']]
            for stage,nstep in zip(STAGES,times):
                anchor=raw if stage=='RAW_PI_BEFORE_MOVE' else c8;anchor_bad=reason(anchor,nstep);local=[]
                for t in members:
                    c=t['case'];bad=reason(t,nstep);matched=bad is None and anchor_bad is None and equal(t,anchor,nstep)
                    if bad is None:bad=('CANONICAL_'+anchor_bad) if anchor_bad is not None else None if equal(t,anchor,nstep) else 'DIFFERENT_PHYSICAL_PREFIX'
                    key=t['keys'][nstep] if nstep is not None and nstep<=c['total_steps'] else None
                    akey=anchor['keys'][nstep] if nstep is not None and nstep<=anchor['case']['total_steps'] else None
                    local.append({'bank':bank,'unit_id':unit,'group':c['group'],'task':c['task'],'context':c['context'],'case_id':c['case_id'],'program':src.pid(c),
                        'stage':stage,'at_control_steps':nstep,'remaining_budget':None if nstep is None else 500-nstep,
                        'source_alive':reason(t,nstep) is None,'canonical_alive':anchor_bad is None,'matches_canonical_prefix':matched,'missing_reason':bad,
                        'prefix_sha256':key,'canonical_prefix_sha256':akey,'first_pi_at':t['pi'],'movement_started_at':t['move'],'post_move_at':t['post'],
                        'actual_fit_times':','.join(str(k) for k in t['fits']),'deadline_loss':c['deadline_loss'],
                        'remaining_deadline_loss':c['deadline_loss']-nstep if matched else None,'success':c['success']})
                bank_nodes+=local
                for request in REQUESTS:
                    selected=[t['case']['case_id'] for t in members if anchor_bad is None and reason(t,nstep) is None and equal(t,anchor,nstep) and candidates(request,stage,nstep,t)]
                    base=local[0]
                    bank_support.append({k:base[k] for k in ('bank','unit_id','group','task','context','stage','at_control_steps','canonical_alive')}|
                        {'requested_suffix':request,'supported':bool(selected),'supporting_case_ids':'|'.join(selected),
                            'missing_reason':None if selected else 'CANONICAL_NODE_UNAVAILABLE' if anchor_bad is not None else 'NO_EXECUTED_SUFFIX_WITH_MATCHING_PREFIX_AND_SEMANTICS'})
                for ia,ib in combinations(range(len(local)),2):
                    left,right=local[ia],local[ib];ta,tb=members[ia],members[ib]
                    same=reason(ta,nstep) is None and reason(tb,nstep) is None and equal(ta,tb,nstep)
                    ok=left['matches_canonical_prefix'] and right['matches_canonical_prefix']
                    delta=ta['case']['deadline_loss']-tb['case']['deadline_loss'] if ok else None
                    pair_rows.append({k:left[k] for k in ('bank','unit_id','group','task','context','stage','at_control_steps')}|
                        {'left':left['program'],'right':right['program'],'same_physical_prefix_between_pair':same,'both_match_canonical':ok,
                            'actual_full_loss_difference':delta,'remaining_loss_difference':delta,
                            'missing_reason':None if ok else 'LEFT:'+str(left['missing_reason'])+';RIGHT:'+str(right['missing_reason'])})
            cs=[t['case'] for t in members];b=raw['case'];move=[c for c in cs if c['style'][:5]=='MOVE_'];lo=min(c['deadline_loss'] for c in cs);ml=min(c['deadline_loss'] for c in move)
            bank_room.append({'bank':bank,'unit_id':unit,'group':b['group'],'task':b['task'],'context':b['context'],'RAW_PI_loss':b['deadline_loss'],'RAW_PI_success':b['success'],
                'all_program_minimum_realized_loss':lo,'all_minimum_labels':'|'.join(src.pid(c) for c in cs if c['deadline_loss']==lo),
                'MOVE_minimum_realized_loss':ml,'MOVE_minimum_labels':'|'.join(src.pid(c) for c in move if c['deadline_loss']==ml),
                'clairvoyant_gap_vs_RAW_PI':b['deadline_loss']-lo,'best_MOVE_minus_RAW_PI':ml-b['deadline_loss'],
                'uses_future_outcomes':True,'deployable_method':False,'population_value_bound':False})
        nodes+=bank_nodes;support+=bank_support;room+=bank_room
        summary={'bank':bank,'executions':n,'groups':groups,'units':len(units),'programs':programs,'actual_saved_control_steps':sum(c['total_steps'] for c in actual),
            'full_program_results':[],'all_task_context_cells':[],'complete_group_room':[],
            'node_missing_counts':dict(Counter(r['missing_reason'] for r in bank_nodes if r['missing_reason'])),
            'support_counts':[{'stage':stage,'requested_suffix':request,'complete_denominator':len(units),'canonical_live_units':sum(r['canonical_alive'] for r in bank_support if r['stage']==stage and r['requested_suffix']==request),
                'supported_units':sum(r['supported'] for r in bank_support if r['stage']==stage and r['requested_suffix']==request)} for stage in STAGES for request in REQUESTS]}
        for p in ids:
            cs=[c for c in actual if src.pid(c)==p];summary['full_program_results'].append({'program':p,'n':len(cs),'successes':sum(c['success'] for c in cs),'mean_deadline_loss':sum(c['deadline_loss'] for c in cs)/len(cs)})
        for task in io.TASKS:
            for context in ('UNCHANGED','CHANGED'):
                cs=[r for r in bank_room if (r['task'],r['context'])==(task,context)]
                summary['all_task_context_cells'].append({'task':task,'context':context,'n':len(cs),'RAW_PI_mean_loss':sum(c['RAW_PI_loss'] for c in cs)/len(cs),
                    'all_program_clairvoyant_min_mean':sum(c['all_program_minimum_realized_loss'] for c in cs)/len(cs),'best_MOVE_mean_loss':sum(c['MOVE_minimum_realized_loss'] for c in cs)/len(cs),
                    'MOVE_better_than_RAW_PI':sum(c['best_MOVE_minus_RAW_PI']<0 for c in cs),'MOVE_worse_than_RAW_PI':sum(c['best_MOVE_minus_RAW_PI']>0 for c in cs)})
        for g in range(groups):
            cs=[c for c in bank_room if c['group']==g];io.require(len(cs)==6,'whole group aggregation')
            summary['complete_group_room'].append({'group':g,'n':6,'mean_clairvoyant_gap_vs_RAW_PI':sum(c['clairvoyant_gap_vs_RAW_PI'] for c in cs)/6,'mean_best_MOVE_minus_RAW_PI':sum(c['best_MOVE_minus_RAW_PI'] for c in cs)/6})
        summaries.append(summary)
    fields=0
    for name,values in (('all_cases.csv',case_rows),('all_nodes.csv',nodes),('all_requested_suffix_support.csv',support),('all_node_program_pairs.csv',pair_rows),('all_unit_portfolio_room.csv',room)):fields+=check_csv(folder,name,values)
    expected={'classification':'POST_HOC_DESCRIPTIVE_ACTION_SUPPORT_ONLY','banks':summaries,'new_environment_steps':0,'new_resets':0,'new_model_fits':0,'new_online_LLM_API_calls':0,
        'uses_future_outcomes_only_in_evaluation':True,'clairvoyant_realized_minimum_is_a_population_bound':False,'new_method_or_gate_promoted':False}
    io.require(io.digest(io.read(folder/'results.json'))==io.digest(expected),'independent complete JSON summary')
    io.require(len(case_rows)==1584 and sum(c['total_steps'] for c in case_rows)==204824,'complete source data denominator')
    for n,h in m['source_sha256'].items():io.require(io.sha(src.ROOT/n)==h,'source unchanged after audit')
    result={'integrity':'PASSED','source_cases':len(case_rows),'source_steps':204824,'fields_checked':fields,'all_rows':{'nodes':len(nodes),'support':len(support),'pairs':len(pair_rows),'units':len(room)},
        'completion_sha256':io.sha(folder/'completion.json'),'auditor_sha256':io.sha(__file__),'artifact_sha256':done['artifact_sha256'],'wall_ns':perf_counter_ns()-start,
        'new_environment_steps':0,'new_model_fits':0,'new_online_LLM_API_calls':0,'scope':'Direct initial-state/physical-list prefix equality and independent complete population summaries; not physics reproduction or a novel-method evaluation'}
    io.write(folder/'audit.json',result);return result
