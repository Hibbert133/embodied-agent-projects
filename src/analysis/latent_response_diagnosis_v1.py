"""Complete descriptive census, fixed TRAIN checkpoints and realized menu ceiling."""
from pathlib import Path
from collections import Counter,defaultdict
from time import perf_counter_ns
import gzip,json
import numpy as np
from src.analysis import latent_response_diagnosis_io_v1 as a
from src.analysis import latent_response_diagnosis_math_v1 as arithmetic
from src.analysis.latent_response_diagnosis_reader_v1 import latent_cases,reference_cases
from src.analysis.latent_response_training_v1 import windows
from src.probe.latent_response_query_v1 import ForecastQuery,context
from src.probe.latent_response_model_v1 import predict
io=a.io


def nominal_at(public,n):return [0.,.6,.2] if n==0 else public['steps'][n-1]['reference_after']['target']


def native_map(records):
    data={r['at_calls']:r['mocap_pos_oracle'][0] for r in records if r['label'] in ('INITIAL','AFTER_STEP')}
    io.require(len(data)==(len(records)-2)//2+1,'complete actual native positions');return data


def components(public,meta,native,k,mask):
    at=meta['entry_at_calls']+k;states=[public['initial_observation'],*[r['observation_after'] for r in public['steps']]]
    nominal=np.zeros((8,2));actual=np.zeros((8,2));truth=np.zeros((8,2))
    q0=np.asarray(native[at][:2]);s0=np.asarray(nominal_at(public,at)[:2]);p0=np.asarray(states[at][:2])
    for h,valid in enumerate(mask):
        if valid:
            nominal[h]=np.asarray(nominal_at(public,at+h+1)[:2])-s0
            actual[h]=np.asarray(native[at+h+1][:2])-q0;truth[h]=np.asarray(states[at+h+1][:2])-p0
    return nominal,actual,truth


def entry_features(case,public,native,query,model):
    if query is None:return None
    n=query.completed_steps;p=np.asarray(query.observations[-1]);q=np.asarray(native[n]);sent=np.asarray(nominal_at(public,n))
    normalized=context(query,model['normalization'],'SS_SENT');previous=np.asarray(query.observations[-2])
    return {'nominal_native_gap_xy_mm':float(np.linalg.norm(sent[:2]-q[:2])*1000),
        'hand_native_gap_xy_mm':float(np.linalg.norm(p[:2]-q[:2])*1000),'previous_hand_motion_xy_mm':float(np.linalg.norm(p[:2]-previous[:2])*1000),
        'hand_object_distance_mm':float(np.linalg.norm(p[:3]-p[4:7])*1000),
        'frozen_TRAIN_normalized_context_rms':float(np.sqrt(np.mean(normalized*normalized))),
        'first_declared_packet_XY_rms':float(np.sqrt(np.mean(np.asarray(query.planned_commands)[:,:2]**2))),
        'scope':'DESCRIPTIVE_EVALUATOR_ENTRY_FEATURES_NOT_APPLICABILITY_CERTIFICATE_OR_MODEL_INPUT'}


def main_windows(case,public,meta,events,bundle_rows,offsets):
    if case['split']=='SOFTWARE':return [],None
    if case['split']=='TRAIN':
        ws=windows(public,meta)
        if ws:
            task=case['task'];saved=bundle_rows[task][offsets[task]]['windows'];offsets[task]+=1
            io.require(io.digest(ws)==io.digest(saved),'full source TRAIN queries/actual labels match frozen bundle')
        return ws,None
    results=[e['public_payload']['result'] for e in events if e.get('agent_event')=='FORECAST_RESULT']
    io.require(len(results)<=1,'one saved entry forecast')
    if not results:io.require(meta['entry_at_calls'] is None,'no missing saved entry result');return [],None
    result=results[0];q=ForecastQuery.from_dict(result['query']);io.require(result['query_sha256']==io.digest(q.to_dict()),'saved public query')
    n=min(8,case['packet_steps']);mask=[h<n for h in range(8)];y=np.zeros((8,2));at=meta['entry_at_calls']
    p=public['initial_observation'] if at==0 else public['steps'][at-1]['observation_after']
    for h in range(n):y[h]=np.asarray(public['steps'][at+h]['observation_after'][:2])-p[:2]
    return [{'query':result['query'],'targets':y.tolist(),'mask':mask}],result['forecasts']


def checkpoint_models(bank):
    result={}
    for task in io.TASKS:
        for method in a.NEURAL:
            model=bank[task][method]
            for checkpoint in a.CHECKPOINTS:
                saved=io.read(a.LATENT/'training/neural'/(task+'_'+method+f'_checkpoint_{checkpoint}.json'))
                io.require(saved['task']==task and saved['method']==method and saved['updates']==checkpoint,'actual frozen checkpoint identity')
                result[task,method,checkpoint]={**model,**saved['parameters']}
                if checkpoint==5000:io.require(all(model[k]==v for k,v in saved['parameters'].items()),'final model remains last checkpoint')
    return result


def prefix_signature(case,events):
    steps=[e for e in events if e['event']=='STEP_COMPLETE'];n=min(case['planned_boundary'],len(steps))
    fields=('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after')
    return {'steps':n,'initial':case['initial'],'prefix':[{k:e[k] for k in fields} for e in steps[:n]]}


def menu_summary(units,program_rows,prefix_checks):
    io.require(len(units)==54 and prefix_checks==378,'full eight-program matched RAW menu, no filtered cases')
    original=io.read(a.REFERENCE/'qual/statistics.json')['program_summaries'];summaries=[]
    for saved in original:
        part=[c for c in program_rows if c['program']==saved['program']];io.require(len(part)==54,'all reference program cases')
        mean=sum(c['deadline_loss'] for c in part)/54;successes=sum(c['success'] for c in part)
        io.require(mean==saved['mean_deadline_loss'] and successes==saved['successes'],'all original program comparisons unchanged')
        summaries.append({'program':saved['program'],'assigned':54,'successes':successes,'mean_deadline_loss':mean})
    groups=[]
    for g in range(9):
        rs=[u for u in units if u['group']==g];io.require(len(rs)==6,'six full task/context units per independent reference group')
        groups.append({'group':g,'allocated_units':6,'oracle_loss_sum':sum(r['oracle_recorded_minimum_loss'] for r in rs),
            'raw_loss_sum':sum(r['menu_losses']['RAW_CONTINUE'] for r in rs),'optimistic_saving_sum':sum(r['optimistic_raw_saving'] for r in rs)})
    cells=[]
    for task in io.TASKS:
        for context_name in ('UNCHANGED','CHANGED'):
            for boundary in (16,32,64):
                rs=[r for r in units if (r['task'],r['context'],r['planned_boundary'])==(task,context_name,boundary)]
                cells.append({'task':task,'context':context_name,'boundary':boundary,'allocated':len(rs),'oracle_mean_loss':sum(r['oracle_recorded_minimum_loss'] for r in rs)/len(rs),
                    'raw_mean_loss':sum(r['menu_losses']['RAW_CONTINUE'] for r in rs)/len(rs),'positive_realized_opportunity_units':sum(r['optimistic_raw_saving']>0 for r in rs)})
    return {'classification':'OPTIMISTIC_REALIZED_FUTURE_RECORD_MENU_ONLY','matched_RAW_prefix_comparisons':prefix_checks,'all_units':54,'independent_groups':9,
        'program_summaries':summaries,'oracle_mean_loss':sum(u['oracle_recorded_minimum_loss'] for u in units)/54,
        'raw_mean_loss':sum(u['menu_losses']['RAW_CONTINUE'] for u in units)/54,'optimistic_mean_raw_saving':sum(u['optimistic_raw_saving'] for u in units)/54,
        'positive_realized_opportunity_units':sum(u['optimistic_raw_saving']>0 for u in units),'groups':groups,'cells':cells,
        'same_acquisition_submenu_mean_loss':sum(u['same_acquisition_submenu_minimum_loss'] for u in units)/54,
        'same_acquisition_submenu_mean_raw_saving':sum(u['same_acquisition_optimistic_raw_saving'] for u in units)/54,
        'deployable_policy_or_learnability_or_new_task_gain':False,'new_confidence_intervals':False}


def run(path):
    start=perf_counter_ns();m=a.checked(path);out=Path(path).parent/'analysis';out.mkdir(exist_ok=False)
    bank=io.read(a.LATENT/'training/models.json')['by_task'];bundle=io.read(a.LATENT/'training/public_train_bundle.json')
    bundle_rows={e['task']:e['trajectories'] for e in bundle['entries']};offsets={t:0 for t in io.TASKS};checkpoints=checkpoint_models(bank)
    register=[];trajectory=[];counts=Counter();new_forwards=0
    with gzip.open(out/'predictions.jsonl.gz','xt',encoding='utf-8',newline='\n') as pf,gzip.open(out/'window_metrics.jsonl.gz','xt',encoding='utf-8',newline='\n') as df:
        def save(f,row):f.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
        for index,case,public,meta,events,private in latent_cases():
            native=native_map(private);ws,saved=main_windows(case,public,meta,events,bundle_rows,offsets)
            qs=[ForecastQuery.from_dict(w['query']) for w in ws];feature=entry_features(case,public,native,qs[0] if qs else None,bank[case['task']]['SS_SENT'])
            register.append({'case_index':index,**{k:case[k] for k in a.latent.KEYS},'actual_control_steps':case['total_steps'],'packet_steps':case['packet_steps'],
                'complete_first_eight':case['complete_first_eight'],'complete_packet':case['complete_packet'],'collection_reason':case['reason'],
                'diagnostic_queries':len(ws),'forecast_scope':'NOT_RUN_SOFTWARE' if case['split']=='SOFTWARE' else 'POST_HOC_TRAIN_FIXED_WEIGHTS' if case['split']=='TRAIN' else 'SAVED_PROSPECTIVE_ENTRY_ONLY',
                'features':feature})
            for method in a.METHODS:
                final_checkpoint=5000 if method in a.NEURAL else None
                versions=(final_checkpoint,*a.CHECKPOINTS[:-1]) if case['split']=='TRAIN' and method in a.NEURAL else (final_checkpoint,)
                for checkpoint in versions:
                    kind='FINAL' if checkpoint==final_checkpoint else 'CHECKPOINT_TRAIN_ONLY'
                    if not ws:trajectory.extend(arithmetic.trajectory_rows(case,method,checkpoint,[],feature));continue
                    if case['split']=='TRAIN':
                        model=bank[case['task']][method] if kind=='FINAL' else checkpoints[case['task'],method,checkpoint]
                        predictions=predict(model,qs).tolist();new_forwards+=len(qs);valid=True
                    else:
                        value=saved[method];valid=value['valid'];predictions=[value['displacements']] if valid else [None]
                    values=[]
                    for k,(w,pred) in enumerate(zip(ws,predictions)):
                        row={'case_index':index,'split':case['split'],'task':case['task'],'method':method,'checkpoint':checkpoint,'window_index':k,'kind':kind,
                            'query_sha256':io.digest(w['query']),'valid':valid,'displacements':pred,
                            'actual_target_mask':w['mask'],'unsupported_outputs_are_not_observations':True}
                        save(pf,row);counts['prediction_rows']+=1
                        if not valid:continue
                        nominal,actual,truth=components(public,meta,native,k,w['mask']);io.require(np.array_equal(truth,np.array(w['targets'])),'actual labels/no fabricated target')
                        value=arithmetic.metrics(pred,truth,w['mask'],nominal,actual);values.append(value)
                        if kind=='FINAL':save(df,{**{k:row[k] for k in ('case_index','method','checkpoint','window_index','query_sha256')},'metrics':value});counts['window_metric_rows']+=1
                    trajectory.extend(arithmetic.trajectory_rows(case if valid else case|{'_diagnostic_missing_reason':'INVALID_SAVED_FORECAST'},method,checkpoint,values,feature))
            if (index+1)%12==0:print({'stage':'LATENT','cases':index+1,'of':792,'new_fixed_model_query_forwards':new_forwards},flush=True)
    io.require(all(offsets[t]==len(bundle_rows[t]) for t in io.TASKS),'all source TRAIN windows consumed')
    io.require(new_forwards==100464 and counts['prediction_rows']==103888 and counts['window_metric_rows']==36912,'frozen complete forward/row census')
    io.write(out/'case_register.json',register)
    with gzip.open(out/'trajectory_metrics.jsonl.gz','xt',encoding='utf-8',newline='\n') as f:
        for row in trajectory:f.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
    io.write(out/'grouped_metrics.json',arithmetic.grouped(trajectory));io.write(out/'broad_grouped_metrics.json',arithmetic.grouped(trajectory,False));io.write(out/'TRAIN_objectives.json',arithmetic.training_objectives(trajectory))
    units=[];all_programs=[];unit={};prefix=None;prefix_checks=0;current=None
    for c,events in reference_cases():
        key=(c['group'],c['task'],c['context'])
        if key!=current:
            if unit:units.append(arithmetic.menu_unit(unit))
            unit={};prefix=None;current=key
        unit[c['program']]=c;all_programs.append(c)
        if c['program'] in a.MENU:
            actual=prefix_signature(c,events)
            if prefix is None:prefix=actual
            else:io.require(io.digest(actual)==io.digest(prefix),'actual RAW menu common history/state before acquisition');prefix_checks+=1
    if unit:units.append(arithmetic.menu_unit(unit))
    io.write(out/'reference_menu_units.json',units);io.write(out/'reference_menu_summary.json',menu_summary(units,all_programs,prefix_checks))
    a.checked(path);done={'status':'DESCRIPTIVE_ANALYSIS_REQUIRES_INDEPENDENT_AUDIT','manifest_id':m['manifest_id'],'source_executions_read':1332,
        'source_control_steps_read':125122,'latent_cases':792,'reference_cases':540,'fixed_weight_model_query_forwards':new_forwards,
        'saved_forecast_rows_read':3424,**dict(counts),'trajectory_metric_rows':len(trajectory),'wall_ns':perf_counter_ns()-start,
        'artifact_sha256':{p.name:io.sha(p) for p in out.iterdir() if p.is_file()},'new_environment_steps':0,'new_model_fits':0,'new_optimizer_updates':0,'online_LLM_API_calls':0,
        'original_qualification_or_task_comparisons_changed':False}
    io.write(out/'completion.json',done);return done
