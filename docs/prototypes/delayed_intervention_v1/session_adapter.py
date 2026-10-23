"""Private host bridge for the isolated delayed-intervention executor.

Validates the actual session before exposing only a strict public Boundary.
The supplied lookup must read the host's immutable, already-written journal.
"""

from copy import deepcopy
from dataclasses import asdict
import hashlib
from time import perf_counter_ns

import numpy as np

from controller import Boundary, ControllerSnapshot, SingleIntervention, StepReceipt
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.paired_probe_host_v1 import ProbeSession, original_noise
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.operator_identification import encode_controller, identity_controller


def require(ok, message):
    if not ok:
        raise ValueError(message)


def tape_hash(session):
    return hashlib.sha256(session.ctx["noise_rows"].tobytes()).hexdigest()


def read_choice(session, sequence, lookup):
    require(type(sequence) is int and sequence in session._map, "earlier same-session choice reference required")
    global_sequence = session._map[sequence]
    event = lookup(global_sequence)
    require(type(event) is dict and event.get("sequence") == global_sequence and event.get("event") == "AGENT_EVENT"
            and event.get("agent_event") == "CHOICE", "reference must resolve to a saved public choice")
    public = event["public_payload"]
    require(public.get("sequence") == sequence and type(public.get("at_calls")) is int
            and 0 <= public["at_calls"] <= session.ctx["calls"], "controller was not available at the live boundary")
    require(public.get("action") in ("RUN_FITTED", "RUN_NEW", "RUN_OLD", "REJECT_KEEP_OLD", "RUN_IDENTITY"),
            "saved choice did not select a task controller")
    controller = public.get("controller")
    require(type(controller) is dict and set(controller) == {"source", "matrix_xy", "offset"}
            and controller["source"] in ("ESTIMATED_AFFINE", "UNCORRECTED"), "unsupported or oracle controller source")
    require(type(controller["offset"]) in (list, tuple) and len(controller["offset"]) == 4
            and controller["offset"][2:] == [0., 0.], "only recorded planar correction supported")
    if controller["source"] == "UNCORRECTED":
        require(controller == identity_controller(), "identity declaration differs")
    snapshot = ControllerSnapshot.from_mapping({"matrix_xy": controller["matrix_xy"], "offset_xy": controller["offset"][:2]})
    provenance = {"source_global_sequence": global_sequence, "source_public_sequence": sequence,
                  "available_at_calls": public["at_calls"], "source_choice_sha256": digest(public)}
    return snapshot, provenance


