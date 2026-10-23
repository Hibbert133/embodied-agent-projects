"""All-movement ARX reference with an explicit causal observation boundary.

This reuses the existing prediction-error estimator. It adds no identification
guarantee, controller execution, data collection, or novel acquisition method.
The host must prove that the supplied public history is from its actual run.
"""

from dataclasses import asdict, dataclass, fields

import numpy as np

from src.probe.continuous import StepObservation
from src.probe.forward_prediction import ForwardQuery
from src.probe.operator_identification import OperatorSample, infer_operator
from src.probe.physical_reprobe_v1 import TASKS, _digest, _ended, _keys, _vector

SCOPE = "ALL_RELOCATION_TRANSITIONS_WITH_TWO_PRIOR_DISPLACEMENTS_V1"
METHOD = "MOVEMENT_ARX_ALL_V1"
MAX_MOVEMENT_STEPS = 64
MAX_EVIDENCE_STEP = 400


def observation(value):
    if type(value) is not StepObservation:
        raise ValueError("exact public observation required")
    _vector(value.observation, 39)
    return value


def parse_observation(value):
    _keys(value, ("observation", "terminated", "truncated", "success"))
    _vector(value["observation"], 39)
    return StepObservation(**value)


@dataclass(frozen=True)
class MovementTransitionV1:
    completed_step: int
    command: tuple
    before: StepObservation
    after: StepObservation

    def __post_init__(self):
        if type(self.completed_step) is not int or not 9 <= self.completed_step <= MAX_EVIDENCE_STEP:
            raise ValueError("actual bounded completed step required")
        command = _vector(self.command, 4)
        if max(abs(x) for x in command) > 1:
            raise ValueError("bounded actual four-axis command required")
        if _ended(observation(self.before)):
            raise ValueError("movement cannot follow an ended observation")
        observation(self.after)
        object.__setattr__(self, "command", command)

    @classmethod
    def from_mapping(cls, value):
        _keys(value, (f.name for f in fields(cls)))
        return cls(value["completed_step"], value["command"],
                   parse_observation(value["before"]), parse_observation(value["after"]))


@dataclass(frozen=True)
class MovementHistoryV1:
    task: str
    start_step: int
    decision_step: int
    context: tuple
    transitions: tuple

    def __post_init__(self):
        if self.task not in TASKS or type(self.start_step) is not int or not 8 <= self.start_step <= MAX_EVIDENCE_STEP:
            raise ValueError("registered task and actual movement start required")
        if type(self.context) not in (list, tuple) or len(self.context) != 3:
            raise ValueError("three real consecutive prior observations required")
        context = tuple(observation(v) for v in self.context)
        if any(_ended(v) for v in context):
            raise ValueError("movement context already ended")
        if type(self.transitions) not in (list, tuple) or len(self.transitions) > MAX_MOVEMENT_STEPS:
            raise ValueError("complete bounded movement history required")
        rows = tuple(self.transitions)
        if type(self.decision_step) is not int or self.decision_step != self.start_step+len(rows) or self.decision_step > MAX_EVIDENCE_STEP:
            raise ValueError("decision cutoff differs from actually completed history")
        current = context[-1]
        for index, row in enumerate(rows, self.start_step+1):
            if type(row) is not MovementTransitionV1 or row.completed_step != index or row.before != current:
                raise ValueError("movement step or observation continuity differs")
            current = row.after
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "transitions", rows)

    @classmethod
    def from_mapping(cls, value):
        _keys(value, (f.name for f in fields(cls)))
        if type(value["context"]) not in (list, tuple) or type(value["transitions"]) not in (list, tuple):
            raise ValueError("ordinary public sequences required")
        return cls(value["task"], value["start_step"], value["decision_step"],
                   tuple(parse_observation(v) for v in value["context"]),
                   tuple(MovementTransitionV1.from_mapping(v) for v in value["transitions"]))

    def to_dict(self):
        return asdict(self)

    @property
    def sha256(self):
        return _digest(self.to_dict())

    @property
    def current(self):
        return self.transitions[-1].after if self.transitions else self.context[-1]


def operator_samples(history):
    """Use every movement response; preserve real pre-movement AR2 context."""
    if type(history) is not MovementHistoryV1:
        raise ValueError("typed movement history required")
    p0, p1, p2 = (np.array(v.observation[:3]) for v in history.context)
    prior, last = p1-p0, p2-p1
    samples = []
    for row in history.transitions:
        query = ForwardQuery(row.before.observation, tuple(last), tuple(prior), row.command)
        delta = np.array(row.after.observation[:3])-row.before.observation[:3]
        samples.append(OperatorSample(row.completed_step, query, tuple(delta[:2])))
        prior, last = last, delta
    return tuple(samples)


def validate_nominal_model(model):
    required = {"method", "training_samples", "mean", "scale", "physical_response_qualified",
                "probability_guarantee", "coefficients", "ridge", "feature_count", "training_rmse"}
    _keys(model, required)
    if (model["method"] != "LINEAR_ARX" or model["physical_response_qualified"] is not False
            or model["probability_guarantee"] is not False or model["ridge"] != .001
            or type(model["feature_count"]) is not int or model["feature_count"] != 11
            or type(model["training_samples"]) is not int or model["training_samples"] < 32):
        raise ValueError("unchanged nominal linear ARX model required")
    _vector(model["mean"], 10)
    if min(_vector(model["scale"], 10)) <= 0 or _vector([model["training_rmse"]], 1)[0] < 0:
        raise ValueError("invalid nominal model scale or error")
    if type(model["coefficients"]) not in (list, tuple) or len(model["coefficients"]) != 11:
        raise ValueError("eleven two-output coefficient rows required")
    for row in model["coefficients"]:
        _vector(row, 2)


def estimate_movement(model, history):
    """Diagnostic estimate only; invalid fits never substitute another controller."""
    validate_nominal_model(model)
    samples = operator_samples(history)
    base = {"method": METHOD, "scope": SCOPE, "history_sha256": history.sha256,
            "model_sha256": _digest(model), "decision_step": history.decision_step,
            "movement_responses": len(samples), "fit_attempts": 0, "optimizer_nfev": 0,
            "physical_response_qualified": False, "task_utility_demonstrated": False,
            "probability_guarantee": False}
    if _ended(history.current):
        return {**base, "status": "ENDED_NO_UPDATE", "fit": None}
    if not samples:
        return {**base, "status": "NO_MOVEMENT_EVIDENCE", "fit": None}
    fit = infer_operator(model, samples)
    return {**base, "status": "VALID_WORKING_ESTIMATE" if fit["valid"] else "INVALID_ESTIMATE",
            "fit_attempts": 1, "optimizer_nfev": sum(t["nfev"] for t in fit.get("optimizer_trials", [])), "fit": fit}
