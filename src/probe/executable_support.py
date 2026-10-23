"""Retarget local IVR to the commands emitted by a saved bounded controller.

This is an experimental control-oriented design adaptation. Its finite measure
is conditional on the current saved controller, not a forecast of task states,
the future posterior controller, or a qualified physical response distribution.
"""
from dataclasses import dataclass
import hashlib
import json
import numpy as np
from src.probe.forward_prediction import vector
from src.probe.gaussian_response_reference import GaussianReference, bounded_command

SCOPE = "UNQUALIFIED_CURRENT_CONTROLLER_PUSHFORWARD"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class DesiredMeasure:
    commands: tuple
    weights: tuple

    def __post_init__(self):
        commands = tuple(vector(q, 2) for q in self.commands)
        weights = vector(self.weights, len(commands))
        if not commands or len(commands) != len(weights) or any(abs(v) > 1 for q in commands for v in q):
            raise ValueError("nonempty bounded desired command measure required")
        if not np.isfinite(weights).all() or any(w < 0 for w in weights) or not np.isclose(sum(weights), 1., atol=1e-12, rtol=0):
            raise ValueError("finite normalized weights required")
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "weights", weights)


def support_map(reference, measure):
    """Only finite visible model moments and a predeclared desired measure enter."""
    if type(reference) is not GaussianReference or type(measure) is not DesiredMeasure:
        raise ValueError("strict visible reference and desired measure required")
    controller = reference.controller()
    commands = [bounded_command(controller, (*q, 0., 0.))[:2].astype(float).tolist() for q in measure.commands]
    return {"scope": SCOPE, "desired_commands": [list(q) for q in measure.commands],
            "weights": list(measure.weights), "executable_commands": commands,
            "controller_sha256": digest(controller), "evidence_digest": reference.evidence_digest,
            "physical_response_qualified": False, "probability_guarantee": False}


def choose(reference, measure, remaining_steps, used_probe_steps, *, anchor=None):
    """A fixed-at-eight anchor is a registered ablation, not an updated posterior."""
    if type(reference) is not GaussianReference or type(measure) is not DesiredMeasure:
        raise ValueError("strict visible reference and desired measure required")
    if anchor is not None and (type(anchor) is not GaussianReference or used_probe_steps not in (8, 12)):
        raise ValueError("registered visible eight-step anchor required")
    mapping = support_map(reference if anchor is None else anchor, measure)
    result = reference.choose(mapping["executable_commands"], mapping["weights"], remaining_steps, used_probe_steps)
    return {**result, "support_mapping": mapping, "support_sha256": digest(mapping),
            "support_mode": "FROZEN_AT_EIGHT" if anchor is not None else "CURRENT_CONTROLLER"}
