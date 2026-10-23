"""Independent scalar arithmetic/queries/forward and realized task-menu audit.

Shares only the source JSON stream reader and earlier frozen forward evaluator;
the new main diagnosis, metrics, query builder and aggregators are disabled.
"""
from pathlib import Path
from collections import defaultdict,Counter
from math import fsum,sqrt,isclose
from time import perf_counter_ns
import numpy as np
from src.analysis import latent_response_diagnosis_io_v1 as a
from src.analysis.latent_response_diagnosis_reader_v1 import latent_cases,reference_cases
from src.analysis.latent_response_record_audit_v1 import independent_query
from src.analysis.latent_response_model_audit_v1 import independent_predict,independent_context
from src.analysis.native_command_witness_audit_v1 import target
io=a.io


def compare(actual,expected,path='root'):
    if type(expected) is dict:
        io.require(type(actual) is dict and set(actual)==set(expected),'independent keys '+path)
        return sum(compare(actual[k],v,path+'/'+k) for k,v in expected.items())
    if type(expected) in (list,tuple):
        io.require(type(actual) in (list,tuple) and len(actual)==len(expected),'independent length '+path)
        return sum(compare(x,y,path+'/'+str(i)) for i,(x,y) in enumerate(zip(actual,expected)))
    if type(expected) is float:
        tolerance=1e-18 if '_m2' in path else 1e-9 if '_mm' in path else 1e-12
        io.require(type(actual) is float and isclose(actual,expected,rel_tol=1e-9,abs_tol=tolerance),'independent float '+path)
    else:io.require(type(actual) is type(expected) and actual==expected,'independent exact field '+path)
    return 1


def scalar_metrics(prediction,truth,mask,sent,native):
    n=min(len(prediction),sum(mask));error=[[float(prediction[h][j])-float(truth[h][j]) for j in range(2)] for h in range(n)]
    mean=lambda xs:fsum(xs)/len(xs)
    squares=[mean([v*v for v in row]) for row in error];d=[]
    for h in range(n):d.append([error[h][j]-(error[h-1][j] if h else 0.) for j in range(2)])
    diagonal=fsum(v*v for row in d for v in row)/2
    cross=fsum(d[l][j]*d[r][j] for l in range(n) for r in range(l+1,n) for j in range(2))
    ca=[[float(prediction[h][j])-float(sent[h][j]) for j in range(2)] for h in range(n)]
    cb=[[float(sent[h][j])-float(native[h][j]) for j in range(2)] for h in range(n)]
    cc=[[float(native[h][j])-float(truth[h][j]) for j in range(2)] for h in range(n)]
    energy=lambda v:fsum(x*x for row in v for x in row)/(2*n)
    twice=lambda v,w:fsum(2*v[h][j]*w[h][j] for h in range(n) for j in range(2))/(2*n)
    return {'actual_horizons':n,'model_horizons':len(prediction),'horizon_mse_m2':squares+[None]*(8-n),
        'masked_H8_objective_m2':mean(squares) if len(prediction)==8 else None,'H1_mse_m2':squares[0],'H1_rmse_m':sqrt(squares[0]),
        'H8_rmse_m':sqrt(mean(squares)) if len(prediction)==8 and n==8 else None,
        'increment_diagonal_energy_m2':diagonal,'increment_cross_energy_m2':cross,'terminal_error_m2':squares[-1],
        'H8_terminal_error_m2':squares[-1] if len(prediction)==n==8 else None,'H8_increment_diagonal_energy_m2':diagonal if len(prediction)==n==8 else None,
        'H8_increment_cross_energy_m2':cross if len(prediction)==n==8 else None,
        'model_minus_nominal_m2':energy(ca),'nominal_minus_native_m2':energy(cb),'native_minus_hand_m2':energy(cc),
        'twice_model_nominal_cross_m2':twice(ca,cb),'twice_model_hand_cross_m2':twice(ca,cc),'twice_nominal_hand_cross_m2':twice(cb,cc)}


def average(rows):
    if not rows:return None
    out={}
    for k in rows[0]:
        if k in ('actual_horizons','model_horizons'):continue
        if k=='horizon_mse_m2':out[k]=[fsum(v)/len(v) if (v:=[r[k][h] for r in rows if r[k][h] is not None]) else None for h in range(8)]
        else:
            v=[r[k] for r in rows if r[k] is not None];out[k]=fsum(v)/len(v) if v else None
    return out


