"""Independent Fraction/80-digit Decimal reconstruction of the finite study.

No imports of the main probability, decision, aggregation or policy functions.
Shares only JSON/hash I/O and the public frozen configuration.
"""
from fractions import Fraction as F
from decimal import Decimal,localcontext
from itertools import product
from time import perf_counter_ns
from src.analysis import information_scope_io_v1 as a
io=a.io


def dec(v):
    v=F(v);return Decimal(v.numerator)/Decimal(v.denominator)


def kl(p,q):
    return sum((dec(x)*(dec(x)/dec(y)).ln() for x,y in zip(p,q)),Decimal(0))


def law(weights,r):
    weights=list(map(F,weights));r=F(r);post=(r,F(1,2),1-r)
    return [[weights[y]*(post[y] if z else 1-post[y]) for y in range(3)] for z in range(2)]


def coarse(j,m):
    return [[sum((j[z][y] for y in range(len(m)) if m[y]==k),F(0)) for k in range(2)] for z in range(2)]


def info(p,q):
    p=[[F(x) for x in row] for row in p];q=[[F(x) for x in row] for row in q]
    io.require(all(x>0 for row in p+q for x in row) and [sum(row) for row in p]==[sum(row) for row in q]
               and sum(map(sum,p))==sum(map(sum,q))==1,'independent strict support/common prior')
    n=len(p[0]);pm=[sum(p[z][y] for z in range(2)) for y in range(n)];qm=[sum(q[z][y] for z in range(2)) for y in range(n)]
    prior=[sum(row) for row in p];mi=conditional=egig=Decimal(0)
    for y in range(n):
        pp=[p[z][y]/pm[y] for z in range(2)];qp=[q[z][y]/qm[y] for z in range(2)]
        mi+=dec(pm[y])*kl(pp,prior);conditional+=dec(pm[y])*kl(pp,qp)
        egig+=sum((dec(p[z][y])*(dec(qp[z])/dec(prior[z])).ln() for z in range(2)),Decimal(0))
    joint=kl([x for row in p for x in row],[x for row in q for x in row]);predictive=kl(pm,qm)
    return dict(true_mutual_information=mi,conditional_posterior_KL=conditional,joint_KL=joint,
        predictive_marginal_KL=predictive,EGIG=egig,RFIM_KL=mi-joint,
        chain_rule_residual=joint-predictive-conditional,EGIG_decomposition_residual=egig-mi+conditional)


def cases(config):
    ws=config['family_A']['weights'];rs=config['family_A']['symmetric_posterior_low']
    maps=[list(v) for v in product((0,1),repeat=3) if 0 in v and 1 in v];values=[]
    stringify=lambda j:[[str(x) for x in row] for row in j]
    for p,q,r,m in product(ws,ws,rs,maps):values.append(dict(family='SAME_FINE_POSTERIOR_DIFFERENT_PREDICTIVE',p=stringify(law(p,r)),q=stringify(law(q,r)),mapping=m))
    for w,rp,rq,m in product(ws,rs,rs,maps):values.append(dict(family='MATCHED_PREDICTIVE_POSITIVE_CONTROL',p=stringify(law(w,rp)),q=stringify(law(w,rq)),mapping=m))
    return [dict(case_id=i,**v) for i,v in enumerate(values)]


def result(case):
    p=[[F(x) for x in r] for r in case['p']];q=[[F(x) for x in r] for r in case['q']]
    fine=info(p,q);c=info(coarse(p,case['mapping']),coarse(q,case['mapping']))
    inc=c['conditional_posterior_KL']-fine['conditional_posterior_KL'];slack=fine['predictive_marginal_KL']-c['predictive_marginal_KL'];eps=Decimal('1e-12')
    return dict(case_id=case['case_id'],family=case['family'],fine=fine,coarse=c,
        posterior_penalty_increase=inc,predictive_slack=slack,unconditional_posterior_contraction_holds=inc<=eps,
        joint_KL_contraction_holds=c['joint_KL']<=fine['joint_KL']+eps,corrected_slack_bound_holds=inc<=slack+eps,
        true_information_contraction_holds=c['true_mutual_information']<=fine['true_mutual_information']+eps)


