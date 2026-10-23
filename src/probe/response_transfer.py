"""Conditional bounded-error / bounded-drift cached affine-response verification.

This is a standard set-membership/interpolation baseline. It does not qualify
the response model or error envelope for a real robot. Its proposals require a
separately verified observation contract before any physical deployment.
"""
from fractions import Fraction
import math
import numbers
import numpy as np
from src.probe.action_support import CommandSupport,assess_query,command,point,ratio,SCOPE


def real(value):
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,numbers.Real) or not np.isfinite(value):
        raise ValueError("response values must be finite real numbers")
    return Fraction.from_float(float(value))


def weights(evidence,query):
    """Exact weights on an independent subset; no floating-rank approval."""
    assessment=assess_query(evidence,query)
    if not assessment["structurally_supported"]: raise ValueError("query is outside observed input support")
    independent=evidence.independent_points
    indices=[]
    for p in independent:
        indices.append(next(i for i,c in enumerate(evidence.commands) if point(c)==p))
    r=len(indices); q=(*point(command(query)),Fraction(1))
    selected=[(*point(evidence.commands[i]),Fraction(1)) for i in indices]
    matrix=[[selected[col][row] for col in range(r)]+[q[row]] for row in range(3)]
    for col in range(r):
        pivot=next(i for i in range(col,3) if matrix[i][col])
        matrix[col],matrix[pivot]=matrix[pivot],matrix[col]
        scale=matrix[col][col];matrix[col]=[v/scale for v in matrix[col]]
        for row in range(3):
            if row==col: continue
            factor=matrix[row][col]
            matrix[row]=[v-factor*b for v,b in zip(matrix[row],matrix[col])]
    if any(any(row) for row in matrix[r:]): raise ArithmeticError("exact interpolation consistency failure")
    w=tuple(matrix[i][-1] for i in range(r))
    if any(sum(w[i]*selected[i][col] for i in range(r))!=q[col] for col in range(3)):
        raise ArithmeticError("exact interpolation does not reconstruct query")
    return indices,w


def rounded(value,direction):
    try: number=float(value)
    except OverflowError: return None
    if not math.isfinite(number): return None
    exact=Fraction.from_float(number)
    if direction<0 and exact>value: number=math.nextafter(number,-math.inf)
    if direction>0 and exact<value: number=math.nextafter(number,math.inf)
    return number if math.isfinite(number) else None


