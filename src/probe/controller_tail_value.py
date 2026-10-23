"""Controller-conditioned Monte Carlo tail regression, a standard reference.

Only TailEvidence enters the predictor. Group identifiers and terminal targets
belong to the offline evaluation layer, never this agent-visible schema.
"""
from dataclasses import dataclass, asdict, fields
import hashlib
import json
import math
import numpy as np

from src.probe.gaussian_response_reference import bounded_command
from src.probe.operator_identification import encode_controller

TASKS = ("push-v3", "reach-v3", "door-open-v3")
KINDS = ("IDENTITY", "AFFINE", "GAUSSIAN")
REGRESSORS = ("DENSE_RFF", "LINEAR_DENSE", "PREFIX_ONLY_RFF", "NO_CONTROLLER_RFF")
REFERENCES = ("TASK_CONSTANT", "TASK_KIND_CONSTANT")
DIMENSION = 90
FIELD_INPUTS = ((0, 0, 0, 0), (1, 0, 0, 0), (-1, 0, 0, 0),
                (0, 1, 0, 0), (0, -1, 0, 0))


def numeric(value, shape):
    raw = np.asarray(value, dtype=object)
    if raw.shape != shape or any(not isinstance(v, (int, float, np.integer, np.floating))
                                 or isinstance(v, (bool, np.bool_)) for v in raw.flat):
        raise ValueError("finite numeric field with registered shape required")
    result = np.asarray(value, dtype=float)
    if not np.isfinite(result).all():
        raise ValueError("nonfinite visible input")
    return result


def command(saved, raw):
    if type(saved) is not dict:
        raise ValueError("saved public controller required")
    if saved.get("kind") == "LOCAL_GAUSSIAN_BOX":
        return bounded_command(saved, raw)
    if saved.get("source") not in ("UNCORRECTED", "ESTIMATED_AFFINE"):
        raise ValueError("oracle and legacy controllers are not agent candidates")
    return encode_controller(saved, raw)


def controller_kind(saved):
    command(saved, (0, 0, 0, 0))  # validate the whole saved schema
    if saved.get("kind") == "LOCAL_GAUSSIAN_BOX":
        return "GAUSSIAN"
    return "IDENTITY" if saved["source"] == "UNCORRECTED" else "AFFINE"


def controller_field(saved):
    return tuple(tuple(float(v) for v in command(saved, raw)[:2]) for raw in FIELD_INPUTS)


@dataclass(frozen=True)
class TailEvidence:
    task: str
    observations: tuple
    commands: tuple
    raw_policy: tuple
    candidate_command: tuple
    controller_field: tuple
    controller_kind: str
    remaining_steps: int

    def __post_init__(self):
        if self.task not in TASKS or self.controller_kind not in KINDS:
            raise ValueError("unregistered task or public controller kind")
        if type(self.remaining_steps) is not int or not 1 <= self.remaining_steps <= 492:
            raise ValueError("registered nonterminal budget required")
        for name, shape in (("observations", (9, 39)), ("commands", (8, 4)),
                            ("raw_policy", (4,)), ("candidate_command", (4,)),
                            ("controller_field", (5, 2))):
            value = numeric(getattr(self, name), shape)
            if name != "observations" and np.max(np.abs(value)) > 1:
                raise ValueError("unbounded command in visible evidence")
            immutable = tuple(tuple(float(v) for v in row) for row in value) if value.ndim == 2 else tuple(float(v) for v in value)
            object.__setattr__(self, name, immutable)

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {f.name for f in fields(cls)}:
            raise ValueError("unknown or missing tail evidence field")
        return cls(**value)

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def build_evidence(task, observations, commands, raw_policy, saved, remaining_steps, field=None):
    raw = np.clip(numeric(raw_policy, (4,)).astype(np.float32), -1, 1)
    return TailEvidence(task, observations, commands, tuple(raw), tuple(command(saved, raw)),
                        controller_field(saved) if field is None else field,
                        controller_kind(saved), remaining_steps)


def features(evidence):
    if type(evidence) is not TailEvidence:
        raise ValueError("strict TailEvidence required")
    obs = np.asarray(evidence.observations); now = obs[-1]
    u = np.asarray(evidence.commands)[:, :2]
    y = np.diff(obs[:, :2], axis=0) / .01
    uc, yc = u - u.mean(axis=0), y - y.mean(axis=0)
    cu, cy, cross = uc.T @ uc / 8, yc.T @ yc / 8, uc.T @ yc / 8
    moments = np.r_[u.mean(axis=0), y.mean(axis=0), cu[0, 0], cu[0, 1], cu[1, 1],
                    cy[0, 0], cy[0, 1], cy[1, 1], cross.ravel()]
    output = np.r_[now, (now[-3:] - now[:3]) / .1, (now[-3:] - now[4:7]) / .1,
                   (now[4:7] - now[:3]) / .1, np.diff(obs[-3:, :3], axis=0).ravel() / .01,
                   evidence.raw_policy, evidence.candidate_command,
                   np.asarray(evidence.controller_field).ravel(), moments,
                   evidence.remaining_steps / 500, [float(evidence.controller_kind == k) for k in KINDS]]
    return numeric(output, (DIMENSION,))


def feature_map(x, name, omega, phase):
    values = np.array(x, dtype=float, copy=True)
    if values.ndim != 2 or values.shape[1] != DIMENSION or not np.isfinite(values).all():
        raise ValueError("finite registered feature matrix required")
    if name not in REGRESSORS:
        raise ValueError("unregistered regressor")
    if name == "NO_CONTROLLER_RFF":
        values[:, 58:72] = 0
        values[:, 87:90] = 0
    values /= math.sqrt(DIMENSION)
    mapped = values if name == "LINEAR_DENSE" else math.sqrt(2 / len(phase)) * np.cos(values @ omega + phase)
    return np.column_stack((np.ones(len(values)), mapped))


def sufficient_statistics(z, targets, weights):
    z = np.asarray(z, float); y = np.asarray(targets, float); w = np.asarray(weights, float)
    if z.ndim != 2 or y.shape != (len(z),) or w.shape != y.shape or not np.isfinite(z).all() or not np.isfinite(y).all() or not np.isfinite(w).all() or np.any(w < 0) or w.sum() <= 0:
        raise ValueError("valid weighted regression sample required")
    return z.T @ (w[:, None] * z), z.T @ (w * y)


def solve_statistics(gram, rhs, ridge=1.0):
    if ridge != 1.0:
        raise ValueError("reference ridge is frozen at one")
    a = np.array(gram, dtype=float, copy=True)
    a += np.diag(np.r_[0., np.full(len(rhs) - 1, ridge)])
    return np.linalg.solve(a, rhs)


def leave_group_out(z, targets, weights, groups, heldout):
    groups = np.asarray(groups)
    if heldout not in groups or not np.any(groups != heldout):
        raise ValueError("held group and independent training groups required")
    mask = groups != heldout
    return solve_statistics(*sufficient_statistics(z[mask], np.asarray(targets)[mask], np.asarray(weights)[mask]))


def remaining_prediction(z, coefficient, remaining):
    return np.clip(np.asarray(z) @ coefficient, 0, 1) * np.asarray(remaining)
