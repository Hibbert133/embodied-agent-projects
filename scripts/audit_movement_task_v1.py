"""Independent grammar replay of paired reacquisition after a private switch.

Does not execute the preparation, task actor, host or collector.
Shares declared estimator, fixed-policy, encoding and ledger arithmetic only.
Source-generated native hashes are witnesses, not external physics validation.
"""

import argparse
from copy import deepcopy
from dataclasses import asdict
import gzip
import json
import math
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import movement_task_io_v1 as io
from src.analysis.movement_task_record_v1 import MovementTaskMonitor, public_observation
from src.analysis.movement_task_numerical_v1 import check_fit
from src.probe.physical_reprobe_v1 import Start
from src.analysis.continuous_state_witness_v1 import compare_witnesses
from src.analysis.capsule_record_json_v2 import normalize
from src.analysis.short_probe_journal_audit_v1 import (
    PHYSICAL, WITNESS, applied, check_ledger, check_observation, ledger_add,
    noise_tape, physical_rows_equal, simulation)
from src.analysis.short_probe_public_audit_v1 import same
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.cold_start_response import ColdPrefix, infer_operator, validate_model
from src.probe.operator_identification import affine_controller, encode_controller, identity_controller
from src.probe.short_joint_reference_v1 import infer_four
from src.rollout.task_registry import create_task_policy

PROGRAM = np.asarray([[.4, 0, 0, 0], [0, .4, 0, 0], [-.4, 0, 0, 0], [0, -.4, 0, 0]], np.float32).tolist()
PREFIX_BRANCH = {"role": "DELAYED_BOUNDARY_PREFIX", "future": 0, "program": "FOUR_EIGHT_THEN_POLICY16"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "strict nonnegative integer required")
    return value