def compare(actual,expected,path='root'):
    if isinstance(expected,dict):
        io.require(isinstance(actual,dict) and set(actual)==set(expected),'independent keys '+path)
        return sum(compare(actual[k],v,path+'/'+k) for k,v in expected.items())
    if isinstance(expected,list):
        io.require(isinstance(actual,list) and len(actual)==len(expected),'independent length '+path)
        return sum(compare(x,y,path+'/'+str(i)) for i,(x,y) in enumerate(zip(actual,expected)))
    if isinstance(expected,Decimal):
        io.require(type(actual) is float and abs(Decimal(str(actual))-expected)<=Decimal('1e-10'),'independent 80-digit value '+path)
    else:io.require(type(actual) is type(expected) and actual==expected,'independent exact value '+path)
    return 1


def decision_cases(config):
    g=config['decision_grid'];vs=product(g['direction'],g['fine_cost'],g['coarse_cost'],g['fine_shift'],g['coarse_shift'])
    return [dict(problem_id=i,direction=d,fine_cost=fc,coarse_cost=cc,fine_shift=fs,coarse_shift=cs,budget=500)
            for i,(d,fc,cc,fs,cs) in enumerate(vs)]


def channel(arm,true,direction):
    p=law(('1/4','1/2','1/4'),'1/10');q=law(('2/5','1/5','2/5'),'1/10')
    matrix=p if (true and direction=='FORWARD') or (not true and direction=='REVERSE') else q
    if arm=='CONTINUE':return [[sum(v)] for v in matrix]
    return matrix if arm=='FINE' else coarse(matrix,[0,0,1])


def parameters(problem,arm):return (0,0) if arm=='CONTINUE' else (problem[arm.lower()+'_cost'],problem[arm.lower()+'_shift'])


def terminal(z,tail,cost,shift,budget):
    if tail=='STOP':return dict(cutoff_loss=F(budget),success_probability=F(0),interaction_equivalent=F(cost))
    i=('KEEP','ADOPT_025','ADOPT_050','ADOPT_100').index(tail)
    length=((120,109,98,75),(120,95,70,20))[z][i]+shift
    f=(F(0),F(1,20),F(1,10),F(1,5))[i] if z==0 else F(0)
    success=1-f if cost+length<=budget else F(0)
    loss=success*(cost+length)+(1-success)*budget
    return dict(cutoff_loss=loss,success_probability=success,interaction_equivalent=loss)


def first_min(v):
    best=0
    for i in range(1,len(v)):
        if v[i]<v[best]-F(1,10**10):best=i
    return best


def choose_tails(problem,arm,true,ignore_state=False,ignore_cost=False):
    matrix=channel(arm,true,problem['direction']);cost,shift=parameters(problem,arm)
    if ignore_state:shift=0
    if ignore_cost:cost=0
    tails=('KEEP','ADOPT_025','ADOPT_050','ADOPT_100','STOP');values=[]
    for y in range(len(matrix[0])):
        den=matrix[0][y]+matrix[1][y]
        risks=[sum(matrix[z][y]/den*terminal(z,t,cost,shift,problem['budget'])['cutoff_loss'] for z in (0,1)) for t in tails]
        values.append(tails[first_min(risks)])
    return values


def expectation(problem,arm,tails,true,ignore_state=False,ignore_cost=False):
    matrix=channel(arm,true,problem['direction']);cost,shift=parameters(problem,arm)
    if ignore_state:shift=0
    if ignore_cost:cost=0
    result={k:F(0) for k in ('cutoff_loss','success_probability','interaction_equivalent')}
    for z in range(2):
        for y,t in enumerate(tails):
            for k,v in terminal(z,t,cost,shift,problem['budget']).items():result[k]+=matrix[z][y]*v
    result['acquisition_equivalent']=F(cost)
    return result


