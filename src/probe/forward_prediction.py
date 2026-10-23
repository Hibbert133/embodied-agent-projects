"""Standard visible forward predictors and trajectory-level split calibration.

Predictions target observed xy displacement, never an inverted actuator action.
No point fit, calibrated radius or input rank certifies fault transfer/control.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
import numbers
import numpy as np
from src.probe.action_support import command
from src.probe.continuous import ContinuousTransition

METHODS=("LEGACY_ARX","LINEAR_ARX","QUADRATIC_STATE","NEAREST_STATE")
RIDGE=1e-3
NEIGHBORS=16


def vector(values,size):
    if not isinstance(values,(tuple,list,np.ndarray)) or len(values)!=size or any(isinstance(x,(bool,np.bool_)) or not isinstance(x,numbers.Real) for x in values):
        raise ValueError("invalid visible numeric vector")
    result=np.asarray(values,dtype=float)
    if result.shape!=(size,) or not np.isfinite(result).all():raise ValueError("invalid visible numeric vector")
    return tuple(float(x) for x in result)


@dataclass(frozen=True)
class ForwardQuery:
    observation: tuple
    last_displacement: tuple
    prior_displacement: tuple
    command: tuple

    def __post_init__(self):
        object.__setattr__(self,"observation",vector(self.observation,39))
        object.__setattr__(self,"last_displacement",vector(self.last_displacement,3))
        object.__setattr__(self,"prior_displacement",vector(self.prior_displacement,3))
        object.__setattr__(self,"command",command(self.command))


class ForwardHistory:
    """A request precedes exactly one continuous observed execution."""
    def __init__(self,observation):
        self.current=vector(observation,39);self.deltas=[];self.pending=None;self.calls=0

    def request(self,sent):
        if self.pending is not None:raise ValueError("previous command has not been observed")
        sent=command(sent)
        query=ForwardQuery(self.current,self.deltas[-1],self.deltas[-2],sent) if len(self.deltas)>=2 else None
        self.pending=sent
        return query

    def observe(self,transition):
        if type(transition) is not ContinuousTransition or self.pending is None:raise ValueError("requires an earlier command request")
        before,after=vector(transition.before,39),vector(transition.after,39)
        if before!=self.current or command(transition.command)!=self.pending:raise ValueError("visible state/command continuity mismatch")
        delta=vector(np.asarray(after[:3])-before[:3],3)
        self.deltas=(self.deltas+[delta])[-2:]
        self.current=after;self.pending=None;self.calls+=1
        return tuple(float(x) for x in delta[:2])


def features(query,kind):
    if type(query) is not ForwardQuery:raise ValueError("requires a causal visible forward query")
    if kind=="LINEAR_ARX":
        return np.array([*query.last_displacement,*query.prior_displacement,*query.command])
    if kind not in ("QUADRATIC_STATE","NEAREST_STATE"):raise ValueError("unregistered predictor")
    observation=np.array(query.observation);hand=observation[:3]
    return np.concatenate((hand,query.last_displacement,query.prior_displacement,query.command,
                           observation[3:4],observation[4:7]-hand,observation[-3:]-hand))


def design(values,quadratic):
    values=np.atleast_2d(np.asarray(values,dtype=float))
    columns=[np.ones((len(values),1)),values]
    if quadratic:
        a,b=np.triu_indices(values.shape[1]);columns.append(values[:,a]*values[:,b])
    result=np.concatenate(columns,axis=1)
    if not np.isfinite(result).all():raise ValueError("nonfinite forward feature range")
    return result


@dataclass(frozen=True)
class TrainingSample:
    query: ForwardQuery
    displacement: tuple
    split: str="TRAIN"

    def __post_init__(self):
        if type(self.query) is not ForwardQuery:raise ValueError("visible training query required")
        object.__setattr__(self,"displacement",vector(self.displacement,2))


def fit_models(samples):
    if len(samples)<32 or any(type(row) is not TrainingSample or row.split!="TRAIN" for row in samples):
        raise ValueError("requires at least 32 training-only visible samples")
    target=np.array([s.displacement for s in samples]);models={}
    for method in METHODS[1:]:
        inputs=np.array([features(s.query,method) for s in samples]);mean=inputs.mean(axis=0);scale=inputs.std(axis=0)
        scale=np.where(scale>1e-6,scale,1.)
        z=(inputs-mean)/scale
        result={"method":method,"training_samples":len(samples),"mean":mean.tolist(),"scale":scale.tolist(),
                "physical_response_qualified":False,"probability_guarantee":False}
        if method=="NEAREST_STATE":
            result.update(inputs=z.tolist(),targets=target.tolist(),neighbors=NEIGHBORS)
        else:
            x=design(z,method=="QUADRATIC_STATE");penalty=RIDGE*np.eye(x.shape[1]);penalty[0,0]=0.
            coefficient=np.linalg.solve(x.T@x+penalty,x.T@target)
            result.update(coefficients=coefficient.tolist(),ridge=RIDGE,feature_count=x.shape[1],
                          training_rmse=float(np.sqrt(np.mean((x@coefficient-target)**2))))
        models[method]=result
    return models


class Predictors:
    def __init__(self,models,legacy):
        if set(models)!=set(METHODS[1:]):raise ValueError("complete registered model set required")
        self.models=models;self.legacy=legacy;self.cached={}
        for name,model in models.items():
            size=10 if name=="LINEAR_ARX" else 20
            mean=np.asarray(vector(model["mean"],size));scale=np.asarray(vector(model["scale"],size))
            if (scale<=0).any() or model["method"]!=name:raise ValueError("invalid training scaler")
            if name=="NEAREST_STATE":
                x=np.asarray(model["inputs"]);y=np.asarray(model["targets"])
                if x.shape!=(model["training_samples"],20) or y.shape!=(len(x),2) or model["neighbors"]!=16:raise ValueError("invalid nearest model")
                self.cached[name]=(mean,scale,x,y)
            else:
                coefficient=np.asarray(model["coefficients"])
                expected=11 if name=="LINEAR_ARX" else 231
                if coefficient.shape!=(expected,2) or model["ridge"]!=RIDGE:raise ValueError("invalid ridge model")
                self.cached[name]=(mean,scale,coefficient)
            if not all(np.isfinite(v).all() for v in self.cached[name]):raise ValueError("nonfinite model")

    def predict(self,query):
        if type(query) is not ForwardQuery:raise ValueError("causal visible query required")
        result={"LEGACY_ARX":(np.array(self.legacy.inertia)@query.last_displacement[:2]+
                 np.array(self.legacy.response)@query.command[:2]+self.legacy.intercept).tolist()}
        for name,arrays in self.cached.items():
            z=(features(query,name)-arrays[0])/arrays[1]
            if name=="NEAREST_STATE":
                distance=np.sum((arrays[2]-z)**2,axis=1)
                indices=np.argsort(distance,kind="stable")[:NEIGHBORS]
                weights=1/(distance[indices]+1e-6)
                prediction=np.sum(arrays[3][indices]*weights[:,None],axis=0)/weights.sum()
            else:prediction=(design(z,name=="QUADRATIC_STATE")@arrays[2])[0]
            result[name]=prediction.tolist()
        if any(not np.isfinite(v).all() for v in result.values()):raise ValueError("nonfinite forward prediction")
        return result


def conformal_radius(scores,alpha=.1):
    """Finite-sample trajectory order statistic, conditional on exchangeability.

    Each score is ONE complete trajectory's maximum xy error. This function
    cannot establish exchangeability, fault transfer, or physical safety.
    """
    if isinstance(alpha,(bool,np.bool_)) or not math.isfinite(alpha) or not 0<alpha<1:raise ValueError("invalid error level")
    if any(s is None or isinstance(s,(bool,np.bool_)) or not math.isfinite(s) or s<0 for s in scores):
        return {"radius":None,"rank":None,"episodes":len(scores),"reason":"MISSING_OR_INVALID_TRAJECTORY_SCORE"}
    rank=math.ceil((len(scores)+1)*(1-Fraction(str(alpha))))
    if rank>len(scores):return {"radius":None,"rank":rank,"episodes":len(scores),"reason":"INSUFFICIENT_CALIBRATION"}
    return {"radius":float(sorted(scores)[rank-1]),"rank":rank,"episodes":len(scores),
            "reason":"TRAJECTORY_ORDER_STATISTIC","exchangeability_verified":False,"physical_response_qualified":False}
