"""Chronological record checker independent of the task actor's control flow.

Shares the registered numerical PID/controller definitions, but never calls the
actor or reruns an optimizer. Physical witnesses and numerical fit recomputation
are separate audit obligations; this checker alone cannot establish either.
"""
from copy import deepcopy
from dataclasses import asdict

from src.probe.continuous import StepObservation
from src.probe.local_reprobe_v1 import anchor_ready, control_update, relocation_evidence, selected_anchor
from src.probe.movement_history_reference_v1 import MovementHistoryV1, MovementTransitionV1
from src.probe.movement_model_binding_v1 import BoundMovementModelV1
from src.probe.movement_task_reference_v1 import METHODS, SCOPE, validate_estimate
from src.probe.operator_identification import affine_controller, encode_controller
from src.probe.physical_reprobe_v1 import Start, _digest, _ended


def require(ok, message):
    if not ok:raise ValueError(message)


def same(actual, expected, message):
    require(_digest(actual) == _digest(expected), message)


def public_observation(value):
    require(type(value) is dict and set(value) == {"observation", "terminated", "truncated", "success"},
            "unknown public observation fields")
    require(type(value["observation"]) in (list, tuple) and len(value["observation"]) == 39, "39 public coordinates required")
    return StepObservation(**value)


class MovementTaskMonitor:
    """Online saved-event admission and offline replay of the same public grammar."""
    def __init__(self, start, context, method, reference):
        require(type(start) is Start and method in METHODS, "registered start and method required")
        empty = MovementHistoryV1(start.task, start.completed_steps, start.completed_steps, context, ())
        require(empty.current == start.current, "actual context must end at start")
        require((reference is None) == (method != "MOVE_ARX_KEEP"), "model access differs from method")
        if reference is not None:
            require(type(reference) is BoundMovementModelV1 and reference.task == start.task, "wrong task model");reference.decoded()
        require(method == "DIRECT_C8" or start.completed_steps <= 336, "missing movement and task reserve")
        self.start, self.context, self.method, self.reference = start, context, method, reference
        self.phase = "ENTRY";self.calls = start.completed_steps;self.current = start.current
        self.sequence = None;self.saved_ns = -1;self.events = [];self.trace = [];self.transitions = []
        self.observations = [start.current.observation];self.integral = [0., 0.];self.updated = None
        self.anchor = selected_anchor(start, "LOCAL_PID");self.lifted = start.current.observation[2] >= self.anchor[2]-.015
        self.original = {"source": "ESTIMATED_AFFINE", "matrix_xy": [list(r) for r in start.correction_xy],
                         "offset": [*start.offset_xy, 0., 0.]}
        self.entry = self.learned = self.snapshot = self.fitted = self.decision = self.pending = None
        self.history = None;self.queries = 0;self.outcome = None

    def moving(self):
        return not _ended(self.current) and len(self.transitions) < 64 and not anchor_ready(self.observations, self.anchor)

    def task_decision(self):
        action, controller, fit_seq = "RUN_SAVED_C8", self.original, None
        if _ended(self.current):action, controller = "ENDED_NO_UPDATE", None
        elif self.method == "MOVE_INTEGRAL":
            action = "RUN_SAVED_INTEGRAL";controller = {**deepcopy(self.learned["controller"]), "source": "ESTIMATED_AFFINE"}
        elif self.method == "MOVE_ARX_KEEP":
            estimate = self.fitted["estimate"];fit_seq = self.fitted["sequence"]
            if estimate["status"] == "VALID_WORKING_ESTIMATE":
                action = "RUN_SAVED_ARX";controller = affine_controller(estimate["fit"]["matrix_xy"], estimate["fit"]["bias_xy"])
            else:action = "REJECT_ARX_KEEP_SAVED_C8"
        return {"at_calls": self.calls, "action": action, "controller": controller, "fit_result_sequence": fit_seq}

    def accept(self, kind, saved):
        require(type(saved) is dict and type(saved.get("sequence")) is int and saved["sequence"] >= 0
                and (self.sequence is None or saved["sequence"] == self.sequence+1)
                and type(saved.get("saved_ns")) is int and saved["saved_ns"] >= self.saved_ns,
                "event sequence or time is not chronological")
        payload = {k: v for k, v in saved.items() if k not in ("sequence", "saved_ns")}
        require(type(payload.get("at_calls")) is int, "ordinary absolute step count required")
        expected_kind = {"ENTRY": "MOVEMENT_TASK_CHOICE", "UPDATE": "INTEGRAL_UPDATE",
            "MOVE_COMMAND": "COMMAND", "TASK_COMMAND": "COMMAND", "RESULT": "STEP_RESULT",
            "EVIDENCE": "RELOCATION_EVIDENCE", "HISTORY": "MOVEMENT_HISTORY", "FIT_INTENT": "MOVEMENT_FIT_INTENT",
            "FIT_RESULT": "MOVEMENT_FIT_RESULT", "DECISION": "MOVEMENT_TASK_DECISION", "OUTCOME": "MOVEMENT_TASK_OUTCOME"}.get(self.phase)
        require(kind == expected_kind, "unexpected event for phase " + self.phase)
        if self.phase == "ENTRY":
            same(payload, {"at_calls": self.calls, "method": self.method, "scope": SCOPE, "start": asdict(self.start),
                "context": [asdict(v) for v in self.context], "anchor": list(self.anchor),
                "maximum_reposition_steps": 0 if self.method == "DIRECT_C8" else 64, "task_reserve": 100,
                "total_steps": 500, "model_sha256": None if self.reference is None else self.reference.model_sha256}, "entry differs")
            self.entry = deepcopy(saved);self.phase = "DECISION" if self.method == "DIRECT_C8" else "UPDATE"
        elif self.phase == "UPDATE":
            require(self.moving(), "movement after its stopping condition")
            self.updated, self.move_command = control_update(self.start, self.observations, self.lifted, self.integral, "LOCAL_PID")
            same(payload, {"at_calls": self.calls, "integral_before": self.integral, "integral_after": self.updated}, "integral update differs")
            self.phase = "MOVE_COMMAND"
        elif self.phase in ("MOVE_COMMAND", "TASK_COMMAND"):
            require(not _ended(self.current) and self.calls < 500, "command after task end or budget")
            moving = self.phase == "MOVE_COMMAND"
            if moving:
                require(self.calls < 400, "missing task reserve")
                raw, command, choice, phase = None, self.move_command, self.entry, "REPOSITION"
            else:
                raw = payload.get("raw_policy");command = encode_controller(self.decision["controller"], raw).tolist()
                choice, phase = self.decision, "TASK_AFTER_MOVEMENT";self.queries += 1
            same(payload, {"at_calls": self.calls, "decision_sequence": choice["sequence"], "phase": phase,
                "before": asdict(self.current), "command": command, "raw_policy": raw}, "command does not consume its saved decision")
            self.pending = deepcopy(saved);self.phase = "RESULT"
        elif self.phase == "RESULT":
            require(set(payload) == {"at_calls", "command_sequence", "after"}
                    and payload["at_calls"] == self.calls+1 and payload["command_sequence"] == self.pending["sequence"], "unmatched physical result")
            after = public_observation(payload["after"]);before = self.current;self.calls += 1;self.current = after
            command = self.pending
            self.trace.append({"phase": command["phase"], "completed_step": self.calls, "decision_sequence": command["decision_sequence"],
                "command_sequence": command["sequence"], "result_sequence": saved["sequence"], "command": command["command"],
                "before": asdict(before), "after": asdict(after), "raw_policy": command["raw_policy"]})
            if command["phase"] == "REPOSITION":
                self.transitions.append(MovementTransitionV1(self.calls, command["command"], before, after))
                self.observations.append(after.observation);self.integral = self.updated;self.updated = None
                self.lifted = self.lifted or after.observation[2] >= self.anchor[2]-.015
                self.phase = "UPDATE" if self.moving() else "EVIDENCE"
            else:self.phase = "OUTCOME" if _ended(after) or self.calls == 500 else "TASK_COMMAND"
            self.pending = None
        elif self.phase == "EVIDENCE":
            same(payload, {"at_calls": self.calls, **relocation_evidence(self.start, self.integral, anchor_ready(self.observations, self.anchor))}, "relocation evidence differs")
            self.learned = deepcopy(saved);self.phase = "HISTORY"
        elif self.phase == "HISTORY":
            self.history = MovementHistoryV1(self.start.task, self.start.completed_steps, self.calls, self.context, tuple(self.transitions))
            same(payload, {"at_calls": self.calls, "history": self.history.to_dict(), "history_sha256": self.history.sha256}, "history omits or changes actual movement")
            self.snapshot = deepcopy(saved)
            self.phase = "FIT_INTENT" if not _ended(self.current) and self.method == "MOVE_ARX_KEEP" else "DECISION"
        elif self.phase == "FIT_INTENT":
            same(payload, {"at_calls": self.calls, "history_sequence": self.snapshot["sequence"],
                "history_sha256": self.history.sha256, "model_sha256": self.reference.model_sha256}, "fit intent has stale evidence")
            self.phase = "FIT_RESULT"
        elif self.phase == "FIT_RESULT":
            require(set(payload) == {"at_calls", "history_sequence", "estimate"} and payload["at_calls"] == self.calls
                    and payload["history_sequence"] == self.snapshot["sequence"], "fit result has stale evidence")
            validate_estimate(payload["estimate"], self.history, self.reference)
            self.fitted = deepcopy(saved);self.phase = "DECISION"
        elif self.phase == "DECISION":
            same(payload, self.task_decision(), "task decision changes the admitted correction")
            self.decision = deepcopy(saved);self.phase = "OUTCOME" if _ended(self.current) or self.calls == 500 else "TASK_COMMAND"
        elif self.phase == "OUTCOME":
            self.outcome = {"success": self.current.success, "total_steps": self.calls, "new_steps": self.calls-self.start.completed_steps,
                "deadline_loss": self.calls if self.current.success else 500, "reposition_steps": len(self.transitions),
                "task_steps": len(self.trace)-len(self.transitions), "policy_queries": self.queries,
                "fit_attempts": int(self.fitted is not None), "fit_results": int(self.fitted is not None),
                "optimizer_nfev": 0 if self.fitted is None else self.fitted["estimate"]["optimizer_nfev"],
                "anchor_reached": False if self.learned is None else self.learned["at_anchor"],
                "action": self.decision["action"], "physical_response_qualified": False, "task_utility_demonstrated": False,
                "probability_guarantee": False}
            same(payload, {"at_calls": self.calls, "outcome": self.outcome, "final": asdict(self.current)}, "outcome or total cost differs")
            self.phase = "DONE"
        self.sequence, self.saved_ns = saved["sequence"], saved["saved_ns"]
        self.events.append({"kind": kind, "payload": deepcopy(saved)})

    def check_record(self, record):
        require(self.phase == "DONE", "incomplete public trace")
        same(record, {"method": self.method, "scope": SCOPE, "start": asdict(self.start), "context": [asdict(v) for v in self.context],
            "events": self.events, "trace": self.trace, "fit": self.fitted, "history": self.snapshot,
            "relocation_evidence": self.learned, "outcome": self.outcome}, "record differs from chronological replay")
        return deepcopy(self.outcome)


def audit_record(record, reference):
    require(type(record) is dict and type(record.get("events")) is list, "complete public record required")
    start = Start.from_mapping(record["start"])
    context = tuple(public_observation(v) for v in record["context"])
    monitor = MovementTaskMonitor(start, context, record["method"], reference)
    for row in record["events"]:
        require(type(row) is dict and set(row) == {"kind", "payload"}, "unknown event container")
        monitor.accept(row["kind"], row["payload"])
    return monitor.check_record(record)