def audit_case(events, record, identity, fault, model, reference, *, planned_boundary, target_fault, initial_ledger=None,
               previous_sequence=-1, previous_saved_ns=-1):
    """Consume exactly the registered complete grammar, retaining early endings.

    Allocation/identity is supplied by the population reader, never by record.
    No test-specific simulation or policy override is an audit API argument.
    """
    require(set(identity) == set(io.IDENTITY) | {"unit", "task", "seed", "variant"}, "strict allocation identity required")
    require(identity["variant"] in io.VARIANTS, "unknown intervention")
    integer(identity["seed"]);integer(identity["unit"])
    validate_model(model);same(model["task"], identity["task"])
    require(type(events) is list and events, "complete event list required")
    ledger = deepcopy(initial_ledger if initial_ledger is not None else {"counts": {}, "by_phase": {}})
    check_ledger(ledger);ledger_before = deepcopy(ledger);source_fault = deepcopy(fault)
    cursor = 0;sequence = previous_sequence;stamp = previous_saved_ns
    steps = queries = 0;physical = [];source = [];delayed = []
    public_clock = {"AGENT_EVENT": -1, "DELAYED_AGENT_EVENT": -1}
    source_global = {};branch = {};clock = None;current = None
    tape = noise_tape(identity["seed"]);policy = create_task_policy(identity["task"]);movement_monitor = None

    def take(kind, fields, *, branched=False):
        nonlocal cursor, sequence, stamp
        require(cursor < len(events), "truncated journal before " + kind)
        row = events[cursor];normalize(row)
        require(type(row) is dict and row.get("event") == kind, "expected event " + kind)
        expected_keys = set(identity) | {"sequence", "saved_ns", "event"} | set(fields)
        if branched:
            expected_keys |= set(branch)
            for key, value in branch.items(): same(row.get(key), value)
        require(set(row) == expected_keys, "unknown or missing event field: " + kind)
        for key, value in identity.items(): same(row[key], value)
        require(integer(row["sequence"]) == sequence + 1, "journal sequence gap or duplication")
        require(integer(row["saved_ns"]) >= max(0, stamp), "journal clock reversal")
        cursor += 1;sequence = row["sequence"];stamp = row["saved_ns"]
        return row

    def event(kind, payload, *, branched=False):
        row = take(kind, payload, branched=branched)
        for key, value in payload.items(): same(row[key], value)
        return row

    def public(kind, payload, namespace="AGENT_EVENT"):
        preceding_saved_ns = stamp
        row = take(namespace, ("agent_event", "public_payload"), branched=True)
        same(row["agent_event"], kind);p = row["public_payload"]
        history = source if namespace == "AGENT_EVENT" else delayed
        require(type(p) is dict and set(p) == set(payload) | {"sequence", "saved_ns"}, "strict public schema required")
        require(integer(p["sequence"]) == len(history), "local event sequence differs")
        require(max(public_clock[namespace], start["saved_ns"], preceding_saved_ns) <= integer(p["saved_ns"]) <= row["saved_ns"], "public saved clock differs")
        public_clock[namespace] = p["saved_ns"]
        for key, value in payload.items(): same(p[key], value)
        history.append({"kind": kind, "payload": deepcopy(p)})
        if movement_monitor is not None: movement_monitor.accept(kind, p)
        if namespace == "AGENT_EVENT": source_global[p["sequence"]] = row["sequence"]
        return row, p

    def witness(row):
        same(row["simulation_time"], clock)
        same(row["noise_past_sha256"], digest(tape[:steps].tolist()))
        for field in ("native_sha256", "python_semantic_sha256"):
            value = row[field]
            require(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value), "invalid state witness")
        return {key: deepcopy(row[key]) for key in WITNESS}

    def live():
        return not any(current[k] for k in ("success", "terminated", "truncated"))

    def move(choice, command=None, namespace="AGENT_EVENT", direct=False, phase_override=None):
        nonlocal ledger, clock, current, steps, queries
        require(live() and steps < 500, "step after termination or exhausted budget")
        if command is None:
            phase = phase_override or "POLICY";raw = np.asarray(policy.get_action(np.array(current["observation"], copy=True)), np.float32).tolist()
            controller = choice["candidate_map"][choice["action_id"]] if namespace == "DELAYED_AGENT_EVENT" else choice["controller"]
            command = encode_controller(controller, raw).tolist();queries += 1
        else:
            phase = phase_override or "FIXED_PROBE";raw = None
        body = {"at_calls": steps, "decision_sequence": choice["sequence"], "before": current,
                "command": command, "raw_policy": raw}
        if namespace == "AGENT_EVENT": body["phase"] = phase
        saved, p = public("COMMAND", body, namespace)
        intent = event("STEP_INTENT", {"logical_step": steps, "global_command_sequence": saved["sequence"],
            "phase": phase, "command": command, "ledger_before": ledger}, branched=True)
        row = take("STEP_COMPLETE", (*PHYSICAL, "intent_sequence", "global_command_sequence",
                   "execution_started_ns", "completed_ns", "ledger_before", "ledger_after"), branched=True)
        for key, expected in {"logical_step": steps, "intent_sequence": intent["sequence"],
                "global_command_sequence": saved["sequence"], "command": command, "phase": phase,
                "raw_policy": raw, "simulation_time_before": clock, "noise_cursor_after": steps + 1,
                "ledger_before": ledger, "executed_action_oracle": applied(command, fault, tape[steps])}.items():
            same(row[key], expected)
        require(saved["saved_ns"] <= intent["saved_ns"] <= integer(row["execution_started_ns"])
                <= integer(row["completed_ns"]) <= row["saved_ns"], "decision must precede execution and result")
        require(type(row["simulation_time_after"]) is float and math.isfinite(row["simulation_time_after"])
                and np.isclose(row["simulation_time_after"] - clock, .0125, atol=1e-10, rtol=0), "physical clock continuity violated")
        ledger = simulation(ledger, "CONTROL", 1, 5);same(row["ledger_after"], ledger)
        check_observation(row["after"])
        require(type(row["info"]) is dict and type(row["reward"]) in (int, float)
                and math.isfinite(row["reward"]), "invalid physical result")
        same(row["after"]["success"], bool(row["info"].get("success", False)))
        current = deepcopy(row["after"]);clock = row["simulation_time_after"];steps += 1
        physical.append({key: deepcopy(row[key]) for key in (*PHYSICAL, "intent_sequence", "global_command_sequence",
                        "execution_started_ns", "completed_ns", "ledger_before", "ledger_after")})
        if steps in (4, 8):
            boundary = take("PHYSICAL_BOUNDARY", ("logical_step", *WITNESS), branched=True)
            same(boundary["logical_step"], steps);witness(boundary)
        if not direct:
            public("STEP_RESULT", {"at_calls": steps, "command_sequence": p["sequence"], "after": current}, namespace)

    def reset(phase):
        nonlocal ledger
        saved = event("LIFECYCLE_RESET_INTENT", {"phase": phase, "before": ledger})
        ledger = ledger_add(ledger, phase, "reset_attempts", 1)
        ledger = simulation(ledger, phase, 100, 500)
        ledger = ledger_add(ledger, phase, "reset_completed", 1)
        event("LIFECYCLE_RESET_COMPLETE", {"intent_sequence": saved["sequence"], "phase": phase, "after": ledger})

    event("FACTORY_INTENT", {"ledger": ledger})
    for _ in range(50): reset("GOAL_GENERATION")
    event("FACTORY_COMPLETE", {"ledger": ledger})
    reset_before = deepcopy(ledger);reset("CONTROLLED_RESET");initial_ledger = deepcopy(ledger)
    initial_row = take("CONTROLLED_INITIAL", ("task", "observation", "simulation_time", "ledger"))
    same(initial_row["ledger"], ledger)
    current = {"observation": initial_row["observation"], "success": False, "terminated": False, "truncated": False}
    check_observation(current);initial = deepcopy(current);clock = initial_row["simulation_time"]
    require(type(clock) is float and math.isfinite(clock), "finite initial clock required")
    branch = PREFIX_BRANCH
    start = take("BOUNDARY_PREPARATION_START", ("reset_before", "ledger", "nominal_model_sha256", *WITNESS), branched=True)
    same(start["reset_before"], reset_before);same(start["ledger"], ledger);same(start["nominal_model_sha256"], digest(model))
    initial_witness = witness(start)
    public("PREFIX_PROGRAM", {"task": identity["task"], "initial": initial, "at_calls": 0,
        "boundary_step": 16, "episode_budget": 500, "nominal_model_sha256": digest(model), "program4": PROGRAM})
    current_choice = saved_choice = None;fits = [];reason = "EARLY_END"
    for count in (4, 8):
        _, choice = public("CHOICE", {"action": "PROBE_FOUR", "at_calls": steps, "program": PROGRAM})
        for command in PROGRAM:
            if not live(): break
            move(choice, command)
        if not live(): break
        prefix = ColdPrefix(identity["task"], tuple(initial["observation"]),
            tuple(tuple(r["command"]) for r in physical), tuple(tuple(r["after"]["observation"]) for r in physical), True)
        _, fit_intent = public("FIT_INTENT", {"at_calls": steps, "prefix": asdict(prefix), "prefix_sha256": digest(asdict(prefix))})
        fitted = normalize(infer_four(model, prefix) if count == 4 else infer_operator(model, prefix))
        _, fitted_event = public("FIT_RESULT", {"at_calls": steps, "intent_sequence": fit_intent["sequence"], "fit": fitted})
        fits.append(fitted)
        if fitted["valid"] is not True:
            reason = "INVALID_FOUR" if count == 4 else "INVALID_EIGHT";break
        _, choice = public("CHOICE", {"action": "RUN_FITTED", "at_calls": steps,
            "controller": affine_controller(fitted["matrix_xy"], fitted["bias_xy"]), "fit_sequence": fitted_event["sequence"],
            "fitted_prefix_steps": count, "purpose": "SAVED_UNUSED_CANDIDATE" if count == 4 else "CURRENT_POLICY_CONTROLLER"})
        if count == 4: saved_choice = choice
        else: current_choice = choice
    if current_choice is not None:
        while live() and steps < 16: move(current_choice)
    ready = steps == 16 and live() and current_choice is not None
    if ready: reason = "LIVE_STEP16"
    nfev = sum(integer(f.get("nfev", 0)) for f in fits)
    prefix_result = {"ready": ready, "reason": reason, "completed_steps": steps,
        "current_choice_sequence": None if current_choice is None else current_choice["sequence"],
        "saved_choice_sequence": None if saved_choice is None else saved_choice["sequence"],
        "policy_queries": queries, "fits_completed": len(fits), "optimizer_nfev": nfev,
        "final_observation": current, "saved_candidate_was_previously_applied": False}
    public("PREFIX_RESULT", {"at_calls": steps, "result": prefix_result})
    prefix_result = {**deepcopy(prefix_result), "events": deepcopy(source)}
    end = take("BOUNDARY_PREPARATION_COMPLETE", ("start_sequence", "result", "ledger", *WITNESS), branched=True)
    same(end["start_sequence"], start["sequence"]);same(end["result"], prefix_result);same(end["ledger"], ledger)
    boundary_witness = witness(end)
    prepared = {"public": prefix_result, "start_sequence": start["sequence"], "end_sequence": end["sequence"],
        "initial_ledger": initial_ledger, "boundary_ledger": deepcopy(ledger), "boundary_witness": boundary_witness}
    require(planned_boundary in (16, 32, 64), "unregistered intervention time")
    prefix_ready = ready;approach_calls = steps;approach_queries = queries;before_approach = deepcopy(ledger)
    branch = {"role": "PRE_REPROBE_APPROACH", "future": 0, "program": "CURRENT_TO_BOUNDARY"}
    approach_start = event("PRE_REPROBE_START", {"planned_boundary": planned_boundary,
        "source_choice_global_sequence": source_global[current_choice["sequence"]] if ready else None,
        "ledger": ledger, "at_calls": steps, **boundary_witness}, branched=True)
    if ready:
        while live() and steps < planned_boundary: move(current_choice, direct=True)
    ready = prefix_ready and live() and steps == planned_boundary
    approach_reason = "READY_FOR_REPROBE" if ready else ("PREFIX_NOT_READY" if not prefix_ready else "ENDED_BEFORE_BOUNDARY")
    approach_public = {"planned_boundary": planned_boundary, "completed_steps": steps,
        "new_steps": steps-approach_calls, "policy_queries": queries-approach_queries,
        "ready": ready, "reason": approach_reason, "final_observation": current}
    approach_end = take("PRE_REPROBE_COMPLETE", ("start_sequence", "result", "ledger", *WITNESS), branched=True)
    same(approach_end["start_sequence"], approach_start["sequence"]);same(approach_end["result"], approach_public)
    same(approach_end["ledger"], ledger);actual_boundary = witness(approach_end)
    approach_result = {"public": deepcopy(approach_public), "start_sequence": approach_start["sequence"],
        "end_sequence": approach_end["sequence"], "initial_ledger": before_approach, "boundary_ledger": deepcopy(ledger),
        "initial_witness": boundary_witness, "boundary_witness": actual_boundary}
    movement = None;end_witness = actual_boundary;motion = None;transition = None
    move_attempts = move_nfev = audit_move_nfev = 0
    if ready:
        switch_intent = event("EVALUATOR_FAULT_SET_INTENT", {"at_calls":steps,"source_fault_oracle":source_fault,
            "target_fault_oracle":target_fault,"ledger":ledger,**actual_boundary}, branched=True)
        switch_complete = event("EVALUATOR_FAULT_SET_COMPLETE", {"intent_sequence":switch_intent["sequence"],
            "at_calls":steps,"active_fault_oracle":target_fault,"ledger":ledger,**actual_boundary}, branched=True)
        transition = {"intent_sequence":switch_intent["sequence"],"complete_sequence":switch_complete["sequence"],
            "at_calls":steps,"source_fault_oracle":source_fault,"active_fault_oracle":target_fault}
        fault = deepcopy(target_fault)
        method = io.method(identity["variant"])
        branch = {"role": "MOVEMENT_TASK", "future": 0, "program": method}
        controller = current_choice["controller"];before_move = deepcopy(ledger);move_calls = steps;move_queries = queries
        public_start = {"task": identity["task"], "completed_steps": steps, "current": current,
            "correction_xy": controller["matrix_xy"], "offset_xy": controller["offset"][:2]}
        context = [deepcopy(p["after"]) for p in physical[-3:]]
        entry = event("MOVEMENT_TASK_START", {"at_calls": steps,
            "source_choice_global_sequence": source_global[current_choice["sequence"]], "ledger": ledger,
            "public_start": public_start, "context": context, **actual_boundary}, branched=True)
        movement_monitor = MovementTaskMonitor(Start.from_mapping(public_start),
            tuple(public_observation(v) for v in context), method, reference)
        public_start_index = len(source)
        motion = record["movement"]["public"]
        expected_events = motion["events"]
        while movement_monitor.phase != "DONE":
            offset = len(source)-public_start_index
            require(offset < len(expected_events), "truncated movement public record")
            declaration = expected_events[offset];kind = declaration["kind"]
            if kind == "COMMAND":
                if movement_monitor.phase == "MOVE_COMMAND":
                    move(movement_monitor.entry, movement_monitor.move_command, phase_override="REPOSITION")
                else:
                    require(movement_monitor.phase == "TASK_COMMAND", "command outside admitted task phase")
                    move(movement_monitor.decision, phase_override="TASK_AFTER_MOVEMENT")
            else:
                body = {k:v for k,v in declaration["payload"].items() if k not in ("sequence", "saved_ns")}
                saved, _ = public(kind, body)
                if kind == "MOVEMENT_TASK_DECISION":
                    checkpoint = take("MOVEMENT_TASK_CHECKPOINT", ("at_calls", "decision_global_sequence", "ledger", *WITNESS), branched=True)
                    same(checkpoint["at_calls"], steps);same(checkpoint["decision_global_sequence"], saved["sequence"])
                    same(checkpoint["ledger"], ledger);witness(checkpoint)
                if kind == "MOVEMENT_FIT_RESULT":
                    numeric = check_fit(reference.decoded(), movement_monitor.history.to_dict(), body["estimate"])
                    audit_move_nfev += numeric["audit_nfev"]
        movement_monitor.check_record(motion)
        same(motion["events"], source[public_start_index:])
        outcome = motion["outcome"]
        same(outcome["total_steps"], steps);same(outcome["policy_queries"], queries-move_queries)
        move_attempts = outcome["fit_attempts"];move_nfev = outcome["optimizer_nfev"]
        final = take("MOVEMENT_TASK_COMPLETE", ("entry_sequence", "result", "ledger", *WITNESS), branched=True)
        same(final["entry_sequence"], entry["sequence"]);same(final["result"], motion);same(final["ledger"], ledger)
        end_witness = witness(final)
        movement = {"public": motion, "entry_sequence": entry["sequence"], "end_sequence": final["sequence"],
            "ledger_before": before_move, "ledger_after": deepcopy(ledger), "new_control_steps": steps-move_calls,
            "new_simulation_frames": 5*(steps-move_calls), "new_policy_queries": queries-move_queries,
            "new_parameter_fits": move_attempts, "optimizer_nfev": move_nfev}
    require(cursor == len(events), "unexpected extra event, reset, restoration or replay")
    expected_record = {**identity, "planned_boundary": planned_boundary, "fault_oracle": source_fault,
        "scheduled_fault_oracle": target_fault, "fault_transition": transition, "context_applied": ready,
        "completed": True, "error": None, "close_error": None, "environment_closed": True,
        "ledger_before": ledger_before, "prefix": prepared, "approach": approach_result, "movement": movement, "movement_failure": None,
        "physical_rows": physical, "host_attempts": steps, "host_returned": steps, "policy_queries": queries,
        "captures": 0, "restores": 0, "computation_counters_complete": True, "initial_witness": initial_witness,
        "boundary_witness": actual_boundary, "success": current["success"], "total_steps": steps,
        "deadline_loss": steps if current["success"] else 500, "boundary_ready": ready,
        "stopped": prefix_result["reason"] in ("INVALID_FOUR", "INVALID_EIGHT"),
        "action": "NO_LIVE_BOUNDARY" if motion is None else motion["outcome"]["action"],
        "reposition_steps": 0 if motion is None else motion["outcome"]["reposition_steps"],
        "task_steps": 0 if motion is None else motion["outcome"]["task_steps"],
        "end_witness": end_witness, "final_observation": current, "ledger_before_close": ledger, "ledger_after_close": ledger,
        "parameter_fit_attempts": len(fits)+move_attempts, "parameter_fit_results": len(fits)+move_attempts,
        "optimizer_nfev": nfev+move_nfev, "movement_fit_attempts": move_attempts, "movement_fit_results": move_attempts,
        "movement_optimizer_nfev": move_nfev, "optimizer_nfev_complete": True}
    same(record, expected_record)
    return {"ledger": ledger, "last_sequence": sequence, "last_saved_ns": stamp,
        "recomputed_policy_queries": queries, "recomputed_parameter_fits": len(fits)+move_attempts,
        "recomputed_cold_optimizer_nfev": nfev, "saved_movement_optimizer_nfev": move_nfev,
        "independent_movement_optimizer_nfev": audit_move_nfev}


