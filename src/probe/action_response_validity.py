"""Experimental cache validation in a local affine response-residual model.

The empirical nominal RMS scale is not a verified error envelope. LP intervals
are conditional on a local residual family and valid grouped error bounds;
simulation hypotheses may use them but no physical/probability qualification is
conferred. No actuator truth, seed, environment or future observation is input.
"""
from dataclasses import dataclass
import math
import numpy as np
from scipy.optimize import linprog

from src.probe.forward_prediction import ForwardQuery, vector
from src.probe.operator_identification import (OperatorSample, ForwardOperatorProblem,
    affine_controller, encode_controller, sample_digest)

PRIMITIVES = {
    "WIDE_X4": ((.4, 0., 0., 0.),) * 2 + ((-.4, 0., 0., 0.),) * 2,
    "WIDE_Y4": ((0., .4, 0., 0.),) * 2 + ((0., -.4, 0., 0.),) * 2,
    "ZERO4": ((0., 0., 0., 0.),) * 4,
}
COEFFICIENT_BOUNDS_MM = ((-20., 20.), (-20., 20.), (-10., 10.))
LP_OPTIONS = {"primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9, "maxiter": 1000}
SCOPE = "UNQUALIFIED_LOCAL_AFFINE_MEAN_RESPONSE_RESIDUAL"
ABSOLUTE_TOLERANCE_MM = .1
RELATIVE_TOLERANCE = .5


@dataclass(frozen=True)
class CachedPoint:
    matrix_xy: tuple
    bias_xy: tuple

    def __post_init__(self):
        if not isinstance(self.matrix_xy,(tuple,list,np.ndarray)) or len(self.matrix_xy)!=2:
            raise ValueError("planar point matrix required")
        matrix = np.asarray([vector(row,2) for row in self.matrix_xy], dtype=float)
        bias = np.asarray(vector(self.bias_xy, 2))
        if matrix.shape != (2, 2) or not np.isfinite(matrix).all() or np.any(np.abs(matrix) > 2.000000001) or np.any(np.abs(bias) > .300000001):
            raise ValueError("registered visible point parameters required")
        singular = np.linalg.svd(matrix, compute_uv=False)
        if singular[-1] < .25 - 1e-9 or singular[0] > 4 + 1e-9:
            raise ValueError("point controller inverse is outside registered numerical domain")
        object.__setattr__(self, "matrix_xy", tuple(tuple(float(v) for v in row) for row in matrix))
        object.__setattr__(self, "bias_xy", tuple(float(v) for v in bias))

    @property
    def controller(self):
        return affine_controller(self.matrix_xy, self.bias_xy)

    @property
    def parameters(self):
        return np.column_stack((self.matrix_xy, self.bias_xy)).ravel()


@dataclass(frozen=True)
class ResidualDesign:
    commands_xy: tuple
    mean_residual_mm: tuple
    counts: tuple
    evidence_digest: str

    def __post_init__(self):
        n = len(self.commands_xy)
        x = np.asarray(self.commands_xy, dtype=float).reshape(-1, 2)
        y = np.asarray(self.mean_residual_mm, dtype=float).reshape(-1, 2)
        if x.shape != (n, 2) or y.shape != (n, 2) or not np.isfinite(x).all() or not np.isfinite(y).all() or np.any(np.abs(x) > 1):
            raise ValueError("invalid visible residual design")
        if len(self.counts) != n or any(type(c) is not int or c < 1 for c in self.counts) or sum(self.counts) > 500:
            raise ValueError("invalid observed group counts")
        if type(self.evidence_digest) is not str or not self.evidence_digest:
            raise ValueError("past evidence digest required")

    @property
    def x(self):
        return np.column_stack((np.asarray(self.commands_xy).reshape(-1, 2), np.ones(len(self.counts))))

    @property
    def y(self):
        return np.asarray(self.mean_residual_mm).reshape(-1, 2)


def forecast(model, cached, query):
    if type(cached) is not CachedPoint or type(query) is not ForwardQuery or model.get("method") != "LINEAR_ARX":
        raise ValueError("requires a visible cached point and causal linear query")
    return ForwardOperatorProblem(model, (OperatorSample(3, query, (0., 0.)),)).predictions(cached.parameters)[0]


def residual_design(model, cached, samples, *, mask_responses=False):
    if type(cached) is not CachedPoint or any(type(s) is not OperatorSample for s in samples) or any(a.step >= b.step for a,b in zip(samples,samples[1:])):
        raise ValueError("chronological completed visible samples required")
    if not samples:
        return ResidualDesign((), (), (), "EMPTY_VISIBLE_HISTORY")
    prediction = ForwardOperatorProblem(model, samples).predictions(cached.parameters)
    residual = (np.array([s.displacement for s in samples]) - prediction) * 1000
    grouped = {}
    for sample, value in zip(samples, residual):
        command = tuple(sample.query.command[:2])
        grouped.setdefault(command, []).append(np.zeros(2) if mask_responses else value)
    return ResidualDesign(tuple(grouped), tuple(tuple(float(x) for x in np.mean(values, axis=0)) for values in grouped.values()),
                          tuple(len(values) for values in grouped.values()), sample_digest(samples))


def action_envelope(model, cached):
    if type(cached) is not CachedPoint or model.get("method") != "LINEAR_ARX":
        raise ValueError("visible point model required")
    # Validate the full frozen model schema through the shared prediction problem.
    zero = ForwardQuery((0.,)*39, (0.,)*3, (0.,)*3, (0.,)*4)
    problem = ForwardOperatorProblem(model, (OperatorSample(3, zero, (0., 0.)),))
    response = problem.linear[:, problem.indices] / problem.scale[list(problem.indices)]
    controller = cached.controller
    zero_sent = encode_controller(controller, (0.,)*4)
    matrix, bias = np.asarray(cached.matrix_xy), np.asarray(cached.bias_xy)
    zero_effective = np.clip(matrix @ zero_sent[:2] + bias, -1, 1)
    commands, thresholds, raw = [], [], []
    for a in ((-1.,-1.), (-1.,1.), (1.,-1.), (1.,1.), (0.,0.)):
        sent = encode_controller(controller, (*a, 0., 0.))
        effective = np.clip(matrix @ sent[:2] + bias, -1, 1)
        signal_mm = float(np.max(np.abs(response @ (effective - zero_effective)))) * 1000
        commands.append(tuple(float(x) for x in sent[:2]))
        thresholds.append(ABSOLUTE_TOLERANCE_MM + RELATIVE_TOLERANCE * signal_mm)
        raw.append(a)
    return {"raw_policy_xy": raw, "sent_xy": commands, "thresholds_mm": thresholds}


def noise_scale(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("finite positive nominal reference RMS required")
    return float(value)


def mean_error_radii(design, sigma_m):
    return 2000 * noise_scale(sigma_m) / np.sqrt(design.counts)


def point_residual(design):
    if not len(design.counts):
        return np.zeros((3,2))
    weight = np.sqrt(np.asarray(design.counts))
    return np.linalg.lstsq(design.x * weight[:,None], design.y * weight[:,None], rcond=1e-10)[0]


def set_intervals(design, queries_xy, sigma_m):
    if type(design) is not ResidualDesign:
        raise ValueError("observed residual design required")
    queries = np.asarray(queries_xy, dtype=float).reshape(-1,2)
    if not np.isfinite(queries).all() or np.any(np.abs(queries)>1):
        raise ValueError("query must be a bounded sent xy command")
    radius = mean_error_radii(design, sigma_m)
    x = design.x
    inequalities = np.concatenate((x, -x)) if len(x) else None
    intervals = []
    for q in queries:
        objective = np.array([*q, 1.])
        lower, upper = [], []
        for axis in range(2):
            values = np.concatenate((design.y[:,axis] + radius, -design.y[:,axis] + radius)) if len(x) else None
            lo = linprog(objective, A_ub=inequalities, b_ub=values, bounds=COEFFICIENT_BOUNDS_MM, method="highs", options=LP_OPTIONS)
            hi = linprog(-objective, A_ub=inequalities, b_ub=values, bounds=COEFFICIENT_BOUNDS_MM, method="highs", options=LP_OPTIONS)
            if lo.status==2 or hi.status==2:
                return {"status":"CONTRACT_REJECTED", "intervals_mm":None}
            if not lo.success or not hi.success:
                return {"status":"NUMERICAL_FAILURE", "intervals_mm":None}
            lower.append(float(lo.fun)); upper.append(float(-hi.fun))
        intervals.append({"lower":lower, "upper":upper})
    return {"status":"FINITE", "intervals_mm":intervals}


def assess(design, envelope, sigma_m, mode="SET"):
    if mode not in ("SET", "GAUSSIAN", "POINT"):
        raise ValueError("unknown response-validation mode")
    sigma_m = noise_scale(sigma_m)
    queries = np.column_stack((envelope["sent_xy"], np.ones(len(envelope["sent_xy"]))))
    thresholds = np.asarray(envelope["thresholds_mm"])
    result = {"scope":SCOPE, "physical_response_qualified":False, "probability_guarantee":False,
              "evidence_digest":design.evidence_digest, "groups":len(design.counts), "observations":sum(design.counts),
              "noise_reference_rms_m":sigma_m, "thresholds_mm":thresholds.tolist(), "mode":mode}
    if mode=="SET":
        intervals=set_intervals(design, envelope["sent_xy"], sigma_m)
        if intervals["status"]!="FINITE":
            return {**result, **intervals}
        lower=np.array([i["lower"] for i in intervals["intervals_mm"]])
        upper=np.array([i["upper"] for i in intervals["intervals_mm"]])
    else:
        mean=queries @ point_residual(design)
        if mode=="GAUSSIAN":
            gram=(design.x.T * np.asarray(design.counts)) @ design.x + 1e-6*np.eye(3)
            radius=2000*sigma_m*np.sqrt(np.einsum("ni,ij,nj->n", queries,np.linalg.inv(gram),queries))
        else:
            radius=np.zeros(len(queries))
        lower,upper=mean-radius[:,None],mean+radius[:,None]
    maximum=np.max(np.maximum(np.abs(lower),np.abs(upper)),axis=1)
    minimum=np.max(np.maximum.reduce((lower,-upper,np.zeros_like(lower))),axis=1)
    status="COMPATIBLE" if np.all(maximum<=thresholds) else "INCOMPATIBLE" if np.any(minimum>thresholds) else "UNRESOLVED"
    return {**result,"status":status,"intervals_mm":[{"lower":lo.tolist(),"upper":hi.tolist()} for lo,hi in zip(lower,upper)],
            "worst_normalized_discrepancy":float(np.max(maximum/thresholds))}


def hypothetical_extension(design, program):
    # This is a prospective model prediction, never an observed measurement.
    coefficient=np.clip(point_residual(design), np.array([-20.,-20.,-10.])[:,None], np.array([20.,20.,10.])[:,None])
    grouped={q:[np.array(y)*n,n] for q,y,n in zip(design.commands_xy,design.mean_residual_mm,design.counts)}
    for command in program:
        q=tuple(float(np.float32(v)) for v in command[:2])
        prediction=np.array([*q,1.]) @ coefficient
        if q not in grouped:grouped[q]=[np.zeros(2),0]
        grouped[q][0]+=prediction; grouped[q][1]+=1
    return ResidualDesign(tuple(grouped),tuple(tuple(float(v) for v in total/n) for total,n in grouped.values()),
                          tuple(n for _,n in grouped.values()),"HYPOTHETICAL_FROM_PAST_POINT_FIT")


def choose_primitive(design, envelope, sigma_m, *, remaining_steps, reserved_task_steps=32, mode="SET"):
    if type(remaining_steps) is not int or type(reserved_task_steps) is not int or remaining_steps<0 or reserved_task_steps<0:
        raise ValueError("invalid physical budget")
    if remaining_steps<4+reserved_task_steps:
        return {"action":"STOP_BUDGET", "program_id":None,"scores":{},"physical_response_qualified":False}
    if mode not in ("SET","GAUSSIAN"):
        raise ValueError("unknown acquisition criterion")
    scores={}
    queries=np.column_stack((envelope["sent_xy"],np.ones(len(envelope["sent_xy"]))))
    for name,program in PRIMITIVES.items():
        extended=hypothetical_extension(design,program)
        if mode=="SET":
            intervals=set_intervals(extended,envelope["sent_xy"],sigma_m)
            if intervals["status"]!="FINITE":scores[name]=None;continue
            width=np.array([max(np.array(r["upper"])-np.array(r["lower"])) for r in intervals["intervals_mm"]])
            scores[name]=float(np.max(width/(2*np.asarray(envelope["thresholds_mm"]))))
        else:
            gram=(extended.x.T * np.asarray(extended.counts)) @ extended.x + 1e-6*np.eye(3)
            scores[name]=float(np.max(np.einsum("ni,ij,nj->n",queries,np.linalg.inv(gram),queries)))
    usable=[(value,name) for name,value in scores.items() if value is not None and np.isfinite(value)]
    if not usable:
        return {"action":"REFRESH_NUMERICAL_DESIGN", "program_id":None,"scores":scores,"physical_response_qualified":False}
    _,name=min(usable)
    return {"action":"REQUEST_MICRO_PROBE", "program_id":name,"scores":scores,
            "prospective_score_is_not_observed_evidence":True,"physical_response_qualified":False}
