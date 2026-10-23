"""Frozen source behavior plus evaluator-only fresh-future program comparisons."""
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scripts import run_strong_chronological_reference_v1 as io
from scripts import run_state_capsule_qualification_v2 as qualified
from src.analysis.capsule_record_json_v2 import normalize,JsonJournal
from src.analysis.paired_probe_host_v1 import ProbeSession,physical_comparison
from src.probe.probe_effect_program_v1 import PROGRAMS
from src.probe.cache_acquisition_evidence_v1 import CacheAcquisitionEvidenceV1,digest
from src.probe.chronological_cache_reference import BLOCK8,accepted_cache,check_choice
from src.probe.cold_start_response import ColdPrefix
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout.chronological_faults import FAMILIES,SCHEDULES,TASKS,states,blend,fraction
from src.rollout.task_registry import create_task_environment,create_task_policy

CONFIG=ROOT/'configs/paired_probe_effects/development_v1.json'
PROTOCOL='docs/protocols/paired_probe_effects_development_v1.md'


def population(phase):
    if phase=='SMOKE':
        a={'matrix_xy':np.eye(2).tolist(),'bias_xy':[.12,-.08],'deadzone_xy':[0.,0.]}
        b={**a,'bias_xy':[-.14,.1]}
        return [{'stream':0,'family_oracle':'BIAS','schedule_oracle':'SMOKE_ABRUPT','cases':[
            {'episode':i,'task':TASKS[(i+1)%3],'seed':20000+i,'fault_oracle':a if i<5 else b} for i in range(9)]}]
    if phase!='MAIN':raise ValueError('registered phase required')
    result=[]
    for replicate in range(4):
        for fi,family in enumerate(FAMILIES):
            for si,schedule in enumerate(SCHEDULES):
                stream=len(result);a,b=states(66001+stream,family)
                result.append({'stream':stream,'family_oracle':family,'schedule_oracle':schedule,'generation_seed_oracle':66001+stream,
                    'cases':[{'episode':i,'task':TASKS[(i+replicate+fi+si)%3],'seed':19200+12*stream+i,
                              'fault_oracle':blend(a,b,fraction(schedule,i))} for i in range(12)]})
    return result


def validate(c):
    if (c['protocol_id']!='paired_probe_effects_development_v1' or tuple(c['programs'])!=PROGRAMS or tuple(c['tasks'])!=TASKS or
        c['source_behavior']!='UNCERTAINTY4_STRICT' or c['source_noise_namespace']!=47001 or c['fresh_future_namespace']!=65001 or
        c['noise_std']!=.05 or c['logical_total_steps']!=500 or c['bootstrap_samples']!=10000 or c['bootstrap_seed']!=20261021 or
        any(c[k]!=0 for k in ('new_api_calls','nominal_model_fits','selector_fits','policy_updates'))):raise ValueError('frozen scope changed')
    expected={'SMOKE':(1,9,20000,20008,[20009,20199],2,50000,9,600000,1),
              'MAIN':(36,432,19200,19631,[19632,19999],8,7200000,432,48000000,0)}
    for phase,want in expected.items():
        q=c[phase.lower()];keys=('streams','units','seed_start','seed_end','reserved','fresh_futures','maximum_environment_steps','maximum_controlled_resets','maximum_simulation_frames','sentinel_replays')
        if tuple(q[k] for k in keys)!=want:raise ValueError('frozen population/resources changed')


def sources(c):
    source,_,model=io.load(ROOT/c['strong_source_manifest'])
    q=qualified.load(ROOT/c['restore_qualification_manifest']);a=io.read(ROOT/c['restore_qualification_audit'])
    summary=ROOT/c['restore_qualification_manifest'];summary=summary.parent/'collection/summary.json'
    if a['integrity']!='PASSED' or a['manifest_id']!=q['manifest_id'] or a['summary_sha256']!=io.sha(summary) or a['registered_restore_contract_passed'] is not True:
        raise ValueError('complete registered restore qualification required')
    return source,q,model


