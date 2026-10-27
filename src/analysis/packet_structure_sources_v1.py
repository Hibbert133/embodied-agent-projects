"""Immutable closed source, explicit plain-JSONL reader, complete family inventory."""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil
from src.analysis import paired_packet_io_v1 as original
from src.analysis.command_target_sources_v1 import GroupedJournal
from src.analysis.response_action_audit_v1 import same
io=original.io;ROOT=io.ROOT;BASE=ROOT/'outputs/paired_packet_structure';OUTPUT=BASE/'analysis_v1';VALIDATION=BASE/'validation_v1'
SOURCE=ROOT/'outputs/paired_packet_response/development_v1/paired_packet_20261027T101154Z_bb74926c3c07'
CONFIG=ROOT/'configs/autoresearch/packet_structure_diagnosis_v1.json';PROTOCOL=ROOT/'docs/protocols/packet_structure_diagnosis_v1_zh.md'
METHODS=('ZERO','INSTANT','FIR','CENTERED_FIR','FREE_CAUSAL');ROLES=('ZERO','PLUS','MINUS')


def config():return dict(protocol='PACKET_STRUCTURE_DIAGNOSIS_V1',classification='POST_HOC_DESCRIPTIVE_NOT_MODEL_OR_TASK_QUALIFICATION',
    source_run=SOURCE.name,source_executions=864,source_families=288,splits=list(original.SPLITS),horizons=list(range(1,17)),
    models=list(METHODS),source_closed_result_retained=True,source_score_and_masks_unchanged=True,new_model_predictions=0,
    new_environment_creations=0,new_resets=0,new_control_steps=0,new_physical_frames=0,new_model_fits=0,new_policy_queries=0,online_LLM_API_calls=0,
    representation='SAME_ENTRY_LINEAR_IN_WHOLE_KNOWN_COMMAND_PACKET',metric='SQUARED_PAIR_XY_ERROR_M2_DISTINCT_FROM_ORIGINAL_CAPPED_RMSE',
    complete_three_role_observations_required=True,missing='NULL_WITH_ORIGINAL_REASON_NO_ZERO_IMPUTATION',
    source_native_and_true_noise_evaluator_only=True,noise_regeneration='DETERMINISTIC_SOURCE_TAPE_NOT_NEW_INDEPENDENT_SAMPLE',
    numerical_audit=dict(vector_atol_m=2e-15,scalar_atol_m2=2e-18,relative_tolerance=2e-11),
    aggregation='FAMILY_H_OR_FIXED4_STEP_BAND_THEN_EQUAL_FAMILY_WITHIN_GROUP_THEN_EQUAL_GROUP_NO_SPLIT_POOL',
    new_bootstrap_replicates=0,new_collection_unlocked=False,publication_goal_complete=False)


def inputs():
    original.checked(SOURCE/'manifest.json');result={}
    def add(p):result[p.relative_to(ROOT).as_posix()]=io.sha(p)
    add(SOURCE/'manifest.json');add(SOURCE/'pipeline_control/completion.json')
    io.require(io.read(SOURCE/'pipeline_control/completion.json')['qualification_status']=='CLOSED_NEGATIVE','closed source retained')
    for split in original.SPLITS:
        folder=SOURCE/split.lower();audit=io.read(folder/'audit.json');done=io.read(folder/'completion.json')
        io.require(audit['integrity']=='PASSED' and audit['artifact_sha256']==done['artifact_sha256'],'audited complete original source')
        for name,h in done['artifact_sha256'].items():io.require(io.sha(folder/name)==h,'unchanged source '+name);add(folder/name)
        for n in ('audit.json','completion.json','trajectory_audit.json'):add(folder/n)
    for split in ('cal','qual'):
        folder=SOURCE/(split+'_evaluation');r=io.read(folder/'result.json');audit=io.read(folder/'audit.json');io.require(audit['integrity']=='PASSED' and audit['result_sha256']==io.sha(folder/'result.json'),'original result audit')
        for n,h in r['artifact_sha256'].items():io.require(io.sha(folder/n)==h,'original score table unchanged');add(folder/n)
        for n in ('result.json','audit.json'):add(folder/n)
    for n in ('training/models.json','training/audit.json','training/training_receipt.json','model_lock.json','presentation/costs.json','presentation/research_decision.json'):add(SOURCE/n)
    add(ROOT/'reports/paired_packet_response_v1_zh.md');add(ROOT/'outputs/paired_packet_response/result_validation_v1/complete.json')
    return result


def plain_rows(path):
    with Path(path).open(encoding='utf8') as f:
        for line in f:
            io.require(bool(line.strip()),'no blank diagnostic rows');yield json.loads(line)


