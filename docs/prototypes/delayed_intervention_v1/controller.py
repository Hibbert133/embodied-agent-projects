"""Isolated execution prototype: one saved intervention at a live boundary.

No acquisition model, detector, simulation factory, reset or RNG API is exposed.
The host remains responsible for truthful receipts and durable journal writes.
This module is not imported by the frozen MAIN experiment.
"""

from dataclasses import asdict, dataclass
from copy import deepcopy
import hashlib
import json
import math

import numpy as np

from src.probe.continuous import StepObservation
from src.probe.operator_identification import encode_controller


TOTAL_BUDGET = 500
TASKS = ("push-v3", "reach-v3", "door-open-v3")
ACTIONS = ("CONTINUE_CURRENT", "SWITCH_SAVED", "RUN_UNCORRECTED", "STOP")


def _exact_keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("strict public schema required")


def _vector(value, size):
    if type(value) not in (list, tuple) or len(value) != size:
        raise ValueError("fixed-size numeric sequence required")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError("finite ordinary numbers required")
    return tuple(float(x) for x in value)


def _observation(value):
    if type(value) is not StepObservation or len(value.observation) != 39:
        raise ValueError("exact visible observation required")
    _vector(value.observation, 39)
    return value


def _ended(value):
    return value.success or value.terminated or value.truncated


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ControllerSnapshot:
    matrix_xy: tuple
    offset_xy: tuple

    def __post_init__(self):
        if type(self.matrix_xy) not in (list, tuple) or len(self.matrix_xy) != 2:
            raise ValueError("finite 2x2 correction required")
        object.__setattr__(self, "matrix_xy", tuple(_vector(row, 2) for row in self.matrix_xy))
        object.__setattr__(self, "offset_xy", _vector(self.offset_xy, 2))

    @classmethod
    def from_mapping(cls, value):
        _exact_keys(value, ("matrix_xy", "offset_xy"))
        return cls(value["matrix_xy"], value["offset_xy"])

    def command_mapping(self):
        return {"source": "ESTIMATED_AFFINE", "matrix_xy": [list(row) for row in self.matrix_xy],
                "offset": [*self.offset_xy, 0., 0.]}


@dataclass(frozen=True)
class Boundary:
    task: str
    completed_steps: int
    current: StepObservation
    current_controller: ControllerSnapshot
    saved_controller: ControllerSnapshot | None = None

    def __post_init__(self):
        if type(self.task) is not str or self.task not in TASKS:
            raise ValueError("registered task required")
        if type(self.completed_steps) is not int or not 0 <= self.completed_steps <= TOTAL_BUDGET:
            raise ValueError("valid already-consumed step count required")
        _observation(self.current)
        if type(self.current_controller) is not ControllerSnapshot:
            raise ValueError("strict current correction required")
        if self.saved_controller is not None and type(self.saved_controller) is not ControllerSnapshot:
            raise ValueError("strict saved correction or None required")

    @classmethod
    def from_mapping(cls, value):
        _exact_keys(value, ("task", "completed_steps", "current", "current_controller", "saved_controller"))
        obs = value["current"]
        _exact_keys(obs, ("observation", "terminated", "truncated", "success"))
        # Reject booleans and nested values before the legacy observation constructor.
        _vector(obs["observation"], 39)
        return cls(value["task"], value["completed_steps"], StepObservation(**obs),
                   ControllerSnapshot.from_mapping(value["current_controller"]),
                   None if value["saved_controller"] is None else ControllerSnapshot.from_mapping(value["saved_controller"]))


@dataclass(frozen=True)
class StepReceipt:
    before: StepObservation
    command: tuple
    after: StepObservation
    completed_steps: int

    def __post_init__(self):
        _observation(self.before)
        _observation(self.after)
        object.__setattr__(self, "command", _vector(self.command, 4))
        if type(self.completed_steps) is not int or not 0 <= self.completed_steps <= TOTAL_BUDGET:
            raise ValueError("valid physical ledger count required")


class ExecutionFailure(RuntimeError):
    def __init__(self, reason, snapshot):
        super().__init__(reason)
        self.reason = reason
        self.snapshot = deepcopy(snapshot)