def audit_private(records, events, private, identity, summary, *, case_offset=0, previous_stamp=-1, next_event_saved_ns=None):
    from src.analysis.continuous_state_witness_v1 import verify_witness, dict_fields
    import hashlib
    require(len(private) == 4*len(records), "four private boundaries per execution required")
    by_sequence = {e["sequence"]:e for e in events};last_stamp = previous_stamp;wall = 0
    fields = {"label", "logical_step", "source_anchor_sequence", "source_anchor_saved_ns", "started_ns", "completed_ns",
        "ledger_before", "ledger_after", "source_witness", "witness"}
    for index, row in enumerate(records):
        packets = private[4*index:4*index+4];same(row["state_witnesses"], packets)
        group = [e for e in events if all(e[k] == row[k] for k in ("unit", "task", "seed", "variant"))]
        initial = next(e for e in group if e["event"] == "CONTROLLED_INITIAL")
        checkpoint = next((e for e in group if e["event"] == "MOVEMENT_TASK_CHECKPOINT"), None)
        if row["boundary_ready"]:
            require(checkpoint is not None, "missing post-movement checkpoint")
            post = ("POST_MOVEMENT", checkpoint["at_calls"], checkpoint["sequence"], {k:checkpoint[k] for k in WITNESS}, checkpoint["ledger"])
        else:
            require(checkpoint is None, "checkpoint on unavailable boundary")
            post = ("POST_MOVEMENT", row["total_steps"], row["approach"]["end_sequence"], row["boundary_witness"], row["approach"]["boundary_ledger"])
        expected = [("INITIAL", 0, initial["sequence"], row["initial_witness"], row["prefix"]["initial_ledger"]),
            ("BOUNDARY", row["approach"]["public"]["completed_steps"], row["approach"]["end_sequence"], row["boundary_witness"], row["approach"]["boundary_ledger"]),
            post,
            ("FINAL", row["total_steps"], group[-1]["sequence"], row["end_witness"], row["ledger_before_close"])]
        for offset, (packet, (label, count, anchor_id, source, ledger)) in enumerate(zip(packets, expected)):
            require(set(packet) == set(identity) | {"unit", "task", "seed", "variant", "event", "sequence", "saved_ns"} | fields,
                    "strict private witness fields required")
            for key, value in {**identity, **{k:row[k] for k in ("unit", "task", "seed", "variant")},
                "event":"STATE_WITNESS", "sequence":4*(case_offset+index)+offset, "label":label, "logical_step":count,
                "source_anchor_sequence":anchor_id, "source_witness":source, "ledger_before":ledger, "ledger_after":ledger}.items(): same(packet[key], value)
            anchor = by_sequence[anchor_id];same(packet["source_anchor_saved_ns"], anchor["saved_ns"])
            next_time = by_sequence[anchor_id+1]["saved_ns"] if anchor_id+1 in by_sequence else (next_event_saved_ns if next_event_saved_ns is not None else summary["collection_closed_ns"])
            require(max(last_stamp, anchor["saved_ns"]) <= integer(packet["started_ns"]) <= integer(packet["completed_ns"])
                    <= integer(packet["saved_ns"]) <= next_time, "private snapshot timing outside phase boundary")
            last_stamp = packet["saved_ns"];wall += packet["completed_ns"]-packet["started_ns"]
            w = packet["witness"];same(w["layer_types"], io.expected_layers(row["task"]))
            verify_witness(w, full_sha256=source["python_semantic_sha256"], native_sha256=source["native_sha256"])
            graph = w["raw_graph"];context = dict_fields(dict_fields(graph[0])["context"])
            require(set(context) == {"initial_observation", "observation", "terminated", "truncated", "success", "calls", "commands", "observations", "noise_rows"}, "unexpected private context field")
            same(context["calls"], ["int", count])
            current = row["physical_rows"][count-1]["after"] if count else {"observation":initial["observation"], "terminated":False,"truncated":False,"success":False}
            for flag in ("terminated", "truncated", "success"): same(context[flag], ["bool", current[flag]])
            def array(node, values, dtype, writable=True):
                expected_array = np.asarray(values, dtype=dtype)
                require(type(node) is list and len(node) == 4 and node[0] == "array", "owned context array required")
                same(node[3], hashlib.sha256(expected_array.tobytes(order="C")).hexdigest())
                metadata = graph[1][integer(node[2])]
                same(metadata[0], "python");same(metadata[3:], [list(expected_array.shape), expected_array.dtype.str, list(expected_array.strides), writable])
            array(context["initial_observation"], initial["observation"], "<f8")
            array(context["observation"], current["observation"], "<f8")
            array(context["noise_rows"], noise_tape(row["seed"]), "<f4", False)
            for key, value_key, dtype in (("commands", "command", "<f4"), ("observations", "after", "<f8")):
                node = context[key];require(node[0] == "builtins.list" and node[2] is None, "owned source evidence list required")
                same(len(node[3]), min(8, count))
                for saved, physical in zip(node[3], row["physical_rows"][:min(8, count)]):
                    values = physical[value_key] if key == "commands" else physical[value_key]["observation"]
                    array(saved, values, dtype)
    return {"private_witness_records":len(private), "witness_construction_wall_ns":wall,
        "context_arrays_and_counters_reconstructed":True, "last_private_saved_ns":last_stamp}


