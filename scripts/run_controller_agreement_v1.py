"""One-shot TRAIN-only descriptive instrument, guarded against physics and fits."""
from pathlib import Path
from itertools import groupby
from collections import Counter
from contextlib import ExitStack
from unittest.mock import patch
from time import perf_counter_ns
import gzip, json, sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io
from src.analysis import controller_agreement_v1 as main
from src.analysis import controller_agreement_independent_v1 as independent
from src.analysis.release_learning_guard_v1 import read_only

SOURCE=ROOT/'outputs/correction_scope/development_v1/correction_scope_20261026T042133Z_d74cba1945e2'
BASE=ROOT/'outputs/controller_agreement'
CONFIG=ROOT/'configs/movement_task/controller_agreement_v1.json'
PROTOCOL=ROOT/'docs/protocols/controller_agreement_v1_zh.md'
OWN=('src/analysis/controller_agreement_v1.py','src/analysis/controller_agreement_independent_v1.py',
    'tests/test_controller_agreement_v1.py','scripts/run_controller_agreement_v1.py','scripts/validate_controller_agreement_freeze_v1.py')
DOCS=('docs/protocols/controller_agreement_v1_zh.md','docs/research/controller_agreement_decision_v1_zh.md','configs/movement_task/controller_agreement_v1.json')


def source_contract():
    audit=io.read(SOURCE/'train/audit.json')
    io.require(audit['integrity']=='PASSED' and audit['executions']==648 and audit['cohort']=='TRAIN','complete audited TRAIN')
    paths=[SOURCE/'manifest.json',SOURCE/'train/audit.json',SOURCE/'train/completion.json']
    paths += [SOURCE/'train'/name for name in audit['collection_sha256']]
    for name,h in audit['collection_sha256'].items():io.require(io.sha(SOURCE/'train'/name)==h,'audited source changed '+name)
    return dict(source_run=SOURCE.relative_to(ROOT).as_posix(),source_manifest_id=audit['manifest_id'],
        source_sha256={p.relative_to(ROOT).as_posix():io.sha(p) for p in paths},source_split='TRAIN',
        historical_cost=dict(executions=648,control_steps=77563,all_resets=33048,physical_frames=16911815))


def config():
    return dict(protocol='CONTROLLER_AGREEMENT_FEASIBILITY_V1',classification='POST_HOC_DESCRIPTIVE_TRAIN_ONLY',
        source=source_contract(),source_cases=648,ordered_pairs=1944,self_replays=648,independent_groups=9,
        receiver_rates=[.125,.5,2.,8.],exact_float32_send_equality=True,stop_before_first_different_response=True,
        thresholds_for_descriptive_columns_only=[1,8],new_environment_creations=0,new_resets=0,new_control_steps=0,new_physical_frames=0,
        new_policy_queries=0,new_model_fits=0,online_LLM_API_calls=0,main_command_cap=2000000,independent_command_cap=2000000,
        new_seed_allocations=0,CAL_TEST_content_used=False,acquisition_rule_developed=False)


def outcome(case):
    return {k:case[k] for k in ('deadline_loss','success','terminated','truncated','total_steps')}


def extract(events, case):
    entry=None;tail=[];pending=None
    for e in events:
        if e['event']=='AGENT_EVENT':
            p=e['public_payload']
            if e['agent_event']=='RATE_COMMIT':
                io.require(entry is None,'single saved rate entry');entry=p['memory']
            if e['agent_event']=='COMMAND' and p['phase']=='TAIL_TASK':
                io.require(entry is not None and pending is None,'actual tail after entry')
                pending={k:p[k] for k in ('at_calls','before','command','raw_policy')}
        elif e['event']=='STEP_COMPLETE' and pending is not None:
            io.require(e['logical_step']==pending['at_calls'] and e['command']==pending['command'],'tail request receipt pairing')
            tail.append({**pending,'after':e['after']});pending=None
    io.require(pending is None and (entry is not None or not tail),'complete saved tail')
    witness=None
    if entry is not None:
        candidates=[r for r in case['state_witness_refs'] if r['label']=='POST_ACQUISITION']
        io.require(len(candidates)==1,'one saved common return witness')
        w=candidates[0];witness={k:w[k] for k in ('logical_step','native_sha256','comparison_python_sha256')}
    return dict(entry=entry,rows=tail,entry_witness=witness,outcome=outcome(case))


