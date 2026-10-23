"""Standard bounded integral relocation; shared old warm-window contract.

No new estimator or probability claim. Integral compensation is saved before
probing so its information cannot be attributed to the later eight pulses.
"""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
from src.probe.physical_reprobe_v1 import (Start, StepReceipt, WarmWindow, TASKS,
    TOTAL_STEPS, REPOSITION_LIMIT, TASK_RESERVE, ANCHOR, POSITION_TOLERANCE,
    PROGRAM, anchor_ready, probe_in_scope, relocation_command, _ended, _digest, _vector)

SCOPE = "BOUNDED_INTEGRAL_ANCHOR_THEN_EIGHT_V1"
METHODS = ("PD", "PID")
INTEGRAL_GAIN = .32
INTEGRAL_LIMIT = .5


def control_update(start, history, lifted, integral, method):
    if type(start) is not Start or method not in METHODS:
        raise ValueError("registered public start and relocation method required")
    state = np.asarray(_vector(integral, 2))
    if np.any(abs(state) > INTEGRAL_LIMIT) or (method == "PD" and np.any(state != 0)):
        raise ValueError("invalid bounded integral state")
    if method == "PD":
        return state.tolist(), relocation_command(start, history, lifted)
    position = np.asarray(history[-1][:3])
    target = np.asarray(ANCHOR if lifted else (*history[0][:2], ANCHOR[2]))
    error = target-position
    velocity = position-np.asarray(history[-2][:3]) if len(history) >= 2 else np.zeros(3)
    feedback = 8.*error-16.*velocity
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
        "scope": SCOPE, "anchor": list(ANCHOR), "maximum_reposition_steps": REPOSITION_LIMIT,
        "task_reserve": TASK_RESERVE, "probe_program": [list(v) for v in PROGRAM],
        "relocation_method": method, "integral_gain": INTEGRAL_GAIN if method == "PID" else 0.,
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
        lifted = current.observation[2] >= ANCHOR[2]-POSITION_TOLERANCE
        while not anchor_ready(history) and reposition_steps < REPOSITION_LIMIT and not _ended(current):
            updated, command = control_update(start, history, lifted, integral, method)
            save("INTEGRAL_UPDATE", {"at_calls": calls, "integral_before": integral, "integral_after": updated})
            move(command, "REPOSITION")
            integral = updated
            reposition_steps += 1
            lifted = lifted or current.observation[2] >= ANCHOR[2]-POSITION_TOLERANCE
        learned = relocation_evidence(start, integral, anchor_ready(history))
        save("RELOCATION_EVIDENCE", {"at_calls": calls, **learned})
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
        "relocation_method": method, "relocation_evidence": learned,
        "window": None if window is None else asdict(window)}
    save("REACQUIRE_RESULT", {"at_calls": calls, **result})
    return {**result, "events": events}
