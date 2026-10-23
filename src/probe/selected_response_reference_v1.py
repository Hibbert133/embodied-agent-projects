"""Selected-location response references, requiring new nominal calibration.

Only visible history and pose are used. TRAIN provenance, random allocation and
physical transfer must be verified by a separate collector and evaluator. These
standard regressions do not establish physical uncertainty or task benefit.
"""
from dataclasses import dataclass, fields
import math

import numpy as np
from scipy.optimize import least_squares

from src.probe.cold_start_response import clipped_normal_mean
from src.probe.forward_prediction import vector
from src.probe.local_reprobe_v1 import SelectedAnchorWindow, anchor_ready
from src.probe.physical_reprobe_v1 import TASKS, probe_in_scope
from src.probe.warm_response_reference_v1 import matrix, strict_fields

SCOPE = "SELECTED_LOCATION_HISTORY_FOUR_THEN_EIGHT_XY_V1"
METHODS = ("SELECTED_INPUT_ONLY", "SELECTED_HISTORY", "SELECTED_POSE_HISTORY")
RIDGE, SIGMA = 1e-6, .05
MINIMUM_TRAINING_WINDOWS = 160
SUPPORT_LIMIT = 1e6
POSE_MARGIN = .01
POSE_CENTER = np.array([0., .7, .35])
POSE_SCALE = np.array([.45, .25, .20])
FEATURES = tuple(["relative_position_"+a for a in "xyz"] +
                 [f"delta{t}_{a}" for t in range(3) for a in "xyz"] +
                 ["absolute_position_"+a for a in "xyz"])
LOWER = np.array([-2., -2., -.3, -2., -2., -.3])
UPPER = -LOWER


def entry_features(history, anchor):
    anchor = vector(anchor, 3)
    if not (-.45 <= anchor[0] <= .45 and .45 <= anchor[1] <= .95 and .25 <= anchor[2] <= .45):
        raise ValueError("registered selected target required")
    if type(history) not in (list, tuple) or len(history) != 4:
        raise ValueError("four actual entry observations required")
    values = np.array([vector(obs, 39) for obs in history])
    if not anchor_ready(values, anchor) or not probe_in_scope(values[-1]):
        raise ValueError("entry outside selected measurement scope")
    return np.r_[(values[-1, :3]-anchor)/.015,
                 np.diff(values[:, :3], axis=0).ravel()/.003,
                 (values[-1, :3]-POSE_CENTER)/POSE_SCALE]


@dataclass(frozen=True)
class NominalSelectedTrajectory:
    """Visible TRAIN record; this type alone cannot prove nominal provenance."""
    task: str
    probe_start_step: int
    anchor: tuple
    entry_history: tuple
    commands: tuple
    observations: tuple
    split: str = "TRAIN"

    def __post_init__(self):
        if self.task not in TASKS or self.split != "TRAIN" or type(self.probe_start_step) is not int or not 8 <= self.probe_start_step <= 392:
            raise ValueError("complete selected nominal TRAIN scope required")
        entry_features(self.entry_history, self.anchor)
        if any(type(v) not in (list, tuple) or len(v) != 8 for v in (self.commands, self.observations)):
            raise ValueError("eight actual commands and observations required")
        commands = tuple(vector(v, 4) for v in self.commands)
        observations = tuple(vector(v, 39) for v in self.observations)
        if any(max(abs(x) for x in c) > 1 or c[2] != 0 or c[3] != 0 for c in commands):
            raise ValueError("bounded planar nominal requests required")
        if not all(probe_in_scope(obs) for obs in observations):
            raise ValueError("nominal selected window left measurement scope")
        object.__setattr__(self, "anchor", vector(self.anchor, 3))
        object.__setattr__(self, "entry_history", tuple(vector(v, 39) for v in self.entry_history))
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "observations", observations)

    @classmethod
    def from_mapping(cls, value):
        strict_fields(value, (f.name for f in fields(cls)))
        return cls(**value)


def displacements(window):
    states = np.array((window.entry_history[-1], *window.observations))
    return np.diff(states[:, :2], axis=0).ravel()


