"""Controlled-reset finite-horizon response reference, not a novel guarantee.

Every displacement is observed. No virtual zero history, actuator truth or
hidden simulator state is supplied to the model. The likelihood is a working
model whose physical probability assumptions remain unqualified.
"""
from dataclasses import dataclass, fields
import math
import numpy as np
from scipy.optimize import least_squares
from src.probe.forward_prediction import vector
from src.probe.action_support import command

TASKS = ("push-v3", "reach-v3", "door-open-v3")
SCOPE = "CONTROLLED_RESET_FIRST_EIGHT_OPEN_LOOP_XY"
RIDGE = 1e-6
SIGMA = .05
MODELS = ("JOINT_FULL8", "JOINT_DROP2", "SAME_DATA_ARX8", "OLD_ARX8")


def clipped_normal_mean(values, sigma=SIGMA):
    """Analytic continuous-Gaussian working mean; not a float32 law proof."""
    if sigma != SIGMA: raise ValueError("frozen actuator noise scale required")
    x = np.asarray(values, float)
    if not np.isfinite(x).all(): raise ValueError("finite latent means required")
    a, b = (-1-x)/sigma, (1-x)/sigma
    cdf = np.vectorize(lambda z: .5*math.erfc(-float(z)/math.sqrt(2)), otypes=[float])
    pa, pb = cdf(a), cdf(b)
    phi_a = np.exp(-a*a/2)/math.sqrt(2*math.pi)
    phi_b = np.exp(-b*b/2)/math.sqrt(2*math.pi)
    mean = x*(pb-pa)+sigma*(phi_a-phi_b)+(1-pb)-pa
    return mean, pb-pa


@dataclass(frozen=True)
class ColdPrefix:
    task: str
    initial_observation: tuple
    commands: tuple
    observations: tuple
    controlled_reset_completed: bool

    def __post_init__(self):
        if self.task not in TASKS or self.controlled_reset_completed is not True:
            raise ValueError("registered task and explicit controlled-reset context required")
        initial = vector(self.initial_observation, 39)
        commands = tuple(command(v) for v in self.commands)
        observations = tuple(vector(v, 39) for v in self.observations)
        if not 1 <= len(commands) <= 8 or len(commands) != len(observations):
            raise ValueError("one through eight completed observations required")
        if any(c[2] != 0 or c[3] != 0 for c in commands):
            raise ValueError("only open-loop planar request scope is calibrated")
        object.__setattr__(self, "initial_observation", initial)
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "observations", observations)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("unknown, future or missing cold-prefix field")
        return cls(**value)

    @property
    def displacements(self):
        states = np.asarray((self.initial_observation, *self.observations))
        return np.diff(states[:, :2], axis=0)


@dataclass(frozen=True)
class NominalTrajectory:
    prefix: ColdPrefix
    split: str = "TRAIN"

    def __post_init__(self):
        if type(self.prefix) is not ColdPrefix or self.split != "TRAIN" or len(self.prefix.commands) != 8:
            raise ValueError("complete training-only nominal trajectory required")


def fit_response(samples, task):
    if len(samples) != 128 or any(type(s) is not NominalTrajectory or s.prefix.task != task for s in samples):
        raise ValueError("128 training-only nominal trajectories for one task required")
    inputs = np.array([clipped_normal_mean(np.array(s.prefix.commands)[:, :2])[0].ravel() for s in samples])
    targets = np.array([s.prefix.displacements.ravel() for s in samples])
    offset = np.zeros(16); impulse = np.zeros((16, 16)); predicted = np.empty_like(targets)
    for t in range(1, 9):
        design = np.c_[np.ones(128), inputs[:, :2*t]]
        penalty = np.diag(np.r_[0., np.full(2*t, RIDGE)])
        coefficient = np.linalg.solve(design.T @ design+penalty, design.T @ targets[:, 2*t-2:2*t])
        offset[2*t-2:2*t] = coefficient[0]
        impulse[2*t-2:2*t, :2*t] = coefficient[1:].T
        predicted[:, 2*t-2:2*t] = design @ coefficient
    residual = targets-predicted
    covariance = residual.T @ residual/(128-17)
    covariance = .95*covariance+.05*np.diag(np.diag(covariance))+1e-12*np.eye(16)
    hands = np.array([s.prefix.initial_observation[:3] for s in samples])
    return {"schema": "cold_response_v1", "task": task, "scope": SCOPE, "training_trajectories": 128,
            "sigma": SIGMA, "ridge": RIDGE, "offset": offset.tolist(), "impulse": impulse.tolist(),
            "covariance": covariance.tolist(), "initial_hand_lower": (hands.min(axis=0)-.01).tolist(),
            "initial_hand_upper": (hands.max(axis=0)+.01).tolist(), "minimum_initial_object_distance": .08,
            "training_joint_rmse_m": float(np.sqrt(np.mean(residual**2))),
            "physical_response_qualified": False, "probability_guarantee": False}


