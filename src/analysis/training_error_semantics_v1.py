"""Post-hoc public TRAIN error algebra, zero new physics/fits/policy queries."""
from collections import Counter
from itertools import groupby
from pathlib import Path
from time import perf_counter_ns
import csv,json
import numpy as np
from src.analysis import learned_acquisition_native_io_v1 as a
from src.analysis import observed_error_terms_v1 as algebra
from src.analysis.release_learning_guard_v1 import read_only
from src.analysis import correction_scope_io_v1 as old
io=a.io


def public_cases(base):
    outer=iter(groupby(io.rows(Path(base)/'train/events.jsonl.gz'),old.case_key))
    for spec in old.population('TRAIN'):
        key,events=next(outer);io.require(key==old.case_key(spec),'fixed source TRAIN event order')
        prior=None;history=[];entry=None
        for event in events:
            if event['event']=='CONTROLLED_INITIAL':prior=dict(observation=event['observation'],success=False,terminated=False,truncated=False)
            elif event['event']=='STEP_COMPLETE':
                io.require(prior is not None and event['logical_step']==len(history),'actual initial state and consecutive history')
                history.append(dict(at_calls=event['logical_step'],before=prior,command=event['command'],after=event['after']));prior=event['after']
            elif event['event']=='AGENT_EVENT' and event['agent_event']=='FORECAST_INPUT':
                p=event['public_payload']
                if p['value']['stage']=='POST':entry=p['at_calls']
        yield spec,history,entry
    io.require(next(outer,None) is None,'no additional source cases')


def analyze(path):
    path=Path(path).resolve();m=a.checked(path);out=path.parent/'training_signal';out.mkdir(exist_ok=False);start=perf_counter_ns();guard={}
    base=io.ROOT/m['config']['source_A1_run'];examples={(old.case_key(r['spec']),r['stage']):r for r in io.rows(base/'train/examples.jsonl.gz')}
    cases=[];past={};past_hash={};future_count=0;step_rows=0
    with read_only(guard),(out/'public_window_terms.csv').open('x',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['window_id','actual_control_index','u_x','u_y','observed_dx_over_0.01','observed_dy_over_0.01','query_bin','error','command_energy','motion_energy','alignment','identity_gap'])
        for index,(spec,history,entry) in enumerate(public_cases(base)):
            key=old.case_key(spec);post=examples[(key,'POST')];pre=examples[(key,'PRE')]
            missing='ALREADY_TERMINAL' if pre['view'] is None else 'ACQUISITION_TERMINAL' if post['view'] is None else None
            row=dict(spec=spec,source_case_index=index,missing_reason=missing,loss=None,entry=entry,past_window_id=None,future=None)
            if entry is None:
                io.require(post['target'] is None and post['view'] is None,'missing actual return retained')
            else:
                io.require(post['view'] is not None and entry==len(post['view']['history']) and post['view']['history']==history[:entry],'actual returned public history')
                before=history[max(0,entry-32):entry];after=history[entry:entry+32];signal=algebra.window(after)
                io.require(signal['n']>0 and post['target'] is not None,'factual tail after returned node')
                reference=np.r_[signal['occupancy'],signal['joint']['error'],signal['means']['error'],signal['n']/32]
                io.require(np.allclose(reference,post['target'][50:100],atol=2e-12,rtol=2e-12),'unchanged original working-model target')
                shared_id=io.digest([*old.unit_key(spec),spec['acquisition_action']]);fingerprint=io.digest(before)
                if shared_id in past_hash:io.require(past_hash[shared_id]==fingerprint,'same physical acquisition history across rate assignments')
                else:past_hash[shared_id]=fingerprint
                row.update(past_window_id=shared_id,future=signal);future_count+=1
                groups=[('FUTURE/'+str(index),after)]
                if spec['time_constant_s']==.5:
                    past[shared_id]=dict(spec=spec,entry=entry,source_public_rows_sha256=fingerprint,signal=algebra.window(before))
                    groups.insert(0,('PAST/'+shared_id,before))
                for name,rows in groups:
                    for step in rows:
                        t=algebra.terms(step);writer.writerow([name,step['at_calls'],*t['command_xy'],*t['observed_scaled_delta_xy'],t['bin_index'],*[t[k] for k in ('error','command_energy','motion_energy','alignment','identity_gap')]]);step_rows+=1
            cases.append(row)
        io.require(len(cases)==648 and future_count==536 and len(past)==134,'complete source population and real missingness')
        io.require({r['past_window_id'] for r in cases if r['entry'] is not None}==set(past),'every repeated past has fixed0.5 canonical source')
    source_cases={old.case_key(c):c for c in io.rows(base/'train/cases.jsonl.gz')}
    for row in cases:row['loss']=source_cases[old.case_key(row['spec'])]['deadline_loss'];row['success']=source_cases[old.case_key(row['spec'])]['success']
    io.write(out/'case_signal.json',cases);io.write(out/'shared_past_signal.json',past)
    summary={}
    for group in range(9):
        values=[r for r in cases if r['spec']['group']==group and r['future'] is not None]
        relative=[r['future']['command_only_relative_l2'] for r in values if r['future']['command_only_relative_l2'] is not None]
        summary[str(group)]=dict(registered=72,available=len(values),means={k:float(np.mean([r['future']['means'][k] for r in values])) for k in ('error','command_energy','motion_energy','alignment')},
            relative_command_only_l2_mean=None if not relative else float(np.mean(relative)),undefined_zero_error_denominators=len(values)-len(relative))
    receipt=dict(integrity='FOR_INDEPENDENT_PUBLIC_SIGNAL_AUDIT',all_cases=648,real_future_windows=536,unique_actual_past_windows=134,step_table_rows=step_rows,
        missing_reasons=dict(Counter(r['missing_reason'] for r in cases if r['missing_reason'] is not None)),groups=summary,
        guard=guard,wall_ns=perf_counter_ns()-start,artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},
        future_commands_used_for_retrospective_diagnosis_only=True,private_values_used_as_signal_inputs=False,
        source_complete_bytes_hashed_but_private_witness_records_not_decoded=True,new_physics=0,new_model_fits=0,new_policy_queries=0,online_LLM_API_calls=0)
    io.write(out/'analysis.json',receipt);return receipt


