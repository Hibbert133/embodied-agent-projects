"""Independent memory-reset population audit, one unit at a time."""
from pathlib import Path
from collections import Counter
from time import perf_counter_ns
from src.analysis import memory_reset_io_v1 as allocation
from src.analysis import memory_reset_audit_v1 as core
from src.probe import memory_reset_program_v1 as actor
io=allocation.io;same=core.same
END=object()


class JournalReader:
    def __init__(self,rows,identity):
        self.rows=iter(rows);self.identity=identity;self.count=0;self.stamp=-1

    def take(self):
        row=next(self.rows,END);io.require(row is not END,'premature journal end')
        same(row['sequence'],self.count);io.require(row['saved_ns']>=self.stamp,'journal chronology')
        for k,v in self.identity.items():same(row[k],v,'journal identity')
        self.count+=1;self.stamp=row['saved_ns'];return row

    def finish(self):io.require(next(self.rows,END) is END,'extra unassigned journal row')


def case_chunk(spec,case,events,private):
    same({k:case[k] for k in allocation.KEYS},spec);same(case['event_start_sequence'],events.count)
    stop=case['event_end_sequence_exclusive'];io.require(type(stop) is int and stop>=events.count,'invalid case event boundary')
    chunk=[]
    while events.count<stop:
        row=events.take();same({k:row[k] for k in allocation.KEYS},spec);chunk.append(row)
    marker=events.take();same(marker['event'],'CASE_COMPLETE');same({k:marker[k] for k in allocation.KEYS},spec)
    same(marker['case_record_sha256'],io.digest(case),'case boundary record digest')
    priv=[]
    for _ in case['state_witness_refs']:
        row=private.take();same({k:row[k] for k in allocation.KEYS},spec,'borrowed witness from another execution');priv.append(row)
    return chunk,priv


