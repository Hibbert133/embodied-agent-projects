"""Visible selected-anchor relocation, incompatible with old estimator inputs.

No calibrated estimator or probability claim. Integral compensation is saved before
probing so its information cannot be attributed to the later eight pulses.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
import math
import numpy as np
from src.probe.physical_reprobe_v1 import (Start, StepReceipt, TASKS,
    TOTAL_STEPS, REPOSITION_LIMIT, TASK_RESERVE, ANCHOR, POSITION_TOLERANCE,
    PROGRAM, probe_in_scope, _ended, _digest, _vector, _keys)

SCOPE = "VISIBLE_SELECTED_ANCHOR_THEN_EIGHT_V1"
METHODS = ("FIXED_PD", "FIXED_PID", "LOCAL_PD", "LOCAL_PID")
INTEGRAL_GAIN = .32
INTEGRAL_LIMIT = .5


def selected_anchor(start, method):
    if type(start) is not Start or method not in METHODS:
        raise ValueError("registered start and method required")
    if method.startswith("FIXED_"):return ANCHOR
    obs = start.current.observation
    # Declared task workspace with an interior target margin, not a safety proof.
    return (min(.45,max(-.45,obs[0])), min(.95,max(.45,obs[1])),
            min(.45,max(.25,obs[6]+.12)))


def anchor_ready(history, anchor):
    anchor = _vector(anchor,3)
    if len(history) < 4:return False
    current = history[-1]
    return (max(abs(x-y) for x,y in zip(current[:3],anchor)) <= .015
        and math.dist(current[:3],current[4:7]) >= .10
        and all(max(abs(x-y) for x,y in zip(a[:3],b[:3])) <= .003
                for a,b in zip(history[-4:-1],history[-3:])))


@dataclass(frozen=True)
class SelectedAnchorWindow:
    task: str
    probe_start_step: int
    anchor: tuple
    entry_history: tuple
    commands: tuple
    observations: tuple

    def __post_init__(self):
        if self.task not in TASKS or type(self.probe_start_step) is not int or not 8 <= self.probe_start_step <= 392:
            raise ValueError("registered selected-anchor window required")
        anchor = _vector(self.anchor,3)
        if not (-.45 <= anchor[0] <= .45 and .45 <= anchor[1] <= .95 and .25 <= anchor[2] <= .45):
            raise ValueError("anchor outside declared target workspace")
        if any(type(v) not in (tuple,list) for v in (self.entry_history,self.commands,self.observations)):
            raise ValueError("ordinary public sequences required")
        history = tuple(_vector(v,39) for v in self.entry_history)
        commands = tuple(_vector(v,4) for v in self.commands)
        observations = tuple(_vector(v,39) for v in self.observations)
        if len(history) != 4 or not anchor_ready(history,anchor) or commands != PROGRAM or len(observations) != 8:
            raise ValueError("complete selected-anchor measurements required")
        if not all(probe_in_scope(v) for v in (history[-1],*observations)):
            raise ValueError("selected-anchor measurement left visible scope")
        object.__setattr__(self,"anchor",anchor)
        object.__setattr__(self,"entry_history",history)
        object.__setattr__(self,"commands",commands)
        object.__setattr__(self,"observations",observations)

    @classmethod
    def from_mapping(cls,value):
        _keys(value,(f.name for f in fields(cls)))
        return cls(**value)


def control_update(start, history, lifted, integral, method):
    if type(start) is not Start or method not in METHODS:
        raise ValueError("registered public start and relocation method required")
    state = np.asarray(_vector(integral, 2))
    if np.any(abs(state) > INTEGRAL_LIMIT) or (method.endswith("_PD") and np.any(state != 0)):
        raise ValueError("invalid bounded integral state")
    anchor = selected_anchor(start, method)
    position = np.asarray(history[-1][:3])
    target = np.asarray(anchor if lifted else (*history[0][:2], anchor[2]))
    error = target-position
    velocity = position-np.asarray(history[-2][:3]) if len(history) >= 2 else np.zeros(3)
    feedback = 8.*error-16.*velocity
    if method.endswith("_PD"):
        desired = np.r_[np.clip(feedback, -.5, .5), -1.]
        desired[:2] = np.asarray(start.correction_xy) @ desired[:2]+start.offset_xy
        return state.tolist(), np.clip(desired, -1., 1.).astype(np.float32).tolist()
    proposed = np.clip(state+INTEGRAL_GAIN*error[:2], -INTEGRAL_LIMIT, INTEGRAL_LIMIT)
    # Conditional integration: reject increments driving either command limit
    # farther outward. The integral itself also has an explicit finite bound.
    for j in range(2):
        delta = proposed[j]-state[j]
        if (feedback[j]+proposed[j] > .5 and delta > 0) or (feedback[j]+proposed[j] < -.5 and delta < 0):
            proposed[j] = state[j]
    desired = np.clip(feedback+np.r_[proposed, 0.], -.5, .5)
    transformed = np.asarray(start.correction_xy) @ desired[:2]+start.offset_xy
    excess = transformed-np.clip(transformed, -1., 1.)
    if np.dot(excess, np.asarray(start.correction_xy) @ (proposed-state)) > 0:
        proposed = state.copy()
    desired = np.r_[np.clip(feedback+np.r_[proposed, 0.], -.5, .5), -1.]
    desired[:2] = np.asarray(start.correction_xy) @ desired[:2]+start.offset_xy
    return proposed.tolist(), np.clip(desired, -1., 1.).astype(np.float32).tolist()


def relocation_evidence(start, integral, ready):
    values = _vector(integral, 2)
    offset = np.asarray(start.offset_xy)+np.asarray(start.correction_xy) @ values
    return {"integral_xy": list(values), "at_anchor": bool(ready),
        "controller": {"source": "RELOCATION_INTEGRAL_REFERENCE", "matrix_xy": start.correction_xy,
                       "offset": [*offset.tolist(), 0., 0.]},
        "parameter_estimate_qualified": False, "task_utility_demonstrated": False}


def acquire(start, step, emit, *, method):
    """Run one bounded operation. Host supplies receipts; no fit or task restart."""
    if type(start) is not Start or method not in METHODS or not callable(step) or not callable(emit):
        raise ValueError("strict public start and host callbacks required")
    current, calls = start.current, start.completed_steps
    anchor = selected_anchor(start, method)
    history = [current.observation]
    events, commands, observations = [], [], []
    sequence = saved_ns = None
    reposition_steps = 0
    integral = [0., 0.]
    learned = None
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
        "scope": SCOPE, "anchor": list(anchor), "maximum_reposition_steps": REPOSITION_LIMIT,
        "task_reserve": TASK_RESERVE, "probe_program": [list(v) for v in PROGRAM],
        "relocation_method": method, "integral_gain": INTEGRAL_GAIN if method.endswith("_PID") else 0.,
        "integral_limit": INTEGRAL_LIMIT})

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
        lifted = current.observation[2] >= anchor[2]-POSITION_TOLERANCE
        while not anchor_ready(history, anchor) and reposition_steps < REPOSITION_LIMIT and not _ended(current):
            updated, command = control_update(start, history, lifted, integral, method)
            save("INTEGRAL_UPDATE", {"at_calls": calls, "integral_before": integral, "integral_after": updated})
            move(command, "REPOSITION")
            integral = updated
            reposition_steps += 1
            lifted = lifted or current.observation[2] >= anchor[2]-POSITION_TOLERANCE
        learned = relocation_evidence(start, integral, anchor_ready(history, anchor))
        save("RELOCATION_EVIDENCE", {"at_calls": calls, **learned})
        if _ended(current):
            reason = "ENDED_DURING_REPOSITION"
        elif not anchor_ready(history, anchor):
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

    window = (SelectedAnchorWindow(start.task, probe_start, anchor, entry_history, tuple(commands), tuple(observations))
              if reason == "COMPLETE_UNQUALIFIED" else None)
    result = {"reason": reason, "completed_steps": calls, "new_steps": calls-start.completed_steps,
        "reposition_steps": reposition_steps, "probe_steps": len(commands), "remaining_steps": TOTAL_STEPS-calls,
        "final": asdict(current), "measurement_model_qualified": False, "parameter_fits": 0,
        "relocation_method": method, "measurement_anchor": list(anchor), "relocation_evidence": learned,
        "window": None if window is None else asdict(window)}
    save("REACQUIRE_RESULT", {"at_calls": calls, **result})
    return {**result, "events": events}
