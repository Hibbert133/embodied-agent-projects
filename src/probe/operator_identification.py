"""Standard affine prediction-error identification above fixed robot policies.

Only completed visible transitions and frozen nominal forward predictors enter
the fit. Effective affine parameters are point estimates, not certified physical
actuator parameters. Experimental simulation execution must disclose this.
"""
from dataclasses import dataclass,asdict
import numpy as np
from scipy.optimize import least_squares
from src.probe.forward_prediction import ForwardQuery,ForwardHistory,features,vector
from src.probe.continuous import ContinuousTransition
from src.probe.frame_identification import canonical_hash


@dataclass(frozen=True)
class OperatorSample:
    step: int
    query: ForwardQuery
    displacement: tuple

    def __post_init__(self):
        if type(self.step) is not int or self.step<3 or type(self.query) is not ForwardQuery:raise ValueError("completed visible sample required")
        object.__setattr__(self,"displacement",vector(self.displacement,2))


def visible_samples(transitions):
    if not transitions:return ()
    if any(type(r) is not ContinuousTransition for r in transitions):raise ValueError("only visible transitions accepted")
    history=ForwardHistory(transitions[0].before);samples=[]
    for row in transitions:
        query=history.request(row.command);target=history.observe(row)
        if query is not None:samples.append(OperatorSample(history.calls,query,target))
    return tuple(samples)


def sample_digest(samples):return canonical_hash([asdict(s) for s in samples])


class ForwardOperatorProblem:
    """Vectorized frozen mean model with an analytic six-parameter Jacobian."""
    def __init__(self,model,samples):
        allowed={"method","training_samples","mean","scale","physical_response_qualified","probability_guarantee","coefficients","ridge","feature_count","training_rmse"}
        if set(model)!=allowed or model.get("method") not in ("LINEAR_ARX","QUADRATIC_STATE") or any(type(s) is not OperatorSample for s in samples):
            raise ValueError("registered forward model/visible samples required")
        if model["physical_response_qualified"] is not False or model["probability_guarantee"] is not False:raise ValueError("nominal point model scope was changed")
        self.kind=model["method"];self.samples=tuple(samples)
        self.base=np.array([features(s.query,self.kind) for s in samples]);self.targets=np.array([s.displacement for s in samples])
        self.x=np.array([[*s.query.command[:2],1.] for s in samples]);size=10 if self.kind=="LINEAR_ARX" else 20
        self.mean=np.array(vector(model["mean"],size));self.scale=np.array(vector(model["scale"],size))
        coefficient=np.asarray(model["coefficients"],dtype=float);expected=11 if size==10 else 231
        if coefficient.shape!=(expected,2) or not np.isfinite(coefficient).all() or (self.scale<=0).any():raise ValueError("invalid frozen coefficients/scaler")
        self.constant=coefficient[0];self.linear=coefficient[1:size+1].T;self.indices=(6,7) if size==10 else (9,10)
        self.quadratic=np.zeros((2,size,size))
        if size==20:
            a,b=np.triu_indices(size)
            for index,(i,j) in enumerate(zip(a,b),size+1):
                self.quadratic[:,i,j]+=coefficient[index]/(1 if i==j else 2)
                if i!=j:self.quadratic[:,j,i]+=coefficient[index]/2

    def predictions(self,parameters,*,jacobian=False):
        p=np.asarray(parameters,dtype=float).reshape(2,3);effective=self.x@p.T
        inputs=self.base.copy();inputs[:,self.indices]=np.clip(effective,-1,1)
        z=(inputs-self.mean)/self.scale
        predicted=self.constant+z@self.linear.T+np.einsum("ni,oij,nj->no",z,self.quadratic,z)
        if not jacobian:return predicted
        gradient=self.linear[None,:,:]+2*np.einsum("oij,nj->noi",self.quadratic,z)
        derivative=gradient[:,:,self.indices]/self.scale[list(self.indices)]
        derivative*=((effective>-1)&(effective<1))[:,None,:]
        jac=np.concatenate((derivative[:,:,0,None]*self.x[:,None,:],derivative[:,:,1,None]*self.x[:,None,:]),axis=2)
        return predicted,jac.reshape(-1,6)

    def residual(self,p):return ((self.predictions(p)-self.targets)/.001).ravel()
    def jacobian(self,p):return self.predictions(p,jacobian=True)[1]/.001

    def linear_start(self):
        # Frozen linear response on the same observed history gives an agnostic
        # initialization. Quadratic model uses its local zero-input derivative.
        identity=np.array([[1.,0.,0.],[0.,1.,0.]])
        if self.kind=="LINEAR_ARX":
            zero=np.zeros((2,3));baseline=self.predictions(zero)
            response=self.linear[:,self.indices]/self.scale[list(self.indices)]
            if np.linalg.svd(response,compute_uv=False)[-1]<1e-8:return identity.ravel()
            coefficient=np.linalg.lstsq(self.x,self.targets-baseline,rcond=None)[0]
            return np.linalg.solve(response,coefficient.T).ravel()
        return identity.ravel()


