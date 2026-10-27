"""One-pass descriptive structure analysis; no model invocation or fitting."""
from pathlib import Path
from time import perf_counter_ns
from collections import Counter,defaultdict
import json
import numpy as np
from src.analysis import packet_structure_sources_v1 as a
from src.analysis import packet_structure_math_v1 as algebra
from src.analysis.short_probe_journal_audit_v1 import applied
from src.analysis.native_command_witness_audit_v1 import target
from src.analysis.response_action_audit_v1 import same
io=a.io
META=('split','group','task','context','boundary','acquisition_action')


def family_values(number,trio,counters):
    base=trio[0]['case'];meta={k:base[k] for k in META};meta['family_index']=number;packets=[t['packet'] for t in trio];entry=base['entry_at_calls'];lengths=[len(p) for p in packets]
    register=[{k:t['case'][k] for k in (*a.original.KEYS,'total_steps','entry_at_calls','packet_steps','reason','success_at_response_horizon')}|dict(family_index=number) for t in trio]
    oracle=[];clips=[];native_clips=[]
    if entry is not None:
        spec={k:base[k] for k in a.original.KEYS};noise=a.original.noise(spec);counters['deterministic_noise_tapes_regenerated']+=1;counters['deterministic_noise_scalars_regenerated']+=1500
        first=[t['before'][entry]['mocap_pos_oracle'][0] for t in trio];same(first[0],first[1]);same(first[0],first[2])
        for t,packet in zip(trio,packets):
            act=[];cc=[];nc=[];fault=t['case']['destination_oracle'];io.require(t['case']['boundary_applied'],'live packet after registered fault boundary')
            for j,e in enumerate(packet):
                n=e['logical_step'];same(e['noise_cursor_after'],n+1);u=np.asarray(e['command'],np.float32);latent=np.asarray(fault['matrix_xy'],np.float32)@u[:2]+np.asarray(fault['bias_xy'],np.float32);zone=np.asarray(fault['deadzone_xy'],np.float32)
                before_clip=u.copy();before_clip[:2]=np.sign(latent)*np.maximum(abs(latent)-zone,np.float32(0))/(np.float32(1)-zone);before_clip[:3]+=noise[n]
                expected=applied(e['command'],fault,noise[n]);same(e['executed_action_oracle'],expected,'saved float32 action chain');same(np.clip(before_clip,-1,1).tolist(),expected)
                b=t['before'][n];p=t['after'][n+1];numbers=target(b['mocap_pos_oracle'][0],expected);same(p['mocap_pos_oracle'][0],numbers['target'],'saved native command target update')
                cc.append(int(np.count_nonzero(before_clip!=np.clip(before_clip,-1,1))));nc.append(sum(numbers['workspace_clip_axes']));act.append(expected)
                counters['saved_packet_actions_checked']+=1;counters['native_target_updates_checked']+=1
            oracle.append(act);clips.append(cc);native_clips.append(nc)
    rows=[];predictions=[];rec=base['forecast_record']
    for h in range(1,17):
        available=min(lengths)>=h;missing=None if available else 'NO_COMMON_PACKET_ENTRY' if entry is None else 'AT_LEAST_ONE_ROLE_ENDED_BEFORE_H'
        row={**meta,'horizon':h,'horizon_band':1+(h-1)//4,'available':available,'missing_reason':missing,'packet_lengths':dict(zip(a.ROLES,lengths)),
            'original_case_reasons':{r:t['case']['reason'] for r,t in zip(a.ROLES,trio)},'response':None,'actuator':None,'prediction_availability':'NO_SAVED_NUMERIC_PREDICTION'}
        if available:
            positions=[p[h-1]['after']['observation'][:2] for p in packets];native=[t['after'][entry+h]['mocap_pos_oracle'][0][:2] for t in trio]
            row['response']=algebra.response(*positions,*native);row['actuator']=algebra.actuator_parity([p[:h] for p in oracle],[sum(x[:h]) for x in clips],[sum(x[:h]) for x in native_clips]);counters['observed_three_role_decompositions']+=1
        numeric=rec is not None and bool(rec['forecasts']) and rec['forecast_error'] is None
        row['prediction_availability']='ALL5_SAVED_BEFORE_OUTCOME' if available and numeric else 'SAVED_NUMERIC_BUT_NO_THREE_ROLE_H' if numeric else 'NO_SAVED_NUMERIC_PREDICTION'
        for method in a.METHODS:
            values=dict.fromkeys(('saved_pair_mse_m2','linear_command_class_floor_m2','saved_odd_component_error_m2','saved_nonclass_correction_m2','saved_class_defect_l2_m','decomposition_error_m2'))
            if available and numeric:
                saved=rec['forecasts'][method];v=[saved[pair][h-1] for pair in ('ZERO__PLUS','ZERO__MINUS','PLUS__MINUS')];values=algebra.saved_error(*positions,v)
                counters['saved_prediction_arithmetic_decompositions']+=1
            predictions.append({**meta,'horizon':h,'horizon_band':row['horizon_band'],'method':method,'available':available and numeric,
                'missing_reason':missing if not available else None if numeric else 'NO_SAVED_NUMERIC_PREDICTION',**values})
            counters['registered_saved_prediction_slots']+=1
        rows.append(row)
    return register,rows,predictions


