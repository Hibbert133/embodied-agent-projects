"""Version full record arithmetic for own-history model deployment, not simulation."""
from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
s=(ROOT/'src/analysis/occam_reference_train_audit_v4.py').read_text(encoding='utf8')
s=s[:s.index('\ndef audit(path,phase):')]
s=s.replace('occam_reference_train_io_v3','occam_reference_qualification_io_v1').replace('occam_train_envelope_v2','occam_qualification_envelope_v1')
s=s.replace('from src.probe.occam_training_behavior_v1 import BehaviorProvider','from src.probe.occam_qualification_program_v1 import program_spec')
s=s.replace('from src.analysis.occam_training_data_v1 import project','from src.analysis.occam_qualification_math_audit_v1 import audit_windows')
s=s.replace('occam_training_program_v1 as actor','occam_qualification_program_v1 as actor')
left=s.index('    p=BehaviorProvider(a.schedule(spec))');right=s.index("    same(cursor,len(public))",left)
s=s[:left]+"    p=a.provider(spec)\n    result=actor.run_program(spec['task'],StepObservation(**case['initial']),spec['planned_boundary'],spec['program'],a.nominal(spec),p,fixed,step,emit)\n"+s[right:]
s=s.replace("    same(case['ledger_before'],ledger);", "    legacy=program_spec(spec['program'])['kind']=='LEGACY'\n    same(case['ledger_before'],ledger);",1)
s=s.replace("pi_count=0;rate=.5;", "pi_count=0;raw_count=0;rate=.5;")
left=s.index("                if p['raw_policy'] is not None:");right=s.index('                command=e',left)
s=s[:left]+'''                if p['raw_policy'] is not None:
                    raw_count+=1
                    if legacy:
                        controller=local[p['decision_sequence']]['public_payload']['controller'];raw=np.asarray(p['raw_policy'],float)
                        manual=raw.copy();manual[:2]=np.array(controller['matrix_xy'],float)@raw[:2]+np.array(controller['offset'][:2],float)
                        manual=np.clip(manual,-1,1).astype(np.float32)
                        io.require(np.allclose(manual,p['command'],atol=1e-7,rtol=0),'independent original C8 command map')
                    else:
                        io.require(pi_pending is not None and p['decision_sequence']==pi_pending['sequence'],'saved PI consumed')
                        q=pi_pending['saved_plan']['pi_plan'];same(q['query']['time_constant_s'],rate)
                        integral,_=audit_pi(q,p['command'],integral,spec['task'],len(steps),current,p['raw_policy']);pi_count+=1
                else:io.require(p['phase'] in ('REPOSITION','WARM_PROBE','FIXED_PROBE'),'missing fixed policy')
'''+s[right:]
left=s.index('                ordinal=len(decisions);schedule=a.schedule(spec)');right=s.index("            elif name=='RATE_PLAN':",left)
s=s[:left]+"                decisions.append(p)\n"+s[right:]
left=s.index("    same(case['policy_queries'],pi_count);");right=s.index('    refs=[];bylabel={}',left)
s=s[:left]+'''    same(case['policy_queries'],raw_count)
    if not legacy:
        same(sum(m['deadline_charge_steps'] for m in costs),case['deadline_loss'])
        io.require(costs and costs[0]['start_at']==0 and costs[-1]['end_at']==len(steps) and costs[-1]['terminal'],'complete cost coverage')
        for left,right in zip(costs,costs[1:]):same(left['end_at'],right['start_at']);io.require(not left['terminal'],'continued terminal')
    else:io.require(not costs and not decisions and not feedback,'legacy references are not model-window programs')
'''+s[right:]
s=s.replace("    if any(e['agent_event']=='TASK_MEMORY_RETURN' for e in public):expected+=['POST_ACQUISITION']", "    if any(e['agent_event']=='RELOCATION_EVIDENCE' for e in public):expected+=['POST_RELOCATION']\n    if any(e['agent_event'] in ('TASK_MEMORY_RETURN','POST_MOVE_TASK_ENTRY') for e in public):expected+=['POST_ACQUISITION']")
left=s.index("    same(case['full_feedback_windows'],0);");s=s[:left]+'''    same(len(decisions),case['performance_windows']);same(len(feedback),len(decisions))
    for d,f in zip(decisions,feedback):same(f['decision_sequence'],d['sequence'])
    return ledger,steps,public,bylabel


'''
s+='''def _literal_model_check(spec,public):
    from contextlib import ExitStack
    from unittest.mock import patch
    from src.probe import occam_qualification_provider_v1 as providers
    from src.probe import occam_performance_core_v1 as online
    settings=program_spec(spec['program']);bank=None
    if settings['kind']=='TRAINED':bank=io.read(a.TRAIN/'learning'/(settings['bank']+'_raw.json'))
    def denied(*args,**kwargs):raise AssertionError('online model/actor forbidden in independent arithmetic')
    with ExitStack() as stack:
        for obj,name in ((providers.TrainedProvider,'declare'),(providers.TrainedProvider,'feedback'),
            (providers.FixedRateProvider,'declare'),(actor,'run_program'),(online,'forecast'),(online,'update'),(online,'basis_forward')):
            stack.enter_context(patch.object(obj,name,denied))
        return audit_windows(spec['program'],public,bank,a.config()['prediction_constant'])


def audit(path,phase):
    from src.analysis.release_learning_guard_v1 import read_only
    path=Path(path).resolve();manifest=a.checked(path);out=path.parent/phase.lower();summary=io.read(out/'summary.json');done=io.read(out/'completion.json')
    io.require(summary['status']==done['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT','complete allocated population before qualification')
    for n,h in done['artifact_sha256'].items():same(io.sha(out/n),h,'immutable complete cohort '+n)
    start=perf_counter_ns();guard={};caps=a.limits(phase);count=Counter();panels=[];prefix={};post={};unit=None
    outer=groupby(io.rows(out/'events.jsonl.gz'),key=lambda row:tuple(row[k] for k in a.KEYS))
    priv=groupby(io.rows(out/'witnesses.jsonl.gz'),key=lambda row:tuple(row[k] for k in a.KEYS));cases=iter(io.rows(out/'cases.jsonl.gz'))
    previous=(0,0,-1,-1);ledger=dict(counts={},by_phase={})
    with read_only(guard,max_solve=caps['audit_solve_max'],max_cold_fits=caps['audit_c4_c8_refits_max']), \\
        gzip.open(out/'prequential_windows.jsonl.gz','xt',encoding='utf8') as diagnostics:
        for spec in a.population(phase):
            case=next(cases);ek,ev=next(outer);pk,pv=next(priv);same(ek,a.key(spec));same(pk,ek);events=list(ev);private=list(pv)
            previous=bind_case(manifest,spec,case,events,private,previous)
            ledger,steps,public,witnesses=reconstruct(spec,case,events,private,ledger)
            queries=replay(spec,case,public,steps);math_result=_literal_model_check(spec,public)
            same(math_result['updates'],case['full_feedback_windows']);same(math_result['updates'],case['filter_update_attempts'])
            count.update(executions=1,control_steps=len(steps),audit_fixed_policy_queries=queries,
                audit_filter_updates=math_result['updates'],independent_batch_solves=math_result['batch_solves'],observed_windows=math_result['windows'],
                actual_c4_c8_fit_attempts=case.get('c4_c8_fit_attempts',0),actual_c4_c8_optimizer_nfev=case.get('c4_c8_optimizer_nfev',0))
            fits=case['legacy_fit_accounting']
            same(fits.get('fit_intents',0),case.get('c4_c8_fit_attempts',0));same(fits.get('fit_results',0),case.get('c4_c8_fit_results',0))
            same(fits.get('optimizer_nfev',0),case.get('c4_c8_optimizer_nfev',0))
            settings=program_spec(spec['program']);next_unit=(spec['group'],spec['task'],spec['context'])
            if next_unit!=unit:prefix.clear();post.clear();unit=next_unit
            source='C8' if settings['kind']=='LEGACY' else 'RAW'
            def physical_same(left,right,n):
                io.require(len(left)>=n and len(right)>=n,'actual common segment length')
                for l,r in zip(left[:n],right[:n]):
                    for field in ('command','raw_policy','after','executed_action_oracle','simulation_time_after','noise_cursor_after'):same(l[field],r[field],'common physical segment '+field)
            if source in prefix:
                ref=prefix[source];io.require(compare_witnesses(ref[1]['INITIAL']['witness'],witnesses['INITIAL']['witness'])['comparison_equal'],'same-source controlled initial state')
                n=min(spec['planned_boundary'],len(steps),len(ref[0]));physical_same(ref[0],steps,n);count['common_prefix_pairs']+=1
            else:prefix[source]=(steps,witnesses)
            if settings['kind']!='LEGACY':
                action=settings['action'];entry=witnesses.get('POST_ACQUISITION')
                if action in post:
                    ref_steps,ref_entry=post[action];same(entry is None,ref_entry is None,'shared acquisition availability')
                    if entry is not None:
                        same(entry['logical_step'],ref_entry['logical_step']);physical_same(ref_steps,steps,entry['logical_step'])
                        io.require(compare_witnesses(entry['witness'],ref_entry['witness'])['comparison_equal'],'common acquisition end full native/RNG state')
                        count['common_acquisition_pairs']+=1
                    else:count['early_end_acquisition_pairs']+=1
                else:post[action]=(steps,entry)
            for value in math_result['diagnostics']:diagnostics.write(json.dumps({**spec,**value},separators=(',',':'),allow_nan=False)+'\\n')
            panels.append({**spec,'success':case['success'],'deadline_loss':case['deadline_loss'],'total_steps':len(steps),
                'boundary_applied':case['boundary_applied'],'performance_windows':case['performance_windows'],'filter_updates':case['full_feedback_windows'],
                'mse':math_result['mse'],'constant_mse':math_result['constant_mse'],'prediction_missing_reason':math_result['missing_reason'],
                'c4_c8_fit_attempts':case.get('c4_c8_fit_attempts',0),'c4_c8_optimizer_nfev':case.get('c4_c8_optimizer_nfev',0)})
    io.require(next(cases,None) is None and next(outer,None) is None and next(priv,None) is None,'exact allocation and all original records consumed')
    same(count['executions'],len(a.population(phase)));same(count['control_steps'],summary['control_steps']);same(ledger,summary['lifecycle'])
    same(previous[0],summary['events']);same(previous[1],summary['private_records'])
    for key,limit in (('audit_fixed_policy_queries','audit_policy_queries_max'),('audit_filter_updates','online_filter_updates_max'),
        ('actual_c4_c8_fit_attempts','c4_c8_fit_attempts_max'),('actual_c4_c8_optimizer_nfev','c4_c8_optimizer_nfev_max')):io.require(count[key]<=caps[limit],'full-population numerical/query budget '+key)
    for program in a.PROGRAMS:
        if program_spec(program)['kind']=='TRAINED':io.require(any(p['program']==program and p['performance_windows'] for p in panels),'native model execution coverage '+program)
    result=dict(integrity='PASSED',phase=phase,manifest_id=manifest['manifest_id'],counts=dict(count),ledger=ledger,guard=guard,panels=panels,
        prequential_windows_sha256=io.sha(out/'prequential_windows.jsonl.gz'),shared_actor_policy_and_strict_feature_extraction_disclosed=True,
        independent_scalar_filter_and_batch_network_arithmetic=True,independent_physics_resimulation=False,
        new_environment_interactions=0,new_neural_training=0,online_LLM_API_calls=0,
        task_benefit_or_paper_qualification=False,wall_ns=perf_counter_ns()-start)
    io.write(out/'audit.json',result);a.checked(path);return {k:v for k,v in result.items() if k!='panels'}
'''
compile(s,'occam_reference_qualification_audit_v1.py','exec')
p=ROOT/'src/analysis/occam_reference_qualification_audit_v1.py';p.write_text(s,encoding='utf8',newline='\n')
print('created full record-only deployment audit',flush=True)