def infer_operator(model,samples):
    if any(type(s) is not OperatorSample for s in samples):raise ValueError("only completed visible samples accepted")
    if any(a.step>=b.step for a,b in zip(samples,samples[1:])):raise ValueError("samples must be chronological")
    result={"valid":False,"samples":len(samples),"sample_digest":sample_digest(samples),
            "physical_response_qualified":False,"probability_guarantee":False,"research_simulation_only":True}
    if len(samples)<6:return {**result,"reason":"INSUFFICIENT_SAMPLES"}
    x=np.array([[*s.query.command[:2],1.] for s in samples]);rank=int(np.linalg.matrix_rank(x))
    scale=np.sqrt(np.mean(x*x,axis=0));condition=float(np.linalg.cond(x/np.where(scale>1e-12,scale,1.)))
    result.update(design_rank=rank,scaled_condition=condition if np.isfinite(condition) else None)
    if rank!=3 or not np.isfinite(condition) or condition>1e6:return {**result,"reason":"MISSING_OR_ILL_CONDITIONED_INPUT_SUPPORT"}
    problem=ForwardOperatorProblem(model,samples);lower=np.array([-2.,-2.,-.3,-2.,-2.,-.3]);upper=-lower
    trials=[]
    if problem.kind=="LINEAR_ARX":
        candidate=problem.linear_start();effective=problem.x@candidate.reshape(2,3).T
        trials.append({"parameters":candidate.tolist(),"success":bool(np.all(np.abs(effective)<=1)),"nfev":0,"start":"CLOSED_LINEAR"})
        start=np.clip(candidate,lower+1e-9,upper-1e-9)
        refined=least_squares(problem.residual,start,jac=problem.jacobian,bounds=(lower,upper),method="trf",
                              ftol=1e-8,xtol=1e-8,gtol=1e-8,x_scale=1.,loss="linear",max_nfev=64)
        trials.append({"parameters":refined.x.tolist(),"success":bool(refined.success),"nfev":int(refined.nfev),"start":"BOUNDED_LINEAR_REFINEMENT"})
    else:
        starts=[np.array([[np.cos(angle),-np.sin(angle),0.],[np.sin(angle),np.cos(angle),0.]]).ravel() for angle in (0.,np.pi/2,np.pi,3*np.pi/2)]
        for index,start in enumerate(starts):
            fitted=least_squares(problem.residual,start,jac=problem.jacobian,bounds=(lower,upper),method="trf",
                                 ftol=1e-8,xtol=1e-8,gtol=1e-8,x_scale=1.,loss="linear",max_nfev=64)
            trials.append({"parameters":fitted.x.tolist(),"success":bool(fitted.success),"nfev":int(fitted.nfev),"start":index})
    for trial in trials:
        p=np.array(trial["parameters"]);trial["residual_rmse_m"]=float(np.sqrt(np.mean((problem.predictions(p)-problem.targets)**2)))
    usable=[t for t in trials if t["success"] and np.all(np.array(t["parameters"])>=lower-1e-12) and np.all(np.array(t["parameters"])<=upper+1e-12)]
    result["optimizer_trials"]=trials
    if not usable:return {**result,"reason":"OPTIMIZER_OR_PARAMETER_DOMAIN_FAILURE"}
    selected=min(usable,key=lambda t:t["residual_rmse_m"]);p=np.array(selected["parameters"]).reshape(2,3)
    singular=np.linalg.svd(p[:,:2],compute_uv=False);result.update(matrix_xy=p[:,:2].tolist(),bias_xy=p[:,2].tolist(),
                    residual_rmse_m=selected["residual_rmse_m"],singular_values=singular.tolist(),selected_start=selected["start"])
    if singular[-1]<.25 or singular[0]>4:return {**result,"reason":"UNSTABLE_ESTIMATED_INVERSE"}
    return {**result,"valid":True,"reason":"POINT_FORWARD_PREDICTION_ERROR_FIT"}


def affine_controller(matrix,bias,*,source="ESTIMATED_AFFINE"):
    matrix=np.asarray(matrix,dtype=float);bias=np.asarray(vector(bias,2))
    if matrix.shape!=(2,2) or not np.isfinite(matrix).all():raise ValueError("invalid affine controller")
    inverse=np.linalg.inv(matrix)
    return {"source":source,"matrix_xy":inverse.tolist(),"offset":[*(-inverse@bias).tolist(),0.,0.]}


def identity_controller():return {"source":"UNCORRECTED","matrix_xy":np.eye(2).tolist(),"offset":[0.,0.,0.,0.]}


def encode_controller(controller,raw_policy):
    if type(controller) is not dict or set(controller)!={"source","matrix_xy","offset"} or controller["source"] not in ("UNCORRECTED","ESTIMATED_AFFINE","LEGACY_OFFSET","ORACLE_EVALUATOR"):
        raise ValueError("invalid saved controller schema")
    matrix=np.asarray(controller["matrix_xy"],dtype=float);offset=np.asarray(vector(controller["offset"],4))
    if matrix.shape!=(2,2) or not np.isfinite(matrix).all() or any(offset[2:]):raise ValueError("invalid saved controller numbers")
    if controller["source"]=="UNCORRECTED" and controller!=identity_controller():raise ValueError("uncorrected controller was changed")
    desired=np.clip(np.asarray(vector(raw_policy,4),dtype=np.float32),-1,1).astype(float)
    sent=desired.copy();sent[:2]=matrix@desired[:2]+offset[:2]
    return np.clip(sent,-1,1).astype(np.float32)
