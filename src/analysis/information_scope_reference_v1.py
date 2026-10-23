"""Finite probability/decision reference, not a robot model or online selector.

True laws here are declared synthetic evaluator objects. No table is a physical
rollout, fitted predictor, natural experience, confidence bound or safety claim.
"""
from fractions import Fraction as F
from itertools import product
import numpy as np

TOL = 1e-12
METHODS = ('WORKING_BAYES', 'ORACLE_JOINT_IMPLEMENTED', 'ORACLE_IDEAL_EXECUTED',
           'OPTIMISTIC_POST_MISMATCH', 'WORKING_IGNORE_STATE', 'WORKING_IGNORE_COST',
           'DIRECT_KEEP', 'DIRECT_025', 'DIRECT_050', 'DIRECT_100',
           'ALWAYS_FINE_WORKING', 'ALWAYS_COARSE_WORKING')
TAILS = ('KEEP', 'ADOPT_025', 'ADOPT_050', 'ADOPT_100', 'STOP')
ARMS = ('CONTINUE', 'FINE', 'COARSE')
WEIGHTS = (('1/4','1/2','1/4'), ('1/3','1/3','1/3'), ('2/5','1/5','2/5'))
POSTERIORS = ('1/10','1/4','2/5')
DURATIONS = ((120,109,98,75), (120,95,70,20))
FAILURE = (F(0), F(1,20), F(1,10), F(1,5))


def require(value, message):
    if not value: raise ValueError(message)


def first_min(values):
    require(len(values)>0 and np.isfinite(values).all(),'finite nonempty ranking')
    best=0
    for i in range(1,len(values)):
        if values[i]<values[best]-1e-10:best=i
    return best


def rational_joint(weights, low):
    w = list(map(F, weights)); r = F(low); post = (r, F(1,2), 1-r)
    return [[str(w[y] * (post[y] if theta else 1-post[y])) for y in range(3)]
            for theta in range(2)]


def float_joint(value):
    j = np.asarray([[float(F(x)) for x in row] for row in value], dtype=float)
    require(j.ndim == 2 and j.shape[0] == 2 and j.shape[1] > 0
            and np.isfinite(j).all() and (j > 0).all()
            and abs(float(j.sum())-1) < 1e-14, 'positive normalized finite joint law')
    return j


def coarsen(joint, mapping):
    j = np.asarray(joint,float)
    require(len(mapping) == j.shape[1] and set(mapping) == {0,1}
            and all(type(v) is int for v in mapping), 'surjective deterministic common channel')
    k = np.zeros((len(mapping),2))
    k[np.arange(len(mapping)),mapping] = 1
    return j @ k


def information(p, q):
    p = float_joint(p); q = float_joint(q)
    require(p.shape == q.shape and np.allclose(p.sum(1),q.sum(1),atol=1e-14,rtol=0),
            'common prior required; no silent prior-mismatch guarantee')
    pm = p.sum(0); qm = q.sum(0); prior = p.sum(1)
    pp = p/pm; qp = q/qm
    mi = float(np.sum(p*np.log(pp/prior[:,None])))
    conditional = float(np.sum(p*np.log(pp/qp)))
    joint = float(np.sum(p*np.log(p/q)))
    predictive = float(np.sum(pm*np.log(pm/qm)))
    egig = float(np.sum(p*np.log(qp/prior[:,None])))
    return dict(true_mutual_information=mi, conditional_posterior_KL=conditional,
                joint_KL=joint, predictive_marginal_KL=predictive,
                EGIG=egig, RFIM_KL=mi-joint,
                chain_rule_residual=joint-predictive-conditional,
                EGIG_decomposition_residual=egig-mi+conditional)


def probability_cases():
    mappings = [list(m) for m in product((0,1),repeat=3) if len(set(m)) == 2]
    cases = []
    for pw,qw,r,m in product(WEIGHTS,WEIGHTS,POSTERIORS,mappings):
        cases.append(dict(family='SAME_FINE_POSTERIOR_DIFFERENT_PREDICTIVE',
            p=rational_joint(pw,r),q=rational_joint(qw,r),mapping=m))
    for w,rp,rq,m in product(WEIGHTS,POSTERIORS,POSTERIORS,mappings):
        cases.append(dict(family='MATCHED_PREDICTIVE_POSITIVE_CONTROL',
            p=rational_joint(w,rp),q=rational_joint(w,rq),mapping=m))
    return [dict(case_id=i,**v) for i,v in enumerate(cases)]


