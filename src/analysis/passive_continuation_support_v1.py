"""Post-hoc normal-control versus validation semantics on immutable real records."""
from pathlib import Path
from collections import Counter,defaultdict
from time import perf_counter_ns
from datetime import datetime,timezone
import traceback
from src.analysis import response_qualification_io_v1 as io
from src.analysis import memory_reset_io_v1 as original
from src.analysis.memory_reset_streaming_audit_v1 import JournalReader
from src.analysis import passive_continuation_replay_v1 as replay

BASE=io.ROOT/'outputs/passive_continuation_support'
VALIDATION=BASE/'validation_v2'
OUTPUT=BASE/'analysis_v1'
CONFIG=io.ROOT/'configs/movement_task/passive_continuation_support_v1.json'
PROTOCOL=io.ROOT/'docs/protocols/passive_continuation_support_v1_zh.md'
SOURCE=io.ROOT/'outputs/memory_reset/qualification_v1/memory_reset_20261022T224151Z_814c7dbd2ce7'
COHORTS=('SOFTWARE_NATIVE','QUAL')
REPLAYS=('RAW','VALIDATE_NO_UPDATE','TAIL_VALIDATE8_1')


def config():return dict(protocol='PASSIVE_CONTINUATION_SUPPORT_V1',classification='POST_HOC_DESCRIPTIVE_SEMANTIC_REPLAY',
    source_run=SOURCE.relative_to(io.ROOT).as_posix(),full_source_executions=630,reference_program='RAW_CONTINUE',reference_executions=72,
    replays=list(REPLAYS),maximum_saved_policy_action_reads=108000,maximum_independent_PI_reconstructions=36000,
    source_scope='all630 registered; all72 RAW_CONTINUE canonical traces, no favorable subset',
    windows='first0..8 actual task steps after live16/32/64 boundary; early/short retained',
    strict='exact float32 command equality before disclosing next saved observation; stop on first divergence',
    counterfactual_task_outcomes_imputed=0,environment_creations=0,resets=0,simulation_steps=0,model_fits=0,
    new_fixed_policy_queries=0,online_LLM_API_calls=0,new_episode_seeds=0,task_benefit_established=False,publication_goal_complete=False)


def sources():
    files=[SOURCE/'manifest.json']
    for cohort in COHORTS:
        folder=SOURCE/cohort.lower()
        audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED','audited original full cohort')
        io.require(audit['collection_completion_sha256']==io.sha(folder/'completion.json'),'original audit/completion binding')
        for name in ('cases.jsonl.gz','events.jsonl.gz'):
            io.require(io.sha(folder/name)==audit['artifact_sha256'][name],'original audited source '+name)
        files.extend(folder/name for name in ('audit.json','completion.json','summary.json','cases.jsonl.gz','events.jsonl.gz'))
    return {p.relative_to(io.ROOT).as_posix():io.sha(p) for p in files}


def prepare():
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED','checked source before analysis')
    io.require(not io.git('status','--porcelain','--untracked-files=no'),'clean tracked analysis freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')),'one preserved analysis, no replacement')
    io.require(io.read(CONFIG)==config(),'exact post-hoc scope')
    for n,h in qa['source_sha256'].items():io.require(io.sha(io.ROOT/n)==h,'checked source changed '+n)
    head=io.git('rev-parse','HEAD');stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    m=dict(analysis_run_id='passive_support_'+stamp+'_'+head[:12],source_git_commit=head,config=config(),
        source_sha256=qa['source_sha256'],historical_artifact_sha256=sources(),new_episode_seeds=0,publication_goal_complete=False)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['analysis_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',m)
    return out/'manifest.json'


def checked(path):
    path=Path(path).resolve();m=io.read(path);body=dict(m);mid=body.pop('manifest_id')
    io.require(path.name=='manifest.json' and path.parent.parent==OUTPUT.resolve() and io.digest(body)==mid,'owned immutable analysis')
    io.require(m['config']==config(),'unchanged descriptive scope')
    for n,h in {**m['source_sha256'],**m['historical_artifact_sha256']}.items():io.require(io.sha(io.ROOT/n)==h,'unchanged source '+n)
    return m


def source_cases(cohort):
    """No private witness/actuator values are extracted for program callbacks."""
    identity={k:io.read(SOURCE/'manifest.json')[k] for k in original.IDENTITY}
    folder=SOURCE/cohort.lower();reader=JournalReader(io.rows(folder/'events.jsonl.gz'),identity)
    cases=iter(io.rows(folder/'cases.jsonl.gz'))
    for spec in original.population(cohort):
        case=next(cases,None);io.require(case is not None,'complete original allocation')
        replay.same({k:case[k] for k in original.KEYS},spec,'original registered population order')
        io.require(case['event_start_sequence']==reader.count,'original case boundary')
        chosen=spec['program']=='RAW_CONTINUE';steps=[];memories=[];pending=None;local_sequence=0
        while reader.count<case['event_end_sequence_exclusive']:
            e=reader.take();replay.same({k:e[k] for k in original.KEYS},spec,'no borrowed event')
            if not chosen or e['event']!='AGENT_EVENT':continue
            p=e['public_payload'];io.require(p['sequence']==local_sequence,'public source order');local_sequence+=1
            kind=e['agent_event']
            if kind=='COMMAND':
                io.require(pending is None and p['at_calls']==len(steps),'one pending public source command')
                pending={k:p[k] for k in ('at_calls','before','command','raw_policy')};pending['sequence']=p['sequence']
            elif kind=='STEP_RESULT':
                io.require(pending is not None and p['command_sequence']==pending['sequence'] and p['at_calls']==len(steps)+1,'matching actual source receipt')
                row={k:v for k,v in pending.items() if k!='sequence'};row['after']=p['after'];steps.append(row);pending=None
            elif kind=='TASK_MEMORY_COMMIT':memories.append(io.digest(p['memory']))
        marker=reader.take();io.require(marker['event']=='CASE_COMPLETE' and marker['case_record_sha256']==io.digest(case),'original case marker')
        if chosen:io.require(pending is None and len(steps)==case['total_steps']==len(memories),'entire real canonical trace')
        yield spec,case,steps,memories
    io.require(next(cases,None) is None,'no extra original case');reader.finish()


