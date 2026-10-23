"""Visible-feedback relocation followed by new measurements, not a qualified fit.

This version has no environment, reset, RNG, policy, fitting or hidden-state API.
The external host must establish physical continuity and durable journal writes.
Acquired windows are deliberately incompatible with controlled-reset ColdPrefix.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math

import numpy as np

from src.probe.continuous import StepObservation


TASKS = ("push-v3", "reach-v3", "door-open-v3")
SCOPE = "VISIBLE_FEEDBACK_ANCHOR_THEN_EIGHT_XY_V1"
TOTAL_STEPS = 500
REPOSITION_LIMIT = 64
TASK_RESERVE = 100
ANCHOR = (0., .6, .25)
POSITION_TOLERANCE = .015
MOTION_TOLERANCE = .003
ENTRY_CLEARANCE = .10
PROBE_CLEARANCE = .08
MINIMUM_PROBE_HEIGHT = .21
PROGRAM = tuple(tuple(float(x) for x in row) for row in np.asarray(
    [[.4, 0, 0, 0], [0, .4, 0, 0], [-.4, 0, 0, 0], [0, -.4, 0, 0]] * 2,
    dtype=np.float32))


def _vector(value, size):
    if type(value) not in (tuple, list) or len(value) != size:
        raise ValueError("fixed-size public vector required")
    if any(type(x) not in (float, int) or not math.isfinite(x) for x in value):
        raise ValueError("finite ordinary numeric values required")
    return tuple(float(x) for x in value)


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("unknown, private or missing public field")


def _observation(value):
    if type(value) is not StepObservation:
        raise ValueError("exact public observation required")
    _vector(value.observation, 39)
    return value


def _ended(value):
    return value.success or value.terminated or value.truncated


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Start:
    task: str
    completed_steps: int
    current: StepObservation
    correction_xy: tuple
    offset_xy: tuple

    def __post_init__(self):
        if self.task not in TASKS or type(self.completed_steps) is not int or not 8 <= self.completed_steps <= TOTAL_STEPS:
            raise ValueError("registered task and real consumed steps required")
        _observation(self.current)
        if type(self.correction_xy) not in (tuple, list) or len(self.correction_xy) != 2:
            raise ValueError("two correction rows required")
        object.__setattr__(self, "correction_xy", tuple(_vector(r, 2) for r in self.correction_xy))
        object.__setattr__(self, "offset_xy", _vector(self.offset_xy, 2))

    @classmethod
    def from_mapping(cls, value):
        _keys(value, (f.name for f in fields(cls)))
        obs = value["current"]
        _keys(obs, ("observation", "terminated", "truncated", "success"))
        _vector(obs["observation"], 39)
        return cls(value["task"], value["completed_steps"], StepObservation(**obs),
                   value["correction_xy"], value["offset_xy"])


@dataclass(frozen=True)
class StepReceipt:
    current: StepObservation
    completed_steps: int

    def __post_init__(self):
        _observation(self.current)
        if type(self.completed_steps) is not int or not 0 <= self.completed_steps <= TOTAL_STEPS:
            raise ValueError("absolute completed step count required")


def _clearance(observation):
    return math.dist(observation[:3], observation[4:7])


def anchor_ready(history):
    """Three actual small displacements plus visible geometry, not a safety proof."""
    if len(history) < 4:
        return False
    current = history[-1]
    return (max(abs(x-y) for x, y in zip(current[:3], ANCHOR)) <= POSITION_TOLERANCE
            and _clearance(current) >= ENTRY_CLEARANCE
            and all(max(abs(x-y) for x, y in zip(a[:3], b[:3])) <= MOTION_TOLERANCE
                    for a, b in zip(history[-4:-1], history[-3:])))


def probe_in_scope(observation):
    return observation[2] >= MINIMUM_PROBE_HEIGHT and _clearance(observation) >= PROBE_CLEARANCE


@dataclass(frozen=True)
class WarmWindow:
    task: str
    probe_start_step: int
    entry_history: tuple
    commands: tuple
    observations: tuple

    def __post_init__(self):
        if self.task not in TASKS or type(self.probe_start_step) is not int or not 8 <= self.probe_start_step <= TOTAL_STEPS-8-TASK_RESERVE:
            raise ValueError("registered warm measurement start required")
        if any(type(v) not in (tuple, list) for v in (self.entry_history, self.commands, self.observations)):
            raise ValueError("ordinary public sequences required")
        history = tuple(_vector(v, 39) for v in self.entry_history)
        commands = tuple(_vector(v, 4) for v in self.commands)
        observations = tuple(_vector(v, 39) for v in self.observations)
        if len(history) != 4 or not anchor_ready(history) or commands != PROGRAM or len(observations) != 8:
            raise ValueError("complete registered measured window required")
        if not all(probe_in_scope(v) for v in (history[-1], *observations)):
            raise ValueError("warm measurement left its visible scope")
        object.__setattr__(self, "entry_history", history)
        object.__setattr__(self, "commands", commands)
        object.__setattr__(self, "observations", observations)

    @classmethod
    def from_mapping(cls, value):
        _keys(value, (f.name for f in fields(cls)))
        return cls(**value)


def relocation_command(start, history, lifted):
    """Fixed damped position feedback; old correction is used only for relocation."""
    current = np.asarray(history[-1][:3])
    target = np.asarray(ANCHOR if lifted else (*history[0][:2], ANCHOR[2]))
    # No derivative term until two actual observations exist; no synthetic sample.
    velocity = current-np.asarray(history[-2][:3]) if len(history) >= 2 else np.zeros(3)
    desired = np.r_[np.clip(8.*(target-current)-16.*velocity, -.5, .5), -1.]
    sent = desired.copy()
    sent[:2] = np.asarray(start.correction_xy) @ desired[:2] + start.offset_xy
    return np.clip(sent, -1., 1.).astype(np.float32).tolist()


def acquire(start, step, emit):
    """Run one bounded operation. Host supplies receipts; no fit or task restart."""
    if type(start) is not Start or not callable(step) or not callable(emit):
        raise ValueError("strict public start and host callbacks required")
    current, calls = start.current, start.completed_steps
    history = [current.observation]
    events, commands, observations = [], [], []
    sequence = saved_ns = None
    reposition_steps = 0
    probe_start = None
    entry_history = None

    def save(kind, payload):
        nonlocal sequence, saved_ns
        expected = deepcopy(payload)
        saved = emit(kind, deepcopy(expected))
        if (type(saved) is not dict or set(saved) != set(expected) | {"sequence", "saved_ns"}
                or _digest({k: saved[k] for k in expected}) != _digest(expected)
                or type(saved["sequence"]) is not int or saved["sequence"] < 0
                or (sequence is not None and saved["sequence"] != sequence+1)
                or type(saved["saved_ns"]) is not int or saved["saved_ns"] < 0
                or (saved_ns is not None and saved["saved_ns"] < saved_ns)):
            raise ValueError("journal changed choice or ordering")
        saved = deepcopy(saved)
        sequence, saved_ns = saved["sequence"], saved["saved_ns"]
        events.append({"kind": kind, "payload": deepcopy(saved)})
        return saved

    choice = save("REACQUIRE_CHOICE", {"at_calls": calls, "start": asdict(start),
        "scope": SCOPE, "anchor": list(ANCHOR), "maximum_reposition_steps": REPOSITION_LIMIT,
        "task_reserve": TASK_RESERVE, "probe_program": [list(v) for v in PROGRAM]})

    def move(command, phase):
        nonlocal calls, current
        if _ended(current) or calls >= TOTAL_STEPS-TASK_RESERVE:
            raise ValueError("ended or task-reserved execution stepped")
        request = save("COMMAND", {"at_calls": calls, "decision_sequence": choice["sequence"],
            "phase": phase, "before": asdict(current), "command": command, "raw_policy": None})
        supplied = deepcopy(request)
        receipt = step(supplied)
        if _digest(supplied) != _digest(request) or type(receipt) is not StepReceipt or receipt.completed_steps != calls+1:
            raise ValueError("host changed command or skipped physical step count")
        current, calls = receipt.current, receipt.completed_steps
        history.append(current.observation)
        save("STEP_RESULT", {"at_calls": calls, "command_sequence": request["sequence"], "after": asdict(current)})

    if _ended(current):
        reason = "ALREADY_ENDED"
    elif TOTAL_STEPS-calls < REPOSITION_LIMIT+len(PROGRAM)+TASK_RESERVE:
        reason = "ENTRY_BUDGET_INSUFFICIENT"
    else:
        lifted = current.observation[2] >= ANCHOR[2]-POSITION_TOLERANCE
        while not anchor_ready(history) and reposition_steps < REPOSITION_LIMIT and not _ended(current):
            move(relocation_command(start, history, lifted), "REPOSITION")
            reposition_steps += 1
            lifted = lifted or current.observation[2] >= ANCHOR[2]-POSITION_TOLERANCE
        if _ended(current):
            reason = "ENDED_DURING_REPOSITION"
        elif not anchor_ready(history):
            reason = "ANCHOR_NOT_REACHED"
        else:
            probe_start, entry_history = calls, tuple(history[-4:])
            save("PROBE_ENTRY", {"at_calls": calls, "entry_history": entry_history,
                                "scope": SCOPE, "measurement_model_qualified": False})
            reason = "COMPLETE_UNQUALIFIED"
            for command in PROGRAM:
                move(list(command), "WARM_PROBE")
                commands.append(command);observations.append(current.observation)
                if _ended(current):
                    reason = "ENDED_DURING_PROBE";break
                if not probe_in_scope(current.observation):
                    reason = "PROBE_SCOPE_EXIT";break

    window = (WarmWindow(start.task, probe_start, entry_history, tuple(commands), tuple(observations))
              if reason == "COMPLETE_UNQUALIFIED" else None)
    result = {"reason": reason, "completed_steps": calls, "new_steps": calls-start.completed_steps,
        "reposition_steps": reposition_steps, "probe_steps": len(commands), "remaining_steps": TOTAL_STEPS-calls,
        "final": asdict(current), "measurement_model_qualified": False, "parameter_fits": 0,
        "window": None if window is None else asdict(window)}
    save("REACQUIRE_RESULT", {"at_calls": calls, **result})
    return {**result, "events": events}
