"""Read a bounded public movement prefix from an independently audited case.

Private case containers are host-side only. Only declared public observations
and requested commands enter MovementHistoryV1; no estimator runs here.
"""

from dataclasses import asdict

from src.probe.local_reprobe_v1 import METHODS, SCOPE, PROGRAM
from src.probe.movement_history_reference_v1 import (
    MovementHistoryV1, MovementTransitionV1, parse_observation,
)
from src.probe.physical_reprobe_v1 import Start, _digest, _keys, _vector


def require(ok, message):
    if not ok:
        raise ValueError(message)


def extract_movement(case):
    """The caller must bind the original closed manifest, records and audit.

    Reads nothing after the first saved RELOCATION_EVIDENCE. This is an archive
    adapter, not proof that arbitrary supplied rows came from a real robot.
    """
    if case["reacquisition"] is None:
        require(case["boundary_ready"] is False, "missing actual movement operation")
        return None, {"status": "NO_MOVEMENT_OPERATION", "responses": 0}
    events = case["reacquisition"]["public"]["events"]
    require(type(events) is list and bool(events), "saved public events required")
    _keys(events[0], ("kind", "payload"))
    require(events[0]["kind"] == "REACQUIRE_CHOICE", "movement choice must come first")
    choice = events[0]["payload"]
    _keys(choice, ("sequence", "saved_ns", "at_calls", "start", "scope", "anchor", "maximum_reposition_steps",
                   "task_reserve", "probe_program", "relocation_method", "integral_gain", "integral_limit"))
    start = Start.from_mapping(choice["start"])
    require(start.task == case["task"] and choice["at_calls"] == start.completed_steps, "wrong public starting state")
    require(choice["scope"] == SCOPE and choice["relocation_method"] in METHODS
            and choice["maximum_reposition_steps"] == 64 and choice["task_reserve"] == 100
            and choice["probe_program"] == [list(v) for v in PROGRAM], "different movement operation")
    require(choice["integral_gain"] == (.32 if choice["relocation_method"].endswith("_PID") else 0.)
            and choice["integral_limit"] == .5, "different public controller specification")
    _vector(choice["anchor"], 3)
    physical = case["physical_rows"]
    context = []
    for step in range(start.completed_steps-2, start.completed_steps+1):
        row = physical[step-1]
        # Host logical_step is the zero-based pre-step clock; after is at +1.
        require(row["logical_step"] == step-1, "prior observation clock changed")
        context.append(parse_observation(row["after"]))
    require(context[-1] == start.current, "context does not end at actual movement start")
    transitions, prefix = [], []
    pending = None
    previous_clock = -1
    sequence = choice["sequence"]
    require(type(sequence) is int and sequence >= 0, "actual event sequence required")
    current, calls = start.current, start.completed_steps
    for event in events:
        _keys(event, ("kind", "payload"))
        kind, payload = event["kind"], event["payload"]
        require(type(payload["sequence"]) is int and payload["sequence"] == sequence, "public sequence gap")
        require(type(payload["saved_ns"]) is int and payload["saved_ns"] >= previous_clock, "public clock reversed")
        require(type(payload["at_calls"]) is int and payload["at_calls"] == calls + int(kind == "STEP_RESULT"), "public step changed")
        sequence += 1
        previous_clock = payload["saved_ns"]
        prefix.append(event)
        if kind == "REACQUIRE_CHOICE":
            require(len(prefix) == 1, "duplicate movement choice")
        elif kind == "INTEGRAL_UPDATE":
            _keys(payload, ("sequence", "saved_ns", "at_calls", "integral_before", "integral_after"))
            require(pending is None, "update before command completion")
            for name in ("integral_before", "integral_after"):
                require(max(abs(x) for x in _vector(payload[name], 2)) <= .5, "invalid saved integral")
        elif kind == "COMMAND":
            _keys(payload, ("sequence", "saved_ns", "at_calls", "decision_sequence", "phase", "before", "command", "raw_policy"))
            require(pending is None and payload["phase"] == "REPOSITION"
                    and payload["decision_sequence"] == choice["sequence"] and payload["raw_policy"] is None,
                    "non-movement, duplicate or foreign command")
            require(parse_observation(payload["before"]) == current, "command before observation changed")
            pending = payload
        elif kind == "STEP_RESULT":
            _keys(payload, ("sequence", "saved_ns", "at_calls", "command_sequence", "after"))
            require(pending is not None and payload["command_sequence"] == pending["sequence"], "result lacks matching intent")
            after = parse_observation(payload["after"])
            transition = MovementTransitionV1(calls+1, pending["command"], current, after)
            row = physical[calls]
            require(row["logical_step"] == calls and row["phase"] == "REPOSITION"
                    and _vector(row["command"], 4) == transition.command and parse_observation(row["after"]) == after,
                    "public movement differs from actual recorded command/result")
            require(pending["saved_ns"] <= row["execution_started_ns"] <= row["completed_ns"] <= payload["saved_ns"],
                    "intent/execution/result time order differs")
            transitions.append(transition)
            calls, current, pending = calls+1, after, None
        elif kind == "RELOCATION_EVIDENCE":
            _keys(payload, ("sequence", "saved_ns", "at_calls", "integral_xy", "at_anchor", "controller",
                           "parameter_estimate_qualified", "task_utility_demonstrated"))
            require(pending is None and type(payload["at_anchor"]) is bool
                    and payload["parameter_estimate_qualified"] is False and payload["task_utility_demonstrated"] is False,
                    "unfinished or relabeled movement evidence")
            _vector(payload["integral_xy"], 2)
            controller = payload["controller"]
            _keys(controller, ("source", "matrix_xy", "offset"))
            require(controller["source"] == "RELOCATION_INTEGRAL_REFERENCE" and len(controller["matrix_xy"]) == 2,
                    "wrong saved integral reference")
            for row in controller["matrix_xy"]:
                _vector(row, 2)
            _vector(controller["offset"], 4)
            history = MovementHistoryV1(start.task, start.completed_steps, calls, tuple(context), tuple(transitions))
            return history, {"status": "SEALED_BEFORE_PROBE", "responses": len(transitions),
                "start_step": start.completed_steps, "decision_step": calls,
                "evidence_sequence": payload["sequence"], "evidence_saved_ns": payload["saved_ns"],
                "public_prefix_sha256": _digest(prefix), "history_sha256": history.sha256,
                "context_observation_sha256": _digest([asdict(v) for v in context])}
        else:
            raise ValueError("probe, future or unknown event before movement cutoff")
    raise ValueError("no sealed movement evidence")
