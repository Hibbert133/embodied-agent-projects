"""Standard undiscounted sequential DR algebra, not a learned robot method.

No file reader, environment, policy, fitted-Q learner or deployment selector.
Actual data admission needs a separate protocol and source audit.
"""
from fractions import Fraction
import math

SCHEMA='STANDARD_SEQUENTIAL_DR_EPISODE_V1'
ROOT_FIELDS={'schema','episode_id','group_id','target_program_id','source_prefix_id','target_prefix_id',
    'target_fit_groups','nuisance_fit_groups','nuisance_model_id','Q_scope','probability_scope','support_scope',
    'prefix','segments','declarations','deadline_loss','total_actual_steps','success'}
SEGMENT_FIELDS={'start_step','actual_steps','loss_charge_steps','terminal','success','before_history_sha256',
                'after_history_sha256','choice_saved_ns','result_saved_ns'}
DECLARATION_FIELDS={'segment_index','feature_cutoff_step','source_history_sha256','computed_ns',
                    'actions','executed_index','behavior_probabilities','target_probabilities','Q_remaining_loss'}


def require(ok,message):
    if not ok:raise ValueError(message)


def number(value):
    require(type(value) in (str,int,float),'literal finite real scalar, no bool')
    if type(value) is float:
        require(math.isfinite(value),'finite scalar');return Fraction.from_float(value)
    try:return Fraction(value)
    except (ValueError,ZeroDivisionError) as error:raise ValueError('finite rational scalar') from error


def identifier(value):
    require(type(value) is str and len(value)==64 and all(x in '0123456789abcdef' for x in value),'complete version hash')


def groups(value):
    require(type(value) is list and all(type(x) is str and x for x in value) and len(set(value))==len(value),'unique independent group identifiers')


def probabilities(value,n):
    require(type(value) is list and len(value)==n,'all legal action probabilities')
    p=[number(x) for x in value]
    require(all(0<=x<=1 for x in p) and sum(p)==1,'exact normalized probabilities; no silent renormalization')
    return p


def source_costs(row):
    require(type(row) is dict and set(row)==ROOT_FIELDS and row['schema']==SCHEMA,'strict standard DR input schema')
    require(type(row['episode_id']) is str and row['episode_id'] and type(row['group_id']) is str and row['group_id'],'case/group identity')
    for k in ('target_program_id','source_prefix_id','target_prefix_id','nuisance_model_id'):identifier(row[k])
    require(row['source_prefix_id']==row['target_prefix_id'],'actual shared prefix required, not a restored or substituted state')
    groups(row['target_fit_groups']);groups(row['nuisance_fit_groups'])
    require(row['group_id'] not in row['target_fit_groups']+row['nuisance_fit_groups'],'target and Q fitting independent of evaluation group')
    require(row['Q_scope']=='REMAINING_TARGET_PROGRAM_CUTOFF_CHARGE','a local window target is not complete Q')
    require(row['probability_scope']=='WORKING_CONDITIONAL_ACTION_KERNEL','declare conditional action-kernel semantics')
    require(row['support_scope'] in ('STRUCTURAL_FULL_SUPPORT_DECLARED','OBSERVED_ONLY','UNVERIFIED'),'explicit support status')
    p=row['prefix'];require(type(p) is dict and set(p)=={'actual_steps','loss_charge_steps','terminal','success'},'explicit prefix costs and terminal status')
    require(type(p['actual_steps']) is int and 0<=p['actual_steps']<=500 and type(p['loss_charge_steps']) is int
            and type(p['terminal']) is type(p['success']) is bool,'literal prefix accounting')
    segments=row['segments'];require(type(segments) is list and len(segments)<=64,'finite source decision sequence')
    require(p['terminal']==(len(segments)==0) and (not p['success'] or p['terminal']),'no continuation after prefix termination')
    require(p['terminal'] or p['actual_steps']<500,'no new decisions after the cutoff')
    require(p['loss_charge_steps']==(500 if p['terminal'] and not p['success'] else p['actual_steps']),'prefix failure penalty charged once')
    cursor=p['actual_steps'];charge=p['loss_charge_steps'];stamp=-1;previous_hash=None
    for i,s in enumerate(segments):
        require(type(s) is dict and set(s)==SEGMENT_FIELDS,'strict factual segment')
        require(type(s['start_step']) is type(s['actual_steps']) is type(s['loss_charge_steps']) is int
                and s['start_step']==cursor and 0<=s['actual_steps']<=500-cursor,'continuous actual control-step budget')
        require(type(s['terminal']) is type(s['success']) is bool and s['terminal']==(i==len(segments)-1)
                and (not s['success'] or s['terminal']),'all true terminal/early outcomes retained')
        require(s['terminal'] or cursor+s['actual_steps']<500,'budget exhaustion is terminal')
        require(s['loss_charge_steps']==(500-cursor if s['terminal'] and not s['success'] else s['actual_steps']),'no duplicate acquisition or failure charges')
        identifier(s['before_history_sha256']);identifier(s['after_history_sha256'])
        if previous_hash is not None:require(s['before_history_sha256']==previous_hash,'same actual history chain')
        require(type(s['choice_saved_ns']) is type(s['result_saved_ns']) is int
                and stamp<s['choice_saved_ns']<s['result_saved_ns'],'original choice before result chronology')
        cursor+=s['actual_steps'];charge+=s['loss_charge_steps'];stamp=s['result_saved_ns'];previous_hash=s['after_history_sha256']
    success=segments[-1]['success'] if segments else p['success']
    require(type(row['success']) is bool and row['success']==success and type(row['total_actual_steps']) is int
            and row['total_actual_steps']==cursor and type(row['deadline_loss']) is int
            and row['deadline_loss']==charge==(cursor if success else 500),'all source loss, physical cost and failures retained')
    require(type(row['declarations']) is list and len(row['declarations'])<=len(segments),'finite causal declaration prefix')
    return segments


