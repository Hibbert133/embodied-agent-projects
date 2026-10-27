"""Standard joint EKF reference: public XY, sent commands, declared input priors.

Unqualified approximate free-space model. Never controls or creates an Env.
Clipped Gaussian moments approximate the float32 actuation law; no safety claim.
"""
from copy import deepcopy
from math import erf,exp,pi,sqrt
import hashlib,json
import numpy as np

SCHEMA='GRAYBOX_OBSERVER_V1';SCALE=.01;SIGMA=.05
INITIAL=(0.,.6);LOW=(-.5,.4);HIGH=(.5,1.)
GRID=tuple((rho,kappa) for rho in (0.,.5,.9) for kappa in (.05,.2,.8))
PARAM_PRIOR_VAR=np.array([.25**2/3,.2**2/3,.2**2/3])

def parameter_prior_variance(axis):
    require(axis in (0,1),'XY row index');v=PARAM_PRIOR_VAR.copy()
    if axis==1:v[:2]=v[:2][::-1]
    return v

def require(ok,message):
    if not ok:raise ValueError(message)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def vector(value,n):
    require(type(value) is list and len(value)==n and all(type(x) in (float,int) and np.isfinite(x) for x in value),'ordinary finite public vector')
    return np.array(value,float)

def sent(value):
    u=vector(value,4);require(np.max(abs(u))<=1 and np.array_equal(u,np.asarray(u,np.float32).astype(float)),'exact bounded float32 sent command')
    return u

def moments(mu,sigma,lower=-1.,upper=1.):
    """E clip(N), Var clip(N), d E clip(N)/d mu for scalar continuous noise."""
    require(all(np.isfinite(x) for x in (mu,sigma,lower,upper)) and sigma>=0 and lower<upper,'normal moment arguments')
    if sigma==0:return float(np.clip(mu,lower,upper)),0.,float(lower<mu<upper)
    a=(lower-mu)/sigma;b=(upper-mu)/sigma
    cdf=lambda z:.5*erf(z/sqrt(2))+.5
    phi=lambda z:exp(-.5*z*z)/sqrt(2*pi)
    pa,pb=cdf(a),cdf(b);inside=max(0.,pb-pa);fa,fb=phi(a),phi(b)
    mean=lower*pa+mu*inside+sigma*(fa-fb)+upper*(1-pb)
    second=lower**2*pa+(mu*mu+sigma*sigma)*inside+2*mu*sigma*(fa-fb)+sigma*sigma*(a*fa-b*fb)+upper**2*(1-pb)
    # Round-off can produce tiny negative variance for effectively deterministic tails.
    require(second-mean*mean>=-1e-12,'negative clipped Gaussian variance')
    return mean,max(0.,second-mean*mean),inside

def parameters(value):
    require(type(value) is dict and set(value)=={'rho','kappa','observation_variance','acceleration_variance'},'strict plant parameters; no fault or private fields')
    require(all(type(x) in (int,float) and np.isfinite(x) for x in value.values()),'finite plant parameters')
    require(0<=value['rho']<1 and 0<value['kappa']<=1 and value['observation_variance']>0 and value['acceleration_variance']>=0,'stable working plant parameters')
    return deepcopy(value)

def default_parameters(rho=.5,kappa=.2):return parameters(dict(rho=rho,kappa=kappa,observation_variance=1e-6,acceleration_variance=6.25e-8))

def initial_axis(axis,y,known_nominal=False):
    m=np.zeros(6);m[:3]=[INITIAL[axis],y,0.];m[3+axis]=1.
    p=np.diag([0.,1e-10,1e-4,*([0.]*3 if known_nominal else parameter_prior_variance(axis).tolist())])
    return dict(mean=m.tolist(),covariance=p.tolist())

def validate_axis(value):
    require(type(value) is dict and set(value)=={'mean','covariance'},'strict approximate axis belief')
    mean=vector(value['mean'],6);rows=value['covariance'];require(type(rows) is list and len(rows)==6,'six covariance rows')
    cov=np.array([vector(r,6) for r in rows]);require(np.max(abs(cov-cov.T))<1e-10,'symmetric covariance')
    require(np.linalg.eigvalsh(cov).min()>=-1e-10,'positive semidefinite covariance');return mean,cov

