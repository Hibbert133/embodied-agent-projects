"""History-conditioned finite-horizon response reference; no physical qualification.

Nominal fitting needs independently varied commands, not repetitions of the
fixed inference probe. Visible entry history is a predictor, not a recovered
hidden state. No collection, oracle, simulator, controller or API is accessed.
"""
from dataclasses import dataclass, fields
import math

import numpy as np
from scipy.optimize import least_squares

from src.probe.cold_start_response import clipped_normal_mean
from src.probe.forward_prediction import vector
from src.probe.physical_reprobe_v1 import (
    ANCHOR, TASKS, WarmWindow, anchor_ready, probe_in_scope)

SCOPE = "VISIBLE_ANCHOR_HISTORY_FOUR_THEN_EIGHT_XY_V1"
RIDGE = 1e-6
SIGMA = .05
MINIMUM_TRAINING_WINDOWS = 64
METHODS = ("WARM_HISTORY", "WARM_NO_HISTORY")
FEATURES = tuple(["position_"+axis for axis in "xyz"] +
                 [f"delta{step}_{axis}" for step in range(3) for axis in "xyz"])
LOWER = np.array([-2., -2., -.3, -2., -2., -.3])
UPPER = -LOWER


def strict_fields(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("unknown, private or missing field")


def matrix(value, shape):
    if type(value) not in (list, tuple) or len(value) != shape[0]:
        raise ValueError("ordinary finite matrix required")
    return np.array([vector(row, shape[1]) for row in value])


def entry_features(history):
    if type(history) not in (list, tuple) or len(history) != 4:
        raise ValueError("four actual entry observations required")
    values = np.array([vector(obs, 39) for obs in history])
    if not anchor_ready(values) or not probe_in_scope(values[-1]):
        raise ValueError("entry observation outside measured scope")
    return np.r_[(values[-1, :3]-ANCHOR)/.015, np.diff(values[:, :3], axis=0).ravel()/.003]


@dataclass(frozen=True)
class NominalWarmTrajectory:
    """Complete training-only visible window; host must prove nominal provenance."""
    task: str
    probe_start_step: int
    entry_history: tuple
    commands: tuple
    observations: tuple
    split: str = "TRAIN"

    def __post_init__(self):
        if self.task not in TASKS or self.split != "TRAIN" or type(self.probe_start_step) is not int or not 8 <= self.probe_start_step <= 392:
            raise ValueError("complete nominal TRAIN scope required")
        entry_features(self.entry_history)
        if any(type(v) not in (tuple, list) for v in (self.commands, self.observations)) or len(self.commands) != 8 or len(self.observations) != 8:
            raise ValueError("eight completed nominal requests and observations required")
        commands = tuple(vector(v, 4) for v in self.commands)
        observations = tuple(vector(v, 39) for v in self.observations)
        if any(max(abs(x) for x in c) > 1 or c[2] != 0 or c[3] != 0 for c in commands):
            raise ValueError("bounded planar nominal requests required")
        if not all(probe_in_scope(v) for v in observations):
            raise ValueError("nominal window left the visible measurement scope")
        object.__setattr__(self, "entry_history", tuple(vector(v, 39) for v in self.entry_history))
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "observations", observations)

    @classmethod
    def from_mapping(cls, value):
        strict_fields(value, (f.name for f in fields(cls)))
        return cls(**value)


def displacements(window):
    observations = np.array((window.entry_history[-1], *window.observations))
    return np.diff(observations[:, :2], axis=0).ravel()


