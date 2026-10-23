"""Fully enumerated finite model for a standard estimator qualification only.

These are symbolic costs and synthetic observations, not robot trajectories.
Oracle conditional means are evaluation fixtures, never deployable models.
"""
from itertools import product
from src.analysis.two_stage_terminal_dr_v1 import History1,History2,LoggedTerminal,ACTIONS,TAILS

MODES=('P_TRUE_Q_ZERO','P_TRUE_Q_WRONG','P_WRONG_Q_TRUE','P1_TRUE_Q2_TRUE','Q1_TRUE_P2_TRUE','BOTH_WRONG')
FIRST_POLICIES=('MIXED','ONLY_CONTINUE','ONLY_VALIDATE','ONLY_MOVE')
TAIL_POLICIES=('POSTSTATE_ADAPTIVE','KEEP_ONLY')
P1=(.3,.3,.4);P2=(.5,.5);WRONG_P1=(.6,.2,.2);WRONG_P2=(.8,.2)
POST={
    (0,'VALIDATE'):(.6,.3,.05,.05),(0,'MOVE_VALIDATE'):(.4,.5,.05,.05),
    (1,'VALIDATE'):(.4,.5,.05,.05),(1,'MOVE_VALIDATE'):(.85,.05,.05,.05)}


def pre(x):return History1(16+16*x,x,(.2+.2*x,-.1),.5)


def post(before,action,position):
    steps=8 if action=='VALIDATE' else 16
    integral=(before.integral_xy[0]+.08,before.integral_xy[1]-.04) if action=='VALIDATE' else before.integral_xy
    return History2(before.sha256,action,before.completed_steps+steps,position,.001 if position=='NEAR' else .003,integral)


def tail_parameters(x,action,position,tail):
    if position=='NEAR':return (60+10*x,.02+.02*x) if tail=='KEEP' else (20+5*x,.05 if action=='VALIDATE' else .01)
    return (140+15*x,.15) if tail=='KEEP' else (50+10*x,.6 if action=='VALIDATE' else .3)


def tail_policy(before,after,name):
    if name=='KEEP_ONLY':return (1.,0.)
    if name!='POSTSTATE_ADAPTIVE':raise ValueError('fixed tail policy')
    return (.1,.9) if after.observed_position_bin=='NEAR' else (.9,.1)


def first_policy(before,name):
    if name=='MIXED':return (.5,.4,.1) if before.observed_code==0 else (.2,.3,.5)
    return tuple(float(name==registered) for registered in FIRST_POLICIES[1:])


def true_q2(before,after):
    remaining=500-after.completed_steps;x=before.observed_code
    return tuple((1-p)*cost+p*remaining for cost,p in (tail_parameters(x,after.action,after.observed_position_bin,b) for b in TAILS))


def true_q1(before,tail_policy_name):
    x=before.observed_code;t=before.completed_steps;remaining=500-t;direct_cost=60+10*x;fail=.02+.02*x
    values=[(1-fail)*direct_cost+fail*remaining]
    for action in ACTIONS[1:]:
        weights=POST[x,action];value=0.
        for position,p in zip(('NEAR','FAR'),weights[:2]):
            after=post(before,action,position);q=true_q2(before,after);policy=tail_policy(before,after,tail_policy_name)
            value+=p*(after.completed_steps-t+sum(pi*mu for pi,mu in zip(policy,q)))
        value+=weights[2]*2+weights[3]*remaining
        values.append(value)
    return tuple(values)


def atoms():
    result=[]
    def add(x,action,prob,row):
        result.append({'atom_id':'atom-'+str(len(result)).zfill(3),'probability_under_true_behavior':.5*P1[ACTIONS.index(action)]*prob,
            'synthetic_finite_model_atom':True,'record':row.to_dict()})
    for x in (0,1):
        before=pre(x);t=before.completed_steps
        fail=.02+.02*x
        for success,p in ((True,1-fail),(False,fail)):
            cost=60+10*x if success else 65+10*x
            add(x,'CONTINUE',p,LoggedTerminal(before,'CONTINUE',cost,'SUCCESS' if success else 'FAILURE',None,None,None,None,t+cost if success else 500))
        for action in ACTIONS[1:]:
            for position,w in zip(('NEAR','FAR'),POST[x,action][:2]):
                after=post(before,action,position);cost=after.completed_steps-t
                for b in TAILS:
                    steps,pfail=tail_parameters(x,action,position,b)
                    for success,p in ((True,1-pfail),(False,pfail)):
                        actual=steps if success else steps+5
                        add(x,action,w*.5*p,LoggedTerminal(before,action,cost,'NONE',after,b,actual,success,after.completed_steps+actual if success else 500))
            for status,w,cost in (('SUCCESS',POST[x,action][2],2),('FAILURE',POST[x,action][3],3)):
                add(x,action,w,LoggedTerminal(before,action,cost,status,None,None,None,None,t+cost if status=='SUCCESS' else 500))
    return result


def inputs(before,after,mode,first,tail):
    """Only pre/post observable histories, never a terminal outcome argument."""
    if mode not in MODES or first not in FIRST_POLICIES or tail not in TAIL_POLICIES:raise ValueError('frozen numerical reference setting')
    p1=P1 if mode in ('P_TRUE_Q_ZERO','P_TRUE_Q_WRONG','P1_TRUE_Q2_TRUE') else WRONG_P1
    p2=P2 if mode in ('P_TRUE_Q_ZERO','P_TRUE_Q_WRONG','Q1_TRUE_P2_TRUE') else WRONG_P2
    q1=true_q1(before,tail) if mode in ('P_WRONG_Q_TRUE','Q1_TRUE_P2_TRUE') else (0.,0.,0.) if mode=='P_TRUE_Q_ZERO' else (100.,100.,100.)
    q2=None if after is None else true_q2(before,after) if mode in ('P_WRONG_Q_TRUE','P1_TRUE_Q2_TRUE') else (0.,0.) if mode=='P_TRUE_Q_ZERO' else (30.,30.)
    return {'behavior1':p1,'target1':first_policy(before,first),'q1':q1,'behavior2':None if after is None else p2,
        'target2':None if after is None else tail_policy(before,after,tail),'q2':q2}


def target_truth(first,tail):
    return sum(.5*(before.completed_steps+sum(p*q for p,q in zip(first_policy(before,first),true_q1(before,tail)))) for before in (pre(0),pre(1)))