def prepare():
    io.clean();c=io.read(CONFIG);validate(c);source,q,_=sources(c);out=ROOT/c['output_root']
    if list(out.glob('*/manifest.json')):raise FileExistsError('one-shot experiment already prepared')
    names=set(q['input_sha256'])|set(io.git('ls-files','src','scripts','tests').splitlines())|{
        CONFIG.relative_to(ROOT).as_posix(),PROTOCOL,'docs/research/paired_probe_effects_design_v1.md','outputs/paired_probe_effects/.gitattributes',
        c['restore_qualification_audit'],c['restore_qualification_manifest'],c['strong_source_manifest']}
    commit=io.git('rev-parse','HEAD');run_id='paired_probe_effects_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+commit[:12]
    m={'experiment_run_id':run_id,'source_git_commit':commit,'config':c,'strong_source_manifest_id':source['manifest_id'],
       'restore_qualification_manifest_id':q['manifest_id'],'population_oracle':{phase:population(phase) for phase in ('SMOKE','MAIN')},
       'input_sha256':{n:io.sha(ROOT/n) for n in sorted(names)},'library_source_sha256':q['library_source_sha256'],
       'native_library_sha256':q['native_library_sha256'],'policy_sha256':q['policy_sha256']}
    m['manifest_id']=digest(m);folder=out/run_id;folder.mkdir(parents=True);io.write(folder/'manifest.json',m,exclusive=True)
    print((folder/'manifest.json').relative_to(ROOT),flush=True)


def load(path):
    m=io.read(path);validate(m['config'])
    if digest({k:v for k,v in m.items() if k!='manifest_id'})!=m['manifest_id'] or any(io.sha(ROOT/n)!=h for n,h in m['input_sha256'].items()):raise ValueError('frozen inputs changed')
    source,q,model=sources(m['config'])
    if source['manifest_id']!=m['strong_source_manifest_id'] or q['manifest_id']!=m['restore_qualification_manifest_id'] or any(m['population_oracle'][p]!=population(p) for p in ('SMOKE','MAIN')):
        raise ValueError('qualified source/population changed')
    return m,model


def cache_view(cache):return None if cache is None else normalize(asdict(cache))


def commit_source(cache,record,result,model,episode,task):
    error=None;outcome=record['outcome']
    if not outcome['success']:return None,error
    if result['fit'] is not None and outcome['applied_new_controller']:
        try:cache=accepted_cache(result['fit'],result['fit_prefix'],task,episode,success=True,joint_model=model)
        except (ValueError,np.linalg.LinAlgError) as exc:cache=None;error=str(exc)
    return cache,error


def require_smoke_ready(path,m):
    a=io.read(path.parent/'smoke_audit.json');n=io.read(path.parent/'smoke_statistics_audit.json')
    p=io.read(path.parent/'smoke_pipeline_completion.json');r=io.read(path.parent/'smoke_analysis_v1/report_receipt.json')
    if (any(v[k]!=m[k] for v in (a,n,p,r) for k in io.IDENTITY) or
        a['integrity']!='PASSED' or a['required_host_coverage'] is not True or
        a['summary_sha256']!=io.sha(path.parent/'smoke/summary.json') or a['events_sha256']!=io.sha(path.parent/'smoke/events.jsonl.gz') or
        n['integrity']!='PASSED' or n['summary_sha256']!=a['summary_sha256'] or
        n['statistics_sha256']!=io.sha(path.parent/'smoke_analysis_v1/statistics.json') or
        p['status']!='COMPLETED_FOR_REVIEW' or p['failure'] is not None or len(p['steps'])!=6 or any(v['returncode']!=0 for v in p['steps']) or
        r['report_path']!='reports/paired_probe_effects_smoke_v1.md' or r['report_sha256']!=io.sha(ROOT/r['report_path']) or
        r['statistics_sha256']!=n['statistics_sha256'] or r['record_audit_sha256']!=io.sha(path.parent/'smoke_audit.json') or
        r['numeric_audit_sha256']!=io.sha(path.parent/'smoke_statistics_audit.json')):
        raise ValueError('complete smoke record/numeric audits, report and pipeline required')