def execute():
    start=perf_counter_ns();validation=io.read(BASE/'freeze_validation_v1/complete.json')
    io.require(validation['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'clean tested freeze')
    for n,h in validation['source_sha256'].items():io.require(io.sha(ROOT/n)==h and io.git('ls-files','--error-unmatch',n)==n,'committed frozen source '+n)
    io.require(io.read(CONFIG)==config(),'immutable exact TRAIN-only contract')
    out=BASE/'feasibility_v1';out.mkdir(parents=True,exist_ok=False)
    manifest=dict(protocol='CONTROLLER_AGREEMENT_FEASIBILITY_V1',classification='POST_HOC_DESCRIPTIVE_TRAIN_ONLY',
        source_git_commit=io.git('rev-parse','HEAD'),config=io.read(CONFIG),source_sha256=validation['source_sha256'],started_ns=start)
    manifest['manifest_id']=io.digest(manifest);io.write(out/'manifest.json',manifest)
    guard={};counts=Counter();pairs=[];self_checks=0;pair_audits=0;case_count=0
    def counted(obj,name,label):
        fn=getattr(obj,name)
        def call(*args,**kw):
            counts[label]+=1;io.require(counts[label]<=2000000,'array operation cap '+label);return fn(*args,**kw)
        return patch.object(obj,name,call)
    def output_line(stream,value):stream.write(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n')
    keys=('cohort','group','task','seed','context','planned_boundary','acquisition_action','time_constant_s')
    def casekey(row):return tuple(row[k] for k in keys)
    def blockkey(row):return tuple(row[k] for k in keys[:-1])
    try:
        with read_only(guard),ExitStack() as stack,gzip.open(out/'pairs.jsonl.gz','xt',encoding='utf8') as pf,gzip.open(out/'shadow_steps.jsonl.gz','xt',encoding='utf8') as tf,gzip.open(out/'independent_audit_rows.jsonl.gz','xt',encoding='utf8') as af:
            stack.enter_context(counted(main.TaskMemoryMachine,'plan','main_command_computations'))
            stack.enter_context(counted(independent,'command','independent_command_computations'))
            # No CAL/TEST path or training loader is opened by this entry.
            events=iter(groupby(io.rows(SOURCE/'train/events.jsonl.gz'),casekey))
            specs=io.read(SOURCE/'manifest.json')['config']['populations']['TRAIN']
            cases=list(io.rows(SOURCE/'train/cases.jsonl.gz'))
            io.require(len(cases)==len(specs)==648,'all allocated TRAIN cases')
            for _,case_group in groupby(cases,blockkey):
                block=[]
                for case in case_group:
                    spec=specs[case_count];case_count+=1
                    io.require(casekey(case)==casekey(spec),'fixed case order')
                    key,it=next(events);io.require(key==casekey(case),'fixed event order')
                    value=extract(it,case);block.append((spec,value))
                    if value['entry'] is not None:
                        self_result=main.replay(value['entry'],value['rows'],spec['time_constant_s'])
                        literal=independent.reconstruct(value['entry'],value['rows'],spec['time_constant_s'])
                        io.require(self_result==literal and self_result['status']=='MATCHED_TO_TERMINAL','whole factual self-controller replay')
                        self_checks+=1
                io.require([s['time_constant_s'] for s,v in block]==list(main.RATES),'all four factual rates retained')
                for spec,source in block:
                    for target_spec,target in block:
                        if target_spec['time_constant_s']==spec['time_constant_s']:continue
                        identifier={**spec,'receiver_rate':target_spec['time_constant_s']}
                        if source['entry'] is None:
                            row={**identifier,'missing_reason':'NO_RATE_ENTRY_EARLY_END','status':None,'matched_steps':None,'loss_delta_interval':None}
                            check=independent.paired_check(source,target,None)
                        else:
                            p=main.replay(source['entry'],source['rows'],target_spec['time_constant_s'])
                            q=independent.reconstruct(source['entry'],source['rows'],target_spec['time_constant_s'])
                            io.require(p==q,'all literal shadow-prefix fields')
                            check=independent.paired_check(source,target,q)
                            interval=main.loss_interval(p,source['entry']['completed_steps'],source['outcome']['deadline_loss'])
                            io.require(interval==check['independently_rebuilt_interval'],'independent causal loss interval')
                            row={**identifier,'missing_reason':None,'status':p['status'],'matched_steps':p['matched_steps'],
                                'first_disagreement_at_calls':p['first_disagreement_at_calls'],'entry_step':source['entry']['completed_steps'],
                                'loss_delta_interval':interval,'source_outcome':source['outcome'],'target_outcome_evaluator_only':target['outcome']}
                            for record in p['trace']:output_line(tf,{**identifier,**record})
                        pairs.append(row);output_line(pf,row);output_line(af,{**identifier,**check});pair_audits+=1
                if case_count%72==0:print(dict(processed_TRAIN_cases=case_count,ordered_pairs=len(pairs)),flush=True)
            io.require(next(events,None) is None and case_count==648 and len(pairs)==pair_audits==1944,'complete source and pair census')
        panels=[]
        for task in ('push-v3','reach-v3','door-open-v3'):
            for context in ('UNCHANGED','CHANGED'):
                for boundary in (16,32,64):
                    for action in ('CONTINUE','VALIDATE8','MOVE_MEASURE'):
                        selected=[r for r in pairs if (r['task'],r['context'],r['planned_boundary'],r['acquisition_action'])==(task,context,boundary,action)]
                        panels.append(dict(task=task,context=context,planned_boundary=boundary,acquisition_action=action,summary=main.aggregate(selected)))
        rates=[]
        for source in main.RATES:
            for receiver in main.RATES:
                if source!=receiver:rates.append(dict(source_rate=source,receiver_rate=receiver,summary=main.aggregate([r for r in pairs if r['time_constant_s']==source and r['receiver_rate']==receiver])))
        summary=dict(classification='POST_HOC_DESCRIPTIVE_TRAIN_ONLY',all=main.aggregate(pairs),panels=panels,rate_pairs=rates,
            status_counts=dict(Counter(r['status'] or r['missing_reason'] for r in pairs)),self_live_replays=self_checks,
            command_computations=dict(counts),guard=guard,wall_ns=perf_counter_ns()-start,
            unqualified_for_acquisition_timing=True,novelty_established=False,new_physics=0,new_fits=0,new_policy_queries=0,online_LLM_API_calls=0)
        io.write(out/'summary.json',summary)
        for n,h in manifest['config']['source']['source_sha256'].items():io.require(io.sha(ROOT/n)==h,'historical source unchanged after analysis '+n)
        io.write(out/'complete.json',dict(integrity='PASSED',classification='POST_HOC_DESCRIPTIVE_TRAIN_ONLY',manifest_id=manifest['manifest_id'],
            source_cases=case_count,ordered_pair_checks=pair_audits,guard=guard,command_computations=dict(counts),wall_ns=perf_counter_ns()-start,
            artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},publication_goal_complete=False))
        print(dict(integrity='PASSED',source_cases=case_count,ordered_pairs=pair_audits,status_counts=summary['status_counts']),flush=True)
    except BaseException as e:
        io.write(out/'failure.json',dict(type=type(e).__name__,message=str(e),processed_cases=case_count,pairs=len(pairs),guard=guard,counts=dict(counts),wall_ns=perf_counter_ns()-start))
        raise


if __name__=='__main__':execute()
