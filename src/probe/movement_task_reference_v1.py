"""Saved-choice task execution for four fixed movement references.

No reset, simulator state, fault label, seed, or outcome from another method is
accepted. This is a standard-baseline bridge, not an acquisition selector.
"""

from copy import deepcopy
from dataclasses import asdict
from time import perf_counter_ns

import numpy as np

from src.probe.local_reprobe_v1 import anchor_ready, control_update, relocation_evidence, selected_anchor
from src.probe.movement_history_reference_v1 import (
    METHOD as ESTIMATE_METHOD, SCOPE as HISTORY_SCOPE, MovementHistoryV1, MovementTransitionV1, operator_samples,
)
from src.probe.movement_model_binding_v1 import BoundMovementModelV1, estimate_bound_movement
from src.probe.operator_identification import affine_controller, encode_controller, sample_digest
from src.probe.physical_reprobe_v1 import Start, StepReceipt, _digest, _ended

METHODS = ("DIRECT_C8", "MOVE_KEEP_C8", "MOVE_INTEGRAL", "MOVE_ARX_KEEP")
TOTAL_STEPS, MOVE_LIMIT, TASK_RESERVE = 500, 64, 100
SCOPE = "LOCAL_PID_THEN_SAVED_REFERENCE_TASK_V1"


class MovementTaskFailure(RuntimeError):
    def __init__(self, record):
        super().__init__(record["error"]["message"])
        self.record = record


def validate_estimate(estimate, history, reference):
    """Reject stale/malformed results; this does not qualify the dynamics model."""
    expected = {"method": ESTIMATE_METHOD, "scope": HISTORY_SCOPE, "history_sha256": history.sha256,
        "model_sha256": reference.model_sha256, "decision_step": history.decision_step,
        "movement_responses": len(history.transitions), "physical_response_qualified": False,
        "task_utility_demonstrated": False, "probability_guarantee": False}
    if (type(estimate) is not dict or set(estimate) != set(expected) | {"status", "fit", "fit_attempts", "optimizer_nfev"}
            or _digest({k: estimate[k] for k in expected}) != _digest(expected)
            or type(estimate["optimizer_nfev"]) is not int or estimate["optimizer_nfev"] < 0
            or type(estimate["fit_attempts"]) is not int or estimate["fit_attempts"] != 1
            or estimate["status"] not in ("VALID_WORKING_ESTIMATE", "INVALID_ESTIMATE")):
        raise ValueError("estimate must refer to the saved current history and bound task model")
    fit = estimate["fit"]
    required = {"valid", "samples", "sample_digest", "physical_response_qualified", "probability_guarantee", "research_simulation_only", "reason"}
    design = {"design_rank", "scaled_condition"}
    estimated = {"matrix_xy", "bias_xy", "residual_rmse_m", "singular_values", "selected_start"}
    schemas = {"INSUFFICIENT_SAMPLES": required, "MISSING_OR_ILL_CONDITIONED_INPUT_SUPPORT": required | design,
        "OPTIMIZER_OR_PARAMETER_DOMAIN_FAILURE": required | design | {"optimizer_trials"},
        "UNSTABLE_ESTIMATED_INVERSE": required | design | {"optimizer_trials"} | estimated,
        "POINT_FORWARD_PREDICTION_ERROR_FIT": required | design | {"optimizer_trials"} | estimated}
    if (type(fit) is not dict or type(fit.get("reason")) is not str or set(fit) != schemas.get(fit.get("reason"))
            or type(fit.get("valid")) is not bool
            or fit["valid"] != (estimate["status"] == "VALID_WORKING_ESTIMATE")
            or fit["valid"] != (fit["reason"] == "POINT_FORWARD_PREDICTION_ERROR_FIT")
            or type(fit["samples"]) is not int or fit["samples"] != len(history.transitions)
            or fit["sample_digest"] != sample_digest(operator_samples(history))
            or fit["physical_response_qualified"] is not False or fit["probability_guarantee"] is not False
            or fit["research_simulation_only"] is not True
            or estimate["optimizer_nfev"] != sum(t["nfev"] for t in fit.get("optimizer_trials", []))):
        raise ValueError("estimate status or optimizer cost differs from its fit")
    for trial in fit.get("optimizer_trials", []):
        if (type(trial) is not dict or set(trial) != {"parameters", "success", "nfev", "start", "residual_rmse_m"}
                or type(trial["nfev"]) is not int or not 0 <= trial["nfev"] <= 64
                or type(trial["success"]) is not bool):
            raise ValueError("unknown optimizer trial fields or costs")
    if fit["valid"]:
        matrix = np.asarray(fit["matrix_xy"], dtype=float)
        bias = np.asarray(fit["bias_xy"], dtype=float)
        if (matrix.shape != (2, 2) or bias.shape != (2,) or not np.isfinite(matrix).all()
                or not np.isfinite(bias).all() or np.max(abs(matrix)) > 2+1e-12 or np.max(abs(bias)) > .3+1e-12):
            raise ValueError("estimate outside registered parameter bounds")
        singular = np.linalg.svd(matrix, compute_uv=False)
        if singular[-1] < .25 or singular[0] > 4:
            raise ValueError("unstable estimated inverse")