def run(path,phase):
    io.clean();m,model=load(path);c=m['config'];limits=c[phase.lower()]
    if io.git('rev-parse','HEAD')!=m['source_git_commit']:raise ValueError('freeze commit differs')
    if phase=='MAIN':require_smoke_ready(path,m)
    folder=path.parent/phase.lower();folder.mkdir();identity={k:m[k] for k in io.IDENTITY}
    collection_started=perf_counter_ns()
    budget={'completed':0,'maximum':limits['maximum_environment_steps']};records=[];counters={'captures':0,'restores':0,'policy_queries':0,'capture_ns':0,'restore_ns':0,'fits':0,'nfev':0};sentinel_left=limits['sentinel_replays'];failure=None
    model_hash=digest(normalize(model))
    with gzip.open(folder/'events.jsonl.gz','xt',encoding='utf-8') as events:
        writer=JsonJournal(events,identity)
        current_key={'phase':phase}
        def emit(event,payload):return writer.emit(event,{**current_key,**payload})
        ledger=LifecycleLedger(emit,limits['maximum_simulation_frames'])
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                for stream in m['population_oracle'][phase]:
                    cache=None
                    with gzip.open(folder/('cases_'+str(stream['stream']).zfill(2)+'.jsonl.gz'),'xt',encoding='utf-8') as case_file:
                        for spec in stream['cases']:
                            current_key={**identity,'phase':phase,'stream':stream['stream'],'episode':spec['episode'],'task':spec['task'],'seed':spec['seed']}
                            # Identity belongs to writer only, not caller payload.
                            current_key={k:v for k,v in current_key.items() if k not in identity}
                            row={**identity,**current_key,'family_oracle':stream['family_oracle'],'schedule_oracle':stream['schedule_oracle'],
                                'cache_before':cache_view(cache),'evaluations':[],'sentinels':[],'source':None,'evidence':None,'references':None};records.append(row)
                            env=None;session=None;case_write_attempted=False
                            try:
                                task_model=model[spec['task']]
                                emit('FACTORY_INTENT',{'ledger':ledger.snapshot()})
                                with ledger.scope('FACTORY_SETUP'):env=create_task_environment(spec['task'],spec['seed'])
                                emit('FACTORY_COMPLETE',{'ledger':ledger.snapshot()})
                                with ledger.scope('CONTROLLED_RESET'):initial,_=env.reset(seed=spec['seed'])
                                session=ProbeSession(env,create_task_policy(spec['task']),initial,spec['task'],spec['seed'],spec['fault_oracle'],emit,ledger,budget)
                                if cache is None:
                                    row['disposition']='COLD_SOURCE'
                                    source,result=session.execute('COLD8',task_model,role='SOURCE',future=0)
                                else:
                                    session.prefix4(BLOCK8[:4])
                                    if not session.alive():
                                        row['disposition']='WARM_PREFIX_ENDED';current=session.public()
                                        outcome={'success':current.success,'stopped':False,'total_steps':session.ctx['calls'],'suffix_steps':0,
                                            'deadline_loss':session.ctx['calls'] if current.success else 500,'fixed_probe_suffix_steps':0,'policy_suffix_steps':0,
                                            'online_parameter_fits':0,'optimizer_nfev':0,'policy_queries':0,'applied_new_controller':False}
                                        source={'role':'SOURCE','future':0,'program':'PREFIX_ENDED','outcome':outcome,'fit':None,'fit_prefix':None};result={'fit':None,'fit_prefix':None}
                                    else:
                                        row['disposition']='WARM_ELIGIBLE';ctx=session.ctx
                                        prefix=ColdPrefix(spec['task'],tuple(ctx['initial_observation']),tuple(map(tuple,ctx['commands'])),tuple(map(tuple,ctx['observations'])),True)
                                        raw=session.policy_query(ctx['observation'])
                                        e=CacheAcquisitionEvidenceV1(prefix,cache.parameters,cache.belief.covariance,cache.source_task,spec['episode']-cache.source_episode,
                                            bool(cache.belief.active_parameter_bound),tuple(raw),496)
                                        row['evidence']=e.to_dict();row['evidence_sha256']=e.evidence_sha256;references={}
                                        for method in ('UNCERTAINTY4','TASK_IVR4'):
                                            try:references[method]=normalize(check_choice(method,task_model,prefix,cache,0.,raw))
                                            except (ValueError,np.linalg.LinAlgError) as exc:references[method]={'action':'STOP_PUBLIC_CHECK','reason':str(exc)}
                                        row['references']=references;choice=emit('SOURCE_CHECK_CHOICE',{'evidence':row['evidence'],'evidence_sha256':e.evidence_sha256,'references':references})
                                        row['source_choice_sequence']=choice['sequence'];before=session.snapshot('FOUR_STEP_SOURCE_BOUNDARY')
                                        action=references['UNCERTAINTY4']['action']
                                        if action=='STOP_PUBLIC_CHECK':
                                            outcome={'success':False,'stopped':True,'total_steps':4,'suffix_steps':0,'deadline_loss':500,'fixed_probe_suffix_steps':0,
                                                'policy_suffix_steps':0,'online_parameter_fits':0,'optimizer_nfev':0,'policy_queries':0,'applied_new_controller':False}
                                            source={'role':'SOURCE','future':0,'program':'STOP_PUBLIC_CHECK','outcome':outcome,'fit':None,'fit_prefix':None};result={'fit':None,'fit_prefix':None}
                                        else:source,result=session.execute('PROBE_UPDATE' if action=='REFRESH8' else 'REUSE_OLD',task_model,e,role='SOURCE',future=0)
                                cache,error=commit_source(cache,source,result,task_model,spec['episode'],spec['task']);row['source']=source;row['cache_after']=cache_view(cache);row['cache_write_error']=error
                                event=emit('SOURCE_CACHE_AFTER_ACTUAL_OUTCOME',{'source':source,'cache_before':row['cache_before'],'cache_after':row['cache_after'],'cache_write_error':error})
                                row['source_cache_sequence']=event['sequence']
                                if row['disposition']=='WARM_ELIGIBLE':
                                    after=session.snapshot('ACTUAL_SOURCE_AFTER_OUTCOME')
                                    for future in range(1,limits['fresh_futures']+1):
                                        outputs={};physical={}
                                        for program in PROGRAMS:
                                            session.recover(before,'EVALUATOR_FORK');session.replace_future(future)
                                            summary,extra=session.execute(program,task_model,e,role='EVAL',future=future)
                                            row['evaluations'].append(summary);outputs[program]=summary;physical[program]=[physical_comparison(v) for v in session.last_rows]
                                            if sentinel_left and future==1 and program=='REUSE_OLD':
                                                expected=physical[program];session.recover(before,'SENTINEL');session.replace_future(future)
                                                sentinel,_=session.execute(program,task_model,e,role='SENTINEL',future=future);row['sentinels'].append(sentinel)
                                                if expected!=[physical_comparison(v) for v in session.last_rows]:raise ValueError('full continuation sentinel differs')
                                                sentinel_left-=1
                                        p,u,k=(outputs[x] for x in ('PROBE_KEEP','PROBE_UPDATE','PROBE_UPDATE_KEEP'))
                                        for program in ('PROBE_UPDATE','PROBE_UPDATE_KEEP'):
                                            left=[v for v in physical['PROBE_KEEP'] if v['logical_step']<8];right=[v for v in physical[program] if v['logical_step']<8]
                                            if left!=right or p['boundary8']!=outputs[program]['boundary8']:raise ValueError('shared probe prefix differs')
                                        if u['fit']!=k['fit']:raise ValueError('same data produced a different numerical fit')
                                        if u['fit'] is None or u['fit']['valid']:
                                            if physical['PROBE_UPDATE']!=physical['PROBE_UPDATE_KEEP']:raise ValueError('valid strict/fallback trajectories differ')
                                        elif physical['PROBE_KEEP']!=physical['PROBE_UPDATE_KEEP']:raise ValueError('invalid fallback did not keep old controller')
                                    session.recover(after,'RETURN_TO_ACTUAL_SOURCE')
                                    returned=emit('SOURCE_STATE_RETURNED',{'cache_after_sha256':digest(row['cache_after']),'logical_step':session.ctx['calls'],**session.witness()})
                                    row['source_return_sequence']=returned['sequence']
                                if digest(normalize(model))!=model_hash:raise ValueError('frozen nominal model mutated')
                                row['case_actual']={'completed_steps':session.completed,'attempted_steps':session.attempts,'policy_queries':session.policy_queries,
                                    'captures':session.captures,'restores':session.restores,'capture_ns':session.capture_ns,'restore_ns':session.restore_ns}
                                for key in counters:
                                    if key in row['case_actual']:counters[key]+=row['case_actual'][key]
                                all_programs=[source,*row['evaluations'],*row['sentinels']]
                                counters['fits']+=sum(p['outcome']['online_parameter_fits'] for p in all_programs);counters['nfev']+=sum(p['outcome']['optimizer_nfev'] for p in all_programs)
                                # Never append the same case again after a write/flush or
                                # later status-file failure. A failed run is not promoted;
                                # summary.json retains any later error/partial counters.
                                case_write_attempted=True
                                case_file.write(json.dumps(normalize(row),ensure_ascii=False,allow_nan=False)+'\n');case_file.flush()
                                emit('SOURCE_CASE_COMPLETE',{'disposition':row['disposition'],'ledger':ledger.snapshot(),'completed_source_units':len(records)})
                                io.write(folder/'status.json',{**identity,'phase':phase,'status':'RUNNING','source_units':len(records),'controlled_steps':budget['completed'],'lifecycle':ledger.snapshot()})
                                print(phase,'stream',stream['stream'],'episode',spec['episode'],'source units',len(records),'steps',budget['completed'],flush=True)
                            except BaseException as exc:
                                row['error']={'type':type(exc).__name__,'reason':str(exc)}
                                if session is not None:
                                    row['partial_actual']={'completed_steps':session.completed,'attempted_steps':session.attempts,'logical_step':session.ctx['calls'],
                                        'policy_queries':session.policy_queries,'captures':session.captures,'restores':session.restores,
                                        'capture_ns':session.capture_ns,'restore_ns':session.restore_ns}
                                row['case_write_attempted_before_failure']=case_write_attempted
                                if not case_write_attempted:
                                    case_file.write(json.dumps(normalize(row),ensure_ascii=False,allow_nan=False)+'\n');case_file.flush()
                                raise
                            finally:
                                if env is not None:env.close()
        except BaseException as exc:
            failure={'type':type(exc).__name__,'reason':str(exc)};emit('STUDY_FAILED',failure)
        status='COLLECTED_FOR_INDEPENDENT_AUDIT' if failure is None else 'FAILED_SAVED_NOT_RETRIED'
        summary={**identity,'phase':phase,'status':status,'source_units':len(records),'cases':records,'controlled_steps':budget['completed'],
            'controlled_resets':ledger.by_phase.get('CONTROLLED_RESET',{}).get('reset_completed',0),'lifecycle':ledger.snapshot(),
            'counters':counters,'computation_counters_complete':failure is None,
            'counter_scope':'Cases with case_actual. On failure, partial_actual may overlap; incomplete optimizer computation is unknown, not zero.',
            'sentinels_completed':limits['sentinel_replays']-sentinel_left,'failure':failure,'new_api_calls':0,
            'collection_body_wall_ns':perf_counter_ns()-collection_started,
            'universal_complete_hidden_state_qualification':False,'registered_restore_source_used':True}
        io.write(folder/'summary.json',summary,exclusive=True);io.write(folder/'status.json',{k:v for k,v in summary.items() if k!='cases'})
    io.write(folder/'completion.json',{**identity,'phase':phase,'status':status,'artifact_sha256':{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}},exclusive=True)
    print(status,flush=True)
    if failure:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['prepare','run']);parser.add_argument('--manifest',type=Path);parser.add_argument('--phase',choices=['SMOKE','MAIN'])
    args=parser.parse_args()
    if args.operation=='prepare':prepare()
    elif args.manifest and args.phase:run(args.manifest.resolve(),args.phase)
    else:parser.error('--manifest and --phase required')