def fit_response(samples, task, *, history_conditioned=True):
    if task not in TASKS or type(history_conditioned) is not bool or type(samples) not in (list, tuple) or len(samples) < MINIMUM_TRAINING_WINDOWS:
        raise ValueError("registered task, ablation and enough independent TRAIN windows required")
    if any(type(s) is not NominalWarmTrajectory or s.task != task for s in samples):
        raise ValueError("same-task nominal TRAIN windows only")
    count = len(samples)
    inputs = np.array([clipped_normal_mean(np.array(s.commands)[:, :2])[0].ravel() for s in samples])
    input_design = np.c_[np.ones(count), inputs]
    input_rank = int(np.linalg.matrix_rank(input_design))
    if input_rank != 17 or np.linalg.cond(input_design) > 1e6:
        raise ValueError("nominal commands do not identify the causal response; repeated fixed probes are insufficient")
    histories = np.array([entry_features(s.entry_history) for s in samples])
    state = histories if history_conditioned else np.empty((count, 0))
    nuisance = np.c_[np.ones(count), state]
    residual_inputs = inputs-nuisance@np.linalg.lstsq(nuisance, inputs, rcond=None)[0]
    conditional_rank = int(np.linalg.matrix_rank(np.c_[nuisance, inputs])-np.linalg.matrix_rank(nuisance))
    # Use pre-projection scales: normalizing a nearly vanished residual column
    # would hide input/history confounding rather than measure its severity.
    input_norms = np.linalg.norm(inputs-inputs.mean(axis=0), axis=0)
    conditional_condition = float(np.linalg.cond(residual_inputs/np.where(input_norms > 0, input_norms, 1.)))
    if conditional_rank != 16 or not math.isfinite(conditional_condition) or conditional_condition > 1e6:
        raise ValueError("nominal input response is confounded with entry history")
    targets = np.array([displacements(s) for s in samples]);predicted = np.empty_like(targets)
    offset = np.zeros(16);history = np.zeros((16, 12));impulse = np.zeros((16, 16))
    for t in range(1, 9):
        design = np.c_[np.ones(count), state, inputs[:, :2*t]]
        penalty = RIDGE*np.eye(design.shape[1]);penalty[0, 0] = 0.
        coefficient = np.linalg.solve(design.T@design+penalty, design.T@targets[:, 2*t-2:2*t])
        offset[2*t-2:2*t] = coefficient[0]
        if history_conditioned: history[2*t-2:2*t] = coefficient[1:13].T
        impulse[2*t-2:2*t, :2*t] = coefficient[1+state.shape[1]:].T
        predicted[:, 2*t-2:2*t] = design@coefficient
    residual = targets-predicted
    covariance = residual.T@residual/(count-17-state.shape[1])
    covariance = .95*covariance+.05*np.diag(np.diag(covariance))+1e-12*np.eye(16)
    return {"schema":"warm_response_reference_v1", "task":task, "scope":SCOPE,
        "method":METHODS[0] if history_conditioned else METHODS[1], "training_trajectories":count,
        "training_input_rank":input_rank, "training_history_rank":int(np.linalg.matrix_rank(np.c_[np.ones(count), histories])),
        "training_conditional_input_rank":conditional_rank, "training_conditional_input_condition":conditional_condition,
        "history_features":list(FEATURES), "sigma":SIGMA, "ridge":RIDGE,
        "offset":offset.tolist(), "history_response":history.tolist(), "impulse":impulse.tolist(), "covariance":covariance.tolist(),
        "training_joint_rmse_m":float(np.sqrt(np.mean(residual**2))),
        "physical_response_qualified":False, "probability_guarantee":False}


def validate_model(saved):
    strict_fields(saved, ("schema", "task", "scope", "method", "training_trajectories", "training_input_rank",
        "training_history_rank", "training_conditional_input_rank", "training_conditional_input_condition",
        "history_features", "sigma", "ridge", "offset", "history_response", "impulse",
        "covariance", "training_joint_rmse_m", "physical_response_qualified", "probability_guarantee"))
    if saved["schema"] != "warm_response_reference_v1" or saved["task"] not in TASKS or saved["scope"] != SCOPE or saved["method"] not in METHODS or saved["history_features"] != list(FEATURES):
        raise ValueError("registered warm model required")
    if type(saved["training_trajectories"]) is not int or saved["training_trajectories"] < MINIMUM_TRAINING_WINDOWS or type(saved["training_input_rank"]) is not int or saved["training_input_rank"] != 17 or type(saved["training_history_rank"]) is not int or not 1 <= saved["training_history_rank"] <= 13:
        raise ValueError("invalid training sample/support metadata")
    if type(saved["training_conditional_input_rank"]) is not int or saved["training_conditional_input_rank"] != 16 or type(saved["training_conditional_input_condition"]) is not float or not math.isfinite(saved["training_conditional_input_condition"]) or not 1 <= saved["training_conditional_input_condition"] <= 1e6:
        raise ValueError("input support after conditioning on history required")
    if type(saved["sigma"]) is not float or saved["sigma"] != SIGMA or type(saved["ridge"]) is not float or saved["ridge"] != RIDGE or saved["physical_response_qualified"] is not False or saved["probability_guarantee"] is not False:
        raise ValueError("working model scope cannot be promoted by metadata")
    if type(saved["training_joint_rmse_m"]) not in (float, int) or not math.isfinite(saved["training_joint_rmse_m"]) or saved["training_joint_rmse_m"] < 0:
        raise ValueError("finite nonnegative training error required")
    offset = np.array(vector(saved["offset"], 16));history = matrix(saved["history_response"], (16, 12))
    impulse = matrix(saved["impulse"], (16, 16));covariance = matrix(saved["covariance"], (16, 16))
    for t in range(8):
        if np.any(impulse[2*t:2*t+2, 2*t+2:] != 0): raise ValueError("future command affects earlier response")
    if saved["method"] == "WARM_NO_HISTORY" and np.any(history != 0):
        raise ValueError("history ablation contains history coefficients")
    if not np.allclose(covariance, covariance.T, atol=1e-14, rtol=0) or np.linalg.eigvalsh(covariance)[0] <= 0:
        raise ValueError("positive definite working covariance required")
    return offset, history, impulse, covariance