def verify_cached_response(evidence,query,observable_responses,cached_model,*,
                           assumed_componentwise_error_bound=None,maximum_response_discrepancy=.1,
                           maximum_coefficient_drift_per_step=0.,observation_steps=None,query_step=None):
    """Propose reuse/reacquisition/rejection under explicit analytic assumptions.

    `observable_responses` must be legitimately observed actuator-equivalent xy
    responses, not hidden executed actions. A Gaussian standard deviation is
    not a deterministic error envelope and must not be supplied as one.
    """
    result={"scope":SCOPE,"model_validity_qualified":False,"task_success_guarantee":False,
            "probability_guarantee":False,"proposal_only":True}
    if type(evidence) is not CommandSupport: raise ValueError("requires previous commanded-input evidence")
    query=command(query)
    tolerance=real(maximum_response_discrepancy)
    if tolerance<0: raise ValueError("response discrepancy tolerance must be nonnegative")
    drift=real(maximum_coefficient_drift_per_step)
    if drift<0: raise ValueError("coefficient drift bound must be nonnegative")
    if drift>0: result["scope"]="BOUNDED_DRIFT_PRECLIP_AFFINE_XY"
    if assumed_componentwise_error_bound is None:
        return {**result,"action":"UNQUALIFIED_RESPONSE_MODEL"}
    epsilon=real(assumed_componentwise_error_bound)
    if epsilon<0: raise ValueError("response error envelope must be nonnegative")
    if drift>0 and (observation_steps is None or query_step is None):
        return {**result,"action":"UNQUALIFIED_TIME_CONTRACT"}
    if observation_steps is not None or query_step is not None:
        if not isinstance(observation_steps,(list,tuple)) or len(observation_steps)!=len(evidence.commands) or \
                type(query_step) is not int or query_step<0 or any(type(t) is not int or not 0<=t<=query_step for t in observation_steps):
            raise ValueError("measurement times must precede the query")
        if any(a>b for a,b in zip(observation_steps,observation_steps[1:])):
            raise ValueError("measurement times must be chronological")
        times=list(observation_steps)
    else:
        times=[0]*len(evidence.commands);query_step=0
    assessment=assess_query(evidence,query)
    if not assessment["structurally_supported"]:
        return {**result,"action":"REACQUIRE_INPUT_SUPPORT","input_assessment":assessment}
    if not isinstance(observable_responses,(list,tuple,np.ndarray)) or len(observable_responses)!=len(evidence.commands):
        raise ValueError("observable responses must align with previous commands")
    responses=[]
    for row in observable_responses:
        if not isinstance(row,(list,tuple,np.ndarray)) or len(row)!=2: raise ValueError("invalid observable response")
        responses.append(tuple(real(v) for v in row))
    if not isinstance(cached_model,(list,tuple,np.ndarray)) or len(cached_model)!=2:
        raise ValueError("cached model must be a planar affine matrix")
    model=[]
    for row in cached_model:
        if not isinstance(row,(list,tuple,np.ndarray)) or len(row)!=3: raise ValueError("invalid cached affine model")
        model.append(tuple(real(v) for v in row))
    q=(*point(command(query)),Fraction(1))
    cached=[sum(coef*x for coef,x in zip(row,q)) for row in model]
    candidates=[weights(evidence,query)]
    reverse=CommandSupport(tuple(reversed(evidence.commands)))
    reversed_indices,reversed_w=weights(reverse,query)
    recent_indices=[len(evidence.commands)-1-i for i in reversed_indices]
    if recent_indices!=candidates[0][0]: candidates.append((recent_indices,reversed_w))
    intervals=[]; any_drift=False
    for indices,w in candidates:
        center=[sum(weight*responses[i][axis] for i,weight in zip(indices,w)) for axis in range(2)]
        measurement_radius=epsilon*sum(abs(weight) for weight in w)
        drift_radius=drift*sum(abs(weight)*(query_step-times[i])*(1+abs(point(evidence.commands[i])[0])+abs(point(evidence.commands[i])[1]))
                              for i,weight in zip(indices,w))
        radius=measurement_radius+drift_radius;any_drift=any_drift or drift_radius>0
        intervals.append({"indices":indices,"weights":w,"lower":[c-radius for c in center],"upper":[c+radius for c in center],
                          "measurement_radius":measurement_radius,"drift_radius":drift_radius})
    # Each subset supplies a valid outer interval under the same declared
    # contract. Intersecting them preserves it; disjoint intervals falsify it.
    lower=[max(interval["lower"][axis] for interval in intervals) for axis in range(2)]
    upper=[min(interval["upper"][axis] for interval in intervals) for axis in range(2)]
    if any(lo>hi for lo,hi in zip(lower,upper)):
        return {**result,"action":"REJECT_DECLARED_RESPONSE_CONTRACT","independent_subset_count":len(intervals)}
    bound=max(max(abs(lo-p),abs(hi-p)) for lo,hi,p in zip(lower,upper,cached))
    minimum=max(max(Fraction(0),lo-p,p-hi) for lo,hi,p in zip(lower,upper,cached))
    action="REUSE_CONDITIONAL_PREDICTION" if bound<=tolerance else "REJECT_CACHE_FOR_QUERY" if minimum>tolerance else "REACQUIRE_PRECISION"
    if action=="REACQUIRE_PRECISION" and any_drift: action="REACQUIRE_TEMPORAL_VALIDITY"
    lo_float=[rounded(v,-1) for v in lower];hi_float=[rounded(v,1) for v in upper]
    bound_float=rounded(bound,1)
    if any(v is None for v in [*lo_float,*hi_float,bound_float]): action="ABSTAIN_NUMERICAL_RANGE"
    return {**result,"action":action,"input_rank":evidence.rank,
        "basis_subsets":[{"indices":v["indices"],"exact_weights":[ratio(w) for w in v["weights"]],
                          "measurement_radius_exact":ratio(v["measurement_radius"]),"drift_radius_exact":ratio(v["drift_radius"])} for v in intervals],
        "response_interval_lower":lo_float,
        "response_interval_upper":hi_float,"maximum_conditional_cache_discrepancy":bound_float,
        "minimum_conditional_cache_discrepancy":rounded(minimum,-1),
        "maximum_discrepancy_exact":ratio(bound),"minimum_discrepancy_exact":ratio(minimum),
        "uses_independent_subsets_only":True,"query_step":query_step,
        "assumptions":"Pre-clip affine response, observable equivalent response, valid componentwise measurement-error envelope, and the declared coefficient-drift bound between supplied measurement times and query time. Conditions not established by this function."}
