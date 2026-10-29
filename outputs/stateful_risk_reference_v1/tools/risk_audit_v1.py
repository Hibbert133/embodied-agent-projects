"""Independent exact expansion; main scoring module must be disabled."""
from fractions import Fraction


def truth(law,targets):
    result={}
    for option,rows in law['options'].items():
        answer=Fraction(0)
        for row in rows:
            r=row['public_return'];p=Fraction(row['mass']);n=r['after_steps'];b=r['before_steps']
            if r['terminal']:answer+=p*((n if r['success'] else 500)-b)
            else:
                for action in law['gain_actions']:
                    answer+=p*Fraction(targets[r['history_token']][action])*((n-b)+Fraction(row['remaining_losses'][action]))
        result[option]=answer
    return result


def expanded(law,models,targets,assumed_logging,mode):
    """Expand residual into outcome and coefficient terms, not the main formula."""
    result={}
    for option,rows in law['options'].items():
        value=Fraction(0)
        for row in rows:
            r=row['public_return'];p=Fraction(row['mass']);h=r['history_token']
            if r['terminal']:
                value+=p*((r['after_steps'] if r['success'] else 500)-r['before_steps']);continue
            value+=p*(r['after_steps']-r['before_steps'])
            for k in law['gain_actions']:
                pi=Fraction(targets[h][k]);model=Fraction(models[h][k])
                if mode=='DM':value+=p*pi*model
                else:
                    actual=Fraction(law['logging'][h][k]);assumed=Fraction(assumed_logging[h][k])
                    if pi and not assumed:raise ValueError('independent unsupported action')
                    ratio=Fraction(0) if not pi else pi/assumed
                    value+=p*(actual*ratio*Fraction(row['remaining_losses'][k])+(pi-actual*ratio)*model)
        result[option]=value
    return result


def conditional_selection_shortcut(law,targets):
    """Deliberately invalid survivor-only average, reported as a counterexample."""
    values={}
    for a,rows in law['options'].items():
        keep=[r for r in rows if not r['public_return']['terminal']]
        mass=sum(Fraction(r['mass']) for r in keep)
        if not mass:values[a]=None;continue
        total=Fraction(0)
        for row in keep:
            r=row['public_return'];h=r['history_token'];loss=r['after_steps']-r['before_steps']
            loss+=sum(Fraction(targets[h][k])*Fraction(row['remaining_losses'][k]) for k in law['gain_actions'])
            total+=Fraction(row['mass'])*loss
        values[a]=total/mass
    return values
