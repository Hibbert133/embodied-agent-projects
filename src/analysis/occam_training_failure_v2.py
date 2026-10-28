"""Stream/accounting-only diagnosis of a closed incomplete allocation, no Env."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
import gzip,hashlib,json
from src.analysis import occam_reader_extension_v3 as extension
from src.analysis.occam_train_envelope_v2 import bind_case
io=extension.io;a=extension.a
BASE=a.BASE/'failure_delivery_v2';FREEZE=BASE/'diagnostic_freeze_v1';OUTPUT=BASE/'analysis_v1'
OWN=('src/analysis/occam_training_failure_v2.py','scripts/diagnose_occam_training_failure_v2.py',
    'tests/test_occam_training_failure_v2.py','docs/protocols/occam_training_failure_diagnostic_v2_zh.md')


def same(left,right,why):io.require(io.digest(left)==io.digest(right),why)


def census(specs,complete,failed):
    io.require(len(complete)<len(specs) and {k:failed[k] for k in a.KEYS}==specs[len(complete)],'partial allocation position')
    rows=[]
    for index,spec in enumerate(specs):
        if index<len(complete):
            case=complete[index];same({k:case[k] for k in a.KEYS},spec,'complete allocation order')
            rows.append({**spec,'status':'COMPLETE_RECORD_NOT_FULL_TRAIN_QUALIFICATION','total_steps':case['total_steps'],'success':case['success'],'deadline_loss':case['deadline_loss']})
        elif index==len(complete):rows.append({**spec,'status':'TECHNICAL_FAILURE_NO_TASK_OUTCOME','total_steps':failed['total_steps'],'success':None,'deadline_loss':None})
        else:rows.append({**spec,'status':'NOT_STARTED','total_steps':None,'success':None,'deadline_loss':None})
    return rows


def ledger_event(ledger,pending,row):
    """Rebuild qualified reset/control charges with literal independent integers."""
    ledger=deepcopy(ledger);kind=row['event']
    def add(phase,key,n):
        ledger['counts'][key]=ledger['counts'].get(key,0)+n
        values=ledger['by_phase'].setdefault(phase,{});values[key]=values.get(key,0)+n
    def simulation(phase,attempt,frames,complete):
        add(phase,'simulation_attempts',attempt);add(phase,'simulation_frames_attempted',frames)
        if complete:add(phase,'simulation_completed',attempt);add(phase,'simulation_frames_completed',frames)
    if kind=='LIFECYCLE_RESET_INTENT':
        io.require(pending is None,'overlapping reset');same(row['before'],ledger,'reset before ledger')
        io.require(row['phase'] in ('GOAL_GENERATION','CONTROLLED_RESET'),'unexpected reset phase')
        add(row['phase'],'reset_attempts',1);pending=row
    elif kind=='LIFECYCLE_RESET_COMPLETE':
        io.require(pending is not None and row['intent_sequence']==pending['sequence'] and row['phase']==pending['phase'],'reset closure')
        simulation(row['phase'],100,500,True);add(row['phase'],'reset_completed',1);same(row['after'],ledger,'reset after ledger');pending=None
    elif kind=='STEP_INTENT':same(row['ledger_before'],ledger,'step before ledger')
    elif kind=='STEP_COMPLETE':
        simulation('CONTROL',1,5,True);same(row['ledger_after'],ledger,'step after ledger')
    return ledger,pending


def stream(path,manifest,specs):
    """All bytes decoded and hashed, with bounded per-row storage."""
    digest=hashlib.sha256();count=0;stamp=-1;current=None;blocks=[];last=[];ledger=dict(counts={},by_phase={});pending=None
    from scripts.check_tracked_secrets import find_secret_rule
    from outputs.research_archive.preflight_v1.scan_snapshot import EXTRA
    with gzip.open(path,'rb') as file:
        for line in file:
            digest.update(line);text=line.decode('utf8');io.require(find_secret_rule(text) is None and not any(p.search(text) for p in EXTRA.values()),'decoded credential pattern')
            row=json.loads(line);io.require(row['sequence']==count and row['saved_ns']>stamp,'global stream cursor or time')
            for key in a.IDENTITY:io.require(row[key]==manifest[key],'stream identity')
            owner={k:row[k] for k in a.KEYS}
            if owner!=current:
                io.require(len(blocks)<len(specs) and owner==specs[len(blocks)],'stream allocation order')
                blocks.append(dict(spec=owner,start=count,end=None,first=row['event'],last=None,events={},step_intents=0,step_complete=0,closure=None));current=owner
            block=blocks[-1];block['end']=count;block['last']=row['event'];block['events'][row['event']]=block['events'].get(row['event'],0)+1
            if row['event']=='STEP_INTENT':block['step_intents']+=1
            if row['event']=='STEP_COMPLETE':block['step_complete']+=1
            if row['event']=='CASE_COMPLETE':block['closure']={k:row[k] for k in ('case_record_sha256','total_steps','deadline_loss')}
            ledger,pending=ledger_event(ledger,pending,row)
            last=(last+[dict(sequence=count,event=row['event'],saved_ns=row['saved_ns'])])[-8:]
            count+=1;stamp=row['saved_ns']
    io.require(pending is None,'unclosed reset');return dict(records=count,decoded_sha256=digest.hexdigest(),blocks=blocks,last_events=last,ledger=ledger,credential_scan='ALL_DECODED_JSONL_ROWS')


def case_closure(case,block):
    io.require(block['first']=='CASE_ALLOCATION' and block['last']=='CASE_COMPLETE' and block['events'].get('CASE_ALLOCATION')==1 and block['events'].get('CASE_COMPLETE')==1,'complete case bracket')
    io.require(case['event_start_sequence']==block['start'] and case['event_end_sequence_exclusive']==block['end'],'case interval')
    same(block['closure'],dict(case_record_sha256=io.digest(case),total_steps=case['total_steps'],deadline_loss=case['deadline_loss']),'case closure hash')
    io.require(block['step_intents']==block['step_complete']==case['total_steps']==case['host_attempts']==case['host_returned'],'case control counts')


def failed_boundary(failed,block):
    io.require(block['first']=='CASE_ALLOCATION' and block['events'].get('CASE_COMPLETE',0)==0,'partial case bracket')
    io.require(failed['total_steps']==failed['host_attempts']==failed['host_returned']==block['step_intents']==block['step_complete']==0,'observed partial has no task command')
    io.require(failed['state_witness_refs']==[] and failed['environment_closed'] and failed['error'] is not None,'failed initial witness facts')
    io.require(block['last']=='NOISE_COMMITMENT' and block['events'].get('CONTROLLED_INITIAL')==1,'observed failure boundary')
    return dict(last_saved_event='NOISE_COMMITMENT',next_unsaved_boundary='INITIAL_WITNESS',exact_native_call_known=False,
        original_error=failed['error'],full_native_traceback_available=False,environment_closed_flag=True,task_outcome_available=False)


def diagnose():
    from src.analysis.release_learning_guard_v1 import read_only
    q=io.read(FREEZE/'complete.json');io.require(q['integrity']=='PASSED','frozen failure diagnosis')
    for name,h in {**q['source_sha256'],**q['input_sha256']}.items():io.require(io.sha(a.ROOT/name)==h,'diagnostic source/input changed '+name)
    extension.verify();m=a.checked(extension.TARGET);raw=extension.TARGET.parent/'train';out=OUTPUT;out.mkdir(exist_ok=False)
    start=perf_counter_ns();guard={}
    with read_only(guard):
        summary=io.read(raw/'summary.json');failed=io.read(raw/'failed_execution.json');completion=io.read(raw/'completion.json')
        io.require(summary['status']==completion['status']=='FAILED_PARTIAL','closed incomplete data only')
        io.require(not (extension.TARGET.parent/'learning').exists() and not (raw/'audit.json').exists(),'no training or complete TRAIN qualification')
        for name,h in completion['artifact_sha256'].items():io.require(io.sha(raw/name)==h,'original completion '+name)
        cases=list(io.rows(raw/'cases.jsonl.gz'));specs=a.population('TRAIN');rows=census(specs,cases,failed)
        same(len(cases),summary['executions'],'complete record count')
        events=stream(raw/'events.jsonl.gz',m,specs);private=stream(raw/'witnesses.jsonl.gz',m,specs)
        io.require(len(events['blocks'])==len(cases)+1 and len(private['blocks'])==len(cases),'complete and partial stream blocks')
        for case,block in zip(cases,events['blocks']):case_closure(case,block)
        boundary=failed_boundary(failed,events['blocks'][-1])
        same(events['records'],summary['events'],'event total');same(private['records'],summary['private_records'],'private total')
        same(events['ledger'],summary['lifecycle'],'independent total ledger');same(events['ledger'],failed['ledger_after_close'],'failed final ledger')
        same(sum(c['total_steps'] for c in cases),summary['control_steps'],'complete/partial control charge')
        native=io.read(extension.TARGET.parent/'native/summary.json')
        costs=dict(control_steps=native['control_steps']+summary['control_steps'],all_resets=native['lifecycle']['counts']['reset_attempts']+summary['lifecycle']['counts']['reset_attempts'],
            physical_frames=native['lifecycle']['counts']['simulation_frames_completed']+summary['lifecycle']['counts']['simulation_frames_completed'])
        result=dict(integrity='PASSED_STREAM_CLOSURE_AND_ACCOUNTING_ONLY',source_manifest_id=m['manifest_id'],allocated_TRAIN=len(specs),completed_TRAIN=len(cases),partial_TRAIN=1,not_started_TRAIN=len(specs)-len(cases)-1,
            completed_success=sum(bool(c['success']) for c in cases),completed_task_failure=sum(not c['success'] for c in cases),
            complete_prefix_is_unbalanced_and_descriptive_only=True,full_population_success_rate=None,full_TRAIN_qualification=False,model_training_allowed=False,
            failure_boundary=boundary,source_record_counts=dict(events=events['records'],private=private['records']),
            decoded_source_sha256=dict(events=events['decoded_sha256'],private=private['decoded_sha256']),last_events=events['last_events'],
            TRAIN_ledger=summary['lifecycle'],whole_allocation_actual_cost=costs,resource_observation=io.read(BASE/'resource_observation.json'),
            no_full_policy_PI_actuator_replay_disclosed=True,policy_queries=0,new_environment_interactions=0,new_fits=0,online_LLM_API_calls=0,guard=guard,publication_goal_complete=False)
        io.write(out/'TRAIN_allocation_status.json',rows)
        native_rows=[{**{k:c[k] for k in a.KEYS},'status':'NATIVE_COMPLETE_AND_AUDITED','success':c['success'],'deadline_loss':c['deadline_loss'],'total_steps':c['total_steps']} for c in native['rows']]
        io.write(out/'all_684_status.json',native_rows+rows)
    result['guard']=guard;result['wall_ns']=perf_counter_ns()-start;io.write(out/'complete.json',result)
    for name,h in q['input_sha256'].items():io.require(io.sha(a.ROOT/name)==h,'original inputs changed during diagnosis '+name)
    return result
