"""Independent population, saved-record, source-cache and resource audit."""
import argparse
import gzip
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
from scripts import run_strong_chronological_reference_v1 as io
from src.analysis.paired_probe_record_audit_v1 import CaseReplay,require
from src.probe.cache_acquisition_evidence_v1 import digest
from src.rollout.chronological_faults import states,blend,fraction


def population(phase):
    tasks=('push-v3','reach-v3','door-open-v3')
    if phase=='SMOKE':
        a={'matrix_xy':np.eye(2).tolist(),'bias_xy':[.12,-.08],'deadzone_xy':[0.,0.]};b={**a,'bias_xy':[-.14,.1]}
        return [{'stream':0,'family_oracle':'BIAS','schedule_oracle':'SMOKE_ABRUPT','cases':[
            {'episode':k,'task':tasks[(k+1)%3],'seed':20000+k,'fault_oracle':a if k<5 else b} for k in range(9)]}]
    require(phase=='MAIN','registered phase required');result=[]
    for replicate in range(4):
        for fi,family in enumerate(('BIAS','COLUMN_Y','DEADZONE')):
            for si,schedule in enumerate(('UNCHANGED','ABRUPT','GRADUAL')):
                stream=len(result);a,b=states(66001+stream,family)
                result.append({'stream':stream,'family_oracle':family,'schedule_oracle':schedule,'generation_seed_oracle':66001+stream,
                    'cases':[{'episode':k,'task':tasks[(k+replicate+fi+si)%3],'seed':19200+12*stream+k,
                        'fault_oracle':blend(a,b,fraction(schedule,k))} for k in range(12)]})
    return result


def case_events(path,identity):
    current=None;rows=[];prior=-1;index=0
    with gzip.open(path,'rt',encoding='utf-8') as handle:
        for line in handle:
            event=json.loads(line)
            require(event['sequence']==index and type(event['saved_ns']) is int and event['saved_ns']>=prior,'global journal order')
            require(all(event[k]==v for k,v in identity.items()),'journal identity')
            key=(event['stream'],event['episode']);prior=event['saved_ns'];index+=1
            if current is not None and key!=current:
                yield current,rows;rows=[]
            current=key;rows.append(event)
    if rows:yield current,rows


