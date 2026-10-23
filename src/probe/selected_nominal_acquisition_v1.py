"""Independent-command nominal acquisition; needs host provenance verification.

Versioned separately from the immutable fixed-program task measurement. The
relocation rule and limits are shared; no RNG, simulator or private labels enter
this actor. A future collector must preregister commands before observing state.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields
import numpy as np
from src.probe.local_reprobe_v1 import (Start, StepReceipt, selected_anchor,
    anchor_ready, control_update, relocation_evidence, REPOSITION_LIMIT,
    TASK_RESERVE, TOTAL_STEPS, POSITION_TOLERANCE, INTEGRAL_GAIN, INTEGRAL_LIMIT,
    probe_in_scope, _ended, _digest, _vector, _keys)
from src.probe.selected_response_reference_v1 import NominalSelectedTrajectory

SCOPE = "SELECTED_NOMINAL_RANDOM_EIGHT_V1"
COMMAND_LIMIT = float(np.float32(.8))


@dataclass(frozen=True)
class NominalProgram:
    commands: tuple

    def __post_init__(self):
        if type(self.commands) not in (tuple, list) or len(self.commands) != 8:
            raise ValueError("eight preregistered nominal commands required")
        commands = tuple(_vector(c, 4) for c in self.commands)
        if any(max(abs(v) for v in c) > COMMAND_LIMIT or c[2] != 0 or c[3] != 0 for c in commands):
            raise ValueError("bounded planar nominal command program required")
        commands = tuple(tuple(float(v) for v in row) for row in np.array(commands, dtype=np.float32))
        object.__setattr__(self, "commands", commands)

    @classmethod
    def from_mapping(cls, value):
        _keys(value, (f.name for f in fields(cls)))
        return cls(**value)


def acquire(start, program, step, emit):
    """Run one bounded operation. Host supplies receipts; no fit or task restart."""
    method = "LOCAL_PID"
    if type(start) is not Start or type(program) is not NominalProgram or not callable(step) or not callable(emit):
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
        "task_reserve": TASK_RESERVE, "probe_program": [list(v) for v in program.commands],
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
    elif TOTAL_STEPS-calls < REPOSITION_LIMIT+len(program.commands)+TASK_RESERVE:
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
            reason = "COMPLETE_NOMINAL_TRAIN"
            for command in program.commands:
                move(list(command), "WARM_PROBE")
                commands.append(command);observations.append(current.observation)
                if _ended(current):
                    reason = "ENDED_DURING_PROBE";break
                if not probe_in_scope(current.observation):
                    reason = "PROBE_SCOPE_EXIT";break

    window = (NominalSelectedTrajectory(start.task, probe_start, anchor, entry_history, tuple(commands), tuple(observations))
              if reason == "COMPLETE_NOMINAL_TRAIN" else None)
    result = {"reason": reason, "completed_steps": calls, "new_steps": calls-start.completed_steps,
        "reposition_steps": reposition_steps, "probe_steps": len(commands), "remaining_steps": TOTAL_STEPS-calls,
        "final": asdict(current), "measurement_model_qualified": False, "parameter_fits": 0,
        "relocation_method": method, "measurement_anchor": list(anchor), "relocation_evidence": learned,
        "nominal_trajectory": None if window is None else asdict(window)}
    save("REACQUIRE_RESULT", {"at_calls": calls, **result})
    return {**result, "events": events}