def checked(path):
    path=Path(path).resolve();m=io.read(path);body=dict(m);mid=body.pop('manifest_id')
    io.require(path.parent.parent==OUTPUT and mid==io.digest(body) and m['config']==config() and io.read(CONFIG)==config(),'owned frozen diagnosis')
    for n,h in {**m['analysis_source_sha256'],**m['input_sha256']}.items():io.require(io.sha(ROOT/n)==h,'unchanged diagnosis/source '+n)
    return m


def prepare(sources):
    qa=io.read(VALIDATION/'complete.json');io.require(qa['integrity']=='PASSED' and not io.git('status','--porcelain','--untracked-files=no'),'committed checked freeze')
    io.require(not list(OUTPUT.glob('*/manifest.json')) and shutil.disk_usage(ROOT).free>=512*1024**2,'one diagnostic run and storage reserve')
    tracked=set(io.git('ls-files').splitlines())
    for n,h in qa['source_sha256'].items():io.require(io.sha(ROOT/n)==h and n in tracked,'committed source '+n)
    head=io.git('rev-parse','HEAD');m=dict(experiment_run_id='packet_structure_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+head[:12],analysis_git_commit=head,
        analysis_source_sha256={n:io.sha(ROOT/n) for n in sources},input_sha256=inputs(),config=config(),classification='POST_HOC_DESCRIPTIVE',publication_goal_complete=False)
    m['manifest_id']=io.digest(m);out=OUTPUT/m['experiment_run_id'];out.mkdir(parents=True,exist_ok=False);io.write(out/'manifest.json',m);return out/'manifest.json'


def source_families():
    identity={k:io.read(SOURCE/'manifest.json')[k] for k in original.IDENTITY};serial=0
    for split in original.SPLITS:
        folder=SOURCE/split.lower();events=GroupedJournal(io.rows(folder/'events.jsonl.gz'),original.KEYS,identity);native=GroupedJournal(io.rows(folder/'private_targets.jsonl.gz'),original.KEYS,identity)
        cases=iter(io.rows(folder/'cases.jsonl.gz'));exports=iter(io.rows(folder/'public_trajectories.jsonl.gz'));specs=original.population(split)
        for i in range(0,len(specs),3):
            trio=[]
            for spec in specs[i:i+3]:
                c=next(cases);same({k:c[k] for k in original.KEYS},spec);e=events.take_case(c);p=native.take_case(c);x=next(exports)
                same(e[-1]['event'],'CASE_COMPLETE');same(e[-1]['case_record_sha256'],io.digest(c));same(c['public_trajectory_sha256'],io.digest(x));same(x['initial'],c['initial'])
                physical=[v for v in e if v['event']=='STEP_COMPLETE'];same(len(physical),c['total_steps']);same(len(x['steps']),len(physical))
                for j,(step,public) in enumerate(zip(physical,x['steps'])):
                    same(step['logical_step'],j);same(public,dict(at_calls=j,before=c['initial'] if j==0 else physical[j-1]['after'],command=step['command'],after=step['after']))
                before={v['at_calls']:v for v in p if v['label']=='BEFORE_STEP'};after={v['at_calls']:v for v in p if v['label']=='AFTER_STEP'}
                packet=[v for v in physical if v['phase']=='EXOGENOUS_PACKET'];same(len(packet),c['packet_steps'])
                entry=c['entry_at_calls']
                if entry is not None:same([v['logical_step'] for v in packet],list(range(entry,entry+len(packet))))
                trio.append(dict(case=c,physical=physical,packet=packet,before=before,after=after,export=x))
            base=trio[0]['case'];same([t['case']['packet_kind'] for t in trio],list(ROLES))
            for other in trio[1:]:
                c=other['case'];same(c['initial'],base['initial']);same(c['entry_at_calls'],base['entry_at_calls']);same(c['entry_witness_oracle'],base['entry_witness_oracle'])
                n=len(trio[0]['physical']) if base['entry_at_calls'] is None else base['entry_at_calls'];same(n,len(other['physical']) if c['entry_at_calls'] is None else c['entry_at_calls'])
                for left,right in zip(trio[0]['physical'][:n],other['physical'][:n]):
                    for key in ('command','raw_policy','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(left[key],right[key],'common real prefix')
                if base['forecast_record'] is not None:
                    fields=('query','query_sha256','model_sha256','forecasts','forecast_error','scope')
                    same({k:c['forecast_record'][k] for k in fields},{k:base['forecast_record'][k] for k in fields},'same before-outcome saved forecast')
            yield serial,trio;serial+=1
        events.finish();native.finish();io.require(next(cases,None) is next(exports,None) is None,'entire source split')
    same(serial,288)
