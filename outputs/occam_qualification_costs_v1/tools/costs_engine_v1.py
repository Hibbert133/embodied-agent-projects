"""Record-only lifecycle and fixed-implementation arithmetic accounting."""
from collections import Counter
from fractions import Fraction

TRAINED=('META_ADAPT','META_FROZEN','ERM_ADAPT','ERM_FROZEN')
LEGACY=('DIRECT_C8','MOVE_INTEGRAL')


def require(ok,message):
    if not ok:raise ValueError(message)


def increment(before,after):
    require(set(before)==set(after)=={'counts','by_phase'},'literal lifecycle structure')
    def difference(x,y):
        out={}
        for k in set(x)|set(y):
            a=x.get(k,0);b=y.get(k,0)
            require(type(a) is type(b) is int and 0<=a<=b,'monotone cumulative counters')
            if b!=a:out[k]=b-a
        return out
    counts=difference(before['counts'],after['counts'])
    phases={p:difference(before['by_phase'].get(p,{}),after['by_phase'].get(p,{})) for p in set(before['by_phase'])|set(after['by_phase'])}
    total=Counter()
    for p in phases.values():total.update(p)
    require(dict(total)==counts,'phase increments sum to root increment')
    return dict(counts=counts,by_phase=phases)


def classify(program):
    if program in LEGACY:return 'LEGACY'
    if '__' in program:
        name=program.split('__')[0];require(name in (*TRAINED,'PI_0125','PI_0500','PI_2000','PI_8000'),'registered same-prefix controller')
        return 'TRAINED' if name in TRAINED else 'FIXED'
    require(program in ('GLOBAL_PI_0125','GLOBAL_PI_2000','GLOBAL_PI_8000'),'registered all-time fixed controller')
    return 'FIXED'


def case_cost(case,spec):
    require(all(case[k]==v for k,v in spec.items()),'original complete case identity')
    require(case['completed'] is True and case['environment_closed'] is True and case['error'] is None and case['close_error'] is None,'complete technical case, task failures allowed')
    d=increment(case['ledger_before'],case['ledger_after_close']);n=case['total_steps'];counts=d['counts']
    require(type(n) is int and 0<=n<=500 and counts['reset_attempts']==counts['reset_completed']==51,'all factory plus controlled resets')
    require(counts['simulation_frames_attempted']==counts['simulation_frames_completed']==25500+5*n,'physical frames, no failure penalty frames')
    require(d['by_phase']['GOAL_GENERATION']['reset_attempts']==50 and d['by_phase']['CONTROLLED_RESET']['reset_attempts']==1,'factory and controlled reset split')
    require(d['by_phase'].get('CONTROL',{}).get('simulation_frames_completed',0)==5*n,'actual control physical frames')
    require(type(case['success']) is bool and case['deadline_loss']==(n if case['success'] else 500),'cutoff cost separated from physical interaction')
    policy=case['policy_queries'];w=case['performance_windows'];u=case['filter_update_attempts']
    require(all(type(x) is int and x>=0 for x in (policy,w,u)) and policy<=n and u<=w and u==case['full_feedback_windows'],'literal policy/window/update counters')
    kind=classify(spec['program']);is_model=kind=='TRAINED';sessions=int(is_model and w>0)
    require(is_model or u==0,'fixed and legacy programs cannot update the learned bank')
    if is_model and spec['program'].split('__')[0].endswith('_FROZEN'):require(u==0,'frozen model updates prohibited')
    fits=case.get('c4_c8_fit_attempts',0);nfev=case.get('c4_c8_optimizer_nfev',0);a=case['legacy_fit_accounting']
    require(fits==a.get('fit_intents',0) and nfev==a.get('optimizer_nfev',0),'recorded C4/C8 attempted fits and reported nfev')
    require(kind=='LEGACY' or fits==nfev==0,'only original legacy controls fit C4/C8')
    require(case['online_LLM_API_calls']==0 and type(case['wall_ns']) is int and case['wall_ns']>=0,'current qualification API and inclusive host wall accounting')
    model_windows=w if is_model else 0
    # From the pinned core: 3 per session, (2 forecast + 1 scoring)*4 per query,
    # 3 covariance validations per update. These are code reconstructions.
    eig=3*sessions+12*model_windows+3*u
    return dict(spec=spec,kind=kind,executions=1,control_steps=n,cutoff_loss=case['deadline_loss'],
        unexecuted_failure_penalty_steps=case['deadline_loss']-n,controlled_resets=1,all_resets=51,
        setup_frames=25500,control_frames=5*n,physical_frames=counts['simulation_frames_completed'],
        fixed_policy_queries=policy,all_provider_windows=w,trained_model_declarations=model_windows,
        trained_basis_batches=model_windows,candidate_predictions=4*model_windows,model_session_initializations=sessions,
        recorded_parameter_update_attempts=u,model_core_solve_calls_reconstructed=u,
        model_core_eigendecompositions_reconstructed=eig,independent_final_batch_solves_expected=int(is_model and u>0),
        C4_C8_fit_attempts=fits,optimizer_reported_nfev=nfev,inclusive_case_host_wall_ns=case['wall_ns'],
        online_LLM_API_calls=0,LLM_tokens=0,mean_API_call_latency_ns=None)