def estimate(row):
    segments=source_costs(row);declarations=row['declarations'];previous_weight=Fraction(1);dr=Fraction();pdis=Fraction();dm=None;trace=[];issues=[]
    if row['support_scope']!='STRUCTURAL_FULL_SUPPORT_DECLARED':issues.append('GLOBAL_SUPPORT_NOT_DECLARED')
    for i,s in enumerate(segments):
        require(i<len(declarations),'every positive-weight history needs a target/Q declaration')
        d=declarations[i];require(type(d) is dict and set(d)==DECLARATION_FIELDS,'strict target/Q declaration')
        require(d['segment_index']==i and type(d['segment_index']) is int and type(d['feature_cutoff_step']) is int
                and d['feature_cutoff_step']==s['start_step'] and d['source_history_sha256']==s['before_history_sha256'],'no future feature cutoff or different source history')
        require(type(d['computed_ns']) is int and d['computed_ns']>=0,'saved nuisance inference provenance')
        actions=d['actions'];require(type(actions) is list and actions and all(type(a) is str and a for a in actions)
                and len(set(actions))==len(actions),'complete unique candidate menu')
        n=len(actions);chosen=d['executed_index'];require(type(chosen) is int and 0<=chosen<n,'actual executed action index')
        mu=probabilities(d['behavior_probabilities'],n);pi=probabilities(d['target_probabilities'],n)
        require(mu[chosen]>0,'factual logger action cannot have zero probability')
        require(type(d['Q_remaining_loss']) is list and len(d['Q_remaining_loss'])==n,'complete target-continuation Q vector')
        q=[number(x) for x in d['Q_remaining_loss']]
        unsupported=[j for j in range(n) if pi[j]>0 and mu[j]==0]
        if unsupported:issues.append('OBSERVED_TARGET_WITHOUT_LOGGER_SUPPORT_AT_'+str(i))
        v=sum((a*b for a,b in zip(pi,q)),Fraction());ratio=pi[chosen]/mu[chosen];weight=previous_weight*ratio
        if dm is None:dm=v
        contribution=weight*(s['loss_charge_steps']-q[chosen])+previous_weight*v
        dr+=contribution;pdis+=weight*s['loss_charge_steps']
        trace.append(dict(segment_index=i,ratio=str(ratio),cumulative_weight=str(weight),previous_weight=str(previous_weight),
                          V_remaining=str(v),Q_executed=str(q[chosen]),DR_contribution=str(contribution),
                          PDIS_contribution=str(weight*s['loss_charge_steps']),unsupported_candidates=unsupported))
        previous_weight=weight
        if weight==0:break # No fictional target state, future Q or posterior is needed.
    require(len(declarations)==len(trace),'unused target declarations after zero weight are rejected')
    prefix=Fraction(row['prefix']['loss_charge_steps'])
    dr+=prefix;pdis+=prefix;dm=prefix+(dm or Fraction())
    if not segments:issues=[] # The identical terminal prefix already determines every outcome.
    status='ARITHMETIC_AVAILABLE_UNDER_DECLARED_ASSUMPTIONS' if not issues else 'NOT_ADMITTED_SUPPORT'
    available=not issues
    return dict(status=status,episode_id=row['episode_id'],group_id=row['group_id'],target_program_id=row['target_program_id'],
        source_deadline_loss=row['deadline_loss'],source_actual_steps=row['total_actual_steps'],all_source_segments=len(segments),
        consumed_declarations=len(trace),zero_weight_suffix_segments=len(segments)-len(trace),
        DR_exact=str(dr) if available else None,PDIS_exact=str(pdis) if available else None,DM_exact=str(dm) if available else None,
        unbounded_DR_point_not_clipped=bool(available and not 0<=dr<=500),trace=trace,missing_reasons=issues,
        empirical_global_support_verified=False,independence_verified_from_original_files=False,
        real_data_qualified=False,task_benefit_or_safety_qualified=False)


def group_summary(results):
    require(type(results) is list and results,'complete registered episode results')
    require(len({r['episode_id'] for r in results})==len(results),'unique complete episode denominator')
    require(len({r['target_program_id'] for r in results})==1,'one fixed target program, not a mixture of fitted policies')
    all_groups=sorted({r['group_id'] for r in results});out=[]
    for group in all_groups:
        rows=[r for r in results if r['group_id']==group];available=[r for r in rows if r['DR_exact'] is not None]
        # Never silently turn an unsupported case into zero or remove it from a mean.
        out.append(dict(group_id=group,allocated=len(rows),available=len(available),
            DR_group_mean_exact=None if len(rows)!=len(available) else str(sum((Fraction(r['DR_exact']) for r in rows),Fraction())/len(rows))))
    complete=all(x['DR_group_mean_exact'] is not None for x in out)
    return dict(allocated=len(results),available=sum(x['available'] for x in out),independent_groups=len(out),groups=out,
        equal_group_DR_mean_exact=None if not complete else str(sum((Fraction(x['DR_group_mean_exact']) for x in out),Fraction())/len(out)),
        no_unsupported_case_omitted=True,no_time_step_independence_claim=True,confidence_interval=None,real_data_qualified=False)
