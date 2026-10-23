"""One frozen FIT-only pass: saved linear matrices and all hypothetical queries."""
from collections import defaultdict
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import numpy as np

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.analysis import linear_command_preflight_io_v1 as allocation
from src.analysis import observable_history_io_v1 as io
from src.probe import linear_command_preflight_v1 as core
from src.probe import response_training_controls_v1 as old
from src.probe.observable_history_model_v1 import HistoryTrajectory, states


def banks():
    public=io.read(allocation.SOURCE/'fit_public.json')
    io.require(public['schema']=='RESPONSE_TRAINING_CONTROLS_FIT_V1' and len(public['entries'])==6,'strict FIT export')
    result={}; ids=set()
    for entry in public['entries']:
        key=entry['source_bank'],entry['task']; ts=[HistoryTrajectory.from_dict(t) for t in entry['trajectories']]
        io.require(key not in result and len(ts)==24,'complete source/task bank')
        for t in ts:
            parts=t.trajectory_id.split('/')
            io.require(t.split=='TRAIN' and len(parts)==5 and parts[0]=='TRAIN' and 0<=int(parts[1])<12
                       and parts[2]==t.task==key[1] and parts[3] in ('NOMINAL','RANDOM') and parts[4]==key[0]
                       and t.trajectory_id not in ids and len(t.commands)>=3,'FIT-only complete unique real history')
            ids.add(t.trajectory_id)
        result[key]=ts
    io.require(len(ids)==144,'complete FIT population')
    return result


