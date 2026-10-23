"""Complete-population streaming execution audit, independent numeric pass."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
from time import perf_counter_ns
from src.analysis import release_learning_io_v1 as a
from src.analysis import release_learning_record_audit_v1 as core
from src.analysis.release_learning_collect_v1 import runtime_for
from src.analysis.memory_reset_streaming_audit_v2 import JournalReader,case_chunk,compare_info
from src.analysis.continuous_state_witness_v1 import compare_witnesses
io=a.io;same=core.same;END=object()


def equal_steps(left,right):
    same(len(left),len(right),'paired trace lengths')
    for x,y in zip(left,right):
        for k in ('command','raw_policy','phase','after','executed_action_oracle','simulation_time_before','simulation_time_after','noise_cursor_after','reward'):same(x[k],y[k],'paired physical/control trace '+k)
        compare_info(x,y)


def audit(path,cohort):
    path=Path(path).resolve();m=a.checked(path);out=path.parent/cohort.lower();start=perf_counter_ns();done=io.read(out/'completion.json')
    io.require(done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','partial collection retained but cannot pass')
    for n,h in done['artifact_sha256'].items():io.require(io.sha(out/n)==h,'collected record changed '+n)
    runtime,models=runtime_for(path,cohort);same(io.read(out/'model_commitment.json')['model_artifact_sha256'],models)
    identity={k:m[k] for k in a.IDENTITY};events=JournalReader(io.rows(out/'events.jsonl.gz'),identity);private=JournalReader(io.rows(out/'witnesses.jsonl.gz'),identity)
    rows=iter(io.rows(out/'cases.jsonl.gz'));nominal,_=a.source_models();ledger=dict(counts={},by_phase={});counts=Counter();unit=None;cache={};cross_context={};rates=Counter();exposed=Counter()
    for spec in a.population(cohort):
        case=next(rows,END);io.require(case is not END,'missing registered execution')
        chunk,priv=case_chunk(spec,case,events,private);ledger,steps,public=core.physical_audit(spec,case,chunk,priv,ledger)
        counts.update(core.randomness(spec,case,chunk,public,priv));counts.update(core.replay(spec,case,public,steps,nominal[spec['task']],runtime,chunk))
        counts.update(core.numerical(spec,case,public,steps,runtime));counts['control_steps']+=len(steps)
        key=(spec['group'],spec['task'],spec['context'])
        if unit!=key:cache={};unit=key
        family='C8' if core.programs.calibrated_prefix(spec['program']) else 'RAW'
        n=min(spec['planned_boundary'],len(steps));prefix=steps[:n]
        if family in cache:
            old=cache[family];equal_steps(prefix,old['steps']);io.require(compare_witnesses(priv[0]['witness'],old['initial']['witness'])['comparison_equal'],'common initial native/Python state differs')
            counts['common_prefix_pairs']+=1
        else:cache[family]=dict(steps=prefix,initial=priv[0])
        pair=(spec['group'],spec['task'],family)
        if spec['context']=='UNCHANGED' and pair not in cross_context:cross_context[pair]=deepcopy(prefix)
        if spec['context']=='CHANGED' and family+'_context' not in cache:
            io.require(pair in cross_context,'missing unchanged-context raw prefix');equal_steps(prefix,cross_context.pop(pair));cache[family+'_context']=True;counts['cross_context_prefix_pairs']+=1
        l=case['learning']
        if l is not None:
            record=l['saved_return']['record'];action=record['action'];signature=io.digest(record);ret=next(v for v in priv if v['label']=='POST_ACQUISITION')
            if 'return/'+action in cache:
                old=cache['return/'+action];same(signature,old['record_sha256'],'same action produced different pre-release public state/history')
                io.require(compare_witnesses(ret['witness'],old['witness'])['comparison_equal'],'same acquisition produced different native/RNG endpoint');counts['common_acquisition_pairs']+=1
            else:cache['return/'+action]=dict(record_sha256=signature,witness=ret['witness'])
            if l['receiver_decision'] is not None:
                rate=l['receiver_decision']['choice']['time_constant_s'];rates[str(rate)]+=1
                exposed[str(l['release_receipt']['binding']['assigned_exposure'])]+=int(bool(record['steps']))
                counts['nonempty_released_receiver_decisions']+=int(l['release_receipt']['binding']['assigned_exposure'] and bool(record['steps']))
        relocated=next((v for v in priv if v['label']=='POST_RELOCATION'),None)
        if relocated is not None and family=='RAW':
            rp=steps[:relocated['logical_step']]
            if 'raw_relocation' in cache:
                old=cache['raw_relocation'];equal_steps(rp,old['steps']);io.require(compare_witnesses(relocated['witness'],old['witness'])['comparison_equal'],'no-probe/measured common raw movement differs')
                counts['common_raw_relocation_pairs']+=1
            else:cache['raw_relocation']=dict(steps=rp,witness=relocated['witness'])
        if cohort=='SOFTWARE_NATIVE':
            if spec['program']=='N_CONT_KEEP':cache['native_raw']=steps
            if spec['program']=='N_CONT_05':equal_steps(steps,cache['native_raw']);counts['full_noop_trace_pairs']+=1
            if spec['program']=='N_MOVE_MASK':cache['native_moved']=steps
            if spec['program'] in ('N_MOVE_FULL','N_MOVE_RANDOM'):equal_steps(steps,cache['native_moved']);counts['full_mask_release_same_rate_pairs']+=1
    io.require(next(rows,END) is END,'extra unallocated case');events.finish();private.finish();summary=io.read(out/'summary.json')
    same(summary['lifecycle'],ledger);same(summary['control_steps'],counts['control_steps']);same(summary['executions'],len(a.population(cohort)))
    same(summary['events'],events.count);same(summary['private_records'],private.count);same(summary['network_guard'],dict(attempted_network_calls=0));same(summary['online_LLM_API_calls'],0)
    limits=a.limits(cohort);same(ledger['counts']['reset_attempts'],limits['all_resets']);io.require(counts['control_steps']<=limits['control_steps']
        and ledger['counts']['simulation_frames_attempted']<=limits['physical_frames'] and counts['independent_c4_c8_refits']<=limits['audit_c4_c8_refits'],'complete phase budget')
    same(summary['c4_c8_fit_attempts'],counts['independent_c4_c8_refits'])
    native='NOT_APPLICABLE'
    if cohort=='SOFTWARE_NATIVE':
        same(counts['full_noop_trace_pairs'],18);same(counts['full_mask_release_same_rate_pairs'],36)
        io.require(all(rates[str(t)]>0 for t in (.125,.5,2.,8.)) and counts['actual_exposure_draws']>0 and exposed['True']>0 and exposed['False']>0,'native rate/exposure coverage')
        native='PASSED'
    result=dict(integrity='PASSED',cohort=cohort,native_software_contract=native,executions=len(a.population(cohort)),costs=dict(counts),
        actual_rates=dict(rates),actual_nonempty_exposures=dict(exposed),artifact_sha256=done['artifact_sha256'],
        completion_sha256=io.sha(out/'completion.json'),model_artifact_sha256=models,new_environment_steps=0,new_response_model_training=0,
        online_LLM_API_calls=0,wall_ns=perf_counter_ns()-start,publication_goal_complete=False)
    io.write(out/'audit.json',result);return result