def literal_window(rows):
    if not rows:return dict(n=0,missing_reason='NO_EXECUTED_WINDOW',means=None,joint=None,command_only_relative_l2=None)
    p=[0.]*24;terms={k:[] for k in ('error','command_energy','motion_energy','alignment')};joint={k:[0.]*24 for k in terms};gap=0.
    for row in rows:
        b=row['before']['observation'];after=row['after']['observation'];u=row['command'];d=[(after[i]-b[i])/.01 for i in (0,1)]
        v=dict(error=sum((d[i]-u[i])**2 for i in (0,1)),command_energy=u[0]**2+u[1]**2,motion_energy=d[0]**2+d[1]**2,alignment=2*(d[0]*u[0]+d[1]*u[1]))
        q=((int(u[0]>=0)+2*int(u[1]>=0))*3+min(2,int(3*max(abs(u[0]),abs(u[1])))))*2+int(sum((b[i+4]-b[i])**2 for i in range(3))**.5<=.1)
        p[q]+=1
        for k,x in v.items():terms[k].append(x);joint[k][q]+=x
        gap=max(gap,abs(v['error']-(v['command_energy']+v['motion_energy']-v['alignment'])))
    n=len(rows);den=sum(v*v for v in terms['error'])**.5;num=sum((x-y)**2 for x,y in zip(terms['error'],terms['command_energy']))**.5
    return dict(n=n,missing_reason=None,means={k:sum(v)/n for k,v in terms.items()},joint={k:[x/n for x in v] for k,v in joint.items()},occupancy=[x/n for x in p],
        command_only_relative_l2=None if den==0 else num/den,command_only_absolute_l2=num/n**.5,max_identity_gap=gap)