def summarize(rows):
    """Family then independent group, four splits separate, no time-step weighting."""
    levels=(('split',),('split','task'),('split','context'),('split','acquisition_action'),('split','boundary'),('split','horizon'),('split','horizon_band'),('split','task','context','acquisition_action','boundary','horizon'))
    output=[]
    for fields in levels:
        groups=defaultdict(list)
        for r in rows:groups[tuple(r[k] for k in fields)+(r.get('method'),)].append(r)
        for key,part in groups.items():
            valid=[r for r in part if r.get('available',True)];models=key[-1] is not None;names=('saved_pair_mse_m2','linear_command_class_floor_m2','saved_odd_component_error_m2','saved_nonclass_correction_m2') if models else ('linear_command_class_floor_m2','native_even_term_m2','tracking_even_term_m2','native_tracking_cross_m2')
            family=defaultdict(list)
            for r in valid:family[(r['group'],r['family_index'])].append(r if models else r['response'])
            bygroup=defaultdict(list)
            for (g,f),rr in family.items():bygroup[g].append({name:float(np.mean([v[name] for v in rr])) for name in names})
            means={name:None if not bygroup else float(np.mean([np.mean([v[name] for v in vv]) for vv in bygroup.values()])) for name in names}
            ratio=None;reason='NOT_A_SAVED_MODEL_PANEL'
            if models:
                denominator=means['saved_pair_mse_m2'];ratio=None if denominator is None or denominator==0 else means['linear_command_class_floor_m2']/denominator
                reason='NO_AVAILABLE_FAMILY' if denominator is None else 'ZERO_DENOMINATOR' if denominator==0 else None
            output.append(dict(level=list(fields),strata=dict(zip(fields,key[:-1])),method=key[-1],allocated_family_h_rows=len(part),available_family_h_rows=len(valid),
                available_families=len(family),available_groups=len(bygroup),mean=means,floor_fraction_of_group_mean_mse=ratio,ratio_missing_reason=reason))
    return output


def run(path):
    from src.analysis.release_learning_guard_v1 import read_only
    start=perf_counter_ns();m=a.checked(path);out=Path(path).parent/'analysis';out.mkdir(exist_ok=False);counts=Counter();guard={};register=[];observed=[];predictions=[]
    with read_only(guard):
        for number,trio in a.source_families():
            c,r,p=family_values(number,trio,counts);register.extend(c);observed.extend(r);predictions.extend(p)
        io.require(len(register)==864 and len(observed)==4608,'complete source inventory at all16 horizons')
        io.write(out/'case_register.json',register)
        for name,data in (('family_horizon_rows.jsonl',observed),('saved_prediction_rows.jsonl',predictions)):
            with (out/name).open('x',encoding='utf8',newline='\n') as f:
                for row in data:f.write(json.dumps(row,allow_nan=False,separators=(',',':'))+'\n')
        io.write(out/'observed_panels.json',summarize(observed));io.write(out/'prediction_panels.json',summarize(predictions))
    a.checked(path)
    result=dict(integrity='ANALYZED_FOR_INDEPENDENT_AUDIT',manifest_id=m['manifest_id'],cases=len(register),families=288,family_horizon_rows=len(observed),saved_prediction_rows=len(predictions),
        counters=dict(counts),guard=guard,source_costs_not_new=io.read(a.SOURCE/'presentation/costs.json')['total'],
        artifact_sha256={p.name:io.sha(p) for p in out.iterdir() if p.is_file()},wall_ns=perf_counter_ns()-start,new_model_fits=0,new_model_predictions=0,online_LLM_API_calls=0)
    io.write(out/'completion.json',result);return result
