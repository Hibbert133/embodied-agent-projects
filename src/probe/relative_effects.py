"""Standard randomized AIPW contrast and normal-mixture confidence reference.

The estimand is the average proximal effect along the realized randomized
history. It is neither a current-state effect nor a continuation policy value.
Conditional randomization, consistency and bounded outcomes are assumptions;
this class enforces sequencing but cannot establish those physical assumptions.
"""
from dataclasses import dataclass, asdict
import hashlib
import json
import math

SCOPE = "STANDARD_RANDOMIZED_PROXIMAL_REFERENCE"
TARGET = "REALIZED_HISTORY_AVERAGE_PROXIMAL_EFFECT"


def finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("finite ordinary number required")
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RelativeRequest:
    trial: int
    history_digest: str
    baseline_action: tuple
    candidate_action: tuple
    probability: float
    predicted_baseline: float
    predicted_candidate: float
    remaining_steps: int

    def __post_init__(self):
        if type(self.trial) is not int or self.trial < 1 or type(self.remaining_steps) is not int:
            raise ValueError("integer trial and remaining budget required")
        if type(self.history_digest) is not str or len(self.history_digest) != 64 or any(c not in "0123456789abcdef" for c in self.history_digest):
            raise ValueError("completed visible history digest required")
        for name in ("baseline_action", "candidate_action"):
            value = getattr(self, name)
            if type(value) not in (tuple, list) or len(value) != 4:
                raise ValueError("four-dimensional command required")
            values = tuple(finite(x) for x in value)
            if any(abs(x) > 1 for x in values):
                raise ValueError("commands must already be in the executable box")
            object.__setattr__(self, name, values)
        if self.baseline_action == self.candidate_action:
            raise ValueError("identical commands need no randomized comparison")
        probability = finite(self.probability)
        if not .1 <= probability <= .9:
            raise ValueError("registered overlap [.1,.9] required")
        object.__setattr__(self, "probability", probability)
        for name in ("predicted_baseline", "predicted_candidate"):
            value = finite(getattr(self, name))
            if abs(value) > 1:
                raise ValueError("predictable predictions must lie in [-1,1]")
            object.__setattr__(self, name, value)

    @classmethod
    def from_payload(cls, payload):
        if type(payload) is not dict or set(payload) != set(cls.__dataclass_fields__):
            raise ValueError("exact visible request schema required; no extra truth, future or seed fields")
        return cls(**payload)


def score_and_range(request, assignment, outcome):
    if type(request) is not RelativeRequest or type(assignment) is not int or assignment not in (0, 1):
        raise ValueError("validated request and randomized binary assignment required")
    y = finite(outcome)
    if abs(y) > 1:
        raise ValueError("observed proximal outcome must lie in [-1,1]; no silent clipping")
    p, m0, m1 = request.probability, request.predicted_baseline, request.predicted_candidate
    difference = m1 - m0
    score = difference + (y - m1) / p if assignment else difference - (y - m0) / (1 - p)
    endpoints = (difference + (-1-m1)/p, difference + (1-m1)/p,
                 difference - (-1-m0)/(1-p), difference - (1-m0)/(1-p))
    return score, min(endpoints), max(endpoints)


def mixture_interval(total, variance_proxy, samples, alpha=.05, rho=4.):
    total, variance_proxy, alpha, rho = map(finite, (total, variance_proxy, alpha, rho))
    if type(samples) is not int or samples < 1 or variance_proxy < 0 or not 0 < alpha < 1 or rho <= 0:
        raise ValueError("positive sample count, mixture scale and valid confidence required")
    boundary = math.sqrt((variance_proxy + rho) * (math.log1p(variance_proxy/rho) - 2*math.log(alpha)))
    estimate = total / samples
    lower, upper = max(-2., estimate-boundary/samples), min(2., estimate+boundary/samples)
    return {"estimate": estimate, "lower": lower, "upper": upper, "empty": lower > upper,
            "half_width_before_intersection": boundary/samples}


class RelativeEffectMonitor:
    def __init__(self, host_random, *, alpha=.05, rho=4., maximum_trials=64, task_reserve=32):
        if not callable(host_random) or type(maximum_trials) is not int or maximum_trials < 1 or type(task_reserve) is not int or task_reserve < 1:
            raise ValueError("host random source and positive budgets required")
        mixture_interval(0., 0., 1, alpha, rho)
        self._random = host_random
        self.alpha, self.rho = float(alpha), float(rho)
        self.maximum_trials, self.task_reserve = maximum_trials, task_reserve
        self.samples, self.total, self.variance_proxy = 0, 0., 0.
        self._pending = None
        self._previous_remaining = None

    def prepare(self, request):
        if type(request) is not RelativeRequest or self._pending is not None:
            raise ValueError("one validated request at a time")
        if request.trial != self.samples + 1 or request.trial > self.maximum_trials:
            raise ValueError("contiguous registered trial required")
        if request.remaining_steps < 1 + self.task_reserve:
            raise ValueError("randomization would spend the task reserve")
        if self._previous_remaining is not None and request.remaining_steps != self._previous_remaining - 1:
            raise ValueError("contiguous execution budget required")
        self._pending = {"request": request, "request_id": digest(asdict(request)), "assignment": None}
        return {"request_id": self._pending["request_id"], "request": asdict(request)}

    def randomize(self):
        if self._pending is None or self._pending["assignment"] is not None:
            raise ValueError("prepare before randomizing exactly once")
        draw = finite(self._random())
        if not 0 <= draw < 1:
            raise ValueError("host random draw must be in [0,1)")
        request = self._pending["request"]
        assignment = int(draw < request.probability)
        self._pending["assignment"] = assignment
        return {"request_id": self._pending["request_id"], "assignment": assignment,
                "command": request.candidate_action if assignment else request.baseline_action}

    def observe(self, request_id, outcome):
        if self._pending is None or self._pending["assignment"] is None or request_id != self._pending["request_id"]:
            raise ValueError("matching saved assignment must precede the outcome")
        pending = self._pending; request = pending["request"]
        score, lower, upper = score_and_range(request, pending["assignment"], outcome)
        self.samples += 1; self.total += score; self.variance_proxy += (upper-lower)**2 / 4
        self._previous_remaining = request.remaining_steps
        self._pending = None
        return {"request_id": request_id, "assignment": pending["assignment"], "observed_outcome": float(outcome),
                "pseudo_outcome": score, "predictable_range": [lower, upper], "samples": self.samples,
                "total": self.total, "variance_proxy": self.variance_proxy,
                "interval": mixture_interval(self.total, self.variance_proxy, self.samples, self.alpha, self.rho),
                "target": TARGET, "scope": SCOPE, "task_utility_guarantee": False, "controller_returned": False}