def _support(inputs, nuisance):
    """Check excitation remaining after state projection, without rescaling it away."""
    width = inputs.shape[1]
    centered = inputs-inputs.mean(axis=0)
    scales = np.linalg.norm(centered, axis=0)
    raw_rank = int(np.linalg.matrix_rank(np.c_[np.ones(len(inputs)), inputs]))
    nuisance_rank = int(np.linalg.matrix_rank(nuisance))
    residual = inputs-nuisance@np.linalg.lstsq(nuisance, inputs, rcond=None)[0]
    conditional_rank = int(np.linalg.matrix_rank(np.c_[nuisance, inputs])-nuisance_rank)
    singular = np.linalg.svd(residual/np.where(scales > 0, scales, 1.), compute_uv=False)
    condition = float(singular[0]/singular[-1]) if singular[-1] > 0 else math.inf
    if (raw_rank != width+1 or conditional_rank != width or
            not math.isfinite(condition) or condition > SUPPORT_LIMIT or singular[-1] < 1/SUPPORT_LIMIT):
        raise ValueError("independent input support required after state conditioning; fixed or confounded probes rejected")
    return raw_rank, nuisance_rank, conditional_rank, condition, float(singular[-1])


def fit_response(samples, task, *, method):
    if task not in TASKS or method not in METHODS or type(samples) not in (list, tuple) or len(samples) < MINIMUM_TRAINING_WINDOWS:
        raise ValueError("registered task/method and sufficient independent TRAIN windows required")
    if any(type(s) is not NominalSelectedTrajectory or s.task != task for s in samples):
        raise ValueError("same-task selected nominal TRAIN windows only")
    count = len(samples)
    features = np.array([entry_features(s.entry_history, s.anchor) for s in samples])
    state_count = {METHODS[0]: 0, METHODS[1]: 12, METHODS[2]: 15}[method]
    basis_count = 4 if method == METHODS[2] else 1
    state = features[:, :state_count]
    basis = np.c_[np.ones(count), features[:, 12:]] if basis_count == 4 else np.ones((count, 1))
    inputs = np.array([clipped_normal_mean(np.array(s.commands)[:, :2])[0].ravel() for s in samples])
    expanded = (basis[:, :, None]*inputs[:, None, :]).reshape(count, 16*basis_count)
    nuisance = np.c_[np.ones(count), state]
    raw_rank, state_rank, conditional_rank, condition, smallest = _support(expanded, nuisance)
    targets = np.array([displacements(s) for s in samples]);predicted = np.empty_like(targets)
    offset = np.zeros(16);state_response = np.zeros((16, 15));impulses = np.zeros((4, 16, 16))
    for t in range(1, 9):
        causal = (basis[:, :, None]*inputs[:, None, :2*t]).reshape(count, basis_count*2*t)
        design = np.c_[nuisance, causal]
        # Augmented least squares avoids squaring an ill-conditioned design.
        penalty = np.sqrt(RIDGE)*np.eye(design.shape[1]);penalty[0, 0] = 0.
        coefficient = np.linalg.lstsq(np.r_[design, penalty],
            np.r_[targets[:, 2*t-2:2*t], np.zeros((design.shape[1], 2))], rcond=None)[0]
        offset[2*t-2:2*t] = coefficient[0]
        state_response[2*t-2:2*t, :state_count] = coefficient[1:1+state_count].T
        for k in range(basis_count):
            impulses[k, 2*t-2:2*t, :2*t] = coefficient[1+state_count+k*2*t:1+state_count+(k+1)*2*t].T
        predicted[:, 2*t-2:2*t] = design@coefficient
    residual = targets-predicted
    covariance = residual.T@residual/(count-state_rank-conditional_rank)
    covariance = .95*covariance+.05*np.diag(np.diag(covariance))+1e-12*np.eye(16)
    hands = np.array([s.entry_history[-1][:3] for s in samples])
    return {"schema": "selected_response_reference_v1", "task": task, "scope": SCOPE, "method": method,
        "training_trajectories": count, "training_input_rank": raw_rank, "training_state_rank": state_rank,
        "training_conditional_input_rank": conditional_rank, "training_conditional_input_condition": condition,
        "training_conditional_minimum_singular": smallest, "state_features": list(FEATURES),
        "pose_center": POSE_CENTER.tolist(), "pose_scale": POSE_SCALE.tolist(), "pose_margin": POSE_MARGIN,
        "training_hand_min": hands.min(axis=0).tolist(), "training_hand_max": hands.max(axis=0).tolist(),
        "sigma": SIGMA, "ridge": RIDGE, "offset": offset.tolist(), "state_response": state_response.tolist(),
        "impulse_basis": impulses.tolist(), "covariance": covariance.tolist(),
        "training_joint_rmse_m": float(np.sqrt(np.mean(residual**2))),
        "physical_response_qualified": False, "probability_guarantee": False}


