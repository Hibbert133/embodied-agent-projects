"""Standard query-specific input informativity for a planar affine actuator.

This module checks commanded-input geometry, not robot-model validity, physical
safety, or task success. The row-span characterization is standard linear
algebra / data informativity, not a new control theorem. No Oracle information,
future observations, or environment handle is accepted.
"""
from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import json
import numbers
import re
import numpy as np

RANK_TOL = 1e-10
QUERY_TOL = 1e-8
SCOPE = "STATIC_PRECLIP_AFFINE_XY"


def point(value):
    return tuple(Fraction.from_float(v) for v in value[:2])


def cross(a,b):
    return a[0]*b[1]-a[1]*b[0]


def difference(a,b):
    return tuple(x-y for x,y in zip(a,b))


def ratio(value):
    return [str(value.numerator),str(value.denominator)]


def command(value):
    if not isinstance(value, (list, tuple, np.ndarray)) or (isinstance(value,np.ndarray) and value.ndim!=1) or len(value) != 4:
        raise ValueError("command must be a numeric four-vector")
    if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Real) for v in value):
        raise ValueError("command must contain real numbers only")
    result = np.asarray(value, dtype=float)
    if result.shape != (4,) or not np.isfinite(result).all() or np.any(np.abs(result) > 1):
        raise ValueError("command must be bounded and finite")
    return tuple(float(v) for v in result)


@dataclass(frozen=True)
class CommandSupport:
    commands: tuple[tuple[float, ...], ...]
    rank: int = field(init=False)
    numerical_rank: int = field(init=False)
    independent_points: tuple = field(init=False)
    basis: tuple[tuple[float, ...], ...] = field(init=False)
    singular_values: tuple[float, ...] = field(init=False)
    digest: str = field(init=False)

    def __post_init__(self):
        if not isinstance(self.commands, (list, tuple)):
            raise ValueError("command evidence must be a sequence")
        rows = tuple(command(v) for v in self.commands)
        object.__setattr__(self, "commands", rows)
        x = np.asarray([[r[0], r[1], 1.] for r in rows], dtype=float).reshape(-1,3)
        if len(x):
            _, singular, vt = np.linalg.svd(x, full_matrices=False)
            numerical_rank = int(np.sum(singular > RANK_TOL * singular[0]))
            basis = tuple(tuple(v) for v in vt[:numerical_rank])
        else:
            singular, numerical_rank, basis = (), 0, ()
        independent=[]
        for row in rows:
            p=point(row)
            if not independent or (len(independent)==1 and p!=independent[0]) or \
                    (len(independent)==2 and cross(difference(independent[1],independent[0]),difference(p,independent[0]))!=0):
                independent.append(p)
            if len(independent)==3: break
        object.__setattr__(self, "rank", len(independent))
        object.__setattr__(self, "numerical_rank", numerical_rank)
        object.__setattr__(self, "independent_points", tuple(independent))
        object.__setattr__(self, "basis", basis)
        object.__setattr__(self, "singular_values", tuple(float(v) for v in singular))
        object.__setattr__(self, "digest", hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest())