def matched_group(group):
    require(len(group) == 8, "all eight condition/method executions required")
    same([r["variant"] for r in group], list(io.VARIANTS));left = group[0]
    def untimed(value):
        if type(value) is dict:return {k:untimed(v) for k,v in value.items() if k != "saved_ns"}
        if type(value) in (tuple,list):return [untimed(v) for v in value]
        return value
    prefix_checks = []
    for right in group[1:]:
        for key in ("unit", "task", "seed", "planned_boundary", "boundary_ready"):same(left[key], right[key])
        count = left["approach"]["public"]["completed_steps"]
        same(left["approach"]["public"], right["approach"]["public"])
        same(untimed(left["prefix"]["public"]), untimed(right["prefix"]["public"]))
        require(physical_rows_equal(left["physical_rows"], right["physical_rows"], count), "common pre-intervention prefix differs")
        checks = [compare_witnesses(left["state_witnesses"][j]["witness"], right["state_witnesses"][j]["witness"]) for j in (0,1)]
        require(all(c["comparison_equal"] for c in checks), "initial/boundary state differs across alternatives")
        prefix_checks.append({"variant": right["variant"], "steps": count, "initial": checks[0], "boundary": checks[1]})
    movement_checks = []
    for offset in (0,4):
        first = group[offset+1]
        for right in group[offset+2:offset+4]:
            count = first["state_witnesses"][2]["logical_step"]
            same(right["state_witnesses"][2]["logical_step"], count)
            require(physical_rows_equal(first["physical_rows"], right["physical_rows"], count), "movement histories differ between correction methods")
            check = compare_witnesses(first["state_witnesses"][2]["witness"], right["state_witnesses"][2]["witness"])
            require(check["comparison_equal"], "task corrections did not start from the same actual post-movement world")
            movement_checks.append({"reference": first["variant"], "variant": right["variant"], "steps": count, "post_movement": check})
    return {"unit": left["unit"], "task": left["task"], "seed": left["seed"], "boundary_ready": left["boundary_ready"],
            "prefix_comparisons": prefix_checks, "movement_comparisons": movement_checks}