def execute_live_session(session, action_id, *, current_choice_sequence, saved_choice_sequence,
                         lookup, reset_before):
    require(type(session) is ProbeSession and callable(lookup), "private session and immutable journal lookup required")
    require(not getattr(session, "_delayed_intervention_consumed", False), "session intervention already consumed")
    require(session.alive() and 0 < session.ctx["calls"] < 500, "live mid-trajectory session required")
    require(session._pending is None and session.attempts == session.completed == session.ctx["calls"],
            "unresolved or inconsistent source execution")
    require(not session.captures and not session.restores and not session._snapshots, "continuous no-copy source required")
    require(type(reset_before) is dict and set(reset_before) == {"counts", "by_phase"}, "initial reset receipt required")
    start_ledger = session.ledger.snapshot()
    for field in ("reset_attempts", "reset_completed"):
        total = start_ledger["counts"].get(field, 0) - reset_before["counts"].get(field, 0)
        controlled = (start_ledger["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0)
                      - reset_before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0))
        require(total == controlled == 1, "source must contain exactly one controlled initial reset")
    require(start_ledger["counts"].get("reset_errors", 0) == reset_before["counts"].get("reset_errors", 0),
            "failed source reset")
    for field in ("simulation_frames_attempted", "simulation_frames_completed"):
        total = start_ledger["counts"].get(field, 0) - reset_before["counts"].get(field, 0)
        reset = (start_ledger["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0)
                 - reset_before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0))
        require(total - reset == 5 * session.ctx["calls"], "unaccounted physical source frames")
    require(session.last_rows and session.last_rows[-1]["logical_step"] == session.ctx["calls"] - 1
            and digest(session.last_rows[-1]["after"]) == digest(asdict(session.public())), "source tail differs from live state")
    previous_command = lookup(session.last_rows[-1]["global_command_sequence"])
    require(previous_command.get("event") == "AGENT_EVENT" and previous_command.get("agent_event") == "COMMAND",
            "source last action must be a saved policy command")
    previous = previous_command["public_payload"]
    require(previous.get("phase") == "POLICY" and previous.get("decision_sequence") == current_choice_sequence,
            "current correction was not the last actually applied choice")
    current, current_provenance = read_choice(session, current_choice_sequence, lookup)
    require(current_provenance["source_global_sequence"] < previous_command["sequence"]
            and current_provenance["available_at_calls"] <= previous["at_calls"]
            and np.array_equal(encode_controller(current.command_mapping(), previous["raw_policy"]), np.asarray(previous["command"], np.float32))
            and previous["command"] == session.last_rows[-1]["command"], "current choice does not explain the actual last command")
    saved, saved_provenance = (None, None) if saved_choice_sequence is None else read_choice(session, saved_choice_sequence, lookup)
    tape = session.ctx["noise_rows"]
    require(type(tape) is np.ndarray and tape.shape == (500, 3) and tape.dtype == np.dtype('<f4')
            and not tape.flags.writeable and np.array_equal(tape, original_noise(session.seed)), "unaltered original private noise tape required")
    initial_tape_hash, initial_tape_object = tape_hash(session), id(tape)
    budget = session.run_budget
    require(type(budget.get("completed")) is int and type(budget.get("maximum")) is int
            and 0 <= budget["completed"] <= budget["maximum"], "valid whole-study ledger required")
    if action_id != "STOP":
        require(budget["maximum"] - budget["completed"] >= 500 - session.ctx["calls"], "remaining case reserve unavailable")
    boundary = Boundary(session.task, session.ctx["calls"], session.public(), current, saved)
    catalog = {"CONTINUE_CURRENT": current.command_mapping(), "RUN_UNCORRECTED": identity_controller(), "STOP": None}
    if saved is not None:
        catalog["SWITCH_SAVED"] = saved.command_mapping()
    require(type(action_id) is str and action_id in catalog, "unavailable saved action")
    session._delayed_intervention_consumed = True
    session.branch = {"role": "DELAYED_INTERVENTION", "future": 0, "program": action_id}
    base = session.env.unwrapped
    addresses = (base.model._address, base.data._address)
    initial_time = float(base.data.time)
    start_counts = (session.attempts, session.completed, session.policy_queries, budget["completed"], len(session.last_rows))
    start = session.emit("DELAYED_INTERVENTION_START", {**session.branch, "logical_step": boundary.completed_steps,
                         "current_provenance": current_provenance, "saved_provenance": saved_provenance,
                         "ledger": start_ledger, "reset_before": reset_before, **session.witness()})
    local_sequence = 0
    pending = query = completed_command = None
    public = {}
    global_map = {}
    actor = None

    def assert_live_world():
        require((base.model._address, base.data._address) == addresses and not session.captures
                and not session.restores and not session._snapshots, "world identity/copy violation")
        require(id(session.ctx["noise_rows"]) == initial_tape_object and not session.ctx["noise_rows"].flags.writeable
                and tape_hash(session) == initial_tape_hash, "private noise was changed")
        for field in ("reset_attempts", "reset_completed", "reset_errors"):
            require(session.ledger.counts.get(field, 0) == start_ledger["counts"].get(field, 0), "mid-trajectory reset")

    def policy(observation):
        nonlocal query
        assert_live_world()
        require(query is None and pending is None and np.array_equal(observation, session.public().observation), "policy query is not current")
        before = session.ledger.snapshot(); native_time = float(base.data.time)
        raw = session.policy_query(observation)
        assert_live_world()
        require(session.ledger.snapshot() == before and float(base.data.time) == native_time, "policy query performed physical work")
        query = (session.ctx["calls"], raw.copy())
        return raw

    def emit(kind, payload):
        nonlocal local_sequence, pending, completed_command
        assert_live_world()
        require(kind in ("CHOICE", "COMMAND", "STEP_RESULT") and pending is None, "unknown or overlapping actor event")
        require(payload.get("at_calls") == session.ctx["calls"], "actor event has a stale clock")
        if kind == "CHOICE":
            require(not public and payload.get("action_id") == action_id and payload.get("task") == session.task
                    and payload.get("remaining_budget") == 500 - session.ctx["calls"]
                    and digest(payload.get("boundary_observation")) == digest(asdict(session.public()))
                    and digest(payload.get("candidate_map")) == digest(catalog)
                    and payload.get("candidate_map_sha256") == digest(catalog), "choice differs from admitted source corrections")
        elif kind == "COMMAND":
            require(query is not None and query[0] == session.ctx["calls"] and payload.get("decision_sequence") == 0,
                    "command lacks its current actual policy query/choice")
            require(digest(payload["before"]) == digest(asdict(session.public()))
                    and np.array_equal(np.asarray(payload["raw_policy"], np.float32), query[1]), "forged policy or stale observation")
            expected = encode_controller(public[0]["candidate_map"][public[0]["action_id"]], payload["raw_policy"])
            require(np.array_equal(expected, np.asarray(payload["command"], np.float32)), "command differs from saved correction")
        else:
            require(completed_command is not None and payload.get("command_sequence") == completed_command
                    and digest(payload.get("after")) == digest(asdict(session.public())), "result differs from actual step")
        saved_public = normalize({**deepcopy(payload), "sequence": local_sequence, "saved_ns": perf_counter_ns()})
        expected_hash = digest(saved_public)
        outer = session.emit("DELAYED_AGENT_EVENT", {**session.branch, "agent_event": kind, "public_payload": deepcopy(saved_public)})
        require(digest(outer.get("public_payload")) == expected_hash, "host journal changed actor acknowledgement")
        public[local_sequence] = deepcopy(saved_public);global_map[local_sequence] = outer["sequence"]
        local_sequence += 1
        if kind == "COMMAND":
            pending = deepcopy(saved_public)
        elif kind == "STEP_RESULT":
            completed_command = None
        return deepcopy(saved_public)

    def step(approved):
        nonlocal pending, query, completed_command
        assert_live_world()
        require(pending is not None and digest(approved) == digest(pending), "only acknowledged pending command can execute")
        require(approved["at_calls"] == session.ctx["calls"] and digest(approved["before"]) == digest(asdict(session.public())),
                "physical host rejected stale boundary")
        before = session.public()
        after = session._step(approved["command"], "POLICY", approved["raw_policy"], global_map[approved["sequence"]])
        assert_live_world()
        completed_command = approved["sequence"]
        pending = query = None
        return StepReceipt(before, tuple(approved["command"]), after, session.ctx["calls"])

    try:
        actor = SingleIntervention(boundary, policy=policy, step=step, emit=emit)
        outcome = actor.execute(action_id)
        assert_live_world()
        actual = session.completed - start_counts[1]
        require(session.attempts - start_counts[0] == actual == outcome["accepted_step_receipts"] == outcome["step_attempts"], "step accounting differs")
        require(session.ctx["calls"] == outcome["completed_steps"] == outcome["charged_steps"]
                and budget["completed"] - start_counts[3] == actual and len(session.last_rows) - start_counts[4] == actual,
                "logical/physical budget mismatch")
        require(session.policy_queries - start_counts[2] == outcome["policy_queries_completed"] == actual, "policy query count differs")
        end_ledger = session.ledger.snapshot()
        require(end_ledger["counts"].get("simulation_frames_completed", 0) - start_ledger["counts"].get("simulation_frames_completed", 0) == 5 * actual
                and np.isclose(float(base.data.time) - initial_time, .0125 * actual, rtol=0, atol=1e-9), "continuous native-frame mismatch")
        require(pending is None and query is None and completed_command is None, "unfinished host transaction")
        record = {**session.branch, "start_sequence": start["sequence"], "actor": outcome,
                  "ledger_before": start_ledger, "ledger_after": end_ledger, "host_completed_suffix_steps": actual,
                  "host_policy_queries": session.policy_queries - start_counts[2], "end_witness": session.witness(),
                  "current_provenance": current_provenance, "saved_provenance": saved_provenance}
        end = session.emit("DELAYED_INTERVENTION_COMPLETE", record)
        return normalize({**record, "end_sequence": end["sequence"]})
    except Exception as error:
        record = {**session.branch, "start_sequence": start["sequence"], "failure_type": type(error).__name__,
                  "failure_reason": str(error), "host_step_attempts": session.attempts - start_counts[0],
                  "host_returned_steps": session.completed - start_counts[1], "host_policy_queries": session.policy_queries - start_counts[2],
                  "unreturned_host_attempts": session.attempts - start_counts[0] - (session.completed - start_counts[1]),
                  "ledger_before": start_ledger, "ledger_after": session.ledger.snapshot(),
                  "native_time_before": initial_time, "native_time_after": float(base.data.time),
                  "actor_snapshot": None if actor is None else actor.snapshot(), "physical_completeness_unverified": True}
        try:
            session.emit("DELAYED_INTERVENTION_ABORTED", record)
        except Exception:
            pass
        raise