def validate_model(saved):
    strict_fields(saved, ("schema", "task", "scope", "method", "training_trajectories", "training_input_rank",
        "training_state_rank", "training_conditional_input_rank", "training_conditional_input_condition",
        "training_conditional_minimum_singular", "state_features", "pose_center", "pose_scale", "pose_margin",
        "training_hand_min", "training_hand_max", "sigma", "ridge", "offset", "state_response", "impulse_basis",
        "covariance", "training_joint_rmse_m", "physical_response_qualified", "probability_guarantee"))
    if saved["schema"] != "selected_response_reference_v1" or saved["scope"] != SCOPE or saved["task"] not in TASKS or saved["method"] not in METHODS or saved["state_features"] != list(FEATURES):
        raise ValueError("registered selected-location model required")
    method = saved["method"];width = 64 if method == METHODS[2] else 16
    state_width = {METHODS[0]: 1, METHODS[1]: 13, METHODS[2]: 16}[method]
    for key, minimum, maximum in (("training_trajectories", MINIMUM_TRAINING_WINDOWS, math.inf),
            ("training_input_rank", width+1, width+1), ("training_state_rank", 1, state_width),
            ("training_conditional_input_rank", width, width)):
        if type(saved[key]) is not int or not minimum <= saved[key] <= maximum:
            raise ValueError("invalid TRAIN support metadata")
    for key, minimum, maximum in (("training_conditional_input_condition", 1., SUPPORT_LIMIT),
            ("training_conditional_minimum_singular", 1/SUPPORT_LIMIT, math.inf),
            ("training_joint_rmse_m", 0., math.inf)):
        if type(saved[key]) not in (int, float) or not math.isfinite(saved[key]) or not minimum <= saved[key] <= maximum:
            raise ValueError("invalid finite training support or error")
    if (type(saved["sigma"]) is not float or saved["sigma"] != SIGMA or
            type(saved["ridge"]) is not float or saved["ridge"] != RIDGE or
            type(saved["pose_margin"]) is not float or saved["pose_margin"] != POSE_MARGIN or
            vector(saved["pose_center"], 3) != tuple(POSE_CENTER) or vector(saved["pose_scale"], 3) != tuple(POSE_SCALE) or
            saved["physical_response_qualified"] is not False or saved["probability_guarantee"] is not False):
        raise ValueError("working scope or fixed numerical conventions changed")
    lo, hi = np.array(vector(saved["training_hand_min"], 3)), np.array(vector(saved["training_hand_max"], 3))
    if np.any(lo > hi) or np.any(lo < [-.465, .435, .235]) or np.any(hi > [.465, .965, .465]):
        raise ValueError("invalid observed training pose range")
    offset = np.array(vector(saved["offset"], 16));state = matrix(saved["state_response"], (16, 15))
    if type(saved["impulse_basis"]) not in (tuple, list) or len(saved["impulse_basis"]) != 4:
        raise ValueError("four ordinary causal response matrices required")
    impulses = np.array([matrix(v, (16, 16)) for v in saved["impulse_basis"]])
    for t in range(8):
        if np.any(impulses[:, 2*t:2*t+2, 2*t+2:] != 0):raise ValueError("future command affects an earlier response")
    if method != METHODS[2] and (np.any(impulses[1:] != 0) or np.any(state[:, 12:] != 0)):
        raise ValueError("pose ablation contains pose coefficients")
    if method == METHODS[0] and np.any(state != 0):raise ValueError("input-only ablation contains state coefficients")
    covariance = matrix(saved["covariance"], (16, 16))
    if not np.allclose(covariance, covariance.T, atol=1e-14, rtol=0) or np.linalg.eigvalsh(covariance)[0] <= 0:
        raise ValueError("positive definite working covariance required")
    return offset, state, impulses, covariance, lo, hi