def assess_query(evidence, query):
    """Check [query_x,query_y,1] in the span of previously commanded inputs.

    Sufficiency for response identification additionally requires a static
    affine model and observable noiseless actuator-equivalent responses. The
    present API deliberately does not assert those conditions for MetaWorld.
    """
    if type(evidence) is not CommandSupport:
        raise ValueError("requires commanded-input evidence only")
    query = command(query)
    q = np.array([*query[:2],1.])
    p=point(query); independent=evidence.independent_points
    supported = evidence.rank==3 or (evidence.rank==1 and p==independent[0]) or \
        (evidence.rank==2 and cross(difference(independent[1],independent[0]),difference(p,independent[0]))==0)
    basis = np.asarray(evidence.basis).reshape(-1,3)
    projection = basis.T @ (basis @ q)
    residual = q-projection
    distance = float(np.linalg.norm(residual))
    numerically_near = distance <= QUERY_TOL * max(1.,float(np.linalg.norm(q)))
    x = np.array([[r[0],r[1],1.] for r in evidence.commands]).reshape(-1,3)
    weights = np.linalg.lstsq(x.T,q,rcond=RANK_TOL)[0] if len(x) else np.array([])
    witness = None
    if not supported:
        # Delta @ X.T = 0, but Delta @ q != 0. It is a hypothetical model
        # difference; it is not the injected operator or a task-failure label.
        if not independent:
            exact=(Fraction(0),Fraction(0),Fraction(1))
        elif evidence.rank==1:
            exact=(Fraction(1),Fraction(0),-independent[0][0]) if p[0]!=independent[0][0] else (Fraction(0),Fraction(1),-independent[0][1])
        else:
            dx,dy=difference(independent[1],independent[0]); x0,y0=independent[0]
            exact=(-dy,dx,dy*x0-dx*y0)
        scale=max(abs(v) for v in exact)
        exact=tuple(v/scale for v in exact)
        gap=sum(v*z for v,z in zip(exact,(*p,Fraction(1))))
        if gap==0 or any(sum(v*z for v,z in zip(exact,(*point(row),Fraction(1))))!=0 for row in evidence.commands):
            raise ArithmeticError("invalid exact nullspace witness")
        v = np.array([float(value) for value in exact])
        delta = np.vstack((v,np.zeros(3)))
        witness = {"delta_operator":delta.tolist(), "query_response_difference":(delta@q).tolist(),
            "delta_first_row_exact":[ratio(value) for value in exact],"query_first_output_difference_exact":ratio(gap),
            "probe_response_difference_exact":"0",
            "probe_response_difference_max_numeric":float(np.max(np.abs(x@delta.T))) if len(x) else 0.}
    return {"scope":SCOPE,"command_evidence_sha256":evidence.digest,"observed_command_count":len(x),
        "input_rank":evidence.rank,"numerical_rank":evidence.numerical_rank,
        "structurally_supported":bool(supported),"numerically_near_span":bool(numerically_near),"outside_span_norm":distance,
        "interpolation_weights":weights.tolist() if supported else None,
        "numerical_interpolation_amplification_l1":float(np.sum(np.abs(weights))) if supported else None,
        "nullspace_witness":witness,"model_validity_qualified":False,"probability_guarantee":False,
        "task_success_guarantee":False}


def recommend_completion(evidence, query, programs, *, remaining_budget, task_reserve):
    """Cheapest listed program completing this input scope, subject to budget.

    This is a structural baseline. It neither certifies probe safety nor chooses
    a statistically sufficient probe length. It does not execute any command.
    """
    if type(remaining_budget) is not int or type(task_reserve) is not int or remaining_budget < 0 or task_reserve < 0:
        raise ValueError("budgets must be nonnegative integers")
    current = assess_query(evidence, query)
    if current["structurally_supported"]:
        return {"action":"INPUT_SUPPORT_PRESENT","program_id":None,"probe_steps":0,"qualification_required":True}
    if type(programs) is not dict:
        raise ValueError("programs must be a registered command mapping")
    choices=[]
    for name, commands in programs.items():
        if not isinstance(name,str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}",name) is None or not isinstance(commands,(list,tuple)) or not commands:
            raise ValueError("invalid registered probe program")
        suffix = tuple(command(c) for c in commands)
        if len(suffix)+task_reserve > remaining_budget:
            continue
        extended = CommandSupport(evidence.commands+suffix)
        if assess_query(extended,query)["structurally_supported"]:
            choices.append((len(suffix),name))
    if not choices:
        return {"action":"ABSTAIN_INPUT_SCOPE","program_id":None,"probe_steps":0,"qualification_required":True}
    length,name=min(choices)
    return {"action":"REQUEST_SUPPORT_COMPLETION","program_id":name,"probe_steps":length,"qualification_required":True}