def rebuilt_source(case,public,meta,events,records):
    states=[public['initial_observation'],*[r['observation_after'] for r in public['steps']]];commands=[r['command'] for r in public['steps']]
    io.require(len(commands)==case['total_steps'],'actual state/control length');nominals=[[0.,.6,.2]]
    for command in commands:nominals.append(target(nominals[-1],command)['target'])
    actual={}
    for r in records:
        if r['label']=='INITIAL' or r['label']=='AFTER_STEP':actual[r['at_calls']]=r['mocap_pos_oracle'][0]
    io.require(set(actual)==set(range(len(commands)+1)),'one actual native sample at every control boundary')
    split=case['split'];entry=meta['entry_at_calls'];ws=[];saved=None
    if split=='SOFTWARE' or entry is None:return ws,saved,states,commands,nominals,actual
    lengths=range(min(case['packet_steps'],25)) if split=='TRAIN' else range(1)
    for k in lengths:
        planned=meta['packet_commands'][k:k+8]
        if len(planned)!=8:break
        at=entry+k;raw=independent_query(case['task'],states[:at+1],commands[:at],nominals[at],planned)
        valid=min(8,case['packet_steps']-k);ys=[[states[at+h+1][j]-states[at][j] for j in range(2)] if h<valid else [0.,0.] for h in range(8)]
        ws.append({'query':raw,'targets':ys,'mask':[h<valid for h in range(8)]})
    if split in ('CAL','QUAL'):
        result=[e['public_payload']['result'] for e in events if e.get('agent_event')=='FORECAST_RESULT'];io.require(len(result)==1,'one saved result')
        compare(result[0]['query'],ws[0]['query'],'causal saved entry query');compare(result[0]['query_sha256'],io.digest(ws[0]['query']))
        saved=result[0]['forecasts']
    return ws,saved,states,commands,nominals,actual


def features(case,ws,states,nominals,actual,bank):
    if not ws:return None
    raw=ws[0]['query'];at=raw['completed_steps'];p=states[at];native=actual[at];sent=nominals[at]
    norm=lambda values:sqrt(fsum(v*v for v in values))
    x=independent_context(raw,bank[case['task']]['SS_SENT']['normalization'],'SS_SENT')
    return {'nominal_native_gap_xy_mm':1000*norm([sent[j]-native[j] for j in range(2)]),
        'hand_native_gap_xy_mm':1000*norm([p[j]-native[j] for j in range(2)]),'previous_hand_motion_xy_mm':1000*norm([p[j]-states[at-1][j] for j in range(2)]),
        'hand_object_distance_mm':1000*norm([p[j]-p[4+j] for j in range(3)]),'frozen_TRAIN_normalized_context_rms':sqrt(fsum(v*v for v in x)/len(x)),
        'first_declared_packet_XY_rms':sqrt(fsum(float(u[j])**2 for u in raw['planned_commands'] for j in range(2))/16),
        'scope':'DESCRIPTIVE_EVALUATOR_ENTRY_FEATURES_NOT_APPLICABILITY_CERTIFICATE_OR_MODEL_INPUT'}


def case_aggregates(case,method,checkpoint,values,feature,invalid=False):
    rows=[]
    for regime in a.REGIMES:
        if case['split']!='TRAIN' and regime.startswith('START_'):continue
        def included(k):
            return regime=='ALL_WINDOWS' or regime=='ENTRY_ONLY' and k==0 or regime=='START_01_08' and 1<=k<=8 or regime=='START_09_16' and 9<=k<=16 or regime=='START_17_24' and 17<=k<=24
        part=[v for k,v in enumerate(values) if included(k)]
        reason=None if part else 'NO_ACTUAL_WINDOW_IN_BIN' if values else 'INVALID_SAVED_FORECAST' if invalid else 'NO_MODEL_BY_SOFTWARE_PROTOCOL' if case['split']=='SOFTWARE' else 'NO_MEASUREMENT_ENTRY'
        rows.append({**{k:case[k] for k in a.latent.KEYS},'method':method,'checkpoint':checkpoint,'regime':regime,'windows':len(part),
            'complete_H8_windows':sum(v['H8_rmse_m'] is not None for v in part),'reason':reason,'metrics':average(part),'features':feature})
    return rows


