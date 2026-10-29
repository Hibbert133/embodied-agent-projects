"""Standard terminal-inclusive one-time continuation DM/DR; exact arithmetic.

Not a learned method or robot deployment. The logging law must be supplied and
qualified outside this core; theoretical mass is not an empirical certificate.
"""
from fractions import Fraction as F


def need(value,message):
    if not value:raise ValueError(message)


def number(value):
    need(type(value) in (int,str,F),'exact rational input only')
    return F(value)


def distribution(value,actions):
    need(type(value) is dict and tuple(value)==tuple(actions),'full ordered action distribution, no hidden omissions')
    p={k:number(value[k]) for k in actions}
    need(all(v>=0 for v in p.values()) and sum(p.values())==1,'normalized nonnegative law')
    return p


def support(target,logging):
    actions=tuple(target);pi=distribution(target,actions);mu=distribution(logging,actions)
    need(all(mu[k]>0 for k in actions if pi[k]>0),'unsupported target: no epsilon repair or renormalization')
    return pi,mu


def public_return(value):
    need(type(value) is dict and set(value)=={'schema','history_token','before_steps','after_steps','terminal','success'}
        and value['schema']=='FINITE_PUBLIC_RETURN_V1','strict illustrative public return')
    need(type(value['history_token']) is str and value['history_token'],'actual public history identity')
    b,n=value['before_steps'],value['after_steps']
    need(type(b) is int and type(n) is int and 0<=b<=n<=500,'continuous paid budget')
    need(type(value['terminal']) is bool and type(value['success']) is bool,'literal public flags')
    need(not value['success'] or value['terminal'],'public success ends option')
    need(value['terminal'] or n<500,'live return before deadline')
    return b,n


def terminal_cost(returned):
    b,n=public_return(returned);need(returned['terminal'],'no invented terminal branch')
    # n-b is already included. Never add acquisition cost again here.
    return F(n-b if returned['success'] else 500-b)


def static_label(label,actions):
    need(type(label) is dict and set(label)=={'schema','selected','gain_history','remaining_loss'}
        and label['schema']=='FACTUAL_COMPLETE_STATIC_LABEL_V1','typed complete factual label')
    chosen=label['selected'];history=label['gain_history']
    need(chosen in actions and type(history) is list and history and all(k==chosen for k in history),
        'random future cannot be relabeled by its first gain')
    return chosen,number(label['remaining_loss'])


def complete_score(returned,label,model,target,logging,*,mode):
    b,n=public_return(returned)
    need(mode in ('DM','DR'),'standard reference mode')
    if returned['terminal']:
        need(label is None,'terminal return has no fictitious gain observation')
        return terminal_cost(returned)
    actions=tuple(target)
    pi=distribution(target,actions)
    need(type(model) is dict and tuple(model)==actions,'all public-state conditional risk candidates')
    m={k:number(model[k]) for k in actions}
    chosen,y=static_label(label,actions)
    need(0<=y<=500-n and all(0<=v<=500-n for v in m.values()),'complete remaining loss and public budget')
    estimate=sum(pi[k]*m[k] for k in actions)
    if mode=='DR':
        pi,mu=support(target,logging)
        need(mu[chosen]>0,'an observed action cannot have zero logging mass')
        estimate+=pi[chosen]/mu[chosen]*(y-m[chosen])
    # A DR pseudo-outcome may lie outside the physical loss range; clipping it
    # would change its expectation and is deliberately absent.
    return F(n-b)+estimate


def choose(scores,candidates):
    need(tuple(scores)==tuple(candidates) and candidates,'complete fixed candidate order')
    need(all(type(scores[k]) is F for k in candidates),'no unsupported/missing value hidden by fallback')
    return min(candidates,key=lambda k:scores[k])


def evaluate(law,models,targets,assumed_logging,*,mode='DR'):
    """Evaluate a fully specified finite law, never historical robot OPE."""
    actions=law['gain_actions'];out={};counts=dict(terminal_rows=0,logged_rows=0)
    for option,branches in law['options'].items():
        need(sum(number(x['mass']) for x in branches)==1,'each option has its complete population')
        total=F(0)
        for branch in branches:
            p=number(branch['mass']);r=branch['public_return'];h=r['history_token']
            if r['terminal']:
                total+=p*complete_score(r,None,None,None,None,mode=mode);counts['terminal_rows']+=1
            else:
                mu=distribution(law['logging'][h],actions)
                for k in actions:
                    if not mu[k]:continue
                    label=dict(schema='FACTUAL_COMPLETE_STATIC_LABEL_V1',selected=k,gain_history=[k],remaining_loss=branch['remaining_losses'][k])
                    total+=p*mu[k]*complete_score(r,label,models[h],targets[h],assumed_logging[h],mode=mode)
                    counts['logged_rows']+=1
        out[option]=total
    return out,counts
