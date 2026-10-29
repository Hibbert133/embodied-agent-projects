"""Predetermined abstract finite tables; no MuJoCo, robot trajectories or sampling."""
from copy import deepcopy

GAINS=('K0','K1')


def public(h,d,terminal=False,success=False):
    return dict(schema='FINITE_PUBLIC_RETURN_V1',history_token=h,before_steps=16,after_steps=16+d,terminal=terminal,success=success)


def branch(h,d,ys,terminal=False,success=False):
    return dict(mass='1/2',public_return=public(h,d,terminal,success),remaining_losses=dict(zip(GAINS,ys)))


def definitions():
    # C,V,M are abstract options, NOT replacements for registered robot macros.
    # M has 20 abstract cost units here, not a modified physical relocation.
    law=dict(gain_actions=list(GAINS),options={
        'C':[branch('C',0,(24,80)),branch('C',0,(400,60))],
        'V':[branch('V0',8,(24,80)),branch('V1',8,(400,60))],
        'M':[branch('M0',20,(4,80)),branch('M1',20,(400,6))]})
    targets={'C':dict(K0=0,K1=1),'V0':dict(K0=1,K1=0),'V1':dict(K0=0,K1=1),
             'M0':dict(K0=1,K1=0),'M1':dict(K0=0,K1=1)}
    means={'C':dict(K0=212,K1=70),'V0':dict(K0=24,K1=80),'V1':dict(K0=400,K1=60),
           'M0':dict(K0=4,K1=80),'M1':dict(K0=400,K1=6)}
    law['logging']={h:dict(K0='1/4',K1='3/4') for h in means}
    unchanged=deepcopy(law);unchanged_means=deepcopy(means)
    unchanged['options']['M']=[branch('M0',20,(24,80)),branch('M1',20,(400,60))]
    unchanged_means['M0']=deepcopy(means['V0']);unchanged_means['M1']=deepcopy(means['V1'])
    failure=deepcopy(law);failure['options']={k:failure['options'][k] for k in ('C','V')}
    failure['options']['V'][1]=branch('VF',8,(0,0),True,False)
    success=deepcopy(failure)
    success['options']['C']=[branch('C',0,(100,100)),branch('C',0,(100,100))]
    success['options']['V']=[branch('V0',8,(160,200)),branch('VS',8,(0,0),True,True)]
    success_means=deepcopy(means);success_means['C']=dict(K0=100,K1=100);success_means['V0']=dict(K0=160,K1=200)
    unsupported=deepcopy(law);unsupported['logging']['M1']=dict(K0=1,K1=0)
    return dict(STATE_CHANGE=(law,means,targets),NO_STATE_EFFECT=(unchanged,unchanged_means,targets),
        TERMINAL_FAILURE=(failure,means,targets),TERMINAL_SUCCESS=(success,success_means,targets),
        NO_OVERLAP=(unsupported,means,targets))
