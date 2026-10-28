"""Independent backward recurrence. Shared Fraction primitive is disclosed."""
from fractions import Fraction


def need(ok,message):
    if not ok:raise ValueError(message)


def numeric(x):
    if type(x) is float:return Fraction.from_float(x)
    return Fraction(x)


def verify_episode(row,saved):
    """No call to the production validator, probabilities or estimator."""
    decl=row['declarations'];segments=row['segments'];ratios=[];values=[];selected=[];issues=[]
    need(saved['source_deadline_loss']==row['deadline_loss'] and saved['source_actual_steps']==row['total_actual_steps'],'independent full source denominator')
    if row['support_scope']!='STRUCTURAL_FULL_SUPPORT_DECLARED':issues.append('GLOBAL_SUPPORT_NOT_DECLARED')
    product=Fraction(1)
    for i,d in enumerate(decl):
        s=segments[i];need(d['segment_index']==i and d['source_history_sha256']==s['before_history_sha256']
                           and d['feature_cutoff_step']==s['start_step'],'independent history cutoff')
        n=len(d['actions']);a=d['executed_index'];b=[numeric(x) for x in d['behavior_probabilities']];p=[numeric(x) for x in d['target_probabilities']]
        q=[numeric(x) for x in d['Q_remaining_loss']]
        need(len(p)==len(b)==len(q)==n and sum(p)==sum(b)==1 and b[a]>0,'independent complete action kernel')
        bad=[j for j in range(n) if p[j]>0 and b[j]==0]
        if bad:issues.append('OBSERVED_TARGET_WITHOUT_LOGGER_SUPPORT_AT_'+str(i))
        rho=p[a]/b[a];v=sum((p[j]*q[j] for j in range(n)),Fraction());product*=rho
        need(saved['trace'][i]['ratio']==str(rho) and saved['trace'][i]['cumulative_weight']==str(product)
             and saved['trace'][i]['V_remaining']==str(v) and saved['trace'][i]['unsupported_candidates']==bad,'independent weights and target averaging')
        ratios.append(rho);values.append(v);selected.append(q[a])
        if rho==0:need(i==len(decl)-1,'no declarations after impossible target history')
    if not segments:issues=[]
    need(len(decl)==len(saved['trace']) and (len(decl)==len(segments) or ratios and ratios[-1]==0),'independent exact supported prefix')
    remaining=Fraction();importance=Fraction()
    for i in range(len(decl)-1,-1,-1):
        cost=segments[i]['loss_charge_steps']
        remaining=values[i]+ratios[i]*(cost+remaining-selected[i])
        importance=ratios[i]*(cost+importance)
    prefix=row['prefix']['loss_charge_steps'];dr=remaining+prefix;is_value=importance+prefix;dm=(values[0] if values else Fraction())+prefix
    need(saved['missing_reasons']==issues,'independent support missingness')
    for key,value in (('DR_exact',dr),('PDIS_exact',is_value),('DM_exact',dm)):
        need(saved[key]==(None if issues else str(value)),'independent backward '+key)
    need(saved['zero_weight_suffix_segments']==len(segments)-len(decl),'independent omitted suffix is not a new trajectory')
    return dict(integrity='PASSED_INDEPENDENT_BACKWARD_RECURRENCE',consumed_declarations=len(decl),
                shared_Fraction_library=True,new_model_queries=0,new_physics=0,online_LLM_API_calls=0)


def verify_groups(results,saved):
    expected=sorted({r['group_id'] for r in results});need(len(results)==saved['allocated'] and len(expected)==saved['independent_groups'],'independent all-case/group count')
    means=[];available=0
    for group,entry in zip(expected,saved['groups']):
        part=[r for r in results if r['group_id']==group];keep=[r for r in part if r['DR_exact'] is not None];available+=len(keep)
        value=None if len(keep)!=len(part) else sum((Fraction(r['DR_exact']) for r in part),Fraction())/len(part)
        need(entry==dict(group_id=group,allocated=len(part),available=len(keep),DR_group_mean_exact=None if value is None else str(value)),'independent within-group mean')
        if value is not None:means.append(value)
    result=None if len(means)!=len(expected) else str(sum(means,Fraction())/len(means))
    need(saved['available']==available and saved['equal_group_DR_mean_exact']==result,'independent equal group mean with full denominator')