class WarmResponseProblem:
    def __init__(self, saved, window):
        if type(saved) is not dict or type(window) is not WarmWindow or window.task != saved.get("task"):
            raise ValueError("complete registered physical warm window required")
        offset, history, self.impulse, covariance = validate_model(saved)
        self.baseline = offset+history@entry_features(window.entry_history)
        self.x = np.c_[np.array(window.commands)[:, :2], np.ones(8)]
        self.y = displacements(window);self.chol = np.linalg.cholesky(covariance)

    def predict(self, parameters, *, jacobian=False):
        p = np.array(vector(parameters, 6)).reshape(2, 3)
        mean, slope = clipped_normal_mean(self.x@p.T)
        predicted = self.baseline+self.impulse@mean.ravel()
        if not jacobian: return predicted
        jac = np.column_stack([self.impulse@((self.x@np.eye(6)[i].reshape(2, 3).T)*slope).ravel() for i in range(6)])
        return predicted, jac

    def residual(self, p): return np.linalg.solve(self.chol, self.predict(p)-self.y)

    def jacobian(self, p): return np.linalg.solve(self.chol, self.predict(p, jacobian=True)[1])

    def linear_design(self):
        return np.column_stack([self.impulse@(self.x@np.eye(6)[i].reshape(2, 3).T).ravel() for i in range(6)])


def infer_operator(saved, window):
    problem = WarmResponseProblem(saved, window)
    result = {"valid":False, "model":saved["method"], "scope":SCOPE,
        "physical_response_qualified":False, "probability_guarantee":False, "observed_rows_used":8}
    linear = np.linalg.solve(problem.chol, problem.linear_design())
    norms = np.linalg.norm(linear, axis=0)
    condition = float(np.linalg.cond(linear/np.where(norms > 0, norms, 1.)))
    rank = int(np.linalg.matrix_rank(linear))
    result.update(response_design_rank=rank, scaled_response_condition=condition if math.isfinite(condition) else None)
    if rank != 6 or not math.isfinite(condition) or condition > 1e6:
        return {**result, "reason":"INSUFFICIENT_LEARNED_RESPONSE_SUPPORT", "nfev":0}
    start = np.linalg.lstsq(linear, np.linalg.solve(problem.chol, problem.y-problem.baseline), rcond=None)[0]
    fitted = least_squares(problem.residual, np.clip(start, LOWER+1e-9, UPPER-1e-9), jac=problem.jacobian,
        bounds=(LOWER, UPPER), ftol=1e-8, xtol=1e-8, gtol=1e-8, max_nfev=64)
    p = fitted.x.reshape(2, 3);singular = np.linalg.svd(p[:, :2], compute_uv=False)
    valid = bool(fitted.success and singular[-1] >= .25 and singular[0] <= 4.)
    return {**result, "valid":valid, "reason":"WORKING_WARM_RESPONSE_FIT" if valid else "OPTIMIZER_OR_INVERSE_DOMAIN_FAILURE",
        "matrix_xy":p[:, :2].tolist(), "bias_xy":p[:, 2].tolist(), "nfev":int(fitted.nfev),
        "residual_rmse_m":float(np.sqrt(np.mean((problem.predict(fitted.x)-problem.y)**2)))}