def validate_model(saved):
    keys = {"schema", "task", "scope", "training_trajectories", "sigma", "ridge", "offset", "impulse", "covariance",
            "initial_hand_lower", "initial_hand_upper", "minimum_initial_object_distance", "training_joint_rmse_m",
            "physical_response_qualified", "probability_guarantee"}
    if type(saved) is not dict or set(saved) != keys or saved["schema"] != "cold_response_v1" or saved["task"] not in TASKS or saved["scope"] != SCOPE or saved["training_trajectories"] != 128 or saved["sigma"] != SIGMA or saved["ridge"] != RIDGE or saved["physical_response_qualified"] is not False or saved["probability_guarantee"] is not False:
        raise ValueError("saved cold response contract differs")
    offset = np.asarray(vector(saved["offset"], 16)); impulse = np.asarray(saved["impulse"], float)
    covariance = np.asarray(saved["covariance"], float)
    if impulse.shape != (16, 16) or covariance.shape != (16, 16) or not np.isfinite(impulse).all() or not np.isfinite(covariance).all():
        raise ValueError("finite causal response and covariance required")
    for t in range(8):
        if np.any(impulse[2*t:2*t+2, 2*t+2:] != 0): raise ValueError("future command enters a response")
    if not np.allclose(covariance, covariance.T, atol=1e-14, rtol=0) or np.linalg.eigvalsh(covariance)[0] <= 0:
        raise ValueError("positive definite working covariance required")
    lo = np.asarray(vector(saved["initial_hand_lower"], 3)); hi = np.asarray(vector(saved["initial_hand_upper"], 3))
    if np.any(lo > hi) or saved["minimum_initial_object_distance"] != .08 or not isinstance(saved["training_joint_rmse_m"], (int, float)) or not math.isfinite(saved["training_joint_rmse_m"]) or saved["training_joint_rmse_m"] < 0:
        raise ValueError("invalid calibrated initial-scope metadata")
    return offset, impulse, covariance


def infer_operator(saved, prefix, drop_first_two=False):
    offset, impulse, covariance = validate_model(saved)
    if type(prefix) is not ColdPrefix or prefix.task != saved["task"] or type(drop_first_two) is not bool:
        raise ValueError("causal cold prefix and registered inference ablation required")
    result = {"valid": False, "model": "JOINT_DROP2" if drop_first_two else "JOINT_FULL8", "scope": SCOPE,
              "physical_response_qualified": False, "probability_guarantee": False}
    if len(prefix.commands) != 8: return {**result, "reason": "INCOMPLETE_EIGHT_STEP_PREFIX"}
    initial = np.asarray(prefix.initial_observation)
    if np.any(initial[:3] < saved["initial_hand_lower"]) or np.any(initial[:3] > saved["initial_hand_upper"]) or np.linalg.norm(initial[4:7]-initial[:3]) < saved["minimum_initial_object_distance"]:
        return {**result, "reason": "OUTSIDE_CONTROLLED_RESET_SCOPE"}
    x = np.c_[np.asarray(prefix.commands)[:, :2], np.ones(8)]
    if np.linalg.matrix_rank(x) != 3: return {**result, "reason": "MISSING_INPUT_SUPPORT"}
    first = 4 if drop_first_two else 0; y = prefix.displacements.ravel()
    chol = np.linalg.cholesky(covariance[first:, first:])
    linear = np.column_stack([(impulse @ (x @ np.eye(6)[i].reshape(2, 3).T).ravel())[first:] for i in range(6)])
    start = np.linalg.lstsq(np.linalg.solve(chol, linear), np.linalg.solve(chol, (y-offset)[first:]), rcond=None)[0]
    lower = np.array([-2., -2., -.3, -2., -2., -.3]); upper = -lower
    def predict(parameters, jacobian=False):
        mu = x @ parameters.reshape(2, 3).T
        mean, slope = clipped_normal_mean(mu)
        value = offset+impulse @ mean.ravel()
        if not jacobian: return value
        jac = np.zeros((16, 6))
        for i in range(6):
            direction = x @ np.eye(6)[i].reshape(2, 3).T
            jac[:, i] = impulse @ (direction*slope).ravel()
        return value, jac
    def residual(parameters): return np.linalg.solve(chol, (predict(parameters)-y)[first:])
    def jacobian(parameters): return np.linalg.solve(chol, predict(parameters, True)[1][first:])
    fitted = least_squares(residual, np.clip(start, lower+1e-9, upper-1e-9), jac=jacobian,
                           bounds=(lower, upper), ftol=1e-8, xtol=1e-8, gtol=1e-8, max_nfev=64)
    matrix = fitted.x.reshape(2, 3); singular = np.linalg.svd(matrix[:, :2], compute_uv=False)
    valid = bool(fitted.success and singular[-1] >= .25 and singular[0] <= 4)
    return {**result, "valid": valid, "reason": "WORKING_JOINT_RESPONSE_FIT" if valid else "OPTIMIZER_OR_INVERSE_DOMAIN_FAILURE",
            "matrix_xy": matrix[:, :2].tolist(), "bias_xy": matrix[:, 2].tolist(), "nfev": int(fitted.nfev),
            "observed_rows_used": 6 if drop_first_two else 8,
            "residual_rmse_m": float(np.sqrt(np.mean((predict(fitted.x)[first:]-y[first:])**2)))}