def probability_result(case):
    p = float_joint(case['p']); q = float_joint(case['q'])
    fine = information(case['p'],case['q'])
    coarse = information(coarsen(p,case['mapping']).tolist(),coarsen(q,case['mapping']).tolist())
    increase = coarse['conditional_posterior_KL']-fine['conditional_posterior_KL']
    slack = fine['predictive_marginal_KL']-coarse['predictive_marginal_KL']
    return dict(case_id=case['case_id'],family=case['family'],fine=fine,coarse=coarse,
        posterior_penalty_increase=increase,predictive_slack=slack,
        unconditional_posterior_contraction_holds=increase <= TOL,
        joint_KL_contraction_holds=coarse['joint_KL'] <= fine['joint_KL']+TOL,
        corrected_slack_bound_holds=increase <= slack+TOL,
        true_information_contraction_holds=coarse['true_mutual_information'] <= fine['true_mutual_information']+TOL)


def witness():
    return dict(case_id='FULL_SUPPORT_WITNESS',family='CONSTRUCTED_RATIONAL_WITNESS',
        p=rational_joint(WEIGHTS[0],POSTERIORS[0]),
        q=rational_joint(WEIGHTS[2],POSTERIORS[0]),mapping=[0,0,1])


def noninformative_witness():
    p=[['1/4','1/4'],['1/4','1/4']]
    q=[['3/8','1/8'],['3/8','1/8']]
    return dict(p=p,q=q,metrics=information(p,q),
        working_posterior_equals_prior=True,
        interpretation='Joint penalty also scores predictive-frequency mismatch; not equivalent to posterior-only no-update normalization.')


def decision_problems():
    return [dict(problem_id=i,direction=direction,fine_cost=fc,coarse_cost=cc,fine_shift=fs,coarse_shift=cs,budget=500)
            for i,(direction,fc,cc,fs,cs) in enumerate(product(('FORWARD','REVERSE'),(0,4,8,12),(0,1,4),(-5,0,20),(-5,0,20)))]


def arm_law(arm, truth, direction='FORWARD'):
    require(direction in ('FORWARD','REVERSE'),'declared synthetic mismatch direction')
    w = witness(); j = float_joint(w['p' if truth == (direction=='FORWARD') else 'q'])
    if arm == 'CONTINUE': return j.sum(1)[:,None]
    if arm == 'FINE': return j
    if arm == 'COARSE': return coarsen(j,w['mapping'])
    raise ValueError('registered acquisition arm')


def arm_parameters(problem, arm):
    if arm == 'CONTINUE': return 0,0
    return problem[arm.lower()+'_cost'],problem[arm.lower()+'_shift']


def terminal(theta, tail, cost, shift, budget):
    require(theta in (0,1) and tail in TAILS and type(cost) is int and 0 <= cost <= budget
            and type(shift) is int and type(budget) is int and budget > 0,'finite terminal contract')
    if tail == 'STOP':return dict(cutoff_loss=float(budget),success_probability=0.,interaction_equivalent=float(cost))
    i = TAILS.index(tail); duration = DURATIONS[theta][i]+shift
    require(duration > 0,'positive synthetic completion duration')
    failure = float(FAILURE[i]) if theta == 0 else 0.
    success = 1-failure if cost+duration <= budget else 0.
    # A failed full task pays the cutoff once, never cutoff+acquisition cost.
    total = success*(cost+duration)+(1-success)*budget
    return dict(cutoff_loss=float(total),success_probability=success,interaction_equivalent=float(total))


def inner_policy(problem, arm, truth, ignore_state=False,ignore_cost=False):
    j = arm_law(arm,truth,problem['direction']); cost,shift = arm_parameters(problem,arm)
    if ignore_state:shift=0
    if ignore_cost:cost=0
    out=[]
    for y in range(j.shape[1]):
        posterior = j[:,y]/j[:,y].sum()
        risks = [float(sum(posterior[t]*terminal(t,tail,cost,shift,problem['budget'])['cutoff_loss'] for t in range(2))) for tail in TAILS]
        out.append(TAILS[first_min(risks)])
    return out


