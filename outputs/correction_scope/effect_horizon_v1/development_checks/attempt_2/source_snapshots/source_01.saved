"""Literal independent source/window reconstruction, no new dynamics fits."""
from collections import Counter,defaultdict
from itertools import groupby,combinations
from pathlib import Path
from time import perf_counter_ns
from unittest.mock import patch
import struct
from src.analysis import correction_effect_horizon_v1 as main
from src.analysis import correction_effect_independent_v1 as old_audit
from src.analysis.release_learning_guard_v1 import read_only
io=main.io;previous=main.previous


def literal(pair,a,b,J):
    result=[];at=pair['first_difference']
    for h in (1,2,4,8,16,32):
        r={k:pair[k] for k in ('pair_id','group','task','context','boundary','acquisition_action','rates','loss_difference','success_a','success_b')}
        r.update(horizon=h,first_difference=at,source_pair_status=pair['status'],analysis_semantics=main.PURPOSE,status=pair['status'] if at is None else 'COMPLETE_FACTUAL_WINDOW',mse=None,predictions=None)
        if at is not None:
            short_a=at+h>len(a);short_b=at+h>len(b)
            if short_a or short_b:r['status']='BOTH_SOURCES_SHORT' if short_a and short_b else 'SOURCE_A_SHORT' if short_a else 'SOURCE_B_SHORT'
            else:
                u=[sum(b[j]['command'][k]-a[j]['command'][k] for j in range(at,at+h)) for k in (0,1)]
                d=[(b[at+h-1]['after']['observation'][k]-a[at+h-1]['after']['observation'][k])/.01 for k in (0,1)]
                p={'ZERO_EFFECT':[0.,0.],'NOMINAL_SENT':u,'FROZEN_GLOBAL_MATRIX':[sum(u[i]*J[i][k] for i in (0,1)) for k in (0,1)]}
                raw=sum(struct.pack('<4f',*a[j]['raw_policy'])!=struct.pack('<4f',*b[j]['raw_policy']) for j in range(at,at+h))
                zg=sum(struct.pack('<2f',*a[j]['command'][2:])!=struct.pack('<2f',*b[j]['command'][2:]) for j in range(at,at+h))
                r.update(command_sum_difference_xy=u,actual_endpoint_difference_xy=d,predictions=p,mse={k:sum((v[i]-d[i])**2 for i in (0,1))/2 for k,v in p.items()},
                    raw_policy_difference_steps=raw,z_gripper_difference_steps=zg,future_commands_consumed_for_evaluation=h-1,no_unexecuted_states_generated=True)
        result.append(r)
    return result


def audit(path):
    path=Path(path);main.checked(path);out=path.parent/'analysis';receipt=io.read(out/'receipt.json');start=perf_counter_ns();guard={}
    for n,h in receipt['artifact_sha256'].items():io.require(io.sha(out/n)==h,'unchanged horizon artifact')
    windows=io.read(out/'windows.json');panels=io.read(out/'panels.json');register={r['pair_id']:r for r in io.read(main.EFFECT/'pairs/pair_register.json')};index=0;matrices={};counts=Counter()
    def denied(*args,**kwargs):raise RuntimeError('main horizon extraction/math disabled')
    with read_only(guard),patch.object(main,'window',denied),patch.object(main,'panels',denied),patch.object(previous,'source_nodes',denied),patch.object(previous,'first_difference',denied):
        for g in range(9):
            m=io.read(main.EFFECT/f'models/group{g}_GLOBAL_MATRIX.json');matrices[g]=[[m['coef'][i][k]/m['scale'][i] for k in (0,1)] for i in (0,1)]
        cases=list(io.rows(previous.SOURCE/'train/cases.jsonl.gz'));outer=iter(groupby(io.rows(previous.SOURCE/'train/events.jsonl.gz'),previous.source.case_key));io.require(len(cases)==648,'all source TRAIN')
        for offset in range(0,648,4):
            family=[]
            for c in cases[offset:offset+4]:
                key,it=next(outer);io.require(key==previous.source.case_key(c),'independent case ordering');steps=[]
                for e in it:
                    if e['event']=='STEP_COMPLETE':io.require(e['logical_step']==len(steps),'independent chronological steps');steps.append(e)
                io.require(len(steps)==c['total_steps'],'source step count');family.append((c,steps))
            for ia,ib in combinations(range(4),2):
                ca,a=family[ia];cb,b=family[ib];node=tuple(ca[k] for k in ('cohort','group','task','context','acquisition_action'));pid=io.digest([node,ia,ib]);r=register[pid]
                io.require(r['source_case_sha256']==[io.digest(ca),io.digest(cb)] and ca['initial']==cb['initial'],'independent actual source provenance')
                at=None
                for j in range(min(len(a),len(b))):
                    if struct.pack('<4f',*a[j]['command'])!=struct.pack('<4f',*b[j]['command']):at=j;break
                    io.require(a[j]['after']==b[j]['after'],'independent common factual prefix')
                io.require(at==r['first_difference'],'independent first actual divergence')
                expected=literal(r,a,b,matrices[r['group']]);old_audit.equal(expected,windows[index:index+6]);index+=6
        io.require(next(outer,None) is None and index==5832,'complete independent horizon population')
        for p in panels:
            selected=[r for r in windows if r['horizon']==p['horizon'] and all((tuple(r[k]) if k=='rates' else r[k])==(tuple(v) if k=='rates' else v) for k,v in zip(p['axes'],p['values']))]
            io.require(p['registered']==len(selected) and p['statuses']==dict(Counter(r['status'] for r in selected)),'all horizon panel denominators')
            actual=[r for r in selected if r['status']=='COMPLETE_FACTUAL_WINDOW'];io.require(len(actual)==p['available'] and len(set(r['group'] for r in actual))==p['independent_groups'],'actual completed-window support')
            if actual:
                w=old_audit.weights(actual)
                for kind in main.METHODS:old_audit.equal(sum(float(q)*r['mse'][kind] for q,r in zip(w,actual)),p['mse'][kind])
                old_audit.equal(sum(float(q)*(r['z_gripper_difference_steps']>0) for q,r in zip(w,actual)),p['any_z_gripper_difference_weighted_fraction'])
                old_audit.equal(sum(float(q)*10*sum(x*x for x in r['actual_endpoint_difference_xy'])**.5 for q,r in zip(w,actual)),p['mean_actual_endpoint_L2_mm'])
            else:io.require(all(v is None for v in p['mse'].values()) and p['mean_actual_endpoint_L2_mm'] is None,'no zero imputation')
        io.require(len(panels)==2214,'all predefined horizon strata')
    complete=sum(r['status']=='COMPLETE_FACTUAL_WINDOW' for r in windows);io.require(complete==receipt['available_windows'],'complete numerical cost')
    result=dict(integrity='PASSED',registered_windows=5832,independent_frozen_matrix_file_reads=9,independent_frozen_matrix_evaluations=complete,
        independent_deterministic_reference_evaluations=2*complete,main_window_extraction_and_panel_math_disabled=True,
        independent_literal_scalar_math=True,shared_old_source_parser_and_numeric_tolerance_disclosed=True,guard=guard,
        new_physics=0,new_fits=0,online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,not_native_or_final_qualification=True)
    io.write(out/'audit.json',result);return result
