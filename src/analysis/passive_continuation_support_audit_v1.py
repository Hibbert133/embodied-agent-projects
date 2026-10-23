"""Re-read original bytes and literal PI; no main actor/replay is available."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
from src.analysis import response_qualification_io_v1 as io
from src.analysis import passive_continuation_support_v1 as a
from src.analysis import passive_continuation_independent_v1 as literal
from src.analysis import memory_reset_io_v1 as old


def audit(path):
    m=a.checked(path);out=Path(path).parent;started=perf_counter_ns();fields=0
    def compare(x,y,message):
        nonlocal fields
        io.require(io.digest(x)==io.digest(y),message)
        def leaves(v):return sum(leaves(t) for t in v.values()) if isinstance(v,dict) else sum(leaves(t) for t in v) if isinstance(v,list) else 1
        fields+=leaves(y)
    registered=io.read(out/'case_registry.json');rows=io.read(out/'reference_replays.json');window_rows=io.read(out/'actual_window_steps.json')
    summary=io.read(out/'summary.json');counts=Counter();expected_registry=[];expected_windows=[];reference_index=0;registry_index=0
    for cohort in a.COHORTS:
        folder=a.SOURCE/cohort.lower();source_cases=list(io.rows(folder/'cases.jsonl.gz'));source_events=iter(io.rows(folder/'events.jsonl.gz'));global_sequence=0
        compare(len(source_cases),len(old.population(cohort)),'full original cohort count')
        for spec,case in zip(old.population(cohort),source_cases):
            compare({k:case[k] for k in old.KEYS},spec,'source allocation')
            ident={k:spec[k] for k in old.KEYS};chosen=spec['program']=='RAW_CONTINUE';steps=[];old_memories=[];pending=None
            compare(case['event_start_sequence'],global_sequence,'source event start')
            while global_sequence<case['event_end_sequence_exclusive']:
                e=next(source_events);compare(e['sequence'],global_sequence,'source event sequence');global_sequence+=1
                if not chosen or e['event']!='AGENT_EVENT':continue
                compare({k:e[k] for k in old.KEYS},spec,'no foreign public source event');p=e['public_payload'];kind=e['agent_event']
                if kind=='COMMAND':
                    io.require(pending is None,'one actual pending command')
                    compare(p['at_calls'],len(steps),'actual command time');pending=p
                elif kind=='STEP_RESULT':
                    io.require(pending is not None,'actual receipt requires command')
                    compare(p['command_sequence'],pending['sequence'],'actual source receipt parent')
                    steps.append(dict(at_calls=pending['at_calls'],before=pending['before'],after=p['after'],command=pending['command'],raw_policy=pending['raw_policy']));pending=None
                elif kind=='TASK_MEMORY_COMMIT':old_memories.append(p['memory'])
            marker=next(source_events);compare(marker['sequence'],global_sequence,'source case completion time');global_sequence+=1
            compare(marker['event'],'CASE_COMPLETE','source completion');compare(marker['case_record_sha256'],io.digest(case),'source completion digest')
            expected_registry.append(dict(**ident,original_success=case['success'],original_deadline_loss=case['deadline_loss'],original_steps=case['total_steps'],
                canonical_reference=chosen,analysis_availability='CANONICAL_RAW_TRACE' if chosen else 'DIFFERENT_REGISTERED_PROGRAM_NOT_A_PASSIVE_HISTORY_REFERENCE'))
            counts['registered_executions']+=1;registry_index+=1
            if not chosen:continue
            io.require(pending is None,'no unfinished original canonical command')
            v=literal.reference(case['initial'],steps,spec['task'],spec['planned_boundary']);n=len(steps);count=v['available_validation_steps']
            compare(v['final_memory'],case['final_memory'],'all original numeric final memory');compare(v['memory_sha256_sequence'],[io.digest(t) for t in old_memories],'all original numeric per-step memory')
            r=rows[reference_index];reference_index+=1
            for k,value in ident.items():compare(r[k],value,'complete canonical identity')
            compare(r['source_steps'],n,'all actual source steps');compare(r['source_public_trace_sha256'],io.digest(steps),'source public steps')
            commands=io.digest([s['command'] for s in steps]);compare(r['source_command_sha256'],commands,'original command digest')
            compare(r['source_memory_sha256_sequence'],v['memory_sha256_sequence'],'original independent memories')
            compare(r['original_success'],case['success'],'historical success');compare(r['original_deadline_loss'],case['deadline_loss'],'historical cutoff')
            compare(r['available_validation_steps'],count,'actual complete/partial window');compare(r['missing_reason'],v['missing_reason'],'missing reason')
            compare([z['program'] for z in r['replays']],list(a.REPLAYS),'all three programs')
            for z in r['replays']:
                compare(z['command_sha256'],commands,'replayed physical commands');compare(z['memory_sha256_sequence'],v['memory_sha256_sequence'],'replayed full numeric memory')
                compare(z['final_memory_sha256'],io.digest(v['final_memory']),'replayed numeric final memory')
                compare(z['full_deadline_loss'],case['deadline_loss'],'full cost, no added8');compare(z['total_steps'],n,'actual full cost')
                compare(z['saved_policy_action_reads'],n,'offline saved action reads');compare(z['outcomes_disclosed'],n,'only matched actual receipts')
                compare(z['validation_label_steps'],0 if z['program']=='RAW' else count,'phase labels differ, not cost')
                compare(z['returned_memory'],None if count==0 else v['before_memory'] if z['program']=='RAW' else v['after_memory'],'real phase return')
                counts['saved_policy_action_reads']+=n;counts['exact_replays']+=1
            for s in steps[spec['planned_boundary']:spec['planned_boundary']+count]:expected_windows.append(dict(**ident,relative_step=s['at_calls']-spec['planned_boundary']+1,**s))
            counts['canonical_references']+=1;counts['source_command_steps']+=n
            counts['full_windows' if count==8 else 'short_windows' if count else 'unavailable_windows']+=1
        io.require(next(source_events,None) is None,'no extra original event')
    compare(registered,expected_registry,'all630 register rows');compare(window_rows,expected_windows,'all actual window steps');compare(summary['counts'],dict(counts),'complete computation counts')
    compare(len(rows),72,'all72 canonical records');compare(reference_index,72,'complete canonical traversal');compare(registry_index,630,'complete source traversal')
    panels=[]
    for cohort in a.COHORTS:
        for task in io.TASKS:
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    group=[r for r in rows if (r['cohort'],r['task'],r['context'],r['planned_boundary'])==(cohort,task,context,boundary)]
                    panels.append(dict(cohort=cohort,task=task,context=context,boundary=boundary,independent_groups=[r['group'] for r in group],complete_denominator=len(group),
                        full_windows=sum(r['available_validation_steps']==8 for r in group),short_windows=sum(0<r['available_validation_steps']<8 for r in group),
                        unavailable_windows=sum(r['available_validation_steps']==0 for r in group),actual_window_steps=sum(r['available_validation_steps'] for r in group),all_three_saved_command_and_memory_traces_equal=True))
    compare(summary['panels'],panels,'all36 cohort/task/condition/boundary panels');compare(summary['classification'],'POST_HOC_DESCRIPTIVE_SEMANTIC_REPLAY','analysis limit')
    io.require(counts['source_command_steps']<=a.config()['maximum_independent_PI_reconstructions'],'offline numerical budget')
    a.checked(path)
    result=dict(integrity='PASSED',analysis_run_id=m['analysis_run_id'],manifest_id=m['manifest_id'],source_git_commit=m['source_git_commit'],
        fields_checked=fields,canonical_traces=72,original_executions_registered=630,independent_PI_reconstructions=counts['source_command_steps'],
        main_actor_replay_and_PI_numbers_disabled=True,no_new_fixed_policy_queries=True,new_physical_activity=0,model_fits=0,online_LLM_API_calls=0,
        task_benefit_established=False,publication_goal_complete=False,wall_ns=perf_counter_ns()-started,
        analysis_artifact_sha256={n:io.sha(out/n) for n in ('case_registry.json','reference_replays.json','actual_window_steps.json','summary.json')})
    io.write(out/'audit.json',result);return result