ADDITIVE=('executions','control_steps','cutoff_loss','unexecuted_failure_penalty_steps','controlled_resets','all_resets',
    'setup_frames','control_frames','physical_frames','fixed_policy_queries','all_provider_windows','trained_model_declarations',
    'trained_basis_batches','candidate_predictions','model_session_initializations','recorded_parameter_update_attempts',
    'model_core_solve_calls_reconstructed','model_core_eigendecompositions_reconstructed','independent_final_batch_solves_expected',
    'C4_C8_fit_attempts','optimizer_reported_nfev','inclusive_case_host_wall_ns','online_LLM_API_calls','LLM_tokens')


def add(rows):return {k:sum(r[k] for r in rows) for k in ADDITIVE}


def check_phase(rows,summary,audit):
    totals=add(rows);counts=audit['counts'];ops=audit['guard']['operation_counts']
    require(summary['status']=='COLLECTED_FOR_INDEPENDENT_AUDIT' and audit['integrity']=='PASSED','original complete audit required')
    for key,field in (('executions','executions'),('control_steps','control_steps'),('fixed_policy_queries','audit_fixed_policy_queries'),
                      ('all_provider_windows','observed_windows'),('recorded_parameter_update_attempts','audit_filter_updates'),
                      ('independent_final_batch_solves_expected','independent_batch_solves'),('C4_C8_fit_attempts','actual_c4_c8_fit_attempts'),
                      ('optimizer_reported_nfev','actual_c4_c8_optimizer_nfev')):
        require(totals[key]==counts[field],'original audited computational count '+field)
    require(totals['control_steps']==summary['control_steps'] and totals['executions']==summary['executions'],'original collection totals')
    require(totals['all_resets']==summary['lifecycle']['counts']['reset_attempts']
            and totals['physical_frames']==summary['lifecycle']['counts']['simulation_frames_completed'],'sum increments, not sum cumulative endpoints')
    require(ops['solve_attempts']==totals['recorded_parameter_update_attempts']+totals['independent_final_batch_solves_expected'],'actor-replay model solves plus independent batch solves')
    require(ops['cold_fit_attempts']==totals['C4_C8_fit_attempts'],'separate original C4/C8 replay refits')
    return dict(totals=totals,original_audit_computation_counts=counts,original_audit_guard_operations=ops,
        actual_collection_model_core=dict(network_basis_batches=totals['trained_basis_batches'],candidate_predictions=totals['candidate_predictions'],
            parameter_updates=totals['recorded_parameter_update_attempts'],solve_calls_reconstructed=totals['model_core_solve_calls_reconstructed'],
            symmetric_eigendecompositions_reconstructed=totals['model_core_eigendecompositions_reconstructed']),
        model_core_eigs_and_collection_solves_are_code_reconstructed_not_directly_instrumented=True,
        audit_actor_replay_reuses_same_core_counts=True,independent_scalar_dense_passes_do_not_add_physics=True,
        wall_intervals_not_isolated_model_latency=True,mean_LLM_API_latency=None)


def standalone_source(program,historical):
    kind=classify(program)
    if kind=='TRAINED':
        p=historical['trained_performance_banks']
        return dict(role='QUALIFIED_PERFORMANCE_BANK_SOURCE',source_controls=p['control_steps'],source_all_resets=p['all_resets'],
            source_frames=p['physical_frames'],standalone_AdamW_updates=p['per_method_standalone_AdamW_updates'],
            actual_joint_AdamW_updates=p['actual_joint_AdamW_updates'],source_is_shared_not_multiplied_in_actual_joint_total=True)
    if kind=='LEGACY':
        p=historical['C8_complete_source_study_including_training_not_additive'];train=historical['C8_nominal_training']
        return dict(role='COMPLETE_C8_SOURCE_INCLUDES_TRAINING_SUBSET',source_controls=p['control_steps'],source_all_resets=p['all_resets'],
            source_frames=p['physical_frames'],training_subset_controls=train['control_steps'],standalone_AdamW_updates=0,
            training_subset_not_added_again=True)
    return dict(role='NO_ADDITIONAL_ROBOT_CALIBRATION_DATA_FOR_THIS_FIXED_PROGRAM',source_controls=0,source_all_resets=0,source_frames=0,
                standalone_AdamW_updates=0,shared_handwritten_policy_and_prior_development_cost_not_asserted_zero=True)


def program_table(rows,historical):
    out=[]
    for program in sorted({r['spec']['program'] for r in rows}):
        selected=[r for r in rows if r['spec']['program']==program];n=len(selected);totals=add(selected);source=standalone_source(program,historical)
        out.append(dict(program=program,executions=n,observed=totals,hypothetical_standalone_source=source,
            actual_online_control_mean_exact=str(Fraction(totals['control_steps'],n)),
            standalone_source_plus_online_control_mean_exact=str(Fraction(source['source_controls']+totals['control_steps'],n)),
            resource_accounting_only_not_a_replacement_primary_metric=True))
    return out
