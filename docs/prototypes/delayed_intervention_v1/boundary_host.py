"""Private continuous host admission for the fixed step-16 preparation."""

from copy import deepcopy
from dataclasses import asdict

import numpy as np

from boundary_prefix import BOUNDARY_STEP, PROGRAM4, prepare_boundary
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.paired_probe_host_v1 import ProbeSession, original_noise
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.operator_identification import affine_controller, encode_controller


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare_live_session(session, model, reset_before):
    require(type(session) is ProbeSession and session.ctx["calls"] == 0 and session.alive(), "fresh live session required")
    require(not getattr(session, "_boundary_preparation_consumed", False), "preparation already consumed")
    require(not session._map and session._pending is None and not session.captures and not session.restores
            and not session._snapshots and session.attempts == session.completed == session.policy_queries == 0,
            "unused continuous source session required")
    before = session.ledger.snapshot()
    for field in ("reset_attempts", "reset_completed"):
        difference = before["counts"].get(field, 0) - reset_before["counts"].get(field, 0)
        controlled = (before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0)
                      - reset_before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0))
        require(difference == controlled == 1, "one actual initial controlled reset required")
    for field in ("simulation_frames_attempted", "simulation_frames_completed"):
        require(before["counts"].get(field, 0) - reset_before["counts"].get(field, 0)
                == before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0)
                - reset_before["by_phase"].get("CONTROLLED_RESET", {}).get(field, 0), "extra pre-prefix physical work")
    require(np.array_equal(session.ctx["observation"], session.ctx["initial_observation"]), "initial observation differs")
    tape = session.ctx["noise_rows"]
    require(not tape.flags.writeable and np.array_equal(tape, original_noise(session.seed)), "original private noise required")
    budget = session.run_budget
    require(type(budget["completed"]) is int and type(budget["maximum"]) is int
            and 0 <= budget["completed"] <= budget["maximum"] - 500, "reserve the complete episode budget")
    session._boundary_preparation_consumed = True
    session.branch = {"role": "DELAYED_BOUNDARY_PREFIX", "future": 0, "program": "FOUR_EIGHT_THEN_POLICY16"}
    base = session.env.unwrapped;addresses = (base.model._address, base.data._address)
    time_before = float(base.data.time);budget_before = budget["completed"]
    start = session.emit("BOUNDARY_PREPARATION_START", {**session.branch, "reset_before": reset_before,
        "ledger": before, "nominal_model_sha256": digest(model), **session.witness()})
    records = {};query = None;last_command = None

    def continuous():
        require((base.model._address, base.data._address) == addresses and not session.captures
                and not session.restores and not session._snapshots, "world identity or copy violation")
        require(session.ctx["noise_rows"] is tape and not tape.flags.writeable
                and np.array_equal(tape, original_noise(session.seed)), "private noise changed")
        for field in ("reset_attempts", "reset_completed", "reset_errors"):
            require(session.ledger.counts.get(field, 0) == before["counts"].get(field, 0), "extra reset during preparation")

    def policy(observation):
        nonlocal query
        continuous()
        require(query is None and np.array_equal(observation, session.public().observation), "stale policy query")
        ledger = session.ledger.snapshot();clock = float(base.data.time)
        raw = session.policy_query(observation)
        continuous();require(ledger == session.ledger.snapshot() and clock == float(base.data.time), "policy performed physical work")
        query = raw.copy()
        return raw

    def emit(kind, payload):
        nonlocal last_command
        continuous()
        require(kind in ("PREFIX_PROGRAM", "CHOICE", "COMMAND", "FIT_INTENT", "FIT_RESULT", "STEP_RESULT", "PREFIX_RESULT")
                and session._pending is None and payload.get("at_calls") == session.ctx["calls"], "unknown or stale prefix event")
        if kind == "PREFIX_PROGRAM":
            require(not records and payload["task"] == session.task and payload["boundary_step"] == BOUNDARY_STEP
                    and payload["episode_budget"] == 500 and digest(payload["initial"]) == digest(asdict(session.public()))
                    and digest(payload["program4"]) == digest(PROGRAM4)
                    and payload["nominal_model_sha256"] == digest(model), "initial prefix declaration differs")
        elif kind == "FIT_INTENT":
            prefix = payload["prefix"]
            require(session.alive() and session.ctx["calls"] in (4, 8) and prefix["task"] == session.task
                    and prefix["controlled_reset_completed"] is True
                    and digest(prefix["initial_observation"]) == digest(session.ctx["initial_observation"].tolist())
                    and digest(prefix["commands"]) == digest(normalize(session.ctx["commands"]))
                    and digest(prefix["observations"]) == digest(normalize(session.ctx["observations"]))
                    and payload["prefix_sha256"] == digest(prefix), "fit lacks its actual observed prefix")
        elif kind == "FIT_RESULT":
            source = records.get(payload["intent_sequence"])
            require(source is not None and source[0] == "FIT_INTENT" and source[1]["at_calls"] == session.ctx["calls"], "fit intent differs")
        elif kind == "CHOICE":
            if payload["action"] == "PROBE_FOUR":
                require(session.ctx["calls"] in (0, 4) and digest(payload["program"]) == digest(PROGRAM4), "probe differs")
            else:
                source = records.get(payload["fit_sequence"])
                require(payload["action"] == "RUN_FITTED" and source is not None and source[0] == "FIT_RESULT"
                        and source[1]["fit"]["valid"] is True and source[1]["at_calls"] == payload["fitted_prefix_steps"], "correction source differs")
                fit = source[1]["fit"]
                require(digest(payload["controller"]) == digest(affine_controller(fit["matrix_xy"], fit["bias_xy"])), "correction differs from fit")
        elif kind == "STEP_RESULT":
            require(payload["command_sequence"] == last_command and digest(payload["after"]) == digest(asdict(session.public())), "step result differs")
        saved = session._agent_emit(kind, payload)
        records[saved["sequence"]] = (kind, deepcopy(saved))
        if kind == "COMMAND": last_command = saved["sequence"]
        return saved

    def step(saved):
        nonlocal query
        continuous()
        require(digest(saved) == digest(session._pending) and digest(saved["before"]) == digest(asdict(session.public())), "unsaved or stale prefix command")
        source = records.get(saved["decision_sequence"])
        require(source is not None and source[0] == "CHOICE", "command has no saved choice")
        choice = source[1]
        if saved["phase"] == "FIXED_PROBE":
            index = session.ctx["calls"] - choice["at_calls"]
            require(choice["action"] == "PROBE_FOUR" and 0 <= index < 4 and saved["raw_policy"] is None and query is None, "bad probe position")
            expected = choice["program"][index]
        else:
            require(saved["phase"] == "POLICY" and choice["purpose"] == "CURRENT_POLICY_CONTROLLER"
                    and query is not None and np.array_equal(query, np.asarray(saved["raw_policy"], np.float32)), "unsaved current policy output")
            expected = encode_controller(choice["controller"], query)
        require(np.array_equal(np.asarray(saved["command"], np.float32), np.asarray(expected, np.float32)), "prefix command differs from selection")
        result = session._agent_step(saved);query = None;continuous()
        return result

    result = prepare_boundary(session.task, session.public(), model, policy, step, emit)
    continuous()
    require(result["completed_steps"] == session.ctx["calls"] == session.completed == session.attempts
            == budget["completed"] - budget_before == len(session.last_rows), "prefix step fees differ")
    require(result["policy_queries"] == session.policy_queries and query is None and session._pending is None, "prefix computation differs")
    after = session.ledger.snapshot()
    require(after["counts"].get("simulation_frames_completed", 0) - before["counts"].get("simulation_frames_completed", 0)
            == 5 * session.completed and np.isclose(float(base.data.time) - time_before, .0125 * session.completed, atol=1e-9, rtol=0), "prefix frame/time fees differ")
    end = session.emit("BOUNDARY_PREPARATION_COMPLETE", {**session.branch, "start_sequence": start["sequence"],
        "result": result, "ledger": after, **session.witness()})
    return normalize({"public": result, "start_sequence": start["sequence"], "end_sequence": end["sequence"],
                      "initial_ledger": before, "boundary_ledger": after, "boundary_witness": session.witness()})


