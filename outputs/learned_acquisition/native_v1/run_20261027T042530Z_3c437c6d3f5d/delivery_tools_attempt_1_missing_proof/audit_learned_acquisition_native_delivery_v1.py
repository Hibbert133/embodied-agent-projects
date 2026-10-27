"""Separate literal descriptive statistics check; all cases remain in denominators."""
from pathlib import Path
from time import perf_counter_ns
import gzip,json,sys
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects');sys.path.insert(0,str(ROOT))
from src.analysis import learned_acquisition_native_io_v1 as a
from src.analysis.release_learning_guard_v1 import read_only
io=a.io;path=Path(sys.argv[1]).resolve();m=a.checked(path);run=path.parent;out=run/'result_delivery';start=perf_counter_ns();guard={};fields=0


def close(x,y):
    global fields
    fields+=1
    if x is None or y is None:assert x is y
    elif isinstance(x,(int,float)) and not isinstance(x,bool):assert abs(x-y)<=1e-10*(1+abs(x))
    else:assert x==y


with read_only(guard):
    receipt=io.read(out/'descriptive_analysis_receipt.json')
    for n,h in receipt['artifact_sha256'].items():assert io.sha(out/n)==h
    rows=list(io.rows(run/'native/cases.jsonl.gz'));compact=io.read(out/'all_native_cases.json');results=io.read(out/'results.json')
    assert len(rows)==len(compact)==54
    for real,saved in zip(rows,compact):
        for k,v in saved.items():close(real[k],v)
    close([r for r in compact if not r['success']],io.read(out/'all_native_failures.json'))
    for program in a.PROGRAMS:
        selected=[r for r in rows if r['program']==program];s=results['programs'][program]
        close(s['n'],18);close(s['success'],sum(bool(r['success']) for r in selected));close(s['mean_deadline_loss'],sum(r['deadline_loss'] for r in selected)/18)
        for name,key in (('total_deadline_loss','deadline_loss'),('actual_steps','total_steps'),('actual_fixed_policy_queries','policy_queries'),('movement_steps','movement_steps'),('measurement_steps','measurement_steps'),('live_model_calls','live_model_calls')):close(s[name],sum(r[key] for r in selected))
    pairs=io.read(out/'all_paired_differences.json');assert len(pairs)==18;diff=[];units=set()
    for pair in pairs:
        unit=tuple(pair['unit']);assert unit not in units;units.add(unit)
        selected={r['program']:r for r in rows if a.unit_key(r)==unit};x=selected['LEARNED_JOINT_BANK0'];y=selected['LEGACY_REFERENCE']
        d=x['deadline_loss']-y['deadline_loss'];diff.append(d);close(pair['loss_difference'],d)
        close(pair['reference_success'],y['success']);close(pair['learned_success'],x['success'])
    close(results['paired_descriptive']['total_difference'],sum(diff));close(results['paired_descriptive']['mean_difference'],sum(diff)/18)
    close(results['paired_descriptive']['worse'],sum(d>0 for d in diff));close(results['paired_descriptive']['better'],sum(d<0 for d in diff));close(results['paired_descriptive']['tie'],sum(d==0 for d in diff))
    for cell in io.read(out/'native_group_task_context_cells.json'):
        selected=[r for r in rows if all(r[k]==cell[k] for k in ('group','task','context','program'))];close(len(selected),1);close(cell['mean_deadline_loss'],selected[0]['deadline_loss']);close(cell['success'],int(selected[0]['success']))
    source=io.read(run/'training_signal/case_signal.json');assert len(source)==648
    for cell in io.read(out/'source_future_cells.json'):
        selected=[r for r in source if all(r['spec'][k]==v for k,v in zip(cell['axes'],cell['values']))]
        close(cell['registered'],len(selected));close(cell['available'],sum(r['future'] is not None for r in selected))
        for k in ('error','command_energy','motion_energy','alignment'):
            group_means=[]
            for group in cell['groups']:
                live=[r for r in selected if r['spec']['group']==group['group'] and r['future'] is not None]
                value=None if not live else sum(r['future']['means'][k] for r in live)/len(live)
                close(group['means'][k],value)
                if value is not None:group_means.append(value)
            close(cell['equal_group_means'][k],None if not group_means else sum(group_means)/len(group_means))
    old_stats=io.ROOT/m['config']['source_A1_run']/'results/statistics.json'
    close(io.sha(old_stats),'d567b1a827b11edb1237b20f59d554fc1cf1a91733adc58b8b614e370c7826a4')
io.write(out/'independent_descriptive_audit.json',dict(integrity='PASSED',independent_fields=fields,all54_native_and648_source_cases_retained=True,
    source_old_statistics_sha256=io.sha(old_stats),guard=guard,wall_ns=perf_counter_ns()-start,new_physics=0,new_model_fits=0,online_LLM_API_calls=0))
print(dict(integrity='PASSED',independent_fields=fields))