def independent_groups(rows,detailed=True):
    grouping={}
    keys=('split','task','initial_kind','context','packet_kind','boundary','method','checkpoint','regime') if detailed else ('split','task','method','checkpoint','regime')
    for row in rows:grouping.setdefault(tuple(row[k] for k in keys),[]).append(row)
    output=[]
    for key,rs in grouping.items():
        by_group=[]
        for g in sorted({r['group'] for r in rs}):
            part=[r['metrics'] for r in rs if r['group']==g and r['metrics'] is not None]
            by_group.append({'group':g,'allocated':sum(r['group']==g for r in rs),'available_trajectories':len(part),'metrics':average(part)})
        support=[r['metrics'] for r in by_group if r['metrics'] is not None]
        output.append(dict(zip(keys,key))|{'allocated_trajectories':len(rs),'available_trajectories':sum(r['metrics'] is not None for r in rs),
            'independent_groups':len(by_group),'available_groups':len(support),'metrics':average(support),'groups':by_group})
    return output


def independent_objectives(rows):
    result=[]
    for t in io.TASKS:
        for m in a.METHODS:
            checkpoints=a.CHECKPOINTS if m in a.NEURAL else (None,)
            for k in checkpoints:
                for regime in ('ALL_WINDOWS','ENTRY_ONLY'):
                    selected=[r for r in rows if (r['split'],r['task'],r['method'],r['checkpoint'],r['regime'])==('TRAIN',t,m,k,regime) and r['metrics'] is not None]
                    result.append({'task':t,'method':m,'checkpoint':k,'regime':regime,'available_trajectories':len(selected),'metrics':average([r['metrics'] for r in selected])})
    return result


def independent_menu(cases):
    io.require(set(cases)==set(a.reference.PROGRAMS),'all original task programs')
    for c in cases.values():io.require(c['deadline_loss']==(c['total_steps'] if c['success'] else 500),'complete task loss')
    ls={p:cases[p]['deadline_loss'] for p in a.MENU};minimum=min(ls.values());raw=ls['RAW_CONTINUE'];keep=ls['LOCAL_PID_KEEP'];c=cases['RAW_CONTINUE']
    return {**{k:c[k] for k in ('group','task','seed','context','planned_boundary')},'menu_losses':ls,'oracle_recorded_minimum_loss':minimum,
        'all_tied_minimizers':[p for p in a.MENU if ls[p]==minimum],'optimistic_raw_saving':raw-minimum,
        'same_acquisition_submenu_minimum_loss':min(ls[p] for p in a.ADOPTION_MENU),
        'same_acquisition_all_tied_minimizers':[p for p in a.ADOPTION_MENU if ls[p]==min(ls[q] for q in a.ADOPTION_MENU)],
        'same_acquisition_optimistic_raw_saving':raw-min(ls[p] for p in a.ADOPTION_MENU),
        'direct_C8_external_whole_program_loss':cases['DIRECT_C8']['deadline_loss'],'integral_external_whole_program_loss':cases['MOVE_INTEGRAL']['deadline_loss'],
        'decompositions':{p:{'whole_minus_raw':ls[p]-raw,'acquisition_keep_minus_raw':keep-raw,'reference_minus_keep':ls[p]-keep} for p in a.REFERENCE_BRANCHES},
        'counterfactual_policy_or_learnability_claim':False}


