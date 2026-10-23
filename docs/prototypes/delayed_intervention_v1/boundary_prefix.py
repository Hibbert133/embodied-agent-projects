"""Visible-only, fixed preparation for a live step-16 qualification boundary.

The four-step correction is saved as an unused candidate. The eight-step
correction actually controls steps 9--16. No mid-contact identification occurs.
"""

from copy import deepcopy
from dataclasses import asdict

import numpy as np

from src.analysis.capsule_record_json_v2 import normalize
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.cold_start_response import ColdPrefix, TASKS, infer_operator, validate_model
from src.probe.continuous import StepObservation
from src.probe.forward_prediction import vector
from src.probe.operator_identification import affine_controller, encode_controller
from src.probe.short_joint_reference_v1 import infer_four


BOUNDARY_STEP = 16
PROGRAM4 = tuple(tuple(float(x) for x in row) for row in np.asarray(
    [[.4, 0, 0, 0], [0, .4, 0, 0], [-.4, 0, 0, 0], [0, -.4, 0, 0]], np.float32))


def ended(observation):
    return observation.success or observation.terminated or observation.truncated


def prepare_boundary(task, initial, model, policy, step, emit):
    """Only public observed data and callbacks enter this fixed preparation."""
    if task not in TASKS or type(initial) is not StepObservation or ended(initial):
        raise ValueError("registered live initial observation required")
    vector(initial.observation, 39)
    validate_model(model)
    if model["task"] != task or not all(callable(f) for f in (policy, step, emit)):
        raise ValueError("matching nominal model and callbacks required")
    model = deepcopy(normalize(model))
    current, calls, queries = initial, 0, 0
    local, saved_ns = -1, -1
    events, commands, observations, fits = [], [], [], []
    saved_choice = current_choice = None
    reason = "EARLY_END"

    def save(kind, payload):
        nonlocal local, saved_ns
        expected = normalize(payload)
        saved = emit(kind, deepcopy(expected))
        if (type(saved) is not dict or set(saved) != set(expected) | {"sequence", "saved_ns"}
                or digest({k: saved[k] for k in expected}) != digest(expected)
                or type(saved["sequence"]) is not int or saved["sequence"] != local + 1
                or type(saved["saved_ns"]) is not int or saved["saved_ns"] < max(0, saved_ns)):
            raise ValueError("prefix journal acknowledgement differs")
        result = deepcopy(saved);local, saved_ns = result["sequence"], result["saved_ns"]
        events.append({"kind": kind, "payload": deepcopy(result)})
        return result

    def move(choice, command, phase, raw=None):
        nonlocal current, calls
        if ended(current) or calls >= BOUNDARY_STEP:
            raise ValueError("ended or complete preparation stepped")
        command = np.asarray(vector(command, 4), np.float32)
        if np.any(abs(command) > 1):
            raise ValueError("bounded prefix command required")
        request = save("COMMAND", {"at_calls": calls, "phase": phase,
            "decision_sequence": choice["sequence"], "before": asdict(current),
            "command": command.tolist(), "raw_policy": None if raw is None else raw.tolist()})
        supplied = deepcopy(request);after = step(supplied)
        if digest(supplied) != digest(request) or type(after) is not StepObservation:
            raise ValueError("prefix host mutated request or returned invalid observation")
        vector(after.observation, 39)
        calls += 1;current = after
        if phase == "FIXED_PROBE":
            commands.append(tuple(request["command"]));observations.append(current.observation)
        save("STEP_RESULT", {"at_calls": calls, "command_sequence": request["sequence"], "after": asdict(current)})

    save("PREFIX_PROGRAM", {"task": task, "initial": asdict(initial), "at_calls": 0,
        "boundary_step": BOUNDARY_STEP, "episode_budget": 500, "nominal_model_sha256": digest(model),
        "program4": [list(row) for row in PROGRAM4]})
    for count in (4, 8):
        choice = save("CHOICE", {"action": "PROBE_FOUR", "at_calls": calls,
                                "program": [list(row) for row in PROGRAM4]})
        for command in choice["program"]:
            if ended(current):
                break
            move(choice, command, "FIXED_PROBE")
        if ended(current):
            break
        prefix = ColdPrefix(task, initial.observation, tuple(commands), tuple(observations), True)
        intent = save("FIT_INTENT", {"at_calls": calls, "prefix": asdict(prefix), "prefix_sha256": digest(asdict(prefix))})
        fit = normalize(infer_four(model, prefix) if count == 4 else infer_operator(model, prefix))
        fitted = save("FIT_RESULT", {"at_calls": calls, "intent_sequence": intent["sequence"], "fit": fit})
        fits.append(fitted)
        if fit["valid"] is not True:
            reason = "INVALID_FOUR" if count == 4 else "INVALID_EIGHT"
            break
        selection = save("CHOICE", {"action": "RUN_FITTED", "at_calls": calls,
            "controller": affine_controller(fit["matrix_xy"], fit["bias_xy"]),
            "fit_sequence": fitted["sequence"], "fitted_prefix_steps": count,
            "purpose": "SAVED_UNUSED_CANDIDATE" if count == 4 else "CURRENT_POLICY_CONTROLLER"})
        if count == 4:
            saved_choice = selection
        else:
            current_choice = selection

    if current_choice is not None:
        while not ended(current) and calls < BOUNDARY_STEP:
            raw = np.asarray(vector(policy(np.array(current.observation, copy=True)), 4), np.float32)
            queries += 1
            move(current_choice, encode_controller(current_choice["controller"], raw), "POLICY", raw)
    ready = calls == BOUNDARY_STEP and not ended(current) and current_choice is not None
    if ready:
        reason = "LIVE_STEP16"
    result = {"ready": ready, "reason": reason, "completed_steps": calls,
        "current_choice_sequence": None if current_choice is None else current_choice["sequence"],
        "saved_choice_sequence": None if saved_choice is None else saved_choice["sequence"],
        "policy_queries": queries, "fits_completed": len(fits),
        "optimizer_nfev": sum(int(f["fit"].get("nfev", 0)) for f in fits),
        "final_observation": asdict(current), "saved_candidate_was_previously_applied": False}
    save("PREFIX_RESULT", {"at_calls": calls, "result": result})
    return normalize({**result, "events": events})