def run():
    started=perf_counter_ns(); manifest=allocation.make_manifest(); folder=allocation.OUTPUT
    allowed=[ROOT/n for n in manifest['input_sha256']]
    with allocation.numeric_guard(allowed) as counts:
        selected,_=allocation.source_files(); data=banks(); details=[]; models={}; geometry={}; bounds={}
        for key,entry in selected.items():
            raw=io.read(allocation.SOURCE/'training'/entry['file']); m=core.LinearCommandModel.from_saved(raw)
            ts=data[entry['source'],entry['task']]
            x=np.concatenate([old.feature_array(t,'F20' if m.feature=='H10' else m.feature)[:,3:13]
                              if m.feature=='H10' else old.feature_array(t,m.feature) for t in ts])
            weights=np.concatenate([np.repeat(1/(len(t.commands)-2),len(t.commands)-2) for t in ts])
            a=np.c_[np.ones(len(x)),(x-m.mean)/m.scale]*np.sqrt(weights[:,None])
            sl=core.COMMAND_SLICES[m.feature]; cols=(1+sl.start,2+sl.start)
            g=core.design_geometry(a,cols); j=m.command_matrix(); js=np.linalg.svd(j[:,:2],compute_uv=False)
            models[key]=m; geometry[key]=g
            sent=np.concatenate([np.asarray(t.commands)[2:] for t in ts]); bounds[key]=sent.min(axis=0),sent.max(axis=0)
            details.append({'model_key':key,'source':entry['source'],'task':m.task,'feature':m.feature,'source_model_sha256':entry['sha256'],
                'state_independent_command_matrix_m':j.tolist(),'xy_singular_values_m':js.tolist(),
                'xy_condition':None if js[-1]==0 else float(js[0]/js[-1]),'xy_determinant_m2':float(np.linalg.det(j[:,:2])),
                'training_trajectories':24,'training_query_positions':len(x),'rank':g['rank'],'columns':g['columns'],
                'design_singular_values':g['singular_values'].tolist(),'rank_tolerance':g['rank_tolerance'],
                'design_condition':g['condition'],'nuisance_rank':g['nuisance_rank'],
                'conditional_xy_rank':g['conditional_command_rank'],
                'conditional_xy_singular_values':g['conditional_command_singular_values'].tolist(),
                'command_axis_min':bounds[key][0].tolist(),'command_axis_max':bounds[key][1].tolist(),
                'physical_qualification':False,'probability_guarantee':False})
        io.write(folder/'model_geometry.json',details)
        totals={'query_positions':0,'model_query_pairs':0,'candidate_model_pairs':0,'unique_trajectories':144,'model_trajectory_pairs':432}
        summaries=[]
        with gzip.open(folder/'queries.jsonl.gz','xb') as handle:
            for (source,task),ts in data.items():
                keys=[k for k,e in selected.items() if (e['source'],e['task'])==(source,task)]
                io.require(len(keys)==3,'all three linear feature references')
                for t in ts:
                    s=states(t); cells={k:[] for k in keys}; parts=t.trajectory_id.split('/')
                    for step in range(2,len(t.commands)):
                        q=core.make_query(task,step,s[step-2:step+1],t.commands[step]); output={}
                        for key in keys:
                            m=models[key]; comparison=m.compare(q); low,high=bounds[key]
                            baseline=core.feature_vector(q,m.feature,q.baseline_command)
                            for candidate,c in zip(comparison['candidates'],q.candidates):
                                difference=np.r_[0.,(core.feature_vector(q,m.feature,c.command)-baseline)/m.scale]
                                diagnostic=core.query_geometry(geometry[key],difference)
                                diagnostic['outside_command_axis_box']=bool(np.any(np.asarray(c.command)<low-1e-12) or np.any(np.asarray(c.command)>high+1e-12))
                                candidate['design_geometry']=diagnostic
                                cells[key].append((candidate['same_as_baseline'],diagnostic['outside_command_axis_box'],
                                    diagnostic['row_span_relative_residual'],diagnostic['weighted_design_leverage'],
                                    float(np.linalg.norm(candidate['predicted_difference_m']))))
                            output[key]=comparison
                        row={'case_id':t.trajectory_id,'source':source,'group':int(parts[1]),'context':parts[3],
                             'query':q.to_dict(),'models':output}
                        handle.write((json.dumps(row,separators=(',',':'),allow_nan=False)+'\n').encode())
                        totals['query_positions']+=1; totals['model_query_pairs']+=3; totals['candidate_model_pairs']+=12
                    for key,values in cells.items():
                        nonzero=[v for v in values if v[2] is not None]
                        summaries.append({'case_id':t.trajectory_id,'source':source,'task':task,'group':int(parts[1]),'context':parts[3],
                            'model_key':key,'query_positions':len(t.commands)-2,'candidates':len(values),'zero_candidates':sum(v[0] for v in values),
                            'outside_command_axis_box':sum(v[1] for v in values),'nonzero_candidates':len(nonzero),
                            'mean_row_span_relative_residual':None if not nonzero else float(np.mean([v[2] for v in nonzero])),
                            'max_row_span_relative_residual':None if not nonzero else max(v[2] for v in nonzero),
                            'mean_weighted_design_leverage':None if not nonzero else float(np.mean([v[3] for v in nonzero])),
                            'max_weighted_design_leverage':None if not nonzero else max(v[3] for v in nonzero),
                            'mean_predicted_contrast_norm_m':float(np.mean([v[4] for v in values])),
                            'max_predicted_contrast_norm_m':max(v[4] for v in values)})
        io.write(folder/'trajectory_summaries.json',summaries)
        io.require(len(details)==18 and len(summaries)==432 and totals=={'query_positions':13402,'model_query_pairs':40206,
                   'candidate_model_pairs':160824,'unique_trajectories':144,'model_trajectory_pairs':432}
                   and not any(counts.values()),'complete preflight/zero forbidden operations')
        allocation.load_manifest()
        io.write(folder/'completion.json',{'status':'COMPLETE_FOR_INDEPENDENT_AUDIT','counts':totals,'models':18,
            'new_model_fits':0,'new_environment_steps':0,'new_all_resets':0,'new_physical_frames':0,'new_online_llm_api_calls':0,
            'design_svd_computations':54,'xy_matrix_svd_computations':18,'optimizer_updates':0,'guard':counts,
            'wall_ns':perf_counter_ns()-started,'manifest_id':manifest['manifest_id'],
            'artifact_sha256':{n:io.sha(folder/n) for n in ('model_geometry.json','queries.jsonl.gz','trajectory_summaries.json')},
            'physical_qualification':False,'task_benefit':False})
    print(json.dumps({'status':'COMPLETE_FOR_INDEPENDENT_AUDIT',**totals}))


if __name__=='__main__':
    try: run()
    except BaseException as error:
        if allocation.OUTPUT.exists(): io.write(allocation.OUTPUT/'failure.json',{'type':type(error).__name__,'message':str(error),'no_automatic_retry':True})
        raise
