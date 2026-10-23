"""Array arithmetic on executed responses; masked missingness and signed cross terms."""
from collections import defaultdict
import numpy as np
from src.analysis import latent_response_diagnosis_io_v1 as a
io=a.io


def regimes(index,split):
    if split!='TRAIN':return ('ALL_WINDOWS','ENTRY_ONLY')
    return ('ALL_WINDOWS','ENTRY_ONLY' if index==0 else 'START_01_08' if index<=8 else 'START_09_16' if index<=16 else 'START_17_24')


def metrics(prediction,targets,mask,nominal_delta,native_delta):
    p=np.asarray(prediction,float);y=np.asarray(targets,float);m=np.asarray(mask,bool)
    io.require(p.ndim==2 and p.shape[1]==2 and len(p) in (1,8) and y.shape==(8,2) and m.shape==(8,) and m[0]
        and np.array_equal(m,np.arange(8)<int(m.sum())) and np.isfinite(p).all() and np.isfinite(y).all(),'diagnostic prediction/actual contiguous mask')
    available=min(len(p),int(m.sum()));e=p[:available]-y[:available]
    per=np.mean(e*e,axis=1);inc=np.diff(np.vstack((np.zeros((1,2)),e)),axis=0)
    diagonal=float(np.sum(inc*inc)/2);terminal=float(np.sum(e[-1]*e[-1])/2);cross=terminal-diagonal
    sent=np.asarray(nominal_delta,float)[:available];native=np.asarray(native_delta,float)[:available]
    ca=p[:available]-sent;cb=sent-native;cc=native-y[:available]
    fields={'model_minus_nominal_m2':float(np.mean(ca*ca)),'nominal_minus_native_m2':float(np.mean(cb*cb)),
        'native_minus_hand_m2':float(np.mean(cc*cc)),'twice_model_nominal_cross_m2':float(2*np.mean(ca*cb)),
        'twice_model_hand_cross_m2':float(2*np.mean(ca*cc)),'twice_nominal_hand_cross_m2':float(2*np.mean(cb*cc))}
    objective=float(np.mean(per));io.require(np.allclose(ca+cb+cc,e,atol=1e-12,rtol=1e-10) and abs(sum(fields.values())-objective)<1e-12,'observed vector/error decomposition identity')
    return {'actual_horizons':available,'model_horizons':len(p),'horizon_mse_m2':[float(per[h]) if h<available else None for h in range(8)],
        'masked_H8_objective_m2':objective if len(p)==8 else None,'H1_mse_m2':float(per[0]),'H1_rmse_m':float(np.sqrt(per[0])),
        'H8_rmse_m':float(np.sqrt(objective)) if len(p)==8 and available==8 else None,
        'increment_diagonal_energy_m2':diagonal,'increment_cross_energy_m2':cross,'terminal_error_m2':terminal,
        'H8_terminal_error_m2':terminal if len(p)==available==8 else None,'H8_increment_diagonal_energy_m2':diagonal if len(p)==available==8 else None,
        'H8_increment_cross_energy_m2':cross if len(p)==available==8 else None,**fields}


def means(rows):
    if not rows:return None
    result={}
    for key in rows[0]:
        if key in ('actual_horizons','model_horizons'):continue
        if key=='horizon_mse_m2':
            result[key]=[float(np.mean(v)) if (v:=[r[key][h] for r in rows if r[key][h] is not None]) else None for h in range(8)]
        else:
            values=[r[key] for r in rows if r[key] is not None];result[key]=float(np.mean(values)) if values else None
    return result


def trajectory_rows(case,method,checkpoint,values,features):
    out=[]
    for regime in a.REGIMES:
        if case['split']!='TRAIN' and regime.startswith('START_'):continue
        selected=[v for index,v in enumerate(values) if regime in regimes(index,case['split'])]
        out.append({**{k:case[k] for k in a.latent.KEYS},'method':method,'checkpoint':checkpoint,'regime':regime,
            'windows':len(selected),'complete_H8_windows':sum(v['H8_rmse_m'] is not None for v in selected),
            'reason':None if selected else 'NO_ACTUAL_WINDOW_IN_BIN' if values else case.get('_diagnostic_missing_reason') or ('NO_MODEL_BY_SOFTWARE_PROTOCOL' if case['split']=='SOFTWARE' else 'NO_MEASUREMENT_ENTRY'),
            'metrics':means(selected),'features':features})
    return out


