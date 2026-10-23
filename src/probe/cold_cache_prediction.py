"""Standard local Gaussian cache prediction; no calibrated probability claim.

Query construction cannot read target responses, task outcomes or hidden context.
Linearized source-fit uncertainty is a diagnostic reference, not a new method.
"""
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import numpy as np
from scipy.stats import chi2
from src.probe.cold_start_response import ColdPrefix, TASKS, clipped_normal_mean, validate_model
from src.probe.forward_prediction import vector
from src.probe.action_support import command

MODES = ("PLUGIN", "SOURCE_UNCERTAINTY")
LOOKS = (2, 4, 8)
ALPHA = .05


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def strict(cls, value):
    if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:
        raise ValueError("unknown or missing visible field")
    return cls(**value)


def positive_matrix(value, size):
    matrix = np.asarray(value, dtype=float)
    if matrix.shape != (size, size) or not np.isfinite(matrix).all() or not np.allclose(matrix, matrix.T, rtol=0, atol=1e-12):
        raise ValueError("finite symmetric covariance required")
    np.linalg.cholesky(matrix)
    return tuple(tuple(float(v) for v in row) for row in matrix)


@dataclass(frozen=True)
class PredictionQuery:
    task: str
    initial_observation: tuple
    commands: tuple
    controlled_reset_completed: bool

    def __post_init__(self):
        if self.task not in TASKS or self.controlled_reset_completed is not True or len(self.commands) not in LOOKS:
            raise ValueError("registered initial-query scope required")
        object.__setattr__(self, "initial_observation", vector(self.initial_observation, 39))
        commands = tuple(command(row) for row in self.commands)
        if any(row[2] != 0 or row[3] != 0 for row in commands):
            raise ValueError("only planar open-loop commands are calibrated")
        object.__setattr__(self, "commands", commands)

    @classmethod
    def from_dict(cls, value):
        return strict(cls, value)


@dataclass(frozen=True)
class SourceBelief:
    task: str
    parameters: tuple
    covariance: tuple
    evidence_sha256: str
    active_parameter_bound: bool

    def __post_init__(self):
        if self.task not in TASKS or type(self.active_parameter_bound) is not bool:
            raise ValueError("visible source task and bound status required")
        parameters = vector(self.parameters, 6)
        if np.any(np.abs(parameters) > np.array([2., 2., .3, 2., 2., .3])+1e-9):
            raise ValueError("point outside frozen estimator bounds")
        if type(self.evidence_sha256) is not str or len(self.evidence_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.evidence_sha256):
            raise ValueError("source evidence digest required")
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "covariance", positive_matrix(self.covariance, 6))

    @classmethod
    def from_dict(cls, value):
        return strict(cls, value)


def response(model, query, parameters):
    offset, impulse, covariance = validate_model(model)
    if type(query) is not PredictionQuery or query.task != model["task"]:
        raise ValueError("matching visible query required")
    initial = np.asarray(query.initial_observation)
    if np.any(initial[:3] < model["initial_hand_lower"]) or np.any(initial[:3] > model["initial_hand_upper"]) or np.linalg.norm(initial[4:7]-initial[:3]) < model["minimum_initial_object_distance"]:
        raise ValueError("query outside controlled-reset calibration scope")
    parameters = np.asarray(vector(parameters, 6))
    n = len(query.commands); x = np.c_[np.asarray(query.commands)[:, :2], np.ones(n)]
    mean_input, slope = clipped_normal_mean(x @ parameters.reshape(2, 3).T)
    local_impulse = impulse[:2*n, :2*n]
    jacobian = np.column_stack([local_impulse @ ((x @ np.eye(6)[i].reshape(2, 3).T)*slope).ravel() for i in range(6)])
    return offset[:2*n]+local_impulse @ mean_input.ravel(), jacobian, covariance[:2*n, :2*n]


def source_belief(model, prefix, parameters):
    if type(prefix) is not ColdPrefix or len(prefix.commands) != 8:
        raise ValueError("complete visible source prefix required")
    query = PredictionQuery(prefix.task, prefix.initial_observation, prefix.commands, True)
    _, jacobian, covariance = response(model, query, parameters)
    information = jacobian.T @ np.linalg.solve(covariance, jacobian)
    if np.linalg.matrix_rank(information) != 6:
        raise ValueError("singular local source information")
    value = np.linalg.solve(information, np.eye(6)); value = (value+value.T)/2
    active = bool(np.any(np.array([2., 2., .3, 2., 2., .3])-np.abs(parameters) <= 1e-6))
    return SourceBelief(prefix.task, parameters, value, digest(asdict(prefix)), active)


def forecast(model, query, cached, mode):
    if type(cached) is not SourceBelief or mode not in MODES:
        raise ValueError("registered cache reference required")
    mean, jacobian, covariance = response(model, query, cached.parameters)
    if mode == "SOURCE_UNCERTAINTY":
        covariance = covariance+jacobian @ np.asarray(cached.covariance) @ jacobian.T
    return {"schema": "cold_cache_forecast_v1", "query_sha256": digest(asdict(query)),
            "source_belief_sha256": digest(asdict(cached)), "steps": len(query.commands), "mode": mode,
            "mean": mean.tolist(), "covariance": [list(row) for row in positive_matrix(covariance, len(mean))],
            "physical_probability_qualified": False}


def score(prediction, prefix):
    keys = {"schema", "query_sha256", "source_belief_sha256", "steps", "mode", "mean", "covariance", "physical_probability_qualified"}
    if type(prediction) is not dict or set(prediction) != keys or prediction["schema"] != "cold_cache_forecast_v1" or prediction["physical_probability_qualified"] is not False or prediction["mode"] not in MODES:
        raise ValueError("registered saved prediction required")
    if type(prefix) is not ColdPrefix or len(prefix.commands) != prediction["steps"]:
        raise ValueError("only requested completed responses may be scored")
    query = PredictionQuery(prefix.task, prefix.initial_observation, prefix.commands, True)
    if digest(asdict(query)) != prediction["query_sha256"]:
        raise ValueError("response belongs to another request")
    residual = prefix.displacements.ravel()-np.asarray(vector(prediction["mean"], 2*prediction["steps"]))
    covariance = np.asarray(positive_matrix(prediction["covariance"], len(residual)))
    whitened = np.linalg.solve(np.linalg.cholesky(covariance), residual)
    statistic = float(whitened @ whitened); degrees = len(residual)
    threshold = float(chi2.isf(ALPHA, degrees)); familywise = float(chi2.isf(ALPHA/len(LOOKS), degrees))
    return {"statistic": statistic, "degrees_of_freedom": degrees,
            "nominal_tail_probability": float(chi2.sf(statistic, degrees)),
            "nominal_threshold_95": threshold, "alarm_95": statistic > threshold,
            "nominal_three_look_threshold": familywise, "three_look_alarm": statistic > familywise,
            "physical_probability_qualified": False}
