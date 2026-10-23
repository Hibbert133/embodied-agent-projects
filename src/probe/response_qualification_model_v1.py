"""Strict visible TRAIN trajectories and fixed, trajectory-weighted ridge models."""
from dataclasses import dataclass
import numpy as np
from src.probe.forward_prediction import ForwardQuery, vector

KINDS=("FRESH_LINEAR_ARX","FRESH_QUADRATIC_STATE")


@dataclass(frozen=True)
class VisibleTrajectory:
    task:str
    trajectory_id:str
    split:str
    initial:tuple
    commands:tuple
    observations:tuple

    def __post_init__(self):
        if self.task not in ("push-v3","reach-v3","door-open-v3") or self.split not in ("TRAIN","CAL","QUAL") or not self.trajectory_id:
            raise ValueError("registered visible trajectory metadata required")
        object.__setattr__(self,"initial",vector(self.initial,39))
        commands=tuple(vector(v,4) for v in self.commands);observations=tuple(vector(v,39) for v in self.observations)
        if not 0<=len(commands)<=160 or len(commands)!=len(observations) or any(max(abs(v) for v in u)>1 for u in commands):
            raise ValueError("bounded continuous observed trajectory required")
        object.__setattr__(self,"commands",commands);object.__setattr__(self,"observations",observations)

    @classmethod
    def from_dict(cls,value):
        if set(value)!={"task","trajectory_id","split","initial","commands","observations"}:
            raise ValueError("unknown, oracle or future trajectory fields")
        return cls(**value)


def samples(trajectory):
    if type(trajectory) is not VisibleTrajectory:raise ValueError("strict visible trajectory required")
    states=np.asarray((trajectory.initial,*trajectory.observations))
    for i,command in enumerate(trajectory.commands):
        if i<2:continue
        yield i,ForwardQuery(tuple(states[i]),tuple(states[i,:3]-states[i-1,:3]),tuple(states[i-1,:3]-states[i-2,:3]),command),states[i+1,:2]-states[i,:2]


def features(query,kind):
    if type(query) is not ForwardQuery:raise ValueError("strict causal query required")
    if kind in ("FRESH_LINEAR_ARX","FROZEN_OLD_LINEAR_ARX"):
        return np.array([*query.last_displacement,*query.prior_displacement,*query.command])
    if kind!="FRESH_QUADRATIC_STATE":raise ValueError("fixed model kind required")
    obs=np.asarray(query.observation);hand=obs[:3]
    return np.r_[hand,query.last_displacement,query.prior_displacement,query.command,obs[3],obs[4:7]-hand,obs[-3:]-hand]


def design(z,quadratic):
    z=np.atleast_2d(z);x=np.c_[np.ones(len(z)),z]
    if quadratic:
        i,j=np.triu_indices(z.shape[1]);x=np.c_[x,z[:,i]*z[:,j]]
    if not np.isfinite(x).all():raise ValueError("nonfinite design")
    return x


def fit(trajectories,task,kind):
    if kind not in KINDS or not trajectories or any(type(t) is not VisibleTrajectory or t.split!="TRAIN" or t.task!=task for t in trajectories):
        raise ValueError("TRAIN-only matching visible trajectories required")
    if len({t.trajectory_id for t in trajectories})!=len(trajectories):raise ValueError("duplicate trajectory")
    inputs=[];targets=[];weights=[]
    for trajectory in trajectories:
        rows=list(samples(trajectory))
        if not rows:raise ValueError("training trajectory has no real AR2 history")
        for _,query,y in rows:
            inputs.append(features(query,kind));targets.append(y);weights.append(1/len(rows))
    if len(inputs)<32:raise ValueError("at least 32 observed training responses required")
    a,y,w=np.asarray(inputs),np.asarray(targets),np.asarray(weights)
    mean=np.average(a,axis=0,weights=w);scale=np.sqrt(np.average((a-mean)**2,axis=0,weights=w))
    scale=np.where(scale>1e-6,scale,1.);x=design((a-mean)/scale,kind=="FRESH_QUADRATIC_STATE")
    penalty=.001*np.eye(x.shape[1]);penalty[0,0]=0
    coefficient=np.linalg.solve(x.T@(w[:,None]*x)+penalty,x.T@(w[:,None]*y))
    if not np.isfinite(coefficient).all():raise ValueError("nonfinite trained model")
    return {"method":kind,"task":task,"mean":mean.tolist(),"scale":scale.tolist(),"coefficients":coefficient.tolist(),
        "ridge":.001,"feature_count":x.shape[1],"training_responses":len(y),"training_trajectories":len(trajectories),
        "trajectory_total_weight":1.,"physical_response_qualified":False,"probability_guarantee":False}


def predict(model,query):
    z=(features(query,model["method"])-np.asarray(model["mean"]))/model["scale"]
    result=(design(z,model["method"]=="FRESH_QUADRATIC_STATE")@np.asarray(model["coefficients"]))[0]
    if not np.isfinite(result).all():raise ValueError("nonfinite prediction")
    return result
