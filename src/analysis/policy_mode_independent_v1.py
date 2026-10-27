"""Independent scalar leaf and factor decomposition; no main math imports."""
import math,struct


def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def norm2(x,y):return math.sqrt(x*x+y*y)


def mode(task,obs):
    x,y,z=map(float,obs[:3]);px,py,pz=map(float,obs[4:7])
    if task=='reach-v3':return [0,0]
    if task=='push-v3':return [0 if norm2(x-(px-.005),y-py)>.02 else 1 if abs(z-pz)>.04 else 2,
        0 if norm2(x-px,y-py)>.02 or abs(z-pz)>.1 else 1]
    if task=='door-open-v3':return [0 if norm2(x-(px-.05),y-py)>.12 else 1 if abs(z-pz)>.04 else 2,1]
    raise ValueError('task')


def action(task,obs,choice):
    p=list(map(float,obs[4:7]));h=list(map(float,obs[:3]));k,g=choice
    if task=='reach-v3':
        if choice!=[0,0]:raise ValueError('reach leaf')
        target=list(map(float,obs[-3:]));gain=5.;grip=0.
    elif task=='push-v3':
        p[0]+=-.005
        if k==0:p[2]+=.2
        elif k==1:p[2]+=.03
        elif k!=2:raise ValueError('push leaf')
        target=list(map(float,obs[-3:])) if k==2 else p;gain=10.;grip=.6*g
    elif task=='door-open-v3':
        p[0]-=.05
        if k==0:p=[p[0]+.06,p[1]+.02,p[2]+.2]
        elif k==1:p=[p[0]+.06,p[1]+.02,p[2]]
        elif k!=2:raise ValueError('door leaf')
        target=p;gain=25.;grip=1.
    else:raise ValueError('task')
    return [f32(gain*(target[i]-h[i])) for i in range(3)]+[f32(grip)]


def factors(task,a,b):
    left,right=mode(task,a),mode(task,b)
    values=[action(task,a,left),action(task,b,left),action(task,a,right),action(task,b,right)]
    out=dict(mode_a=left,mode_b=right,mode_changed=left!=right)
    for stage in ('raw','sent'):
        q=values if stage=='raw' else [[min(1.,max(-1.,x)) for x in row] for row in values]
        d=[q[3][i]-q[0][i] for i in (2,3)]
        m=[((q[2][i]-q[0][i])+(q[3][i]-q[1][i]))/2 for i in (2,3)]
        s=[((q[1][i]-q[0][i])+(q[3][i]-q[2][i]))/2 for i in (2,3)]
        if [m[i]+s[i] for i in range(2)]!=d:raise ValueError('scalar functional sum')
        out[stage]=dict(delta_zg=d,mode_zg=m,state_zg=s,total_energy=sum(x*x for x in d)/2,mode_energy=sum(x*x for x in m)/2,
            state_energy=sum(x*x for x in s)/2,cross_energy=sum(2*x*y for x,y in zip(m,s))/2,total_L1=sum(abs(x) for x in d)/2,
            mode_L1=sum(abs(x) for x in m)/2,state_L1=sum(abs(x) for x in s)/2,
            any_difference=any(x!=0 for x in d),mode_nonzero=any(x!=0 for x in m),state_nonzero=any(x!=0 for x in s))
    return out


def window_mean(records):
    if not records:raise ValueError('empty actual window')
    n=len(records);out={'mode_changed_fraction':sum(1 for r in records if r['mode_changed'])/n}
    for stage in ('raw','sent'):
        for field in ('total_energy','mode_energy','state_energy','cross_energy','total_L1','mode_L1','state_L1'):
            out[stage+'_'+field]=sum(r[stage][field] for r in records)/n
        for field in ('any_difference','mode_nonzero','state_nonzero'):
            out[stage+'_'+field+'_fraction']=sum(1 for r in records if r[stage][field])/n
        out[stage+'_any_difference_in_window']=any(r[stage]['any_difference'] for r in records)
    return out