def grouped(rows,detailed=True):
    cells=defaultdict(list)
    keys=('split','task','initial_kind','context','packet_kind','boundary','method','checkpoint','regime') if detailed else ('split','task','method','checkpoint','regime')
    for r in rows:
        key=tuple(r[k] for k in keys);cells[key].append(r)
    result=[]
    for key,part in cells.items():
        groups=[]
        for g in sorted({r['group'] for r in part}):
            actual=[r['metrics'] for r in part if r['group']==g and r['metrics'] is not None]
            groups.append({'group':g,'allocated':sum(r['group']==g for r in part),'available_trajectories':len(actual),'metrics':means(actual)})
        available=[g['metrics'] for g in groups if g['metrics'] is not None]
        result.append(dict(zip(keys,key))|
            {'allocated_trajectories':len(part),'available_trajectories':sum(r['metrics'] is not None for r in part),
             'independent_groups':len(groups),'available_groups':len(available),'metrics':means(available),'groups':groups})
    return result


def training_objectives(rows):
    # Unlike inferential group descriptions, this exactly matches the frozen
    # neural sampler's uniform available-trajectory then uniform-window objective.
    result=[]
    for task in io.TASKS:
        for method in a.METHODS:
            for checkpoint in (a.CHECKPOINTS if method in a.NEURAL else (None,)):
                for regime in ('ALL_WINDOWS','ENTRY_ONLY'):
                    part=[r for r in rows if (r['split'],r['task'],r['method'],r['checkpoint'],r['regime'])==('TRAIN',task,method,checkpoint,regime) and r['metrics'] is not None]
                    result.append({'task':task,'method':method,'checkpoint':checkpoint,'regime':regime,'available_trajectories':len(part),'metrics':means([r['metrics'] for r in part])})
    return result


def menu_unit(cases):
    io.require(set(cases)==set(a.reference.PROGRAMS),'whole ten-program unit, no filtered sources')
    for c in cases.values():io.require(c['deadline_loss']==(c['total_steps'] if c['success'] else 500),'full observed cutoff loss')
    losses={p:cases[p]['deadline_loss'] for p in a.MENU};best=min(losses.values());raw=losses['RAW_CONTINUE'];keep=losses['LOCAL_PID_KEEP']
    decompositions={}
    for p in a.REFERENCE_BRANCHES:
        reference=losses[p];decompositions[p]={'whole_minus_raw':reference-raw,'acquisition_keep_minus_raw':keep-raw,'reference_minus_keep':reference-keep}
        io.require(reference-raw==(keep-raw)+(reference-keep),'complete-program signed loss identity')
    c=cases['RAW_CONTINUE']
    return {**{k:c[k] for k in ('group','task','seed','context','planned_boundary')},'menu_losses':losses,'oracle_recorded_minimum_loss':best,
        'all_tied_minimizers':[p for p in a.MENU if losses[p]==best],'optimistic_raw_saving':raw-best,
        'same_acquisition_submenu_minimum_loss':min(losses[p] for p in a.ADOPTION_MENU),
        'same_acquisition_all_tied_minimizers':[p for p in a.ADOPTION_MENU if losses[p]==min(losses[q] for q in a.ADOPTION_MENU)],
        'same_acquisition_optimistic_raw_saving':raw-min(losses[p] for p in a.ADOPTION_MENU),
        'direct_C8_external_whole_program_loss':cases['DIRECT_C8']['deadline_loss'],'integral_external_whole_program_loss':cases['MOVE_INTEGRAL']['deadline_loss'],
        'decompositions':decompositions,'counterfactual_policy_or_learnability_claim':False}
