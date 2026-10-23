"""Strict causal trajectories and fixed linear/GRU representations; no oracle fields."""
from dataclasses import dataclass
import numpy as np
from src.probe.forward_prediction import vector

METHODS=("HISTORY_LINEAR10","STATE_LINEAR20","QUADRATIC_STATE20","GRU_WINDOW1","GRU_WINDOW16")


@dataclass(frozen=True)
class HistoryTrajectory:
    task:str
    trajectory_id:str
    split:str
    initial:tuple
    commands:tuple
    observations:tuple

    def __post_init__(self):
        if self.task not in ("push-v3","reach-v3","door-open-v3") or self.split not in ("TRAIN","CAL","TEST") or not self.trajectory_id:raise ValueError("registered trajectory metadata")
        object.__setattr__(self,"initial",vector(self.initial,39));commands=tuple(vector(x,4) for x in self.commands);observations=tuple(vector(x,39) for x in self.observations)
        if not 0<=len(commands)<=168 or len(commands)!=len(observations) or any(max(abs(x) for x in u)>1 for u in commands):raise ValueError("bounded continuous trajectory required")
        object.__setattr__(self,"commands",commands);object.__setattr__(self,"observations",observations)
    @classmethod
    def from_dict(cls,value):
        if set(value)!={"task","trajectory_id","split","initial","commands","observations"}:raise ValueError("oracle/seed/unknown trajectory field")
        return cls(**value)


def states(t):
    if type(t) is not HistoryTrajectory:raise ValueError("strict public trajectory")
    return np.array((t.initial,*t.observations),float)


def inputs43(t):return np.c_[states(t)[:-1],np.asarray(t.commands).reshape(-1,4)]


def inputs20(t):
    s=states(t);u=np.asarray(t.commands).reshape(-1,4)
    if len(u)<3:return np.empty((0,20))
    hand=s[2:-1,:3]
    return np.c_[hand,s[2:-1,:3]-s[1:-2,:3],s[1:-2,:3]-s[:-3,:3],u[2:],s[2:-1,3],s[2:-1,4:7]-hand,s[2:-1,-3:]-hand]


def targets(t):return np.diff(states(t)[:,:2],axis=0)[2:]


def normalization(arrays,weights):
    x=np.concatenate(arrays);w=np.concatenate(weights);mean=np.sum(w[:,None]*x,axis=0)/sum(w);scale=np.sqrt(np.sum(w[:,None]*(x-mean)**2,axis=0)/sum(w))
    return mean,np.where(scale>1e-6,scale,1.)


def design(z,method):
    out=np.c_[np.ones(len(z)),z]
    if method=="QUADRATIC_STATE20":
        i,j=np.triu_indices(20);out=np.c_[out,z[:,i]*z[:,j]]
    return out


def fit_linear(trajectories,task,method):
    if method not in METHODS[:3] or not trajectories or any(type(t) is not HistoryTrajectory or t.task!=task or t.split!="TRAIN" for t in trajectories):raise ValueError("matching TRAIN-only trajectories")
    x=[];y=[];w=[]
    if len({t.trajectory_id for t in trajectories})!=len(trajectories):raise ValueError("duplicated trajectory")
    for t in trajectories:
        v=inputs20(t);v=v[:,3:13] if method=="HISTORY_LINEAR10" else v
        if not len(v):raise ValueError("TRAIN trajectory lacks common real history")
        x.append(v);y.append(targets(t));w.append(np.full(len(v),1/len(v)))
    if sum(map(len,x))<32:raise ValueError("TRAIN has fewer than32 common responses")
    mean,scale=normalization(x,w);a=design((np.concatenate(x)-mean)/scale,method);target=np.concatenate(y);weight=np.concatenate(w);reg=.001*np.eye(a.shape[1]);reg[0,0]=0
    coefficients=np.linalg.solve(a.T@(weight[:,None]*a)+reg,a.T@(weight[:,None]*target))
    if not np.isfinite(coefficients).all():raise ValueError("nonfinite response model")
    return {"method":method,"task":task,"mean":mean.tolist(),"scale":scale.tolist(),"coefficients":coefficients.tolist(),"ridge":.001,"feature_count":a.shape[1],
        "training_trajectories":len(trajectories),"training_responses":len(target),"trajectory_total_weight":1.,"probability_guarantee":False}


def gru_normalization(trajectories,task):
    if not trajectories or any(type(t) is not HistoryTrajectory or t.task!=task or t.split!="TRAIN" for t in trajectories):raise ValueError("TRAIN-only GRU statistics")
    x=[];y=[];w=[]
    for t in trajectories:
        v=inputs43(t)[2:]
        if not len(v):raise ValueError("TRAIN lacks common targets")
        x.append(v);y.append(targets(t));w.append(np.full(len(v),1/len(v)))
    xm,xs=normalization(x,w);ym,ys=normalization(y,w)
    return {"input_mean":xm.tolist(),"input_scale":xs.tolist(),"target_mean":ym.tolist(),"target_scale":ys.tolist(),"training_responses":sum(map(len,y)),"training_trajectories":len(trajectories)}


def causal_window(t,step,length):
    if type(t) is not HistoryTrajectory or type(step) is not int or not 0<=step<len(t.commands) or length not in (1,16):raise ValueError("actual causal window required")
    # Current observation and sent command precede the target at step+1.
    return inputs43(t)[max(0,step-length+1):step+1]


def gru_cell(x,h,parameters):
    w=np.asarray(parameters["weight_ih_l0"]);u=np.asarray(parameters["weight_hh_l0"]);b=np.asarray(parameters["bias_ih_l0"]);c=np.asarray(parameters["bias_hh_l0"])
    gates=x@w.T+b;hidden=h@u.T+c;ir,iz,inn=np.split(gates,3,axis=-1);hr,hz,hn=np.split(hidden,3,axis=-1)
    sigmoid=lambda v:np.exp(-np.logaddexp(0,-v))
    r=sigmoid(ir+hr);z=sigmoid(iz+hz);candidate=np.tanh(inn+r*hn)
    return (1-z)*candidate+z*h


def predict_gru_batch(model,t,steps):
    length=model["window"];n=len(steps)
    if not n:return np.empty((0,2))
    x=inputs43(t);mean=np.array(model["input_mean"]);scale=np.array(model["input_scale"]);h=np.zeros((n,32),float)
    starts=np.maximum(0,np.asarray(steps)-length+1);lens=np.asarray(steps)-starts+1
    for k in range(length):
        active=k<lens
        if not np.any(active):break
        value=(x[starts[active]+k]-mean)/scale;h[active]=gru_cell(value,h[active],model["gru"])
    return ((h@np.array(model["output_weight"]).T+model["output_bias"])*model["target_scale"]+model["target_mean"])


def predict(model,t):
    if type(t) is not HistoryTrajectory or t.task!=model["task"]:raise ValueError("matching public trajectory")
    if model["method"] in METHODS[3:]:out=predict_gru_batch(model,t,list(range(2,len(t.commands))))
    else:
        x=inputs20(t);x=x[:,3:13] if model["method"]=="HISTORY_LINEAR10" else x
        out=design((x-model["mean"])/model["scale"],model["method"])@np.array(model["coefficients"])
    if out.shape!=(max(len(t.commands)-2,0),2) or not np.isfinite(out).all():raise ValueError("finite common-population prediction required")
    return out