class SingleIntervention:
    """Single-use executor. Callback faults abort without retries or substitution."""

    def __init__(self, boundary, *, policy, step, emit):
        if type(boundary) is not Boundary or not all(callable(x) for x in (policy, step, emit)):
            raise ValueError("strict boundary and three callbacks required")
        self.boundary = boundary
        self._policy, self._step, self._emit = policy, step, emit
        self._current = boundary.current
        self._completed = boundary.completed_steps
        self._attempts = self._accepted = self._queries = self._query_completed = 0
        self._events = []
        self._sequence = self._saved_ns = -1
        self._spent = False
        self._status, self._failure = "READY", None
        self._choice = None

    def available_actions(self):
        if self._spent:
            return ()
        if _ended(self._current) or self._completed == TOTAL_BUDGET:
            return ("STOP",)
        return tuple(x for x in ACTIONS if x != "SWITCH_SAVED" or self.boundary.saved_controller is not None)

    def snapshot(self):
        charged = self.boundary.completed_steps + self._attempts
        return deepcopy({"status": self._status, "failure": self._failure,
                         "initial_completed_steps": self.boundary.completed_steps,
                         "completed_steps": self._completed, "charged_steps": charged,
                         "remaining_budget": TOTAL_BUDGET - charged,
                         "step_attempts": self._attempts, "accepted_step_receipts": self._accepted,
                         "unconfirmed_step_attempts": self._attempts - self._accepted,
                         "policy_queries_attempted": self._queries, "policy_queries_completed": self._query_completed,
                         "last_confirmed_observation": asdict(self._current), "choice": self._choice,
                         "success": self._current.success,
                         "deadline_loss": self._completed if self._current.success else TOTAL_BUDGET,
                         "events": self._events})

    def _fail(self, reason):
        self._status, self._failure = "FAILED", reason
        raise ExecutionFailure(reason, self.snapshot())

    def _save(self, kind, payload):
        expected = json.loads(json.dumps(payload, allow_nan=False))
        try:
            saved = self._emit(kind, deepcopy(expected))
        except Exception:
            self._fail("JOURNAL_CALLBACK_FAILED")
        try:
            valid = (type(saved) is dict and set(saved) == set(expected) | {"sequence", "saved_ns"}
                     and _digest({k: saved[k] for k in expected}) == _digest(expected)
                     and type(saved["sequence"]) is int and saved["sequence"] == self._sequence + 1
                     and type(saved["saved_ns"]) is int and saved["saved_ns"] >= 0 and saved["saved_ns"] >= self._saved_ns)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            self._fail("JOURNAL_ACK_MISMATCH")
        # Detach from callback-owned dictionaries before any later callback runs.
        stored = deepcopy(saved)
        self._sequence, self._saved_ns = stored["sequence"], stored["saved_ns"]
        self._events.append({"kind": kind, "payload": deepcopy(stored)})
        return stored

    def execute(self, action_id):
        if self._spent:
            raise ValueError("single intervention already consumed")
        if type(action_id) is not str or action_id not in self.available_actions():
            raise ValueError("unavailable intervention")
        # Consumed before user callbacks: exceptions and reentrant calls cannot retry.
        self._spent, self._status = True, "SELECTED"
        catalog = {"CONTINUE_CURRENT": self.boundary.current_controller.command_mapping(),
                   "RUN_UNCORRECTED": {"source": "UNCORRECTED", "matrix_xy": [[1., 0.], [0., 1.]], "offset": [0., 0., 0., 0.]},
                   "STOP": None}
        if self.boundary.saved_controller is not None:
            catalog["SWITCH_SAVED"] = self.boundary.saved_controller.command_mapping()
        available = ("STOP",) if _ended(self._current) or self._completed == TOTAL_BUDGET else tuple(x for x in ACTIONS if x in catalog)
        catalog = {name: catalog[name] for name in available}
        saved = self._save("CHOICE", {"action_id": action_id, "at_calls": self._completed,
                                      "boundary_observation": asdict(self._current), "task": self.boundary.task,
                                      "remaining_budget": TOTAL_BUDGET - self._completed,
                                      "candidate_map": catalog, "candidate_map_sha256": _digest(catalog)})
        self._choice = deepcopy(saved)
        # This exact acknowledged candidate drives every executed command.
        selected = deepcopy(saved["candidate_map"][saved["action_id"]])
        if selected is None:
            self._status = "COMPLETED" if _ended(self._current) or self._completed == TOTAL_BUDGET else "STOPPED"
            return self.snapshot()
        self._status = "RUNNING"
        while not _ended(self._current) and self.boundary.completed_steps + self._attempts < TOTAL_BUDGET:
            before = self._current
            self._queries += 1
            try:
                raw = np.asarray(self._policy(np.array(before.observation, dtype=float, copy=True)))
                if raw.shape != (4,) or raw.dtype.kind not in "fiu" or not np.isfinite(raw).all():
                    raise ValueError("finite numeric policy action required")
                with np.errstate(over="raise", invalid="raise"):
                    raw32 = np.asarray(raw, dtype=np.float32)
                    command = encode_controller(deepcopy(selected), raw32).tolist()
                if not np.isfinite(command).all() or any(abs(x) > 1 for x in command):
                    raise ValueError("invalid bounded command")
            except Exception:
                self._fail("POLICY_OR_COMMAND_INVALID")
            self._query_completed += 1
            approved = self._save("COMMAND", {"at_calls": self._completed, "decision_sequence": saved["sequence"],
                                               "command": command, "raw_policy": raw32.tolist(),
                                               "before": asdict(before)})
            # Charge the attempt before invoking a possibly partially executing host.
            self._attempts += 1
            try:
                receipt = self._step(deepcopy(approved))
            except Exception:
                self._fail("STEP_CALLBACK_FAILED")
            if (type(receipt) is not StepReceipt or receipt.before != before
                    or receipt.command != tuple(approved["command"])
                    or receipt.completed_steps != self._completed + 1):
                self._fail("STEP_RECEIPT_MISMATCH")
            self._accepted += 1
            self._completed = receipt.completed_steps
            self._current = receipt.after
            self._save("STEP_RESULT", {"command_sequence": approved["sequence"],
                                       "at_calls": self._completed, "after": asdict(self._current)})
        self._status = "COMPLETED"
        return self.snapshot()