def audit(path,phase):
    started=time.perf_counter_ns();m=io.read(path);identity={k:m[k] for k in io.IDENTITY};folder=path.parent/phase.lower()
    require(digest({k:v for k,v in m.items() if k!='manifest_id'})==m['manifest_id'],'manifest digest')
    require(all(io.sha(ROOT/n)==h for n,h in m['input_sha256'].items()),'frozen source changed')
    require(m['population_oracle']=={p:population(p) for p in ('SMOKE','MAIN')},'independent population reconstruction')
    _,_,model=io.load(ROOT/m['config']['strong_source_manifest'])
    qualified=io.read(ROOT/m['config']['restore_qualification_manifest']);qa=io.read(ROOT/m['config']['restore_qualification_audit'])
    require(qa['integrity']=='PASSED' and qa['registered_restore_contract_passed'] is True and qa['manifest_id']==qualified['manifest_id']==m['restore_qualification_manifest_id'],'registered restore source qualification')
    require(qa['summary_sha256']==io.sha((ROOT/m['config']['restore_qualification_manifest']).parent/'collection/summary.json'),'qualified source bytes')
    require(m['library_source_sha256']==qualified['library_source_sha256'] and m['native_library_sha256']==qualified['native_library_sha256'] and m['policy_sha256']==qualified['policy_sha256'],'qualified runtime binding')
    require(io.sha(Path(qualified['native_library_path']))==m['native_library_sha256'],'native library changed')
    s=io.read(folder/'summary.json');completion=io.read(folder/'completion.json');limits=m['config'][phase.lower()]
    require(all(x[k]==v for x in (s,completion) for k,v in identity.items()),'summary/completion identity')
    require(s['phase']==phase and s['status']==completion['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT' and s['failure'] is None and s['computation_counters_complete'] is True,'failed/partial run cannot pass')
    require(all(io.sha(folder/n)==h for n,h in completion['artifact_sha256'].items()),'collection artifact bytes changed')
    require(s['new_api_calls']==0 and s['universal_complete_hidden_state_qualification'] is False and s['registered_restore_source_used'] is True,'scope changed')
    specs=[(stream,spec) for stream in m['population_oracle'][phase] for spec in stream['cases']]
    require(len(s['cases'])==s['source_units']==limits['units']==len(specs),'complete source population required')
    saved=[]
    for stream in m['population_oracle'][phase]:
        with gzip.open(folder/('cases_'+str(stream['stream']).zfill(2)+'.jsonl.gz'),'rt',encoding='utf-8') as handle:saved.extend(json.loads(v) for v in handle)
    require(saved==s['cases'],'per-stream cases differ from summary')
    ledger={'counts':{},'by_phase':{}};cache=None;previous_stream=None;total_events=0
    totals={k:0 for k in ('captures','restores','policy_queries','capture_ns','restore_ns','fits','nfev')}
    coverage={k:0 for k in ('warm_boundaries','cache_writes','matched_probe_prefixes','valid_update_equalities','invalid_fallback_equalities','sentinels','source_returns','branch_executions')}
    groups=iter(case_events(folder/'events.jsonl.gz',identity))
    for index,(row,(stream,spec)) in enumerate(zip(s['cases'],specs),1):
        key,events=next(groups)
        require(key==(stream['stream'],spec['episode']),'event population/order')
        require(all(e['seed']==spec['seed'] and e['task']==spec['task'] for e in events),'event owner')
        require(events[-1]['event']=='SOURCE_CASE_COMPLETE' and events[-1]['completed_source_units']==index,'completed population counter')
        require(all(row[k]==v for k,v in identity.items()) and row['phase']==phase and row['stream']==stream['stream'] and row['episode']==spec['episode'] and row['seed']==spec['seed'] and row['task']==spec['task'],'case allocation/identity')
        require(row['family_oracle']==stream['family_oracle'] and row['schedule_oracle']==stream['schedule_oracle'],'case factor allocation')
        if previous_stream!=stream['stream']:cache=None;previous_stream=stream['stream']
        replay=CaseReplay(row,spec,events,model[spec['task']],cache,ledger,limits['fresh_futures']);result=replay.audit()
        ledger=result['ledger'];cache=result['cache_after'];total_events+=len(events)
        for k in totals:totals[k]+=result[k] if k in ('fits','nfev') else result['actual'][k]
        coverage['warm_boundaries']+=int(result['warm'])
        for k in coverage:
            if k!='warm_boundaries':coverage[k]+=result[k]
    require(next(groups,None) is None,'extra cases/events')
    require(ledger==s['lifecycle'] and totals==s['counters'],'summary lifecycle/computation counts differ')
    steps=ledger['by_phase'].get('CONTROL',{}).get('simulation_completed',0)
    resets=ledger['by_phase'].get('CONTROLLED_RESET',{}).get('reset_completed',0)
    require(s['controlled_steps']==steps<=limits['maximum_environment_steps'] and s['controlled_resets']==resets==limits['units']<=limits['maximum_controlled_resets'],'physical control/reset budget')
    require(ledger['counts']['simulation_frames_attempted']==ledger['counts']['simulation_frames_completed']==500*51*resets+5*steps<=limits['maximum_simulation_frames'],'complete factory/control frame cost')
    require(ledger['counts']['reset_completed']==51*resets and s['sentinels_completed']==coverage['sentinels']==limits['sentinel_replays'],'all resets/sentinels')
    host_coverage=(coverage['warm_boundaries']>=2 and coverage['cache_writes']>0 and coverage['source_returns']==coverage['warm_boundaries'] and coverage['matched_probe_prefixes']>0 and (phase!='SMOKE' or coverage['sentinels']==1))
    require(phase!='SMOKE' or host_coverage,'registered smoke mechanical coverage not met')
    return {**identity,'phase':phase,'integrity':'PASSED','required_host_coverage':bool(host_coverage),'coverage':coverage,
        'events_checked':total_events,'source_units':len(specs),'controlled_steps':steps,'controlled_resets':resets,'lifecycle':ledger,
        'recorded_computation':totals,'audit_policy_queries':totals['policy_queries'],'audit_shared_fitter_attempts':totals['fits'],
        'audit_shared_optimizer_nfev':totals['nfev'],'summary_sha256':io.sha(folder/'summary.json'),'events_sha256':io.sha(folder/'events.jsonl.gz'),
        'new_environment_steps':0,'new_api_calls':0,'universal_complete_hidden_state_qualification':False,
        'registered_restore_source_used':True,'audit_wall_ns':time.perf_counter_ns()-started,
        'shared_dependencies':['Fixed policies','Joint numerical fitter','Controller encoder','Cache/check/source-belief mathematics','Old fault endpoint generator'],
        'scope':'Independent saved-record/noise/ledger/program/cache replay, no task Env or capture/restore execution. Physical state signatures are qualified source-generated witnesses; no universal hidden-state proof, task-value certificate or novel method.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--phase',choices=['SMOKE','MAIN'],required=True);args=parser.parse_args()
    result=audit(args.manifest.resolve(),args.phase);io.write(args.manifest.resolve().parent/(args.phase.lower()+'_audit.json'),result,exclusive=True)
    print(json.dumps({k:result[k] for k in ('phase','integrity','coverage','events_checked','controlled_steps','audit_wall_ns')}),flush=True)