def expected_metrics(problem,arm,tails,truth,ignore_state=False,ignore_cost=False):
    j=arm_law(arm,truth,problem['direction']); cost,shift=arm_parameters(problem,arm)
    require(len(tails)==j.shape[1] and all(t in TAILS for t in tails),'saved observation-indexed legal continuation')
    if ignore_state:shift=0
    if ignore_cost:cost=0
    values={k:0. for k in ('cutoff_loss','success_probability','interaction_equivalent')}
    for theta in range(2):
        for y,tail in enumerate(tails):
            for key,v in terminal(theta,tail,cost,shift,problem['budget']).items():values[key]+=float(j[theta,y])*v
    values['acquisition_equivalent']=float(cost)
    return values


def plan(problem,method):
    require(method in METHODS,'registered reference only')
    truth_inner=method in ('ORACLE_IDEAL_EXECUTED','OPTIMISTIC_POST_MISMATCH')
    truth_outer=method in ('ORACLE_JOINT_IMPLEMENTED','ORACLE_IDEAL_EXECUTED','OPTIMISTIC_POST_MISMATCH')
    ignore_state=method=='WORKING_IGNORE_STATE';ignore_cost=method=='WORKING_IGNORE_COST'
    arms={}
    for arm in ARMS:
        cost,_=arm_parameters(problem,arm)
        if cost>problem['budget']:continue
        scored=inner_policy(problem,arm,truth_inner,ignore_state,ignore_cost)
        executed=inner_policy(problem,arm,False) if method=='OPTIMISTIC_POST_MISMATCH' else list(scored)
        value=expected_metrics(problem,arm,scored,truth_outer,ignore_state,ignore_cost)['cutoff_loss']
        arms[arm]=dict(planned_score=value,scored_continuations=scored,executed_continuations=executed)
    if method.startswith('DIRECT_'):
        tail={'DIRECT_KEEP':'KEEP','DIRECT_025':'ADOPT_025','DIRECT_050':'ADOPT_050','DIRECT_100':'ADOPT_100'}[method]
        chosen='CONTINUE';arms[chosen]=dict(planned_score=expected_metrics(problem,chosen,[tail],False)['cutoff_loss'],
                                          scored_continuations=[tail],executed_continuations=[tail])
    elif method.startswith('ALWAYS_'):chosen='FINE' if method=='ALWAYS_FINE_WORKING' else 'COARSE'
    else:chosen=list(arms)[first_min([v['planned_score'] for v in arms.values()])]
    require(chosen in arms,'budget-infeasible fixed acquisition rejected')
    return dict(problem_id=problem['problem_id'],method=method,chosen_arm=chosen,arm_predictions=arms,
        saved_continuations=arms[chosen]['executed_continuations'],
        role='PRIVILEGED_FINITE_REFERENCE_NOT_DEPLOYABLE' if truth_inner or truth_outer else 'WORKING_FINITE_REFERENCE_NOT_ROBOT_POLICY',
        scope='SYNTHETIC_ENUMERATION_NO_PHYSICAL_EXECUTION')


def evaluate(problem,ledger):
    require(ledger['problem_id']==problem['problem_id'] and ledger['method'] in METHODS,'saved policy/problem identity')
    arm=ledger['chosen_arm'];tails=ledger['saved_continuations']
    v=expected_metrics(problem,arm,tails,True)
    j=arm_law(arm,True,problem['direction']);cost,shift=arm_parameters(problem,arm)
    harmful=beneficial=missed=0.
    for y,tail in enumerate(tails):
        mass=float(j[:,y].sum());posterior=j[:,y]/mass
        risks={t:sum(float(posterior[z])*terminal(z,t,cost,shift,problem['budget'])['cutoff_loss'] for z in range(2)) for t in TAILS}
        if tail not in ('KEEP','STOP'):
            harmful+=mass if risks[tail]>risks['KEEP']+1e-10 else 0.
            beneficial+=mass if risks[tail]<risks['KEEP']-1e-10 else 0.
        elif tail=='KEEP' and min(risks.values())<risks['KEEP']-1e-10:missed+=mass
    # Only this evaluator uses the true synthetic law to score the saved choices.
    return dict(problem_id=problem['problem_id'],method=ledger['method'],chosen_arm=ledger['chosen_arm'],
                saved_continuations=tails,**v,harmful_adoption_probability=harmful,
                beneficial_adoption_probability=beneficial,keep_missing_benefit_probability=missed,
                scope='TRUE_FINITE_EXPECTATION_NOT_A_ROBOT_OR_STOCHASTIC_TRIAL')