def plan(problem,method):
    ti=method in ('ORACLE_IDEAL_EXECUTED','OPTIMISTIC_POST_MISMATCH')
    to=method in ('ORACLE_JOINT_IMPLEMENTED','ORACLE_IDEAL_EXECUTED','OPTIMISTIC_POST_MISMATCH')
    is_=method=='WORKING_IGNORE_STATE';ic=method=='WORKING_IGNORE_COST';arms={}
    for arm in ('CONTINUE','FINE','COARSE'):
        if parameters(problem,arm)[0]>problem['budget']:continue
        scored=choose_tails(problem,arm,ti,is_,ic)
        executed=choose_tails(problem,arm,False) if method=='OPTIMISTIC_POST_MISMATCH' else list(scored)
        arms[arm]=dict(planned_score=dec(expectation(problem,arm,scored,to,is_,ic)['cutoff_loss']),
                       scored_continuations=scored,executed_continuations=executed)
    if method.startswith('DIRECT_'):
        t=dict(DIRECT_KEEP='KEEP',DIRECT_025='ADOPT_025',DIRECT_050='ADOPT_050',DIRECT_100='ADOPT_100')[method];chosen='CONTINUE'
        arms[chosen]=dict(planned_score=dec(expectation(problem,chosen,[t],False)['cutoff_loss']),scored_continuations=[t],executed_continuations=[t])
    elif method.startswith('ALWAYS_'):chosen='FINE' if method=='ALWAYS_FINE_WORKING' else 'COARSE'
    else:
        names=list(arms);best=0
        for i in range(1,len(names)):
            if arms[names[i]]['planned_score']<arms[names[best]]['planned_score']-Decimal('1e-10'):best=i
        chosen=names[best]
    return dict(problem_id=problem['problem_id'],method=method,chosen_arm=chosen,arm_predictions=arms,
        saved_continuations=arms[chosen]['executed_continuations'],
        role='PRIVILEGED_FINITE_REFERENCE_NOT_DEPLOYABLE' if ti or to else 'WORKING_FINITE_REFERENCE_NOT_ROBOT_POLICY',
        scope='SYNTHETIC_ENUMERATION_NO_PHYSICAL_EXECUTION')


def evaluate(problem,ledger):
    arm=ledger['chosen_arm'];tails=ledger['saved_continuations'];v=expectation(problem,arm,tails,True)
    matrix=channel(arm,True,problem['direction']);cost,shift=parameters(problem,arm);harm=good=miss=F(0)
    for y,t in enumerate(tails):
        mass=sum(matrix[z][y] for z in range(2))
        risks={tail:sum(matrix[z][y]/mass*terminal(z,tail,cost,shift,problem['budget'])['cutoff_loss'] for z in range(2))
               for tail in ('KEEP','ADOPT_025','ADOPT_050','ADOPT_100','STOP')}
        if t not in ('KEEP','STOP'):
            if risks[t]>risks['KEEP']+F(1,10**10):harm+=mass
            if risks[t]<risks['KEEP']-F(1,10**10):good+=mass
        elif t=='KEEP' and min(risks.values())<risks['KEEP']-F(1,10**10):miss+=mass
    return dict(problem_id=problem['problem_id'],method=ledger['method'],chosen_arm=arm,saved_continuations=tails,
        **{k:dec(val) for k,val in v.items()},harmful_adoption_probability=dec(harm),beneficial_adoption_probability=dec(good),
        keep_missing_benefit_probability=dec(miss),scope='TRUE_FINITE_EXPECTATION_NOT_A_ROBOT_OR_STOCHASTIC_TRIAL')


