"""Visible-only standard cache/revalidation references, not a novelty claim."""
from dataclasses import asdict, dataclass, fields
import numpy as np
from src.probe.cold_cache_prediction import PredictionQuery, SourceBelief, digest, forecast, response, score, source_belief
from src.probe.cold_start_response import ColdPrefix, TASKS, clipped_normal_mean
from src.probe.continuous import symmetric_program
from src.probe.forward_prediction import vector
from src.probe.operator_identification import affine_controller, encode_controller

METHODS = ("NO_PROBE", "ALWAYS8", "ALWAYS16_OLD", "STALE", "PERIODIC4", "PASSIVE_RECENT8",
           "CUSUM4", "PLUGIN4", "UNCERTAINTY4", "BALANCED4", "TASK_IVR4")
CHECK_METHODS = ("CUSUM4", "PLUGIN4", "UNCERTAINTY4", "BALANCED4", "TASK_IVR4")
OLD_METHODS = ("ALWAYS16_OLD", "PASSIVE_RECENT8")
BLOCK8 = symmetric_program(.4, 2)
BALANCED8 = symmetric_program(.4, 1)*2


@dataclass(frozen=True)
class VerifiedPoint:
    parameters: tuple
    belief: SourceBelief | None
    source_episode: int
    source_task: str
    evidence_sha256: str
    verification_success: bool

    def __post_init__(self):
        p = np.asarray(vector(self.parameters, 6)); matrix = p.reshape(2, 3)[:, :2]
        singular = np.linalg.svd(matrix, compute_uv=False)
        if self.verification_success is not True or type(self.source_episode) is not int or self.source_episode < 0 or self.source_task not in TASKS:
            raise ValueError("earlier actually verified point required")
        if singular[-1] < .25 or singular[0] > 4 or np.any(np.abs(p) > [2, 2, .3, 2, 2, .3]):
            raise ValueError("verified inverse outside numerical domain")
        if self.belief is not None and (type(self.belief) is not SourceBelief or tuple(p) != self.belief.parameters or self.source_task != self.belief.task or self.evidence_sha256 != self.belief.evidence_sha256):
            raise ValueError("cache point and observed belief differ")
        if len(self.evidence_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.evidence_sha256):
            raise ValueError("visible evidence digest required")
        object.__setattr__(self, "parameters", tuple(float(v) for v in p))

    @property
    def controller(self):
        theta = np.asarray(self.parameters).reshape(2, 3)
        return affine_controller(theta[:, :2], theta[:, 2])

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("unknown or missing cache field")
        value = dict(value)
        if value["belief"] is not None: value["belief"] = SourceBelief.from_dict(value["belief"])
        return cls(**value)


def program(method):
    if method not in METHODS: raise ValueError("unknown method")
    return BALANCED8 if method == "BALANCED4" else BLOCK8


def initial_choice(method, cache, episode):
    if method not in METHODS or type(episode) is not int or episode < 0:
        raise ValueError("registered method and visible own clock required")
    if cache is not None and (type(cache) is not VerifiedPoint or cache.source_episode >= episode):
        raise ValueError("future or unverified cache")
    if method == "NO_PROBE": return "RUN_IDENTITY"
    if method == "ALWAYS8": return "PROBE8"
    if method == "ALWAYS16_OLD": return "PROBE16"
    if method == "PASSIVE_RECENT8": return "PASSIVE8"
    if cache is None: return "PROBE8"
    if method == "PERIODIC4": return "PROBE8" if episode % 4 == 0 else "RUN_CACHED"
    if method == "STALE": return "RUN_CACHED"
    return "CHECK4"