def advance(axis,belief,command,plant,q_parameter=0.,ledger=None):
    """Predict one step before seeing its observation; affine row is [a_x,a_y,b]."""
    require(axis in (0,1) and type(q_parameter) in (int,float) and np.isfinite(q_parameter) and q_parameter>=0,'axis and parameter process scale')
    x,p=validate_axis(belief);u=sent(command);plant=parameters(plant);phi=np.array([u[0],u[1],1.])
    cov=p.copy();cov[3:,3:]+=q_parameter*np.diag(parameter_prior_variance(axis))
    action,variance,daction=moments(float(x[3:]@phi),SIGMA)
    requested=x[0]+SCALE*action;gate=float(LOW[axis]<requested<HIGH[axis]);mocap=float(np.clip(requested,LOW[axis],HIGH[axis]))
    rho=plant['rho'];beta=(1-rho)*plant['kappa'];velocity=rho*x[2]+beta*(mocap-x[1]);position=x[1]+velocity
    jac=np.eye(6);jac[0,:]=0.;jac[0,0]=gate;jac[0,3:]=gate*SCALE*daction*phi
    jac[2,:]=beta*jac[0,:];jac[2,1]-=beta;jac[2,2]+=rho
    jac[1,:]=jac[2,:];jac[1,1]+=1.
    noise=np.zeros((6,2));noise[:,0]=[gate,beta*gate,beta*gate,0.,0.,0.];noise[:,1]=[0.,1.,1.,0.,0.,0.]
    process=noise@np.diag([SCALE**2*variance,plant['acceleration_variance']])@noise.T
    after=x.copy();after[:3]=[mocap,position,velocity];after_cov=jac@cov@jac.T+process;after_cov=(after_cov+after_cov.T)/2
    if ledger is not None:ledger['axis_predictions']=ledger.get('axis_predictions',0)+1
    return dict(mean=after.tolist(),covariance=after_cov.tolist()),dict(action_mean=action,action_variance=variance,action_mean_derivative=daction,
        requested_target_mean=requested,workspace_mean_clipped=not bool(gate),jacobian=jac.tolist(),process_covariance=process.tolist())

def observe(belief,y,plant,ledger=None):
    require(type(y) in (int,float) and np.isfinite(y),'finite current public coordinate');x,p=validate_axis(belief);plant=parameters(plant)
    variance=p[1,1]+plant['observation_variance'];require(variance>0,'positive innovation variance')
    residual=float(y-x[1]);gain=p[:,1]/variance;after=x+gain*residual
    j=np.eye(6);j[:,1]-=gain;after_cov=j@p@j.T+np.outer(gain,gain)*plant['observation_variance'];after_cov=(after_cov+after_cov.T)/2
    if ledger is not None:ledger['axis_observations']=ledger.get('axis_observations',0)+1
    return dict(mean=after.tolist(),covariance=after_cov.tolist()),dict(innovation=residual,innovation_variance=float(variance),
        negative_log_likelihood=.5*(residual**2/variance+np.log(2*pi*variance)))

