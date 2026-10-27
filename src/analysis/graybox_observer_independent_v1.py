"""Scalar-loop numerical check of a standard approximate observer, not physics.

No production model import. Gaussian moments use quadrature, covariance updates
use the conditional covariance identity rather than the production Joseph form.
"""
from math import exp,log,pi,sqrt
from scipy.integrate import quad

def clipped_moments(mu,sigma=.05):
    if sigma==0:return min(1.,max(-1.,mu)),0.,float(-1<mu<1)
    density=lambda z:exp(-z*z/2)/sqrt(2*pi)
    points=[z for z in ((-1-mu)/sigma,(1-mu)/sigma) if -12<z<12]
    def expectation(power):
        return quad(lambda z:min(1.,max(-1.,mu+sigma*z))**power*density(z),-12,12,points=points,epsabs=1e-12,epsrel=1e-12)[0]
    mean=expectation(1);second=expectation(2)
    lo=max(-12.,(-1-mu)/sigma);hi=min(12.,(1-mu)/sigma)
    derivative=quad(density,lo,hi,epsabs=1e-12,epsrel=1e-12)[0] if lo<hi else 0.
    return mean,max(0.,second-mean*mean),derivative

def predict(axis,belief,command,plant,q):
    x=list(belief['mean']);p=[list(r) for r in belief['covariance']];phi=[command[0],command[1],1.]
    prior=[(.25 if axis==0 else .2)**2/3,(.25 if axis==1 else .2)**2/3,.2**2/3]
    for i in range(3):p[3+i][3+i]+=q*prior[i]
    mu=sum(x[3+i]*phi[i] for i in range(3));mean,var,d=clipped_moments(mu)
    low=(-.5,.4)[axis];high=(.5,1.)[axis];request=x[0]+.01*mean
    gate=int(low<request<high);target=min(high,max(low,request));rho=plant['rho'];beta=(1-rho)*plant['kappa']
    v=rho*x[2]+beta*(target-x[1]);xx=[target,x[1]+v,v,*x[3:]]
    f=[[0.]*6 for _ in range(6)];f[0][0]=gate
    for i in range(3):f[0][3+i]=gate*.01*d*phi[i]
    for i in range(6):f[2][i]=beta*f[0][i]
    f[2][1]-=beta;f[2][2]+=rho
    for i in range(6):f[1][i]=f[2][i]
    f[1][1]+=1.
    for i in range(3,6):f[i][i]=1.
    target_noise=[gate,beta*gate,beta*gate,0.,0.,0.];accel_noise=[0.,1.,1.,0.,0.,0.]
    pp=[[sum(f[i][k]*p[k][l]*f[j][l] for k in range(6) for l in range(6))+
         target_noise[i]*target_noise[j]*.0001*var+accel_noise[i]*accel_noise[j]*plant['acceleration_variance']
         for j in range(6)] for i in range(6)]
    return dict(mean=xx,covariance=pp)

def update(belief,y,plant):
    x=belief['mean'];p=belief['covariance'];s=p[1][1]+plant['observation_variance'];r=y-x[1]
    mean=[x[i]+p[i][1]*r/s for i in range(6)]
    cov=[[p[i][j]-p[i][1]*p[1][j]/s for j in range(6)] for i in range(6)]
    return dict(mean=mean,covariance=cov),.5*(r*r/s+log(2*pi*s))