class Buffered:
    def __init__(self, values):self.values = iter(values);self.next = next(self.values, None)
    def pop(self):
        value = self.next;self.next = next(self.values, None);return value


def audit_records(manifest, models, references, records, events, private, summary):
    """Bounded memory: audit one case and match one eight-arm group at a time."""
    config = manifest["config"];identity = {k:manifest[k] for k in io.IDENTITY}
    rows_iter, event_iter, private_iter = iter(records), Buffered(events), iter(private)
    ledger = {"counts": {}, "by_phase": {}};sequence = stamp = private_stamp = -1
    rows = [];group = [];matching = [];computations = [];private_wall = 0;event_count = 0
    for index, spec in enumerate(config["cases"]):
        row = next(rows_iter, None);require(type(row) is dict, "missing execution")
        same({k:row[k] for k in spec}, spec)
        allocation = {k:spec[k] for k in ("unit", "task", "seed", "variant")};case_events = []
        while event_iter.next is not None and all(event_iter.next.get(k) == v for k,v in allocation.items()):case_events.append(event_iter.pop())
        reference = references[spec["task"]] if io.method(spec["variant"]) == "MOVE_ARX_KEEP" else None
        checked = audit_case(case_events, {k:v for k,v in row.items() if k != "state_witnesses"}, {**identity, **allocation},
            config["fault_oracle"], models[spec["task"]], reference, planned_boundary=spec["planned_boundary"],
            target_fault=io.destination(spec), initial_ledger=ledger, previous_sequence=sequence, previous_saved_ns=stamp)
        ledger, sequence, stamp = checked["ledger"], checked["last_sequence"], checked["last_saved_ns"]
        packets = [next(private_iter, None) for _ in range(4)]
        require(all(type(p) is dict for p in packets), "missing state witness")
        witness_cost = audit_private([row], case_events, packets, identity, summary, case_offset=index,
            previous_stamp=private_stamp, next_event_saved_ns=None if event_iter.next is None else event_iter.next["saved_ns"])
        private_stamp = witness_cost["last_private_saved_ns"];private_wall += witness_cost["witness_construction_wall_ns"]
        computations.append(checked);event_count += len(case_events);rows.append(io.compact(row));group.append(row)
        if len(group) == 8:matching.append(matched_group(group));group = []
    require(not group and next(rows_iter, None) is None and event_iter.next is None and next(private_iter, None) is None, "extra or incomplete population")
    same(summary["rows"], rows);same(summary["lifecycle"], ledger)
    for key, expected in identity.items():same(summary[key], expected)
    same(summary["status"], "COLLECTED_FOR_INDEPENDENT_AUDIT");same(summary["failure"], None)
    same(len(rows), config["executions"]);same(summary["completed_executions"], len(rows));same(len(matching), config["paired_units"])
    total = sum(r["total_steps"] for r in rows);same(summary["controlled_steps"], total)
    require(total <= config["maximum_environment_steps"], "control cap exceeded")
    same(summary["event_count"], event_count);same(summary["private_witness_records"], 4*len(rows))
    for field in ("reset_attempts", "reset_completed"):
        same(ledger["counts"][field], 51*len(rows));same(ledger["by_phase"]["CONTROLLED_RESET"][field], len(rows))
    for field in ("simulation_frames_attempted", "simulation_frames_completed"):
        same(ledger["counts"][field], 25500*len(rows)+5*total)
        require(ledger["counts"][field] <= config["maximum_simulation_frames"], "frame cap exceeded")
    for key in ("new_api_calls", "new_nominal_training", "new_selector_fits", "policy_updates"):same(summary[key], 0)
    integer(summary["wall_ns"]);integer(summary["collection_closed_ns"])
    return {"executions": len(rows), "independent_groups": config["independent_groups"], "paired_units": len(matching),
        "matched_groups": matching, "rows": rows, "event_count": event_count, "private_witness_records": 4*len(rows),
        "post_movement_world_comparisons": 4*len(matching), "pre_intervention_world_comparisons": 7*len(matching),
        "measurement_model_qualified": False, "novel_method_demonstrated": False, "task_benefit_evaluated": False,
        "costs": {"new_control_steps": total, "lifecycle": ledger, "collection_wall_ns": summary["wall_ns"],
            "private_witness_wall_ns": private_wall, "new_api_calls": 0,
            **{k:sum(r[k] for r in rows) for k in ("policy_queries", "parameter_fit_attempts", "parameter_fit_results", "optimizer_nfev",
                "movement_fit_attempts", "movement_fit_results", "movement_optimizer_nfev")},
            "historical_c8_source": config["historical_c8_cost"], "historical_arx_source": manifest["arx_source_receipt"]["costs"]},
        "audit_computations": {k:sum(c[k] for c in computations) for k in ("recomputed_policy_queries", "recomputed_parameter_fits",
            "recomputed_cold_optimizer_nfev", "saved_movement_optimizer_nfev", "independent_movement_optimizer_nfev")}}


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:yield json.loads(line)


