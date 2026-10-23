"""Continuous, commanded-action-only probes with no reset capability.

This is a baseline identification primitive, not a calibrated acquisition policy.
The host must pass a step callback that preserves environment and actuator RNG.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Callable, Sequence
import numpy as np


@dataclass(frozen=True)
class StepObservation:
    observation: tuple[float, ...]
    terminated: bool
    truncated: bool
    success: bool

    def __post_init__(self):
        object.__setattr__(self, "observation", _observation(self.observation))
        if any(type(x) is not bool for x in (self.terminated, self.truncated, self.success)):
            raise ValueError("step status must contain booleans only")


@dataclass(frozen=True)
class ContinuousTransition:
    command: tuple[float, ...]
    before: tuple[float, ...]
    after: tuple[float, ...]


@dataclass(frozen=True)
class ContinuousEvidence:
    transitions: tuple[ContinuousTransition, ...]
    final: StepObservation
    stop_reason: str
    requested_steps: int

    @property
    def steps(self):
        return len(self.transitions)

    def to_dict(self):
        return asdict(self)


def _observation(value):
    if len(value) < 3 or any(isinstance(x, (bool, np.bool_)) or not isinstance(x, (int, float, np.number)) for x in value):
        raise ValueError("observation must contain numeric position coordinates")
    array = np.asarray(value, dtype=float)
    if array.ndim != 1 or not np.isfinite(array).all():
        raise ValueError("observation must be a finite vector")
    return tuple(float(x) for x in array)


def symmetric_program(magnitude=.2, steps_per_direction=4):
    if not np.isfinite(magnitude) or not 0 < magnitude <= 1 or type(steps_per_direction) is not int or steps_per_direction < 1:
        raise ValueError("invalid continuous probe program")
    return tuple(tuple(float(x) for x in command) for command in
                 np.repeat(np.array([[magnitude,0,0,0],[-magnitude,0,0,0],
                                     [0,magnitude,0,0],[0,-magnitude,0,0]], dtype=np.float32),
                           steps_per_direction, axis=0))


def collect_continuous(step: Callable[[np.ndarray], StepObservation], initial: StepObservation,
                       commands: Sequence[Sequence[float]], *, remaining_budget: int,
                       task_reserve: int = 500) -> ContinuousEvidence:
    """Consume one live trajectory. No factory, reset, fault, or Oracle argument.

    The final observation is handed back for immediate task continuation.
    Preflight validation occurs before the first physical interaction.
    """
    if type(remaining_budget) is not int or type(task_reserve) is not int or task_reserve < 0:
        raise ValueError("budgets must be nonnegative integers")
    if type(initial) is not StepObservation or initial.terminated or initial.truncated or initial.success:
        raise ValueError("cannot probe an ended or already successful episode")
    program = []
    for command in commands:
        a = np.asarray(command, dtype=np.float32)
        if a.shape != (4,) or not np.isfinite(a).all() or np.any(np.abs(a) > 1):
            raise ValueError("command must be a finite bounded four-vector")
        program.append(a)
    if not program or len(program) + task_reserve > remaining_budget:
        raise ValueError("probe would consume reserved task budget")
    before = _observation(initial.observation)
    transitions = []
    latest = initial
    for command in program:
        latest = step(command.copy())
        if type(latest) is not StepObservation or len(latest.observation) != len(before):
            raise ValueError("step must return the registered visible observation schema")
        after = _observation(latest.observation)
        transitions.append(ContinuousTransition(tuple(float(x) for x in command), before, after))
        before = after
        reason = "SUCCESS" if latest.success else "TERMINATED" if latest.terminated else "TRUNCATED" if latest.truncated else None
        if reason:
            return ContinuousEvidence(tuple(transitions), latest, reason, len(program))
    return ContinuousEvidence(tuple(transitions), latest, "PROGRAM_COMPLETE", len(program))


@dataclass(frozen=True)
class LocalResponseFit:
    valid: bool
    reason: str
    samples: int
    design_rank: int
    design_condition: float | None
    bias_in_command_units: tuple[float, float] | None = None
    inertia: tuple[tuple[float, float], ...] | None = None
    response: tuple[tuple[float, float], ...] | None = None
    intercept: tuple[float, float] | None = None
    residual_rmse: float | None = None


def fit_local_response(evidence: ContinuousEvidence) -> LocalResponseFit:
    """OLS baseline: delta[t] = A delta[t-1] + B command[t] + c.

    Uses observed xy positions and commanded xy inputs only. B^-1 c is an
    equivalent input offset under this local model, not identified physical
    bias in general. No confidence or task-performance certificate is returned.
    """
    rows = evidence.transitions
    if rows and rows[-1].after != evidence.final.observation:
        raise ValueError("final observation does not match collected trajectory")
    if len(rows) < 8:
        return LocalResponseFit(False, "INSUFFICIENT_TRANSITIONS", max(0,len(rows)-1), 0, None)
    for index, row in enumerate(rows):
        _observation(row.before)
        _observation(row.after)
        if index and row.before != rows[index-1].after:
            raise ValueError("discontinuous observation chain")
        if len(row.command) != 4 or not np.isfinite(row.command).all() or np.any(np.abs(row.command) > 1):
            raise ValueError("invalid observed command")
    delta = np.array([np.array(r.after[:2])-r.before[:2] for r in rows])
    commands = np.array([r.command[:2] for r in rows])
    raw = np.column_stack((delta[:-1], commands[1:]))
    scale = np.std(raw, axis=0)
    scale[scale < 1e-12] = 1.
    design = np.column_stack((raw / scale, np.ones(len(raw))))
    rank = int(np.linalg.matrix_rank(design))
    condition = float(np.linalg.cond(design))
    if rank != 5 or not np.isfinite(condition) or condition > 1e6:
        return LocalResponseFit(False, "UNIDENTIFIABLE_DESIGN", len(raw), rank, condition if np.isfinite(condition) else None)
    coef, _, _, _ = np.linalg.lstsq(design, delta[1:], rcond=None)
    coef[:4] /= scale[:,None]
    inertia, response, intercept = coef[:2].T, coef[2:4].T, coef[4]
    singular = np.linalg.svd(response, compute_uv=False)
    if singular[-1] < 1e-6 or singular[0]/singular[-1] > 1e6:
        return LocalResponseFit(False, "UNIDENTIFIABLE_RESPONSE", len(raw), rank, condition)
    bias = np.linalg.solve(response, intercept)
    prediction = raw @ coef[:4] + intercept
    rmse = float(np.sqrt(np.mean((prediction-delta[1:])**2)))
    return LocalResponseFit(True, "LOCAL_OLS_ESTIMATE_ONLY", len(raw), rank, condition,
        tuple(float(x) for x in bias), tuple(tuple(float(x) for x in row) for row in inertia),
        tuple(tuple(float(x) for x in row) for row in response), tuple(float(x) for x in intercept), rmse)
