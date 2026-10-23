"""Standard local-Gaussian IVR and bounded inverse reference, not a new method.

The covariance is conditional on the frozen nominal model's local Jacobian and
empirical RMS. It is not a calibrated physical error envelope or a posterior
with verified likelihood assumptions. No environment, seed or truth is input.
"""
from dataclasses import dataclass
from itertools import product
import math
import numpy as np

from src.probe.operator_identification import ForwardOperatorProblem, OperatorSample, infer_operator, sample_digest
from src.probe.forward_prediction import vector

SCOPE = "UNQUALIFIED_LOCAL_GAUSSIAN_RESPONSE_REFERENCE"
REGULARIZATION = .01
RISK_WEIGHT = 1.
PRIOR_VARIANCES = (1., 1., .09, 1., 1., .09)
PRIMITIVES = {
    "X4": ((.4, 0., 0., 0.),) * 2 + ((-.4, 0., 0., 0.),) * 2,
    "Y4": ((0., .4, 0., 0.),) * 2 + ((0., -.4, 0., 0.),) * 2,
    "ZERO4": ((0., 0., 0., 0.),) * 4,
}


def matrix(value, shape):
    result = np.asarray(value, float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError("finite registered matrix required")
    return result


@dataclass(frozen=True)
class GaussianReference:
    mean: tuple
    covariance: tuple
    nominal_response: tuple
    noise_rms_m: float
    evidence_digest: str

    def __post_init__(self):
        mean = np.asarray(vector(self.mean, 6))
        cov = matrix(self.covariance, (6, 6)); response = matrix(self.nominal_response, (2, 2))
        if not np.allclose(cov, cov.T, rtol=0, atol=1e-12) or np.linalg.eigvalsh(cov)[0] <= 0:
            raise ValueError("positive definite conditional covariance required")
        if type(self.noise_rms_m) not in (int, float) or not math.isfinite(self.noise_rms_m) or self.noise_rms_m <= 0 or type(self.evidence_digest) is not str or not self.evidence_digest:
            raise ValueError("visible scale and completed evidence binding required")
        object.__setattr__(self, "mean", tuple(float(x) for x in mean))
        object.__setattr__(self, "covariance", tuple(tuple(float(x) for x in row) for row in cov))
        object.__setattr__(self, "nominal_response", tuple(tuple(float(x) for x in row) for row in response))

    @classmethod
    def from_visible(cls, model, samples, sigma):
        if model.get("method") != "LINEAR_ARX" or any(type(s) is not OperatorSample for s in samples):
            raise ValueError("frozen linear nominal model and visible samples required")
        fit = infer_operator(model, samples)
        if "matrix_xy" not in fit or "bias_xy" not in fit:
            raise ValueError("no finite observed point fit")
        mean = np.column_stack((fit["matrix_xy"], fit["bias_xy"])).ravel()
        problem = ForwardOperatorProblem(model, samples)
        _, jac = problem.predictions(mean, jacobian=True)
        if type(sigma) not in (int, float) or not math.isfinite(sigma) or sigma <= 0:
            raise ValueError("positive empirical scale required")
        precision = np.diag(1 / np.asarray(PRIOR_VARIANCES)) + jac.T @ jac / sigma ** 2
        cov = np.linalg.solve(precision, np.eye(6))
        cov = (cov + cov.T) / 2
        response = problem.linear[:, problem.indices] / problem.scale[list(problem.indices)]
        return cls(tuple(mean), cov, response, float(sigma), sample_digest(samples)), fit

    def command_jacobian(self, command):
        q = np.asarray(vector(command, 2)); x = np.array([*q, 1.])
        if np.any(np.abs(q) > 1):
            raise ValueError("query outside executable command box")
        raw = np.asarray(self.mean).reshape(2, 3) @ x
        # Local saturation derivative is an approximation at the saved point;
        # it does not integrate clipping or actuator-noise tails.
        response = np.asarray(self.nominal_response) * ((raw > -1) & (raw < 1))[None, :]
        return np.concatenate((response[:, 0, None] * x, response[:, 1, None] * x), axis=1)

    def after_commands(self, commands):
        cov = np.asarray(self.covariance)
        for command in commands:
            command = vector(command, 4)
            if any(abs(x) > 1 for x in command) or any(command[2:]):
                raise ValueError("planar measurement command required")
            jac = self.command_jacobian(command[:2])
            innovation = self.noise_rms_m ** 2 * np.eye(2) + jac @ cov @ jac.T
            cov = cov - cov @ jac.T @ np.linalg.solve(innovation, jac @ cov)
            cov = (cov + cov.T) / 2
        return cov

    def ivr(self, commands, query_commands, weights):
        queries = np.asarray(query_commands, float); weights = np.asarray(weights, float)
        if queries.ndim != 2 or queries.shape[1] != 2 or len(queries) != len(weights) or not np.isfinite(weights).all() or np.any(weights < 0) or not np.isclose(weights.sum(), 1., atol=1e-12, rtol=0):
            raise ValueError("declared normalized task measure required")
        old, new = np.asarray(self.covariance), self.after_commands(commands)
        reduction = sum(w * np.trace(self.command_jacobian(q) @ (old - new) @ self.command_jacobian(q).T) for q, w in zip(queries, weights))
        if reduction < -1e-12 or not np.isfinite(reduction):
            raise ValueError("invalid conditional variance reduction")
        return float(max(0., reduction))

    def choose(self, query_commands, weights, remaining_steps, used_probe_steps):
        if type(remaining_steps) is not int or type(used_probe_steps) is not int or used_probe_steps not in (8, 12):
            raise ValueError("registered continuation boundary required")
        if remaining_steps < 4 + 32:
            raise ValueError("insufficient probe/task budget")
        scores = {name: self.ivr(program, query_commands, weights) for name, program in PRIMITIVES.items()}
        action = max(scores, key=lambda name: (scores[name], -list(PRIMITIVES).index(name)))
        return {"action": action, "scores": scores, "evidence_digest": self.evidence_digest,
                "remaining_steps": remaining_steps, "used_probe_steps": used_probe_steps, "scope": SCOPE,
                "physical_response_qualified": False, "probability_guarantee": False}

    def controller(self):
        return {"kind": "LOCAL_GAUSSIAN_BOX", "mean": list(self.mean), "covariance": [list(r) for r in self.covariance],
                "regularization": REGULARIZATION, "risk_weight": RISK_WEIGHT, "scope": SCOPE,
                "evidence_digest": self.evidence_digest, "physical_response_qualified": False, "probability_guarantee": False}


def box_minimum(hessian, linear):
    h, g = matrix(hessian, (2, 2)), np.asarray(vector(linear, 2))
    if not np.allclose(h, h.T, atol=1e-12, rtol=0) or np.linalg.eigvalsh(h)[0] <= 0:
        raise ValueError("strictly convex command objective required")
    candidates = []
    for active in product((-1, 0, 1), repeat=2):
        value = np.asarray(active, float); free = [i for i in range(2) if active[i] == 0]; fixed = [i for i in range(2) if active[i] != 0]
        if free:
            rhs = -g[free]
            if fixed:
                rhs -= h[np.ix_(free, fixed)] @ value[fixed]
            value[free] = np.linalg.solve(h[np.ix_(free, free)], rhs)
        if np.all(np.abs(value) <= 1 + 1e-12):
            value = np.clip(value, -1, 1)
            candidates.append((float(value @ h @ value + 2 * g @ value), tuple(value)))
    if not candidates:
        raise ValueError("no executable command candidate")
    return np.asarray(min(candidates)[1])


def bounded_command(saved, raw):
    allowed = {"kind", "mean", "covariance", "regularization", "risk_weight", "scope", "evidence_digest", "physical_response_qualified", "probability_guarantee"}
    if set(saved) != allowed or saved["kind"] != "LOCAL_GAUSSIAN_BOX" or saved["scope"] != SCOPE or saved["physical_response_qualified"] is not False or saved["probability_guarantee"] is not False:
        raise ValueError("saved empirical controller contract differs")
    if saved["regularization"] != REGULARIZATION or saved["risk_weight"] != RISK_WEIGHT:
        raise ValueError("controller objective changed after choice")
    mean = np.asarray(vector(saved["mean"], 6)).reshape(2, 3); cov = matrix(saved["covariance"], (6, 6))
    if not np.allclose(cov, cov.T, atol=1e-12, rtol=0) or np.linalg.eigvalsh(cov)[0] <= 0:
        raise ValueError("invalid controller covariance")
    desired = np.clip(np.asarray(vector(raw, 4), dtype=np.float32), -1, 1).astype(float)
    a, b, target = mean[:, :2], mean[:, 2], desired[:2]
    risk_h = cov[:2, :2] + cov[3:5, 3:5]
    risk_g = cov[:2, 2] + cov[3:5, 5]
    h = a.T @ a + REGULARIZATION * np.eye(2) + RISK_WEIGHT * risk_h
    g = a.T @ (b - target) - REGULARIZATION * target + RISK_WEIGHT * risk_g
    sent = desired.copy(); sent[:2] = box_minimum(h, g)
    return sent.astype(np.float32)
