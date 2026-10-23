"""Versioned host for saved bounded-integral relocation and its PD control."""
from copy import deepcopy
from dataclasses import asdict

import numpy as np

from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.paired_probe_host_v1 import ProbeSession, original_noise
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.operator_identification import affine_controller, encode_controller
from src.probe.local_reprobe_v1 import (Start, StepReceipt, acquire, REPOSITION_LIMIT, PROGRAM,
    ANCHOR, POSITION_TOLERANCE, anchor_ready, control_update, relocation_evidence, METHODS,
    SCOPE, INTEGRAL_GAIN, INTEGRAL_LIMIT, TASK_RESERVE, selected_anchor)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def execute_reprobe(session, current_choice_sequence, lookup, *, reset_before, method):
    require(method in METHODS, "unknown relocation method")
    require(type(session) is ProbeSession and callable(lookup), "registered live host and saved journal required")
    require(not getattr(session, "_physical_reprobe_consumed", False), "reprobe already consumed")
    require(session.alive() and session.ctx["calls"] >= 9 and session._pending is None,
            "live boundary after an actually applied correction required")
    require(not session.captures and not session.restores and not session._snapshots,
            "source with no simulator copy or restoration required")
    require(session.ctx["calls"] == session.attempts == session.completed == len(session.last_rows),
            "source physical history incomplete")
    ledger_before = session.ledger.snapshot()
    require(type(reset_before) is dict and set(reset_before) == {"counts", "by_phase"},
            "actual per-case pre-reset ledger required")
    for field in ("reset_attempts", "reset_completed"):
        all_delta = ledger_before["counts"].get(field, 0)-reset_before["counts"].get(field, 0)
        controlled_delta = (ledger_before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0)
            -reset_before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0))
        require(all_delta == controlled_delta == 1, "one actual per-case controlled reset required")
    require(type(current_choice_sequence) is int and current_choice_sequence in session._map,
            "saved source correction required")

    def saved_public(local, kind):
        require(type(local) is int and local in session._map, "unknown saved public reference")
        row = deepcopy(lookup(session._map[local]))
        require(row["event"] == "AGENT_EVENT" and row["agent_event"] == kind
                and row["public_payload"]["sequence"] == local, "source journal kind differs")
        return row["public_payload"]

    choice = saved_public(current_choice_sequence, "CHOICE")
    require(choice["action"] == "RUN_FITTED" and choice["purpose"] == "CURRENT_POLICY_CONTROLLER"
            and choice["fitted_prefix_steps"] == choice["at_calls"] == 8, "saved cold-eight correction required")
    fit = saved_public(choice["fit_sequence"], "FIT_RESULT")
    require(fit["at_calls"] == 8 and fit["fit"]["valid"] is True
            and digest(choice["controller"]) == digest(affine_controller(fit["fit"]["matrix_xy"], fit["fit"]["bias_xy"])),
            "source correction differs from saved valid fit")
    last_command = deepcopy(lookup(session.last_rows[-1]["global_command_sequence"]))
    require(last_command["event"] == "AGENT_EVENT" and last_command["agent_event"] == "COMMAND"
            and last_command["public_payload"]["phase"] == "POLICY"
            and last_command["public_payload"]["decision_sequence"] == current_choice_sequence
            and digest(last_command["public_payload"]["command"]) == digest(session.last_rows[-1]["command"]),
            "selected source is not the last actually applied correction")
    controller = choice["controller"]
    require(session._map[choice["fit_sequence"]] < session._map[current_choice_sequence]
            < session.last_rows[-1]["global_command_sequence"], "source fit and choice must precede physical use")
    require(last_command["public_payload"]["raw_policy"] is not None and np.array_equal(
                encode_controller(controller, last_command["public_payload"]["raw_policy"]),
                np.asarray(session.last_rows[-1]["command"], np.float32)), "last command did not apply source correction")
    require(digest(session.last_rows[-1]["after"]) == digest(asdict(session.public())),
            "source observation differs from last physical receipt")
    public_start = Start(session.task, session.ctx["calls"], session.public(),
                         controller["matrix_xy"], controller["offset"][:2])
    anchor = selected_anchor(public_start, method)
    budget = session.run_budget
    require(type(budget["completed"]) is int and type(budget["maximum"]) is int
            and budget["maximum"]-budget["completed"] >= REPOSITION_LIMIT+len(PROGRAM),
            "reserve complete new operation in whole-study budget")
    tape = session.ctx["noise_rows"]
    require(not tape.flags.writeable and np.array_equal(tape, original_noise(session.seed)), "original noise tape required")
    base = session.env.unwrapped; addresses = (base.model._address, base.data._address)
    clock_before = float(base.data.time); budget_before = budget["completed"]
    calls_before = session.ctx["calls"]; queries_before = session.policy_queries
    source_before = digest(normalize((session.ctx["commands"], session.ctx["observations"])))
    session._physical_reprobe_consumed = True
    session.branch = {"role": "PHYSICAL_REPROBE", "future": 0, "program": "ANCHOR_THEN_EIGHT"}
    entry = session.emit("PHYSICAL_REPROBE_START", {**session.branch, "at_calls": calls_before,
        "source_choice_global_sequence": session._map[current_choice_sequence], "ledger": ledger_before,
        "public_start": asdict(public_start), **session.witness()})
    saved_events = {}; history = [public_start.current.observation]
    lifted = history[-1][2] >= anchor[2]-POSITION_TOLERANCE
    relocation_count = probe_count = 0
    probe_entry = None
    integral = [0., 0.]
    pending_update = None
    learned_saved = None

    def continuous():
        require(session.env.unwrapped is base and (base.model._address, base.data._address) == addresses and not session.captures
                and not session.restores and not session._snapshots, "world replacement or simulator restoration")
        require(session.ctx["noise_rows"] is tape and not tape.flags.writeable
                and np.array_equal(tape, original_noise(session.seed)), "noise tape replaced or rewound")
        require(digest(normalize((session.ctx["commands"], session.ctx["observations"]))) == source_before,
                "original cold evidence was changed")
        for key in ("reset_attempts", "reset_completed", "reset_errors"):
            require(session.ledger.counts.get(key, 0) == ledger_before["counts"].get(key, 0), "mid-operation reset")
        require(session.policy_queries == queries_before, "unexpected policy query")
        actual = session.ctx["calls"]-calls_before
        for key in ("simulation_frames_attempted", "simulation_frames_completed"):
            require(session.ledger.counts.get(key, 0)-ledger_before["counts"].get(key, 0) == 5*actual,
                    "extra or unrecorded physical frame work")
        require(np.isclose(float(base.data.time)-clock_before, .0125*actual, atol=1e-9, rtol=0),
                "physical clock changed outside saved commands")

    def emit(kind, payload):
        nonlocal probe_entry, pending_update, learned_saved
        continuous()
        require(kind in ("REACQUIRE_CHOICE", "COMMAND", "STEP_RESULT", "PROBE_ENTRY", "REACQUIRE_RESULT", "INTEGRAL_UPDATE", "RELOCATION_EVIDENCE")
                and session._pending is None and payload["at_calls"] == session.ctx["calls"], "stale public event")
        if kind == "REACQUIRE_CHOICE":
            require(not saved_events and digest(payload) == digest({"at_calls": calls_before,
                "start": asdict(public_start), "scope": SCOPE, "anchor": list(anchor),
                "maximum_reposition_steps": REPOSITION_LIMIT, "task_reserve": TASK_RESERVE,
                "probe_program": [list(v) for v in PROGRAM], "relocation_method": method,
                "integral_gain": INTEGRAL_GAIN if method.endswith("_PID") else 0., "integral_limit": INTEGRAL_LIMIT}),
                "saved relocation choice differs from admitted method")
        if kind == "INTEGRAL_UPDATE":
            require(pending_update is None and learned_saved is None, "duplicate or late integral update")
            updated, command = control_update(public_start, history, lifted, integral, method)
            require(digest(payload) == digest({"at_calls": session.ctx["calls"], "integral_before": integral, "integral_after": updated}), "integral update differs from visible history")
            pending_update = (updated, command)
        if kind == "RELOCATION_EVIDENCE":
            require(learned_saved is None and pending_update is None, "duplicate or premature relocation evidence")
            require(digest(payload) == digest({"at_calls": session.ctx["calls"], **relocation_evidence(public_start, integral, anchor_ready(history, anchor))}), "relocation compensation changed")
            learned_saved = deepcopy(payload)
        if kind == "PROBE_ENTRY":
            require(learned_saved is not None and probe_entry is None and anchor_ready(history, anchor)
                    and digest(payload["entry_history"]) == digest(history[-4:]), "unobserved probe entry")
            probe_entry = session.ctx["calls"]
        saved = session._agent_emit(kind, payload)
        saved_events[saved["sequence"]] = (kind, deepcopy(saved))
        return saved

    def step(saved):
        nonlocal lifted, relocation_count, probe_count, integral, pending_update
        continuous()
        require(digest(saved) == digest(session._pending) and digest(saved["before"]) == digest(asdict(session.public())),
                "unsaved or stale physical command")
        source = saved_events.get(saved["decision_sequence"])
        require(source is not None and source[0] == "REACQUIRE_CHOICE"
                and digest(source[1]["start"]) == digest(asdict(public_start)), "command has no admitted choice")
        require(saved["raw_policy"] is None, "reacquisition cannot query task policy")
        if saved["phase"] == "REPOSITION":
            require(probe_entry is None and relocation_count < REPOSITION_LIMIT and not anchor_ready(history, anchor),
                    "relocation beyond its permitted phase")
            require(pending_update is not None and learned_saved is None, "integral choice must be saved before movement")
            expected = pending_update[1]
            relocation_count += 1
        else:
            require(saved["phase"] == "WARM_PROBE" and probe_entry is not None and probe_count < len(PROGRAM)
                    and session.ctx["calls"] == probe_entry+probe_count, "unavailable or repeated probe")
            expected = PROGRAM[probe_count]
            probe_count += 1
        require(np.array_equal(np.asarray(saved["command"], np.float32), np.asarray(expected, np.float32)),
                "saved physical command differs from registered program")
        after = session._agent_step(saved)
        if saved["phase"] == "REPOSITION":
            integral = pending_update[0];pending_update = None
        history.append(after.observation)
        lifted = lifted or after.observation[2] >= anchor[2]-POSITION_TOLERANCE
        continuous()
        return StepReceipt(after, session.ctx["calls"])

    result = acquire(public_start, step, emit, method=method)
    continuous()
    new_steps = session.ctx["calls"]-calls_before
    require(new_steps == result["new_steps"] == budget["completed"]-budget_before
            and session.ctx["calls"] == session.attempts == session.completed == len(session.last_rows)
            and session._pending is None, "actual control cost differs")
    after = session.ledger.snapshot()
    for key in ("simulation_frames_attempted", "simulation_frames_completed"):
        require(after["counts"].get(key, 0)-ledger_before["counts"].get(key, 0) == 5*new_steps,
                "unrecorded simulation frame cost")
    require(np.isclose(float(base.data.time)-clock_before, .0125*new_steps, atol=1e-9, rtol=0),
            "physical clock does not advance continuously")
    end = session.emit("PHYSICAL_REPROBE_COMPLETE", {**session.branch, "entry_sequence": entry["sequence"],
        "result": result, "ledger": after, **session.witness()})
    return normalize({"public": result, "entry_sequence": entry["sequence"], "end_sequence": end["sequence"],
        "ledger_before": ledger_before, "ledger_after": after, "new_control_steps": new_steps,
        "new_simulation_frames": 5*new_steps, "new_policy_queries": 0, "new_parameter_fits": 0})
