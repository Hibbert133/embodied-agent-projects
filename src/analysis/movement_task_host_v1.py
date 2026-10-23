"""Continuous live host for the four saved movement/task references.

The evaluator owns environment, noise, source journal and reset ledger. Only
visible observation history and a task-bound nominal model reach the actor.
"""
from copy import deepcopy
from dataclasses import asdict

import numpy as np

from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.movement_task_record_v1 import MovementTaskMonitor, public_observation, require, same
from src.analysis.paired_probe_host_v1 import ProbeSession, original_noise
from src.probe.movement_model_binding_v1 import BoundMovementModelV1
from src.probe.movement_task_reference_v1 import METHODS, MovementTaskFailure, run_movement_task
from src.probe.operator_identification import affine_controller, encode_controller
from src.probe.physical_reprobe_v1 import Start, StepReceipt, _digest


class MovementHostFailure(RuntimeError):
    def __init__(self, record):
        super().__init__(record["error"]["message"]);self.record = record


def execute_movement_task(session, current_choice_sequence, lookup, *, reset_before, method, reference=None):
    require(type(session) is ProbeSession and callable(lookup) and method in METHODS, "registered live host and method required")
    require(not getattr(session, "_movement_task_consumed", False)
            and not getattr(session, "_physical_reprobe_consumed", False), "movement operation already consumed")
    require(session.alive() and 9 <= session.ctx["calls"] <= 336 and session._pending is None,
            "live boundary after an actually applied correction required")
    require(not session.captures and not session.restores and not session._snapshots,
            "source with no simulator copy or restoration required")
    require(session.ctx["calls"] == session.attempts == session.completed == len(session.last_rows), "source physical history incomplete")
    require((reference is None and method != "MOVE_ARX_KEEP") or
            (type(reference) is BoundMovementModelV1 and method == "MOVE_ARX_KEEP" and reference.task == session.task),
            "task model access differs from admitted method")
    ledger_before = session.ledger.snapshot()
    require(type(reset_before) is dict and set(reset_before) == {"counts", "by_phase"}, "actual per-case pre-reset ledger required")
    for field in ("reset_attempts", "reset_completed"):
        all_delta = ledger_before["counts"].get(field, 0)-reset_before["counts"].get(field, 0)
        controlled_delta = (ledger_before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0)
            -reset_before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0))
        require(all_delta == controlled_delta == 1, "one actual per-case controlled reset required")

    def saved_public(local, kind):
        require(type(local) is int and local in session._map, "unknown saved public reference")
        row = deepcopy(lookup(session._map[local]))
        require(row["event"] == "AGENT_EVENT" and row["agent_event"] == kind
                and row["public_payload"]["sequence"] == local, "source journal kind differs")
        return row["public_payload"]

    choice = saved_public(current_choice_sequence, "CHOICE")
    require(choice["action"] == "RUN_FITTED" and choice["purpose"] == "CURRENT_POLICY_CONTROLLER"
            and choice["fitted_prefix_steps"] == choice["at_calls"] == 8, "saved cold-eight correction required")
    fitted = saved_public(choice["fit_sequence"], "FIT_RESULT")
    require(fitted["at_calls"] == 8 and fitted["fit"]["valid"] is True, "valid saved cold-eight fit required")
    same(choice["controller"], affine_controller(fitted["fit"]["matrix_xy"], fitted["fit"]["bias_xy"]), "source differs from saved valid fit")
    last = session.last_rows[-1];last_command = deepcopy(lookup(last["global_command_sequence"]))
    require(last_command["event"] == "AGENT_EVENT" and last_command["agent_event"] == "COMMAND"
            and last_command["public_payload"]["phase"] == "POLICY"
            and last_command["public_payload"]["decision_sequence"] == current_choice_sequence,
            "selected source is not the last actually applied correction")
    same(last_command["public_payload"]["command"], last["command"], "last physical command differs")
    require(session._map[choice["fit_sequence"]] < session._map[current_choice_sequence] < last["global_command_sequence"],
            "source fit and choice must precede physical use")
    require(last_command["public_payload"]["raw_policy"] is not None and np.array_equal(
        encode_controller(choice["controller"], last_command["public_payload"]["raw_policy"]), np.asarray(last["command"], np.float32)),
        "last command did not apply source correction")
    same(last["after"], asdict(session.public()), "source observation differs from last physical receipt")
    context = []
    for index in range(session.ctx["calls"]-3, session.ctx["calls"]):
        row = session.last_rows[index]
        require(row["logical_step"] == index and row["noise_cursor_after"] == index+1, "source context lacks chronological physical receipts")
        context.append(public_observation(row["after"]))
    context = tuple(context)
    start = Start(session.task, session.ctx["calls"], session.public(), choice["controller"]["matrix_xy"], choice["controller"]["offset"][:2])
    monitor = MovementTaskMonitor(start, context, method, reference)
    budget = session.run_budget
    require(type(budget["completed"]) is int and type(budget["maximum"]) is int
            and budget["maximum"]-budget["completed"] >= 500-start.completed_steps, "reserve full remaining task in whole-study budget")
    tape = session.ctx["noise_rows"]
    require(not tape.flags.writeable and np.array_equal(tape, original_noise(session.seed)), "original noise tape required")
    base = session.env.unwrapped;addresses = (base.model._address, base.data._address)
    clock_before = float(base.data.time);budget_before = budget["completed"];queries_before = session.policy_queries
    source_before = _digest(normalize((session.ctx["commands"], session.ctx["observations"])))
    prefix_before = _digest(session.last_rows)
    query_count = 0;pending_raw = None

    def continuous():
        require(session.env.unwrapped is base and (base.model._address, base.data._address) == addresses
                and not session.captures and not session.restores and not session._snapshots, "world replacement or simulator restoration")
        require(session.ctx["noise_rows"] is tape and not tape.flags.writeable and np.array_equal(tape, original_noise(session.seed)),
                "noise tape replaced or rewound")
        require(_digest(normalize((session.ctx["commands"], session.ctx["observations"]))) == source_before
                and _digest(session.last_rows[:start.completed_steps]) == prefix_before, "original source evidence changed")
        for key in ("reset_attempts", "reset_completed", "reset_errors"):
            require(session.ledger.counts.get(key, 0) == ledger_before["counts"].get(key, 0), "mid-operation reset")
        require(session.policy_queries == queries_before+query_count, "unexpected policy query")
        actual = session.ctx["calls"]-start.completed_steps
        require(session.ctx["calls"] == session.attempts == session.completed == len(session.last_rows)
                and budget["completed"]-budget_before == actual, "actual control cost differs")
        for key in ("simulation_frames_attempted", "simulation_frames_completed"):
            require(session.ledger.counts.get(key, 0)-ledger_before["counts"].get(key, 0) == 5*actual, "extra or unrecorded physical frame work")
        require(np.isclose(float(base.data.time)-clock_before, .0125*actual, atol=1e-9, rtol=0), "physical clock changed outside saved commands")

    def emit(kind, payload):
        continuous()
        require(session._pending is None and payload["at_calls"] == session.ctx["calls"], "stale public event")
        if kind == "STEP_RESULT":same(payload["after"], asdict(session.public()), "result differs from actual physical receipt")
        if kind == "COMMAND" and payload["phase"] == "TASK_AFTER_MOVEMENT":
            require(pending_raw is not None, "task command has no actual policy query")
            same(payload["raw_policy"], pending_raw, "task command changes actual fixed-policy query")
        saved = session._agent_emit(kind, payload)
        monitor.accept(kind, saved)  # Admitted after persistence, before any physical use.
        return saved

    def policy(observation):
        nonlocal query_count, pending_raw
        continuous()
        require(monitor.phase == "TASK_COMMAND" and pending_raw is None, "unexpected or duplicate task-policy query")
        same(np.asarray(observation).tolist(), list(session.public().observation), "policy received stale observation")
        query_count += 1
        pending_raw = session.policy_query(observation).tolist()
        continuous();return np.array(pending_raw, np.float32)

    def step(saved):
        nonlocal pending_raw
        continuous()
        require(monitor.phase == "RESULT", "physical step without admitted command")
        same(saved, monitor.pending, "physical step changed admitted saved command")
        same(saved, session._pending, "unsaved physical command")
        same(saved["before"], asdict(session.public()), "stale physical command")
        result = session._agent_step(saved)
        if saved["phase"] == "TASK_AFTER_MOVEMENT":pending_raw = None
        continuous();return StepReceipt(result, session.ctx["calls"])

    session._movement_task_consumed = True
    session.branch = {"role": "MOVEMENT_TASK", "future": 0, "program": method}
    entry = session.emit("MOVEMENT_TASK_START", {**session.branch, "at_calls": start.completed_steps,
        "source_choice_global_sequence": session._map[current_choice_sequence], "public_start": asdict(start),
        "context": [asdict(v) for v in context], "ledger": ledger_before, **session.witness()})
    try:
        result = run_movement_task(start, context, method=method, reference=reference, policy=policy, step=step, emit=emit)
        outcome = monitor.check_record(result);continuous()
        require(pending_raw is None and session._pending is None and outcome["policy_queries"] == query_count,
                "unconsumed task query or command")
        after = session.ledger.snapshot()
        end = session.emit("MOVEMENT_TASK_COMPLETE", {**session.branch, "entry_sequence": entry["sequence"],
            "result": result, "ledger": after, **session.witness()})
        return normalize({"public": result, "entry_sequence": entry["sequence"], "end_sequence": end["sequence"],
            "ledger_before": ledger_before, "ledger_after": after, "new_control_steps": outcome["new_steps"],
            "new_simulation_frames": 5*outcome["new_steps"], "new_policy_queries": query_count,
            "new_parameter_fits": outcome["fit_attempts"], "optimizer_nfev": outcome["optimizer_nfev"]})
    except BaseException as error:
        failure = {"error": {"type": type(error).__name__, "message": str(error)}, "entry_sequence": entry["sequence"],
            "public_partial": error.record if isinstance(error, MovementTaskFailure) else None,
            "ledger_before": ledger_before, "ledger_after": session.ledger.snapshot(),
            "actual_attempted_control_steps": session.attempts-start.completed_steps,
            "actual_completed_control_steps": session.completed-start.completed_steps,
            "actual_new_policy_queries": session.policy_queries-queries_before,
            "new_simulation_frames_attempted": session.ledger.counts.get("simulation_frames_attempted", 0)-ledger_before["counts"].get("simulation_frames_attempted", 0),
            "new_simulation_frames_completed": session.ledger.counts.get("simulation_frames_completed", 0)-ledger_before["counts"].get("simulation_frames_completed", 0)}
        session.emit("MOVEMENT_TASK_FAILED", normalize(failure))
        raise MovementHostFailure(normalize(failure)) from error