def compute(path,cohort):
    path=Path(path).resolve();m=allocation.checked(path);out=path.parent/cohort.lower();start=perf_counter_ns();done=io.read(out/'completion.json')
    io.require(done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial allocation cannot pass')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'collection bytes changed '+n)
    specs=allocation.population(cohort);cases=iter(io.rows(out/'cases.jsonl.gz'));identity={k:m[k] for k in allocation.IDENTITY}
    events=JournalReader(io.rows(out/'events.jsonl.gz'),identity);private=JournalReader(io.rows(out/'witnesses.jsonl.gz'),identity)
    nominal,_=allocation.source_models();ledger={'counts':{},'by_phase':{}};counts=Counter();actual_modes=Counter()
    prefix={};local={};reloc={};unit=None;raw_full=None
    from src.analysis.continuous_state_witness_v1 import compare_witnesses
    for spec in specs:
        case=next(cases,END);io.require(case is not END,'missing allocated execution')
        next_unit=(spec['group'],spec['task'],spec['context'])
        if next_unit!=unit:
            # All ten registered arms for a unit are contiguous. No comparison
            # in v1 spans units; keep just the current unit's required prefixes.
            prefix.clear();local.clear();reloc.clear();unit=next_unit;raw_full=None
        chunk,priv=case_chunk(spec,case,events,private)
        ledger,steps,public=core.physical_audit(spec,case,chunk,priv,ledger)
        counts.update(core.replay(spec,case,public,steps,nominal[spec['task']]))
        if not actor.is_legacy(spec['program']):counts.update(core.independent_raw(spec,case,public,steps))
        counts['control_steps']+=len(steps);key='C8' if actor.is_legacy(spec['program']) else 'RAW'
        if spec['program']=='RAW_CONTINUE':raw_full=(steps,case)
        if spec['program']=='RAW_NOOP':
            io.require(raw_full is not None,'no-op comparator missing');same(len(steps),len(raw_full[0]),'no-op total length')
            for left,right in zip(steps,raw_full[0]):
                for k in ('command','raw_policy','phase','after','executed_action_oracle','simulation_time_before','simulation_time_after','noise_cursor_after','reward','info'):
                    same(left[k],right[k],'no-op entire physical/control/policy trace differs')
            for k in ('success','deadline_loss','total_steps','policy_queries','final_memory','final'):same(case[k],raw_full[1][k],'no-op final state differs')
            counts['full_noop_trace_pairs']+=1
        if key in prefix:
            ref=prefix[key];io.require(compare_witnesses(priv[0]['witness'],ref['initial']['witness'])['comparison_equal'],'initial private state differs')
            n=min(spec['planned_boundary'],len(ref['steps']),len(steps))
            for left,right in zip(steps[:n],ref['steps'][:n]):
                for k in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(left[k],right[k],'same-source physical prefix differs')
            counts['common_prefix_pairs']+=1
        else:prefix[key]={'steps':steps[:spec['planned_boundary']],'initial':priv[0]}
        if spec['program'].startswith('LOCAL_PID_'):
            rp=next((p for p in priv if p['label']=='POST_RELOCATION'),None);n=len(steps) if rp is None else rp['logical_step']
            if 'same' in reloc:
                old=reloc['same'];same(n,old['n']);same(rp is None,old['return'] is None)
                for left,right in zip(steps[:n],old['steps'][:n]):
                    for k in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(left[k],right[k],'warm/no-probe common relocation differs')
                if rp is not None:io.require(compare_witnesses(rp['witness'],old['return']['witness'])['comparison_equal'],'common pre-probe private state differs')
                counts['common_pre_probe_pairs']+=1
            else:reloc['same']={'steps':steps[:n],'return':rp,'n':n}
        if spec['program'] in ('LOCAL_PID_KEEP','LOCAL_PID_RESET_I','LOCAL_PID_REFERENCE_RESET','LOCAL_PID_REFERENCE_CARRY'):
            ret=next((p for p in priv if p['label']=='POST_ACQUISITION'),None);n=len(steps) if ret is None else ret['logical_step']
            if 'same' in local:
                old=local['same'];same(ret is None,old['return'] is None,'post-acquisition availability differs');same(n,old['n'])
                for left,right in zip(steps[:n],old['steps'][:n]):
                    for k in ('command','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(left[k],right[k],'common real local-PID acquisition differs')
                if ret is not None:io.require(compare_witnesses(ret['witness'],old['return']['witness'])['comparison_equal'],'same acquisition state/RNG differs')
                counts['common_post_acquisition_pairs']+=1
            else:local['same']={'steps':steps[:n],'return':ret,'n':n}
        if case['reference_update_applied']:actual_modes[case['reference_update_mode']]+=1
    io.require(next(cases,END) is END,'extra unallocated execution');events.finish();private.finish();summary=io.read(out/'summary.json')
    same(summary['lifecycle'],ledger);same(summary['control_steps'],counts['control_steps']);same(summary['executions'],len(specs));same(summary['events'],events.count);same(summary['private_records'],private.count)
    same(summary['c4_c8_fit_attempts'],counts.get('independent_c4_c8_refits',0));same(summary['network_guard'],{'attempted_network_calls':0});same(summary['online_LLM_API_calls'],0)
    limits=allocation.limits(cohort);io.require(counts['control_steps']<=limits['control_steps'] and ledger['counts']['reset_attempts']==limits['all_resets'] and ledger['counts']['simulation_frames_attempted']<=limits['physical_frames'],'whole phase budget')
    io.require(counts.get('independent_c4_c8_refits',0)<=limits['c4_c8_fit_attempts'],'independent replay fit budget')
    expected_pairs=18 if cohort=='SOFTWARE_NATIVE' else 54
    same(counts['full_noop_trace_pairs'],expected_pairs,'complete no-op population')
    same(counts['common_prefix_pairs'],72 if cohort=='SOFTWARE_NATIVE' else 432,'all registered shared prefixes')
    same(counts['common_pre_probe_pairs'],18 if cohort=='SOFTWARE_NATIVE' else 216,'all registered shared relocation pairs')
    same(counts['common_post_acquisition_pairs'],18 if cohort=='SOFTWARE_NATIVE' else 162,'all registered shared acquisition pairs')
    native='NOT_APPLICABLE' if cohort!='SOFTWARE_NATIVE' else 'PASSED' if counts['direct_integral_resets'] and counts['post_move_integral_resets'] and counts['full_noop_trace_pairs']==18 else 'FAILED_COVERAGE'
    return {'integrity':'PASSED','cohort':cohort,'native_software_contract':native,'executions':len(specs),'costs':dict(counts),'actual_reference_modes':dict(actual_modes),
        'collection_completion_sha256':io.sha(out/'completion.json'),'artifact_sha256':done['artifact_sha256'],'wall_ns':perf_counter_ns()-start,
        'new_environment_steps':0,'new_response_training':0,'new_online_LLM_API_calls':0,'standard_reference_not_new_algorithm':True,'publication_goal_complete':False}