def independent_menu_summary(units,cases,checks):
    summaries=[]
    for program in a.reference.PROGRAMS:
        rs=[r for r in cases if r['program']==program];io.require(len(rs)==54,'all per-program cases')
        summaries.append({'program':program,'assigned':54,'successes':sum(r['success'] for r in rs),'mean_deadline_loss':sum(r['deadline_loss'] for r in rs)/54})
    groups=[{'group':g,'allocated_units':6,'oracle_loss_sum':sum(r['oracle_recorded_minimum_loss'] for r in units if r['group']==g),
        'raw_loss_sum':sum(r['menu_losses']['RAW_CONTINUE'] for r in units if r['group']==g),'optimistic_saving_sum':sum(r['optimistic_raw_saving'] for r in units if r['group']==g)} for g in range(9)]
    cells=[]
    for task in io.TASKS:
        for ctx in ('UNCHANGED','CHANGED'):
            for at in (16,32,64):
                rs=[r for r in units if r['task']==task and r['context']==ctx and r['planned_boundary']==at]
                cells.append({'task':task,'context':ctx,'boundary':at,'allocated':len(rs),'oracle_mean_loss':sum(r['oracle_recorded_minimum_loss'] for r in rs)/len(rs),
                    'raw_mean_loss':sum(r['menu_losses']['RAW_CONTINUE'] for r in rs)/len(rs),'positive_realized_opportunity_units':sum(r['optimistic_raw_saving']>0 for r in rs)})
    return {'classification':'OPTIMISTIC_REALIZED_FUTURE_RECORD_MENU_ONLY','matched_RAW_prefix_comparisons':checks,'all_units':54,'independent_groups':9,
        'program_summaries':summaries,'oracle_mean_loss':sum(r['oracle_recorded_minimum_loss'] for r in units)/54,
        'raw_mean_loss':sum(r['menu_losses']['RAW_CONTINUE'] for r in units)/54,'optimistic_mean_raw_saving':sum(r['optimistic_raw_saving'] for r in units)/54,
        'positive_realized_opportunity_units':sum(r['optimistic_raw_saving']>0 for r in units),'groups':groups,'cells':cells,
        'same_acquisition_submenu_mean_loss':sum(r['same_acquisition_submenu_minimum_loss'] for r in units)/54,
        'same_acquisition_submenu_mean_raw_saving':sum(r['same_acquisition_optimistic_raw_saving'] for r in units)/54,
        'deployable_policy_or_learnability_or_new_task_gain':False,'new_confidence_intervals':False}


