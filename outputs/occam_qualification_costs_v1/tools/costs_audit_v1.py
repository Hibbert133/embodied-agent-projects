"""Independent scalar cost projection; no production cost formulas called."""
from fractions import Fraction


def need(ok,message):
    if not ok:raise ValueError(message)


def verify_case(case,spec,saved):
    root={k:case['ledger_after_close']['counts'].get(k,0)-case['ledger_before']['counts'].get(k,0)
          for k in set(case['ledger_after_close']['counts'])|set(case['ledger_before']['counts'])}
    n=case['total_steps'];name=spec['program'].split('__')[0];trained=name in ('META_ADAPT','META_FROZEN','ERM_ADAPT','ERM_FROZEN')
    w=case['performance_windows'] if trained else 0;u=case['filter_update_attempts'];sessions=int(trained and w!=0)
    cov_checks=sum((3 for _ in range(sessions)),0)
    for _ in range(w):
        for candidate in range(4):cov_checks+=2+1
    cov_checks+=sum((3 for _ in range(u)),0)
    expected=dict(executions=1,control_steps=n,cutoff_loss=case['deadline_loss'],unexecuted_failure_penalty_steps=case['deadline_loss']-n,
        controlled_resets=1,all_resets=root['reset_attempts'],setup_frames=root['simulation_frames_completed']-5*n,
        control_frames=5*n,physical_frames=root['simulation_frames_completed'],fixed_policy_queries=case['policy_queries'],
        all_provider_windows=case['performance_windows'],trained_model_declarations=w,trained_basis_batches=w,candidate_predictions=4*w,
        model_session_initializations=sessions,recorded_parameter_update_attempts=u,model_core_solve_calls_reconstructed=u,
        model_core_eigendecompositions_reconstructed=cov_checks,independent_final_batch_solves_expected=int(trained and u>0),
        C4_C8_fit_attempts=case.get('c4_c8_fit_attempts',0),optimizer_reported_nfev=case.get('c4_c8_optimizer_nfev',0),
        inclusive_case_host_wall_ns=case['wall_ns'],online_LLM_API_calls=0,LLM_tokens=0,mean_API_call_latency_ns=None)
    need(saved['spec']==spec and all(saved[k]==v for k,v in expected.items()),'independent raw case cost projection')
    need(root['reset_attempts']==root['reset_completed']==51 and root['simulation_frames_completed']==25500+5*n,'independent literal lifecycle')
    return expected


def verify_programs(rows,historical,table):
    names=sorted({r['spec']['program'] for r in rows});need([r['program'] for r in table]==names,'all actual programs, aliases not duplicated')
    for item in table:
        program=item['program'];part=[r for r in rows if r['spec']['program']==program];need(item['executions']==len(part),'complete program denominator')
        fields=set(part[0])-{'spec','kind','mean_API_call_latency_ns'}
        need(set(item['observed'])==fields,'complete observed program cost columns')
        for field in fields:need(item['observed'][field]==sum(r[field] for r in part),'independent program total '+field)
        n=len(part);online=sum(r['control_steps'] for r in part);source=item['hypothetical_standalone_source']
        if program.split('__')[0] in ('META_ADAPT','META_FROZEN','ERM_ADAPT','ERM_FROZEN'):
            original=historical['trained_performance_banks'];value=original['control_steps']
            need(source['standalone_AdamW_updates']==5000 and source['actual_joint_AdamW_updates']==9000,'shared 1000 pretrain not multiplied by program count')
        elif program in ('DIRECT_C8','MOVE_INTEGRAL'):
            original=historical['C8_complete_source_study_including_training_not_additive'];value=original['control_steps']
            need(source['training_subset_controls']==historical['C8_nominal_training']['control_steps'] and source['training_subset_not_added_again'],'C8 training subset not counted twice')
        else:original={'all_resets':0,'physical_frames':0};value=0
        need(source['source_controls']==value and source['source_all_resets']==original['all_resets'] and source['source_frames']==original['physical_frames'],'independent source attribution')
        need(item['actual_online_control_mean_exact']==str(Fraction(online,n))
             and item['standalone_source_plus_online_control_mean_exact']==str(Fraction(online+value,n)),'standalone resource projection')


def verify_phase(rows,summary,audit,saved):
    names=set(rows[0])-{'spec','kind','mean_API_call_latency_ns'}
    need(set(saved['totals'])==names,'all additive quantities, no hidden missing count')
    for name in names:need(saved['totals'][name]==sum(row[name] for row in rows),'independent complete phase sum '+name)
    counts=audit['counts'];need(sum(r['control_steps'] for r in rows)==summary['control_steps']==counts['control_steps'],'independent control count')
    need(sum(r['physical_frames'] for r in rows)==summary['lifecycle']['counts']['simulation_frames_completed'],'independent physical frame count')
    need(sum(r['all_resets'] for r in rows)==summary['lifecycle']['counts']['reset_attempts'],'independent all resets')
    need(sum(r['all_provider_windows'] for r in rows)==counts['observed_windows'],'fixed windows not all neural predictions')
    need(sum(r['recorded_parameter_update_attempts'] for r in rows)==counts['audit_filter_updates'],'independent recursive update count')