class SelectedResponseProblem:
    def __init__(self, saved, window):
        if type(saved) is not dict or type(window) is not SelectedAnchorWindow or window.task != saved.get("task"):
            raise ValueError("complete selected-location measurement window required")
        offset, state, impulses, covariance, lo, hi = validate_model(saved)
        features = entry_features(window.entry_history, window.anchor)
        self.in_training_pose_box = bool(np.all(np.array(window.entry_history[-1][:3]) >= lo-POSE_MARGIN) and
                                        np.all(np.array(window.entry_history[-1][:3]) <= hi+POSE_MARGIN))
        self.baseline = offset+state@features
        self.impulse = impulses[0]+np.einsum("k,kij->ij", features[12:], impulses[1:])
        self.x = np.c_[np.array(window.commands)[:, :2], np.ones(8)]
        self.y = displacements(window);self.chol = np.linalg.cholesky(covariance)

    def predict(self, parameters, *, jacobian=False):
        p = np.array(vector(parameters, 6)).reshape(2, 3)
        mean, slope = clipped_normal_mean(self.x@p.T)
        predicted = self.baseline+self.impulse@mean.ravel()
        if not jacobian:return predicted
        derivative = np.column_stack([self.impulse@((self.x@np.eye(6)[i].reshape(2, 3).T)*slope).ravel() for i in range(6)])
        return predicted, derivative

    def residual(self, p):return np.linalg.solve(self.chol, self.predict(p)-self.y)
    def jacobian(self, p):return np.linalg.solve(self.chol, self.predict(p, jacobian=True)[1])
    def linear_design(self):
        return np.column_stack([self.impulse@(self.x@np.eye(6)[i].reshape(2, 3).T).ravel() for i in range(6)])


def infer_operator(saved, window):
    problem = SelectedResponseProblem(saved, window)
    result = {"valid": False, "model": saved["method"], "scope": SCOPE, "observed_rows_used": 8,
        "physical_response_qualified": False, "probability_guarantee": False}
    if not problem.in_training_pose_box:
        return {**result, "reason": "OUTSIDE_OBSERVED_TRAINING_POSE_BOX", "nfev": 0}
    linear = np.linalg.solve(problem.chol, problem.linear_design());norms = np.linalg.norm(linear, axis=0)
    condition = float(np.linalg.cond(linear/np.where(norms > 0, norms, 1.)))
    rank = int(np.linalg.matrix_rank(linear))
    result.update(response_design_rank=rank, scaled_response_condition=condition if math.isfinite(condition) else None)
    if rank != 6 or not math.isfinite(condition) or condition > SUPPORT_LIMIT:
        return {**result, "reason": "INSUFFICIENT_LEARNED_RESPONSE_SUPPORT", "nfev": 0}
    start = np.linalg.lstsq(linear, np.linalg.solve(problem.chol, problem.y-problem.baseline), rcond=None)[0]
    fitted = least_squares(problem.residual, np.clip(start, LOWER+1e-9, UPPER-1e-9), jac=problem.jacobian,
        bounds=(LOWER, UPPER), ftol=1e-8, xtol=1e-8, gtol=1e-8, max_nfev=64)
    p = fitted.x.reshape(2, 3);singular = np.linalg.svd(p[:, :2], compute_uv=False)
    valid = bool(fitted.success and singular[-1] >= .25 and singular[0] <= 4.)
    return {**result, "valid": valid, "reason": "WORKING_SELECTED_RESPONSE_FIT" if valid else "OPTIMIZER_OR_INVERSE_DOMAIN_FAILURE",
        "matrix_xy": p[:, :2].tolist(), "bias_xy": p[:, 2].tolist(), "nfev": int(fitted.nfev),
        "residual_rmse_m": float(np.sqrt(np.mean((problem.predict(fitted.x)-problem.y)**2)))}