def audit(path):
    started = perf_counter_ns();manifest, models, references = io.load(path);folder = path.parent/"collection"
    completion = io.read(folder/"completion.json");identity = {k:manifest[k] for k in io.IDENTITY}
    for key, value in identity.items():same(completion[key], value)
    same(completion["status"], "COLLECTED_FOR_INDEPENDENT_AUDIT")
    require(set(completion["artifact_sha256"]) == {"events.jsonl.gz", "cases.jsonl.gz", "state_witnesses.jsonl.gz", "status.json", "summary.json"}, "incomplete collection artifact set")
    for name, expected in completion["artifact_sha256"].items():same(io.sha(folder/name), expected)
    output = path.parent/"audit";output.mkdir()
    try:
        summary = io.read(folder/"summary.json");same(io.read(folder/"status.json"), {k:v for k,v in summary.items() if k != "rows"})
        result = audit_records(manifest, models, references, lines(folder/"cases.jsonl.gz"), lines(folder/"events.jsonl.gz"),
            lines(folder/"state_witnesses.jsonl.gz"), summary)
        result = {**identity, "integrity": "PASSED", "computations_complete": True, **result,
            "collection_artifact_sha256": completion["artifact_sha256"], "audit_wall_ns": perf_counter_ns()-started,
            "scope": "Recorded-trajectory and inspectable-world replay; independent movement inverse arithmetic; no dynamics resimulation or transfer guarantee."}
        io.write(output/"record_audit.json", result);return result
    except BaseException as error:
        io.write(output/"failed_audit.json", {**identity, "integrity": "FAILED", "error": type(error).__name__, "message": str(error), "wall_ns": perf_counter_ns()-started})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("manifest", type=Path)
    result = audit(parser.parse_args().manifest.resolve())
    print(json.dumps({k:result[k] for k in ("integrity", "executions", "event_count", "private_witness_records")}, ensure_ascii=False))