def run_movement_task(start, context, *, method, reference, policy, step, emit):
    if type(start) is not Start or method not in METHODS or not all(callable(f) for f in (policy, step, emit)):
        raise ValueError("registered movement task and actual host callbacks required")
    empty_history = MovementHistoryV1(start.task, start.completed_steps, start.completed_steps, context, ())
    if empty_history.current != start.current:
        raise ValueError("context must end at the actual starting observation")
    if method == "MOVE_ARX_KEEP":
        if type(reference) is not BoundMovementModelV1 or reference.task != start.task:
            raise ValueError("matching frozen task model required before movement")
        reference.decoded()
    elif reference is not None:
        raise ValueError("non-ARX reference must not receive a fitted response model")
    if method != "DIRECT_C8" and TOTAL_STEPS-start.completed_steps < MOVE_LIMIT+TASK_RESERVE:
        raise ValueError("reserve full movement and subsequent task budget before entry")
    current, calls = start.current, start.completed_steps
    anchor = selected_anchor(start, "LOCAL_PID")
    original = {"source": "ESTIMATED_AFFINE", "matrix_xy": [list(r) for r in start.correction_xy],
                "offset": [*start.offset_xy, 0., 0.]}
    record = {"method": method, "scope": SCOPE, "start": asdict(start), "context": asdict(empty_history)["context"],
              "events": [], "trace": [], "fit": None, "history": None, "relocation_evidence": None}
    sequence, saved_ns = None, -1
    move_rows, movement_observations = [], [current.observation]
    integral = [0., 0.]
    queries = fit_attempts = fit_results = optimizer_nfev = 0
    task_choice = None

    def save(kind, payload):
        nonlocal sequence, saved_ns
        expected = deepcopy(payload)
        saved = emit(kind, deepcopy(payload))
        if (type(saved) is not dict or set(saved) != set(expected) | {"sequence", "saved_ns"}
                or _digest({k: saved[k] for k in expected}) != _digest(expected)
                or type(saved["sequence"]) is not int or saved["sequence"] < 0
                or (sequence is not None and saved["sequence"] != sequence+1)
                or type(saved["saved_ns"]) is not int or not saved_ns <= saved["saved_ns"] <= perf_counter_ns()):
            raise ValueError("saved acknowledgement changed values or chronology")
        sequence, saved_ns = saved["sequence"], saved["saved_ns"]
        result = deepcopy(saved)
        record["events"].append({"kind": kind, "payload": result})
        return result

    def act(command, phase, decision, raw=None):
        nonlocal current, calls
        if _ended(current) or calls >= TOTAL_STEPS or (phase == "REPOSITION" and calls >= TOTAL_STEPS-TASK_RESERVE):
            raise ValueError("ended or exhausted movement/task execution")
        before = current
        intent = save("COMMAND", {"at_calls": calls, "decision_sequence": decision["sequence"], "phase": phase,
                                  "before": asdict(current), "command": command, "raw_policy": raw})
        supplied = deepcopy(intent)
        receipt = step(supplied)
        if _digest(supplied) != _digest(intent) or type(receipt) is not StepReceipt or receipt.completed_steps != calls+1:
            raise ValueError("host changed saved command or actual step count")
        current, calls = receipt.current, receipt.completed_steps
        result = save("STEP_RESULT", {"at_calls": calls, "command_sequence": intent["sequence"], "after": asdict(current)})
        record["trace"].append({"phase": phase, "completed_step": calls, "decision_sequence": decision["sequence"],
            "command_sequence": intent["sequence"], "result_sequence": result["sequence"],
            "command": deepcopy(intent["command"]), "before": asdict(before), "after": asdict(current), "raw_policy": raw})
        if phase == "REPOSITION":
            move_rows.append(MovementTransitionV1(calls, intent["command"], before, current))
            movement_observations.append(current.observation)

    try:
        entry = save("MOVEMENT_TASK_CHOICE", {"at_calls": calls, "method": method, "scope": SCOPE,
            "start": asdict(start), "context": record["context"], "anchor": list(anchor),
            "maximum_reposition_steps": MOVE_LIMIT if method != "DIRECT_C8" else 0,
            "task_reserve": TASK_RESERVE, "total_steps": TOTAL_STEPS,
            "model_sha256": reference.model_sha256 if reference is not None else None})
        learned = None
        if method != "DIRECT_C8":
            lifted = current.observation[2] >= anchor[2]-.015
            while not _ended(current) and len(move_rows) < MOVE_LIMIT and not anchor_ready(movement_observations, anchor):
                updated, command = control_update(start, movement_observations, lifted, integral, "LOCAL_PID")
                save("INTEGRAL_UPDATE", {"at_calls": calls, "integral_before": integral, "integral_after": updated})
                act(command, "REPOSITION", entry)
                integral = updated
                lifted = lifted or current.observation[2] >= anchor[2]-.015
            learned = save("RELOCATION_EVIDENCE", {"at_calls": calls,
                **relocation_evidence(start, integral, anchor_ready(movement_observations, anchor))})
            record["relocation_evidence"] = learned
            history = MovementHistoryV1(start.task, start.completed_steps, calls, context, tuple(move_rows))
            snapshot = save("MOVEMENT_HISTORY", {"at_calls": calls, "history": history.to_dict(), "history_sha256": history.sha256})
            record["history"] = snapshot
        if _ended(current):
            task_choice = save("MOVEMENT_TASK_DECISION", {"at_calls": calls, "action": "ENDED_NO_UPDATE",
                                                         "controller": None, "fit_result_sequence": None})
        else:
            controller, action, fit_sequence = original, "RUN_SAVED_C8", None
            if method == "MOVE_INTEGRAL":
                controller = {**deepcopy(learned["controller"]), "source": "ESTIMATED_AFFINE"}
                action = "RUN_SAVED_INTEGRAL"
            elif method == "MOVE_ARX_KEEP":
                # Consume the acknowledged snapshot, not a freshly reconstructed
                # history or observations obtained after this decision time.
                snapshot_history = MovementHistoryV1.from_mapping(snapshot["history"])
                save("MOVEMENT_FIT_INTENT", {"at_calls": calls, "history_sequence": snapshot["sequence"],
                    "history_sha256": snapshot_history.sha256, "model_sha256": reference.model_sha256})
                fit_attempts += 1
                estimate = estimate_bound_movement(reference, snapshot_history)
                validate_estimate(estimate, snapshot_history, reference)
                fitted = save("MOVEMENT_FIT_RESULT", {"at_calls": calls, "history_sequence": snapshot["sequence"], "estimate": estimate})
                fit_results += 1
                record["fit"] = fitted
                estimate = fitted["estimate"]
                optimizer_nfev += estimate["optimizer_nfev"]
                fit_sequence = fitted["sequence"]
                if estimate["status"] == "VALID_WORKING_ESTIMATE":
                    fit = estimate["fit"]
                    controller = affine_controller(fit["matrix_xy"], fit["bias_xy"])
                    action = "RUN_SAVED_ARX"
                else:
                    action = "REJECT_ARX_KEEP_SAVED_C8"
            task_choice = save("MOVEMENT_TASK_DECISION", {"at_calls": calls, "action": action,
                "controller": controller, "fit_result_sequence": fit_sequence})
            while not _ended(current) and calls < TOTAL_STEPS:
                queries += 1
                raw = np.asarray(policy(np.array(current.observation, dtype=float, copy=True)), np.float32).tolist()
                command = encode_controller(task_choice["controller"], raw).tolist()
                act(command, "TASK_AFTER_MOVEMENT", task_choice, raw)
        outcome = {"success": current.success, "total_steps": calls, "new_steps": calls-start.completed_steps,
            "deadline_loss": calls if current.success else TOTAL_STEPS, "reposition_steps": len(move_rows),
            "task_steps": len(record["trace"])-len(move_rows), "policy_queries": queries,
            "fit_attempts": fit_attempts, "fit_results": fit_results, "optimizer_nfev": optimizer_nfev,
            "anchor_reached": False if learned is None else learned["at_anchor"],
            "action": task_choice["action"], "physical_response_qualified": False,
            "task_utility_demonstrated": False, "probability_guarantee": False}
        record["outcome"] = outcome
        save("MOVEMENT_TASK_OUTCOME", {"at_calls": calls, "outcome": outcome, "final": asdict(current)})
        return record
    except BaseException as error:
        record.update(error={"type": type(error).__name__, "message": str(error)}, completed_steps=calls,
                      partial_current=asdict(current), policy_queries=queries, fit_attempts=fit_attempts,
                      fit_results=fit_results, optimizer_nfev=optimizer_nfev,
                      optimizer_nfev_complete=fit_attempts == fit_results)
        raise MovementTaskFailure(record) from error