def direct_continue(session, current_choice, lookup):
    """Independent ordinary loop; no SingleIntervention or adapter execution."""
    selected = lookup(session._map[current_choice])["public_payload"]
    require(selected["action"] == "RUN_FITTED", "saved current choice required")
    session.branch = {"role": "DIRECT_CONTINUATION", "future": 0, "program": "DIRECT_CURRENT"}
    session.emit("DIRECT_CONTINUATION_START", {**session.branch, "at_calls": session.ctx["calls"],
        "source_choice_global_sequence": session._map[current_choice], **session.witness()})
    while session.alive() and session.ctx["calls"] < 500:
        raw = session.policy_query(session.public().observation)
        saved = session._agent_emit("COMMAND", {"at_calls": session.ctx["calls"], "phase": "POLICY",
            "decision_sequence": current_choice, "before": asdict(session.public()), "raw_policy": raw.tolist(),
            "command": encode_controller(selected["controller"], raw).tolist()})
        session._agent_step(saved)
    result = {"completed_steps": session.ctx["calls"], "success": session.public().success,
              "deadline_loss": session.ctx["calls"] if session.public().success else 500,
              "end_witness": session.witness()}
    session.emit("DIRECT_CONTINUATION_COMPLETE", {**session.branch, **result})
    return normalize(result)
