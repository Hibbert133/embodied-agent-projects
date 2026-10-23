"""Task-bound immutable references to the existing nominal ARX coefficients.

These hashes identify a fixed historical model, not physical transfer validity.
Filesystem provenance and full source costs belong to the host-side loader.
"""

from dataclasses import dataclass
import json

from src.probe.movement_history_reference_v1 import (
    MovementHistoryV1, estimate_movement, validate_nominal_model,
)
from src.probe.physical_reprobe_v1 import _digest

TASK_MODEL_SHA256 = {
    "push-v3": "5f303cb585fbe8afbdd0eb63736fc0409bea3ee106c168e287761359ca3b78b1",
    "reach-v3": "46c5f7ce4dfa88329797a963d873248fa833a0524bb0f4399e0eb14971e436a4",
    "door-open-v3": "3ce3d189ff4ea21af957a55c89a19b24d761194341b55e6fc09e39a936bcb440",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class BoundMovementModelV1:
    task: str
    model_json: str

    def __post_init__(self):
        if type(self.task) is not str or self.task not in TASK_MODEL_SHA256 or type(self.model_json) is not str:
            raise ValueError("registered task and immutable model encoding required")
        model = json.loads(self.model_json)
        validate_nominal_model(model)
        if canonical(model) != self.model_json or _digest(model) != TASK_MODEL_SHA256[self.task]:
            raise ValueError("model coefficients do not belong to this frozen task")

    @property
    def model_sha256(self):
        return TASK_MODEL_SHA256[self.task]

    def decoded(self):
        # Return an independent copy; revalidate even if object internals were
        # modified outside the frozen dataclass's ordinary API.
        checked = BoundMovementModelV1(self.task, self.model_json)
        return json.loads(checked.model_json)


def estimate_bound_movement(reference, history):
    if type(reference) is not BoundMovementModelV1 or type(history) is not MovementHistoryV1 or reference.task != history.task:
        raise ValueError("matching task-bound model and actual movement history required")
    model = reference.decoded()
    return estimate_movement(model, history)