def audit(path):
    start=perf_counter_ns();m=a.checked(path);out=Path(path).parent/'analysis';done=io.read(out/'completion.json')
    for name,h in done['artifact_sha256'].items():io.require(io.sha(out/name)==h,'completed diagnosis bytes changed')
    predictions=iter(io.rows(out/'predictions.jsonl.gz'));diagnostics=iter(io.rows(out/'window_metrics.jsonl.gz'))
    bank=io.read(a.LATENT/'training/models.json')['by_task'];bundle=io.read(a.LATENT/'training/public_train_bundle.json');bundle_rows={r['task']:r['trajectories'] for r in bundle['entries']};offsets=Counter()
    checkpoint_bank={};rows=[];register=[];fields=0;forwards=0;prediction_count=diagnostic_count=0
    for task in io.TASKS:
        for method in a.NEURAL:
            for checkpoint in a.CHECKPOINTS[:-1]:
                state=io.read(a.LATENT/'training/neural'/(task+'_'+method+f'_checkpoint_{checkpoint}.json'));io.require(state['updates']==checkpoint,'fixed saved checkpoint')
                checkpoint_bank[task,method,checkpoint]={**bank[task][method],**state['parameters']}
    for index,c,public,meta,events,private in latent_cases():
        ws,saved,states,commands,sent,actual=rebuilt_source(c,public,meta,events,private);feature=features(c,ws,states,sent,actual,bank)
        if c['split']=='TRAIN' and ws:
            fields+=compare(bundle_rows[c['task']][offsets[c['task']]]['windows'],ws,'source TRAIN supervision');offsets[c['task']]+=1
        register.append({'case_index':index,**{k:c[k] for k in a.latent.KEYS},'actual_control_steps':c['total_steps'],'packet_steps':c['packet_steps'],
            'complete_first_eight':c['complete_first_eight'],'complete_packet':c['complete_packet'],'collection_reason':c['reason'],'diagnostic_queries':len(ws),
            'forecast_scope':'NOT_RUN_SOFTWARE' if c['split']=='SOFTWARE' else 'POST_HOC_TRAIN_FIXED_WEIGHTS' if c['split']=='TRAIN' else 'SAVED_PROSPECTIVE_ENTRY_ONLY','features':feature})
        for method in a.METHODS:
            final=5000 if method in a.NEURAL else None;versions=(final,1000,2000,3000,4000) if c['split']=='TRAIN' and method in a.NEURAL else (final,)
            for checkpoint in versions:
                kind='FINAL' if checkpoint==final else 'CHECKPOINT_TRAIN_ONLY';values=[];valid=True
                if ws:
                    if c['split']=='TRAIN':
                        model=bank[c['task']][method] if kind=='FINAL' else checkpoint_bank[c['task'],method,checkpoint]
                        expected=independent_predict(model,[w['query'] for w in ws]).tolist();forwards+=len(ws)
                    else:
                        value=saved[method];valid=value['valid'];expected=[value['displacements']] if valid else [None]
                    for k,(w,pred) in enumerate(zip(ws,expected)):
                        expected_row={'case_index':index,'split':c['split'],'task':c['task'],'method':method,'checkpoint':checkpoint,'window_index':k,'kind':kind,
                            'query_sha256':io.digest(w['query']),'valid':valid,'displacements':pred,
                            'actual_target_mask':w['mask'],'unsupported_outputs_are_not_observations':True}
                        row=next(predictions,None);io.require(row is not None,'missing saved diagnostic prediction');fields+=compare(row,expected_row,'fixed/saved prediction');prediction_count+=1
                        if not valid:continue
                        at=w['query']['completed_steps'];nominal=[[sent[at+h+1][j]-sent[at][j] for j in range(2)] if w['mask'][h] else [0.,0.] for h in range(8)]
                        native=[[actual[at+h+1][j]-actual[at][j] for j in range(2)] if w['mask'][h] else [0.,0.] for h in range(8)]
                        value=scalar_metrics(pred,w['targets'],w['mask'],nominal,native);values.append(value)
                        if kind=='FINAL':
                            row=next(diagnostics,None);io.require(row is not None,'missing window diagnostic');fields+=compare(row,{**{k:expected_row[k] for k in ('case_index','method','checkpoint','window_index','query_sha256')},'metrics':value},'observed error identities');diagnostic_count+=1
                rows.extend(case_aggregates(c,method,checkpoint,values,feature,not valid))
        if (index+1)%12==0:print({'audit':'LATENT','cases':index+1,'forwards':forwards,'fields':fields},flush=True)
    io.require(next(predictions,None) is next(diagnostics,None) is None,'extra diagnostic windows');io.require(forwards==100464 and prediction_count==103888 and diagnostic_count==36912,'independent full census')
    fields+=compare(io.read(out/'case_register.json'),register,'complete register');fields+=compare(list(io.rows(out/'trajectory_metrics.jsonl.gz')),rows,'trajectory weights/missingness')
    fields+=compare(io.read(out/'grouped_metrics.json'),independent_groups(rows),'independent group summaries');fields+=compare(io.read(out/'broad_grouped_metrics.json'),independent_groups(rows,False),'broad group summaries');fields+=compare(io.read(out/'TRAIN_objectives.json'),independent_objectives(rows),'exact sampler objective')
    units=[];cases=[];unit={};current=None;prefix=None;checks=0
    for c,events in reference_cases():
        key=tuple(c[k] for k in ('group','task','context'))
        if current!=key:
            if unit:units.append(independent_menu(unit))
            unit={};current=key;prefix=None
        cases.append(c);unit[c['program']]=c
        if c['program'] in a.MENU:
            steps=[e for e in events if e['event']=='STEP_COMPLETE'];count=min(c['planned_boundary'],len(steps))
            view={'steps':count,'initial':c['initial'],'prefix':[{k:s[k] for k in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after')} for s in steps[:count]]}
            if prefix is None:prefix=view
            else:fields+=compare(view,prefix,'actual common RAW history');checks+=1
    if unit:units.append(independent_menu(unit))
    fields+=compare(io.read(out/'reference_menu_units.json'),units,'realized menu outcomes');fields+=compare(io.read(out/'reference_menu_summary.json'),independent_menu_summary(units,cases,checks),'task menu summary')
    a.checked(path);result={'integrity':'PASSED','manifest_id':m['manifest_id'],'independently_checked_fields':fields,'fixed_weight_query_forwards':forwards,
        'source_executions':1332,'source_steps':125122,'reference_common_RAW_prefix_comparisons':checks,'artifact_sha256':done['artifact_sha256'],
        'new_main_metrics_queries_and_aggregators_disabled':True,'shared_raw_reader_and_prior_frozen_forward_evaluator_disclosed':True,
        'new_environment_steps':0,'new_model_fits':0,'new_optimizer_updates':0,'online_LLM_API_calls':0,'wall_ns':perf_counter_ns()-start,'classification':'POST_HOC_DESCRIPTIVE_ONLY'}
    io.write(out/'audit.json',result);return result