def compute(path):
    m=checked(path);out=Path(path).parent;started=perf_counter_ns();registry=[];rows=[];windows=[];counts=Counter()
    for cohort in COHORTS:
        for spec,case,steps,memories in source_cases(cohort):
            ident={k:spec[k] for k in original.KEYS};reference=spec['program']=='RAW_CONTINUE'
            registry.append(dict(**ident,original_success=case['success'],original_deadline_loss=case['deadline_loss'],
                original_steps=case['total_steps'],canonical_reference=reference,
                analysis_availability='CANONICAL_RAW_TRACE' if reference else 'DIFFERENT_REGISTERED_PROGRAM_NOT_A_PASSIVE_HISTORY_REFERENCE'))
            counts['registered_executions']+=1
            if not reference:continue
            n=len(steps);boundary=spec['planned_boundary'];available=max(0,min(8,n-boundary))
            row=dict(**ident,source_public_trace_sha256=io.digest(steps),source_command_sha256=io.digest([s['command'] for s in steps]),
                source_memory_sha256_sequence=memories,source_steps=n,original_success=case['success'],original_deadline_loss=case['deadline_loss'],
                available_validation_steps=available,missing_reason='EARLY_END_AT_OR_BEFORE_BOUNDARY' if n<=boundary else 'SHORT_WINDOW_EARLY_END' if available<8 else None,replays=[])
            for program in REPLAYS:
                result,record=replay.run(spec['task'],boundary,case['initial'],steps,program);r=result['outcome']
                for name in ('success','terminated','truncated','total_steps','deadline_loss','final_memory'):replay.same(r[name],case[name],'same actual complete outcome '+name)
                regenerated=[io.digest(e['payload']['memory']) for e in result['events'] if e['kind']=='TASK_MEMORY_COMMIT']
                replay.same(regenerated,memories,'all real per-step control memory, no hidden reset')
                io.require(r['warm_probe_steps']==(0 if program=='RAW' else available),'semantic label versus actual full cost')
                expected_return=None if available==0 else result['outcome']['learning']['saved_return']['record']['post_memory']
                row['replays'].append(dict(program=program,command_sha256=io.digest(record.executed_commands),memory_sha256_sequence=regenerated,
                    final_memory_sha256=io.digest(r['final_memory']),full_deadline_loss=r['deadline_loss'],total_steps=r['total_steps'],
                    saved_policy_action_reads=record.policy_reads,outcomes_disclosed=record.outcomes_read,
                    validation_label_steps=r['warm_probe_steps'],returned_memory=expected_return))
                counts['saved_policy_action_reads']+=record.policy_reads;counts['exact_replays']+=1
            rows.append(row);counts['canonical_references']+=1;counts['source_command_steps']+=n
            counts['full_windows' if available==8 else 'short_windows' if available else 'unavailable_windows']+=1
            for s in steps[boundary:boundary+available]:windows.append(dict(**ident,relative_step=s['at_calls']-boundary+1,**s))
    io.require(counts['registered_executions']==630 and counts['canonical_references']==72 and counts['exact_replays']==216,'full intended semantic census')
    io.require(counts['saved_policy_action_reads']<=config()['maximum_saved_policy_action_reads'],'declared offline budget')
    panels=[]
    for cohort in COHORTS:
        for task in io.TASKS:
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    selected=[r for r in rows if (r['cohort'],r['task'],r['context'],r['planned_boundary'])==(cohort,task,context,boundary)]
                    io.require(len(selected)==(1 if cohort=='SOFTWARE_NATIVE' else 3),'every task/condition/boundary cell')
                    panels.append(dict(cohort=cohort,task=task,context=context,boundary=boundary,independent_groups=[r['group'] for r in selected],
                        complete_denominator=len(selected),full_windows=sum(r['available_validation_steps']==8 for r in selected),
                        short_windows=sum(0<r['available_validation_steps']<8 for r in selected),unavailable_windows=sum(r['available_validation_steps']==0 for r in selected),
                        actual_window_steps=sum(r['available_validation_steps'] for r in selected),all_three_saved_command_and_memory_traces_equal=True))
    io.write(out/'case_registry.json',registry);io.write(out/'reference_replays.json',rows);io.write(out/'actual_window_steps.json',windows)
    result=dict(integrity='PASSED_PENDING_INDEPENDENT_AUDIT',analysis_run_id=m['analysis_run_id'],manifest_id=m['manifest_id'],
        source_git_commit=m['source_git_commit'],classification='POST_HOC_DESCRIPTIVE_SEMANTIC_REPLAY',counts=dict(counts),panels=panels,
        conclusion='VALIDATE8_WITH_UNCHANGED_RECEIVER_IS_NORMAL_PASSIVE_TASK_CONTINUATION_WITH_DIFFERENT_PHASE_LABELS',
        same_gain_only=True,changed_gain_unexecuted_outcomes_imputed=0,learned_receiver_task_benefit_established=False,
        physical_activity=0,scientific_model_fits=0,new_fixed_policy_queries=0,online_LLM_API_calls=0,publication_goal_complete=False,wall_ns=perf_counter_ns()-started)
    io.write(out/'summary.json',result);checked(path);return result