def audit(path):
    from unittest.mock import patch
    from src.analysis.correction_transfer_independent_v1 import equal_tree
    path=Path(path).resolve();m=a.checked(path);out=path.parent/'training_signal';before=io.read(out/'analysis.json');guard={};start=perf_counter_ns();fields=0
    for n,h in before['artifact_sha256'].items():io.require(io.sha(out/n)==h,'signal artifact unchanged '+n)
    cases=io.read(out/'case_signal.json');past=io.read(out/'shared_past_signal.json')
    source_cases={old.case_key(c):c for c in io.rows(io.ROOT/m['config']['source_A1_run']/'train/cases.jsonl.gz')}
    def denied(*args,**kwargs):raise RuntimeError('main signal arithmetic disabled')
    with read_only(guard),patch.object(algebra,'terms',denied),patch.object(algebra,'window',denied),(out/'public_window_terms.csv').open(encoding='utf8',newline='') as csv_file:
        table=iter(csv.DictReader(csv_file));table_count=0
        # Separate event-to-history loop, not the main public_cases iterator.
        outer=iter(groupby(io.rows(io.ROOT/m['config']['source_A1_run']/'train/events.jsonl.gz'),old.case_key))
        for index,spec in enumerate(old.population('TRAIN')):
            key,it=next(outer);io.require(key==old.case_key(spec),'independent source order');prior=None;history=[];entry=None;pre_seen=False
            for e in it:
                if e['event']=='CONTROLLED_INITIAL':prior={'observation':e['observation'],'success':False,'terminated':False,'truncated':False}
                elif e['event']=='STEP_COMPLETE':history.append({'at_calls':len(history),'before':prior,'command':e['command'],'after':e['after']});prior=e['after']
                elif e['event']=='AGENT_EVENT' and e['agent_event']=='FORECAST_INPUT':
                    if e['public_payload']['value']['stage']=='POST':entry=e['public_payload']['at_calls']
                    else:pre_seen=True
            row=cases[index];io.require(row['spec']==spec and row['entry']==entry,'complete case registration')
            source=source_cases[old.case_key(spec)];io.require(row['loss']==source['deadline_loss'] and row['success']==source['success'],'actual source outcomes, descriptive only')
            if entry is not None:
                expected=literal_window(history[entry:entry+32]);equal_tree(expected,row['future']);fields+=4*24+4+24+5
                identity=io.digest([*old.unit_key(spec),spec['acquisition_action']]);io.require(row['past_window_id']==identity,'canonical shared past identity')
                io.require(io.digest(history[max(0,entry-32):entry])==past[identity]['source_public_rows_sha256'],'all rate assignments share exact prior physical history')
                windows=[('FUTURE/'+str(index),history[entry:entry+32])]
                if spec['time_constant_s']==.5:
                    equal_tree(literal_window(history[max(0,entry-32):entry]),past[identity]['signal']);fields+=129
                    windows.insert(0,('PAST/'+identity,history[max(0,entry-32):entry]))
                for name,window_rows in windows:
                    for actual in window_rows:
                        saved=next(table);io.require(saved['window_id']==name and int(saved['actual_control_index'])==actual['at_calls'],'step table ownership and clock')
                        b=actual['before']['observation'];after=actual['after']['observation'];u=actual['command'];d=[(after[i]-b[i])/.01 for i in (0,1)]
                        single=literal_window([actual]);mean=single['means'];q=next(i for i,p in enumerate(single['occupancy']) if p==1)
                        expected_numbers=[u[0],u[1],d[0],d[1],q,mean['error'],mean['command_energy'],mean['motion_energy'],mean['alignment'],mean['error']-(mean['command_energy']+mean['motion_energy']-mean['alignment'])]
                        keys=('u_x','u_y','observed_dx_over_0.01','observed_dy_over_0.01','query_bin','error','command_energy','motion_energy','alignment','identity_gap')
                        io.require(np.allclose([float(saved[k]) for k in keys],expected_numbers,atol=2e-10,rtol=2e-10),'independent step signal table')
                        table_count+=1;fields+=10
            else:
                io.require(row['future'] is None and row['past_window_id'] is None,'no missing-value imputation')
                io.require(row['missing_reason']==('ACQUISITION_TERMINAL' if pre_seen else 'ALREADY_TERMINAL'),'actual missing reason')
        io.require(next(outer,None) is None,'no extra source events')
        io.require(next(table,None) is None and table_count==before['step_table_rows'],'all step table rows audited')
        for group in range(9):
            live=[r['future'] for r in cases if r['spec']['group']==group and r['future'] is not None];summary=before['groups'][str(group)]
            io.require(summary['registered']==72 and summary['available']==len(live),'full grouped signal denominator')
            for key in ('error','command_energy','motion_energy','alignment'):
                io.require(abs(summary['means'][key]-sum(r['means'][key] for r in live)/len(live))<2e-10,'independent equal-trajectory group mean')
    result=dict(integrity='PASSED',all_cases=648,independent_signal_fields=fields,artifact_sha256=before['artifact_sha256'],analysis_sha256=io.sha(out/'analysis.json'),
        main_signal_math_disabled=True,guard=guard,wall_ns=perf_counter_ns()-start,new_physics=0,new_model_fits=0,new_policy_queries=0,online_LLM_API_calls=0)
    io.write(out/'audit.json',result);return result