def ivr_reference(model, prefix, cached, raw_policy):
    if type(cached) is not VerifiedPoint or cached.belief is None:
        raise ValueError("joint source information required")
    query4 = PredictionQuery(prefix.task, prefix.initial_observation, prefix.commands, True)
    query8 = PredictionQuery(prefix.task, prefix.initial_observation, BLOCK8, True)
    inverse_prior = np.linalg.inv(cached.belief.covariance)
    variances = []
    sent = encode_controller(cached.controller, raw_policy)
    x = np.array([*sent[:2], 1.]); theta = np.asarray(cached.parameters).reshape(2, 3)
    _, slope = clipped_normal_mean(theta @ x)
    task_jacobian = np.zeros((2, 6)); task_jacobian[0, :3] = slope[0]*x; task_jacobian[1, 3:] = slope[1]*x
    for query in (query4, query8):
        _, jacobian, covariance = response(model, query, cached.parameters)
        posterior = np.linalg.inv(inverse_prior+jacobian.T @ np.linalg.solve(covariance, jacobian))
        variances.append(float(np.trace(task_jacobian @ posterior @ task_jacobian.T)))
    reduction = (variances[0]-variances[1])/max(variances[0], 1e-12)
    if not np.isfinite(reduction) or reduction < -1e-8 or reduction > 1+1e-8:
        raise ValueError("invalid nested-query variance reduction")
    return {"variance_after4": variances[0], "expected_variance_after8": variances[1],
            "relative_variance_reduction": float(max(0., min(1., reduction))), "threshold": .25}


def check_choice(method, model, prefix, cached, cusum, raw_policy):
    if method not in CHECK_METHODS or type(prefix) is not ColdPrefix or len(prefix.commands) != 4 or type(cached) is not VerifiedPoint or cached.belief is None:
        raise ValueError("requested four-step visible check and own joint cache required")
    if not np.isfinite(cusum) or cusum < 0: raise ValueError("invalid past CUSUM state")
    if prefix.commands != program(method)[:4]: raise ValueError("substituted probe program")
    query = PredictionQuery(prefix.task, prefix.initial_observation, prefix.commands, True)
    prediction = forecast(model, query, cached.belief, "PLUGIN" if method == "PLUGIN4" else "SOURCE_UNCERTAINTY")
    result = score(prediction, prefix)
    next_cusum = float(max(0., cusum+(result["statistic"]-8)/4-.5)) if method == "CUSUM4" else 0.
    refresh = next_cusum >= 5 if method == "CUSUM4" else result["alarm_95"]
    reason = "CUSUM_THRESHOLD" if method == "CUSUM4" else "MARGINAL_PREDICTIVE_CHECK"
    ivr = None
    if method == "TASK_IVR4":
        ivr = ivr_reference(model, prefix, cached, raw_policy)
        refresh = refresh or ivr["relative_variance_reduction"] >= .25
        reason = "PREDICTIVE_OR_TASK_VARIANCE_REFERENCE"
    if cached.belief.active_parameter_bound:
        refresh = True; reason = "SOURCE_BOUND_ACTIVE_REFRESH"
    return {"action": "REFRESH8" if refresh else "RUN_CACHED", "reason": reason,
            "prediction": prediction, "score": result, "cusum_before": float(cusum),
            "cusum_after_check": next_cusum, "ivr": ivr, "physical_probability_qualified": False}


def accepted_cache(fit, prefix, task, episode, *, success, joint_model=None, evidence=None):
    if not success: return None
    if fit is None or fit.get("valid") is not True:
        raise ValueError("successful actual new fit required for cache write")
    parameters = tuple(np.column_stack((fit["matrix_xy"], fit["bias_xy"])).ravel())
    belief = source_belief(joint_model, prefix, parameters) if joint_model is not None else None
    evidence_hash = belief.evidence_sha256 if belief is not None else digest(evidence)
    return VerifiedPoint(parameters, belief, episode, task, evidence_hash, True)


def budget_valid(remaining, count):
    if type(remaining) is not int or type(count) is not int or count < 0 or remaining < 0:
        raise ValueError("integer nonnegative budget required")
    return count+32 <= remaining