class Observer:
    def __init__(self,initial_xy,plants,*,q_parameter=0.,known_nominal=False):
        y=vector(initial_xy,2);require(type(plants) is list and len(plants)==2,'one plant per XY coordinate')
        require(type(known_nominal) is bool,'nominal experiment declaration')
        require(type(q_parameter) in (int,float),'ordinary parameter process scale')
        self.plants=[parameters(p) for p in plants];self.q_parameter=float(q_parameter);self.known_nominal=known_nominal
        require(np.isfinite(q_parameter) and q_parameter>=0 and (not known_nominal or q_parameter==0),'nominal parameters fixed during declared clean training')
        self.beliefs=[initial_axis(i,float(y[i]),known_nominal) for i in range(2)];self.at_calls=0;self.current=y.tolist();self.pending=None
    def snapshot(self):
        return dict(schema=SCHEMA,at_calls=self.at_calls,current_xy=list(self.current),beliefs=deepcopy(self.beliefs),plants=deepcopy(self.plants),
            q_parameter=self.q_parameter,known_nominal=self.known_nominal,belief_is_observed_private_state=False,
            predictive_or_physical_qualification=False,probability_or_safety_guarantee=False)
    def plan(self,command,at_calls,ledger=None):
        require(type(at_calls) is int and at_calls==self.at_calls and at_calls<500 and self.pending is None,'one causally ordered pending command')
        sent(command);beliefs=[];diagnostics=[]
        for i in range(2):
            b,d=advance(i,self.beliefs[i],command,self.plants[i],self.q_parameter,ledger);beliefs.append(b);diagnostics.append(d)
        self.pending=dict(before_sha256=digest(self.snapshot()),at_calls=at_calls,command=list(command),predicted_beliefs=beliefs,diagnostics=diagnostics)
        return deepcopy(self.pending)
    def consume(self,saved,observed_xy,completed_calls,ledger=None):
        require(self.pending is not None and digest(saved)==digest(self.pending),'unchanged saved filter plan before observation')
        require(digest(self.snapshot())==saved['before_sha256'],'filter state changed after saved plan')
        require(type(completed_calls) is int and completed_calls==self.at_calls+1,'no future, duplicate, or skipped observation')
        y=vector(observed_xy,2);diagnostics=[]
        for i in range(2):
            self.beliefs[i],d=observe(self.pending['predicted_beliefs'][i],float(y[i]),self.plants[i],ledger);diagnostics.append(d)
        self.current=y.tolist();self.at_calls=completed_calls;self.pending=None;return diagnostics
    def forecast(self,commands,ledger=None):
        require(self.pending is None and type(commands) is list and 0<len(commands)<=500-self.at_calls,'only declared future commands, before their outcomes')
        beliefs=deepcopy(self.beliefs);out=[]
        for command in commands:
            for i in range(2):beliefs[i],_=advance(i,beliefs[i],command,self.plants[i],self.q_parameter,ledger)
            out.append(dict(position_xy=[b['mean'][1] for b in beliefs],variance_xy=[b['covariance'][1][1] for b in beliefs]))
        return out

def validate_trace(trace):
    require(type(trace) is dict and set(trace)=={'initial_xy','steps'},'strict nominal public trajectory; no oracle or identity features')
    vector(trace['initial_xy'],2);require(type(trace['steps']) is list and 0<len(trace['steps'])<=500,'observed nonempty trace')
    for i,row in enumerate(trace['steps']):
        require(type(row) is dict and set(row)=={'at_calls','command','after_xy'} and type(row['at_calls']) is int and row['at_calls']==i,'continuous actual public history')
        sent(row['command']);vector(row['after_xy'],2)

def fit_nominal_grid(traces,weights=None,ledger=None):
    """Finite declared plant grid, innovations only; no fault/noise/private labels."""
    require(type(traces) is list and bool(traces),'nominal TRAIN trajectories')
    for trace in traces:validate_trace(trace)
    weights=np.ones(len(traces))/len(traces) if weights is None else np.asarray(weights,float)
    require(weights.shape==(len(traces),) and np.isfinite(weights).all() and np.min(weights)>0 and abs(weights.sum()-1)<1e-10,'positive trajectory weights sum to one')
    scores=[]
    for rho,kappa in GRID:
        plants=[default_parameters(rho,kappa)]*2;totals=np.zeros(2)
        for trace,w in zip(traces,weights):
            model=Observer(trace['initial_xy'],plants,known_nominal=True)
            for row in trace['steps']:
                plan=model.plan(row['command'],row['at_calls'],ledger);d=model.consume(plan,row['after_xy'],row['at_calls']+1,ledger)
                totals+=w*np.array([v['negative_log_likelihood'] for v in d])/len(trace['steps'])
        scores.append(totals)
        if ledger is not None:ledger['nominal_grid_candidate_evaluations']=ledger.get('nominal_grid_candidate_evaluations',0)+1
    scores=np.asarray(scores);chosen=[int(np.argmin(scores[:,i])) for i in range(2)]
    return dict(schema='GRAYBOX_NOMINAL_GRID_FIT_V1',plants=[default_parameters(*GRID[j]) for j in chosen],selected_grid_indices=chosen,
        per_candidate_per_axis_nll=scores.tolist(),traces=len(traces),physical_prediction_qualified=False,controller_or_task_qualified=False)
