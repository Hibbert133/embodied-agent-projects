"""Frozen nominal ARX inversion and a standard passive affine-response fit.

Only visible positions, previous visible displacement and commanded inputs are
used. Numeric fit validity does not qualify sensor inversion or task outcomes.
"""
from dataclasses import dataclass,asdict
import numpy as np
from src.probe.continuous import ContinuousTransition
from src.probe.frame_identification import NominalARX
from src.probe.action_support import command


@dataclass(frozen=True)
class InverseSample:
    step: int
    command: tuple[float,...]
    estimate: tuple[float,float]
    phase: str

    def to_dict(self): return asdict(self)


class NominalObserver:
    def __init__(self,model):
        if type(model) is not NominalARX: raise ValueError("requires a frozen nominal ARX model")
        self.a,self.b,self.c=np.asarray(model.inertia),np.asarray(model.response),np.asarray(model.intercept)
        if self.a.shape!=(2,2) or self.b.shape!=(2,2) or self.c.shape!=(2,) or not all(np.isfinite(v).all() for v in (self.a,self.b,self.c)):
            raise ValueError("invalid nominal coefficients")
        if np.linalg.svd(self.b,compute_uv=False)[-1]<1e-8: raise ValueError("noninvertible nominal response")
        self.previous=None; self.delta=None; self.calls=0

    def observe(self,transition,*,phase):
        if type(transition) is not ContinuousTransition or phase not in ("PROBE","POLICY"):
            raise ValueError("requires registered visible transition/phase")
        if len(transition.before)!=39 or len(transition.after)!=39 or any(isinstance(v,(bool,np.bool_)) for v in transition.before+transition.after) or \
                not np.isfinite(transition.before+transition.after).all():
            raise ValueError("invalid visible observation")
        if self.previous is not None and transition.before!=self.previous: raise ValueError("observation continuity was broken")
        sent=command(transition.command)
        delta=np.asarray(transition.after[:2])-transition.before[:2]
        self.calls+=1
        estimate=np.linalg.solve(self.b,delta-self.a@self.delta-self.c) if self.delta is not None else None
        self.previous=transition.after; self.delta=delta
        if estimate is None: return None  # No unobserved initial velocity is invented.
        if not np.isfinite(estimate).all(): raise ValueError("nonfinite inverse observation")
        return InverseSample(self.calls,sent,tuple(float(x) for x in estimate),phase)


def passive_affine_fit(samples):
    if any(type(row) is not InverseSample for row in samples): raise ValueError("requires visible inverse samples only")
    x=np.array([[r.command[0],r.command[1],1.] for r in samples]).reshape(-1,3)
    y=np.array([r.estimate for r in samples]).reshape(-1,2)
    rank=int(np.linalg.matrix_rank(x)) if len(x) else 0
    result={"samples":len(x),"design_rank":rank,"valid":False,"matrix":None,"scaled_condition":None,
            "residual_rmse":None,"model_validity_qualified":False,"probability_guarantee":False}
    if len(x)<8: return {**result,"reason":"INSUFFICIENT_SAMPLES"}
    if rank!=3: return {**result,"reason":"MISSING_INPUT_SUPPORT"}
    scales=np.sqrt(np.mean(x*x,axis=0));scaled=x/scales
    condition=float(np.linalg.cond(scaled));result["scaled_condition"]=condition
    if condition>1e6: return {**result,"reason":"ILL_CONDITIONED"}
    coefficient=np.linalg.lstsq(scaled,y,rcond=None)[0]/scales[:,None]
    return {**result,"valid":True,"reason":"NUMERIC_AFFINE_FIT","matrix":coefficient.T.tolist(),
            "residual_rmse":float(np.sqrt(np.mean((x@coefficient-y)**2)))}


def mean_blocks(samples,block_size=4):
    if type(block_size) is not int or block_size!=4 or any(type(r) is not InverseSample for r in samples):
        raise ValueError("requires registered four-sample visible blocks")
    blocks=[]
    for start in range(0,len(samples)-block_size+1,block_size):
        rows=samples[start:start+block_size]
        if [r.step for r in rows]!=list(range(rows[0].step,rows[0].step+4)):
            raise ValueError("block must contain consecutive observed transitions")
        known=np.mean([r.command[:2] for r in rows],axis=0)
        estimate=np.mean([r.estimate for r in rows],axis=0)
        phases=set(r.phase for r in rows)
        blocks.append({"start_step":rows[0].step,"end_step":rows[-1].step,
            "phase":next(iter(phases)) if len(phases)==1 else "MIXED",
            "known_nominal_command_mean":known.tolist(),"inverse_response_mean":estimate.tolist(),
            "nominal_mean_error_inf":float(np.max(np.abs(estimate-known)))})
    return blocks