def audit(path):
    start=perf_counter_ns();m=a.checked(path);root=path.parent;planning=io.read(root/'planning/completion.json');evaluation=io.read(root/'evaluation/completion.json')
    for folder,done in (('planning',planning),('evaluation',evaluation)):
        for name,h in done['artifact_sha256'].items():io.require(io.sha(root/folder/name)==h,'immutable saved finite outputs')
    fields=0
    with localcontext() as ctx:
        ctx.prec=80
        cs=cases(m['config']);fields+=compare(io.read(root/'planning/probability_cases.json'),cs,'full rational census')
        results=[result(c) for c in cs];fields+=compare(io.read(root/'planning/probability_results.json'),results,'80 digit information')
        c=dict(case_id='FULL_SUPPORT_WITNESS',family='CONSTRUCTED_RATIONAL_WITNESS',p=[[str(x) for x in r] for r in law(('1/4','1/2','1/4'),'1/10')],q=[[str(x) for x in r] for r in law(('2/5','1/5','2/5'),'1/10')],mapping=[0,0,1])
        fields+=compare(io.read(root/'planning/witness.json'),dict(input=c,result=result(c)),'explicit witness')
        pp=[['1/4','1/4'],['1/4','1/4']];qq=[['3/8','1/8'],['3/8','1/8']]
        non=dict(p=pp,q=qq,metrics=info(pp,qq),working_posterior_equals_prior=True,
            interpretation='Joint penalty also scores predictive-frequency mismatch; not equivalent to posterior-only no-update normalization.')
        fields+=compare(io.read(root/'planning/noninformative_witness.json'),non,'normalization boundary')
        problems=decision_cases(m['config']);fields+=compare(io.read(root/'planning/decision_problems.json'),problems,'all declared finite decisions')
        predicted=io.read(root/'planning/policies.json');actual=io.read(root/'evaluation/results.json');i=0;rebuilt=[]
        for p in problems:
            for method in m['config']['reference_methods']:
                candidate=plan(p,method);fields+=compare(predicted[i],candidate,'policy before evaluation')
                value=evaluate(p,candidate);fields+=compare(actual[i],value,'saved-policy exact true expectation');rebuilt.append(value);i+=1
        io.require(i==len(predicted)==len(actual)==2592,'complete synthetic reference population')
        summaries=[]
        for method in m['config']['reference_methods']:
            rows=[v for v in rebuilt if v['method']==method]
            summaries.append(dict(method=method,constructed_problems=len(rows),
                means={k:sum(v[k] for v in rows)/Decimal(len(rows)) for k in ('cutoff_loss','success_probability','interaction_equivalent','acquisition_equivalent',
                    'harmful_adoption_probability','beneficial_adoption_probability','keep_missing_benefit_probability')},
                chosen_arms={arm:sum(v['chosen_arm']==arm for v in rows) for arm in ('CONTINUE','FINE','COARSE')}))
        fields+=compare(io.read(root/'evaluation/summary.json'),summaries,'all descriptive synthetic means')
        high_precision_witness={key:str(value) for key,value in result(c)['coarse'].items()}
    a.checked(path);result_={'integrity':'PASSED','manifest_id':m['manifest_id'],'independently_checked_fields':fields,
        'numeric_backend':'Fraction exact probabilities and80-digit Decimal logarithms','new_main_numerical_functions_disabled':True,
        'shared_scope':'JSON/hash/config I/O only','probability_records':324,'decision_problems':216,'saved_policies':2592,
        'source_planning_completion_sha256':io.sha(root/'planning/completion.json'),
        'source_evaluation_completion_sha256':io.sha(root/'evaluation/completion.json'),
        'high_precision_witness_coarse':high_precision_witness,'wall_ns':perf_counter_ns()-start,
        'new_environment_steps':0,'new_model_fits':0,'online_LLM_API_calls':0,'robot_or_paper_qualification':False}
    io.write(root/'audit.json',result_);return result_
