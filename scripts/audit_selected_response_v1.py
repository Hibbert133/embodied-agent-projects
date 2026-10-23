"""Independent grammar replay of paired reacquisition after a private switch.

Does not import or execute the preparation, intervention actor or collector.
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
from src.analysis import selected_response_io_v1 as io
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


def audit_case(events, record, identity, fault, model, *, planned_boundary, target_fault, initial_ledger=None,
               previous_sequence=-1, previous_saved_ns=-1, bank_hash=None):
    """Consume exactly the registered complete grammar, retaining early endings.

    Allocation/identity is supplied by the population reader, never by record.
    No test-specific simulation or policy override is an audit API argument.
    """
    require(set(identity) == set(io.IDENTITY) | {"unit", "task", "seed", "variant"}, "strict allocation identity required")
    require(identity["variant"] in io.VARIANTS, "unknown intervention")
    integer(identity["seed"]);integer(identity["unit"])
    training = identity["variant"] == "TRAIN"
    assigned = None
    if training:
        rng = np.random.default_rng(np.random.SeedSequence([identity["seed"],88001]))
        assigned = np.c_[rng.uniform(-.8,.8,(8,2)),np.zeros((8,2))].astype(np.float32).tolist()
    program = assigned if training else PROGRAM*2
    scope = "SELECTED_NOMINAL_RANDOM_EIGHT_V1" if training else "VISIBLE_SELECTED_ANCHOR_THEN_EIGHT_V1"
    complete_reason = "COMPLETE_NOMINAL_TRAIN" if training else "COMPLETE_UNQUALIFIED"
    window_key = "nominal_trajectory" if training else "window"
    validate_model(model);same(model["task"], identity["task"])
    require(type(events) is list and events, "complete event list required")
    ledger = deepcopy(initial_ledger if initial_ledger is not None else {"counts": {}, "by_phase": {}})
    check_ledger(ledger);ledger_before = deepcopy(ledger);source_fault = deepcopy(fault)
    cursor = 0;sequence = previous_sequence;stamp = previous_saved_ns
    steps = queries = 0;physical = [];source = [];delayed = []
    public_clock = {"AGENT_EVENT": -1, "DELAYED_AGENT_EVENT": -1}
    source_global = {};branch = {};clock = None;current = None
    tape = noise_tape(identity["seed"]);policy = create_task_policy(identity["task"])

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
            phase = "POLICY";raw = np.asarray(policy.get_action(np.array(current["observation"], copy=True)), np.float32).tolist()
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

    assignment = event("COLLECTION_ASSIGNMENT", {"nominal_program":assigned,"model_bank_sha256":bank_hash})
    if training: same(bank_hash,None)
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
    reacquisition = None;end_witness = actual_boundary;warm = None;transition = None
    if ready:
        if not training:
            switch_intent = event("EVALUATOR_FAULT_SET_INTENT", {"at_calls":steps,"source_fault_oracle":source_fault,
                "target_fault_oracle":target_fault,"ledger":ledger,**actual_boundary}, branched=True)
            switch_complete = event("EVALUATOR_FAULT_SET_COMPLETE", {"intent_sequence":switch_intent["sequence"],
                "at_calls":steps,"active_fault_oracle":target_fault,"ledger":ledger,**actual_boundary}, branched=True)
            transition = {"intent_sequence":switch_intent["sequence"],"complete_sequence":switch_complete["sequence"],
                "at_calls":steps,"source_fault_oracle":source_fault,"active_fault_oracle":target_fault}
            fault = deepcopy(target_fault)
        branch = ({"role":"NOMINAL_SELECTED_ACQUISITION","future":0,"program":"SAVED_RANDOM_EIGHT"} if training else
                  {"role":"PHYSICAL_REPROBE","future":0,"program":"ANCHOR_THEN_EIGHT"})
        controller = current_choice["controller"];before_warm = deepcopy(ledger);warm_calls = steps
        public_start = {"task": identity["task"], "completed_steps": steps, "current": current,
            "correction_xy": controller["matrix_xy"], "offset_xy": controller["offset"][:2]}
        entry = event("PHYSICAL_REPROBE_START", {"at_calls": steps,
            "source_choice_global_sequence": source_global[current_choice["sequence"]], "ledger": ledger,
            "public_start": public_start, **actual_boundary}, branched=True)
        method = "LOCAL_PID"
        obs = current["observation"]
        anchor = ([0.,.6,.25] if method.startswith("FIXED_") else
                  [min(.45,max(-.45,obs[0])),min(.95,max(.45,obs[1])),min(.45,max(.25,obs[6]+.12))])
        public_start_index = len(source)
        _, choice = public("REACQUIRE_CHOICE", {"at_calls": steps, "start": public_start,
            "scope": scope, "anchor": anchor,
            "maximum_reposition_steps": 64, "task_reserve": 100, "probe_program": program,
            "relocation_method": "LOCAL_PID", "integral_gain": .32 if "LOCAL_PID".endswith("_PID") else 0.,
            "integral_limit": .5})
        history = [deepcopy(current["observation"])];relocation_steps = 0;probe_steps = 0;window = None
        integral = [0., 0.];learned = None;method = "LOCAL_PID"

        def at_anchor():
            if len(history) < 4: return False
            return (max(abs(a-b) for a,b in zip(history[-1][:3], anchor)) <= .015
                and math.dist(history[-1][:3], history[-1][4:7]) >= .10
                and all(max(abs(a-b) for a,b in zip(left[:3], right[:3])) <= .003
                        for left,right in zip(history[-4:-1], history[-3:])))

        if 500-steps < 172:
            warm_reason = "ENTRY_BUDGET_INSUFFICIENT"
        else:
            lifted = history[-1][2] >= anchor[2]-.015
            while not at_anchor() and relocation_steps < 64 and live():
                xyz = np.asarray(history[-1][:3])
                target = np.array(anchor if lifted else [*history[0][:2], anchor[2]])
                displacement = xyz-np.asarray(history[-2][:3]) if len(history) > 1 else np.zeros(3)
                feedback = 8.*(target-xyz)-16.*displacement
                previous_integral = list(integral)
                updated = list(integral)
                if method.endswith("_PID"):
                    for axis in range(2):
                        candidate = min(.5, max(-.5, integral[axis]+.32*(target[axis]-xyz[axis])))
                        change = candidate-integral[axis]
                        if not ((feedback[axis]+candidate > .5 and change > 0) or (feedback[axis]+candidate < -.5 and change < 0)):
                            updated[axis] = float(candidate)
                    bounded = [min(.5,max(-.5,feedback[a]+updated[a])) for a in range(2)]
                    mapped = np.asarray(controller["matrix_xy"]) @ bounded+controller["offset"][:2]
                    excess = mapped-np.clip(mapped,-1.,1.)
                    effect = np.asarray(controller["matrix_xy"]) @ (np.asarray(updated)-integral)
                    if sum(float(a*b) for a,b in zip(excess,effect)) > 0:updated = list(integral)
                public("INTEGRAL_UPDATE", {"at_calls":steps,"integral_before":previous_integral,"integral_after":updated})
                integral = updated
                requested = np.r_[np.clip(feedback+np.r_[integral,0.], -.5, .5), -1.]
                requested[:2] = np.asarray(controller["matrix_xy"]) @ requested[:2] + controller["offset"][:2]
                command = np.clip(requested, -1., 1.).astype(np.float32).tolist()
                move(choice, command, phase_override="REPOSITION");relocation_steps += 1
                history.append(deepcopy(current["observation"]));lifted = lifted or history[-1][2] >= anchor[2]-.015
            offset = np.asarray(controller["offset"][:2])+np.asarray(controller["matrix_xy"]) @ integral
            learned = {"integral_xy":integral, "at_anchor":at_anchor(),
                "controller":{"source":"RELOCATION_INTEGRAL_REFERENCE", "matrix_xy":controller["matrix_xy"], "offset":[*offset.tolist(),0.,0.]},
                "parameter_estimate_qualified":False,"task_utility_demonstrated":False}
            public("RELOCATION_EVIDENCE", {"at_calls":steps,**learned})
            if not live(): warm_reason = "ENDED_DURING_REPOSITION"
            elif not at_anchor(): warm_reason = "ANCHOR_NOT_REACHED"
            else:
                entry_history = deepcopy(history[-4:]);probe_start = steps
                public("PROBE_ENTRY", {"at_calls": steps, "entry_history": entry_history,
                    "scope": scope, "measurement_model_qualified": False})
                warm_reason = complete_reason;probe_observations = []
                for command in program:
                    move(choice, command, phase_override="WARM_PROBE");probe_steps += 1
                    probe_observations.append(deepcopy(current["observation"]))
                    if not live(): warm_reason = "ENDED_DURING_PROBE";break
                    obs = current["observation"]
                    if obs[2] < .21 or math.dist(obs[:3], obs[4:7]) < .08:
                        warm_reason = "PROBE_SCOPE_EXIT";break
                if warm_reason == complete_reason:
                    window = {"task": identity["task"], "probe_start_step": probe_start, "anchor":anchor, "entry_history": entry_history,
                        "commands": program, "observations": probe_observations}
                    if training:window["split"] = "TRAIN"
        warm = {"reason": warm_reason, "completed_steps": steps, "new_steps": steps-warm_calls,
            "reposition_steps": relocation_steps, "probe_steps": probe_steps, "remaining_steps": 500-steps,
            "final": current, "measurement_model_qualified": False, "parameter_fits": 0, window_key: window,
            "relocation_method":method,"measurement_anchor":anchor,"relocation_evidence":learned}
        public("REACQUIRE_RESULT", {"at_calls": steps, **warm})
        warm = {**deepcopy(warm), "events": deepcopy(source[public_start_index:])}
        final = take("PHYSICAL_REPROBE_COMPLETE", ("entry_sequence", "result", "ledger", *WITNESS), branched=True)
        same(final["entry_sequence"], entry["sequence"]);same(final["result"], warm);same(final["ledger"], ledger)
        end_witness = witness(final)
        reacquisition = {"public": warm, "entry_sequence": entry["sequence"], "end_sequence": final["sequence"],
            "ledger_before": before_warm, "ledger_after": deepcopy(ledger), "new_control_steps": steps-warm_calls,
            "new_simulation_frames": 5*(steps-warm_calls), "new_policy_queries": 0, "new_parameter_fits": 0}
    require(cursor == len(events), "unexpected extra event, reset, state restoration or replay")
    expected_record = {**identity, "planned_boundary": planned_boundary, "fault_oracle": source_fault,
        "scheduled_fault_oracle":target_fault,"fault_transition":transition,"context_applied":ready and not training,"assignment_sequence":assignment["sequence"],"model_bank_sha256":bank_hash,
        "completed": True, "error": None, "close_error": None, "environment_closed": True,
        "ledger_before": ledger_before, "prefix": prepared, "approach": approach_result, "reacquisition": reacquisition,
        "physical_rows": physical, "host_attempts": steps, "host_returned": steps, "policy_queries": queries,
        "captures": 0, "restores": 0, "computation_counters_complete": True, "initial_witness": initial_witness,
        "boundary_witness": actual_boundary, "success": current["success"], "total_steps": steps,
        "boundary_ready": ready, "collection_stop_reason": approach_reason if warm is None else warm["reason"],
        "complete_window": warm is not None and warm[window_key] is not None,
        "reposition_steps": 0 if warm is None else warm["reposition_steps"], "probe_steps": 0 if warm is None else warm["probe_steps"],
        "end_witness": end_witness, "final_observation": current, "ledger_before_close": ledger, "ledger_after_close": ledger,
        "parameter_fit_attempts": len(fits), "parameter_fit_results": len(fits), "optimizer_nfev": nfev,
        "optimizer_nfev_complete": True}
    same(record, expected_record)
    return {"ledger": ledger, "last_sequence": sequence, "last_saved_ns": stamp,
        "recomputed_policy_queries": queries, "recomputed_parameter_fits": len(fits), "recomputed_optimizer_nfev": nfev}


def audit_private(records, events, private, identity, summary, record_offset=0):
    from src.analysis.continuous_state_witness_v1 import verify_witness, dict_fields
    import hashlib
    require(len(private) == 3*len(records), "three private boundaries per execution required")
    by_sequence = {e["sequence"]:e for e in events};last_stamp = -1;wall = 0
    fields = {"label", "logical_step", "source_anchor_sequence", "source_anchor_saved_ns", "started_ns", "completed_ns",
        "ledger_before", "ledger_after", "source_witness", "witness"}
    for index, row in enumerate(records):
        packets = private[3*index:3*index+3];same(row["state_witnesses"], packets)
        group = [e for e in events if all(e[k] == row[k] for k in ("unit", "task", "seed", "variant"))]
        initial = next(e for e in group if e["event"] == "CONTROLLED_INITIAL")
        expected = [("INITIAL", 0, initial["sequence"], row["initial_witness"], row["prefix"]["initial_ledger"]),
            ("BOUNDARY", row["approach"]["public"]["completed_steps"], row["approach"]["end_sequence"], row["boundary_witness"], row["approach"]["boundary_ledger"]),
            ("FINAL", row["total_steps"], group[-1]["sequence"], row["end_witness"], row["ledger_before_close"])]
        for offset, (packet, (label, count, anchor_id, source, ledger)) in enumerate(zip(packets, expected)):
            require(set(packet) == set(identity) | {"unit", "task", "seed", "variant", "event", "sequence", "saved_ns"} | fields,
                    "strict private witness fields required")
            for key, value in {**identity, **{k:row[k] for k in ("unit", "task", "seed", "variant")},
                "event":"STATE_WITNESS", "sequence":3*(record_offset+index)+offset, "label":label, "logical_step":count,
                "source_anchor_sequence":anchor_id, "source_witness":source, "ledger_before":ledger, "ledger_after":ledger}.items(): same(packet[key], value)
            anchor = by_sequence[anchor_id];same(packet["source_anchor_saved_ns"], anchor["saved_ns"])
            next_time = by_sequence[anchor_id+1]["saved_ns"] if anchor_id+1 in by_sequence else summary["collection_closed_ns"]
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
        "context_arrays_and_counters_reconstructed":True}


def lines(path):
    with gzip.open(path,"rt",encoding="utf-8") as handle:
        for line in handle:yield json.loads(line)


def match_pair(left, right):
    for key in ("unit","task","seed","planned_boundary","boundary_ready"):same(left[key],right[key])
    same(left["variant"],"UNCHANGED");same(right["variant"],"CHANGED")
    count = left["approach"]["public"]["completed_steps"]
    same(left["approach"]["public"],right["approach"]["public"])
    require(physical_rows_equal(left["physical_rows"],right["physical_rows"],count),"pre-change physical history differs")
    comparisons = [compare_witnesses(left["state_witnesses"][i]["witness"],right["state_witnesses"][i]["witness"]) for i in (0,1)]
    require(all(c["comparison_equal"] for c in comparisons),"pre-change state differs")
    return {"unit":left["unit"],"matched_steps":count,"initial":comparisons[0],"boundary":comparisons[1]}


def audit_stream(manifest, models, stage, records, events, private, summary):
    config = manifest["config"];specs = config[stage+"_cases"];caps = io.limits(config,stage)
    identity = {k:manifest[k] for k in io.IDENTITY}
    ledger = {"counts":{},"by_phase":{}};sequence = stamp = -1;event_count = witness_wall = 0
    computed = {k:0 for k in ("recomputed_policy_queries","recomputed_parameter_fits","recomputed_optimizer_nfev")}
    costs = {k:0 for k in ("total_steps","reposition_steps","probe_steps","host_attempts","host_returned",
        "policy_queries","parameter_fit_attempts","parameter_fit_results","optimizer_nfev")}
    rows = [];matching = [];previous = None;pending = next(events,None)
    for index,spec in enumerate(specs):
        row = next(records,None);require(row is not None,"incomplete registered population")
        for k,v in spec.items():same(row[k],v)
        group = []
        while pending is not None and all(pending.get(k) == spec[k] for k in ("unit","task","seed","variant")):
            group.append(pending);pending = next(events,None)
        allocation = {k:spec[k] for k in ("unit","task","seed","variant")}
        require(bool(group) and group[0]["saved_ns"] >= summary["collection_started_ns"],"assignment predates collection")
        checked = audit_case(group,{k:v for k,v in row.items() if k != "state_witnesses"},{**identity,**allocation},
            io.initial(spec["variant"]),models[spec["task"]],planned_boundary=spec["planned_boundary"],
            target_fault=io.destination(spec),initial_ledger=ledger,previous_sequence=sequence,previous_saved_ns=stamp,
            bank_hash=summary["model_bank_sha256"])
        packets = [next(private,None) for _ in range(3)];require(all(p is not None for p in packets),"incomplete private witnesses")
        boundary = summary["collection_closed_ns"] if pending is None else pending["saved_ns"]
        private_cost = audit_private([row],group,packets,identity,{"collection_closed_ns":boundary},record_offset=index)
        ledger = checked["ledger"];sequence = checked["last_sequence"];stamp = max(checked["last_saved_ns"],packets[-1]["saved_ns"])
        event_count += len(group);witness_wall += private_cost["witness_construction_wall_ns"]
        for k in computed:computed[k] += checked[k]
        for k in costs:costs[k] += row[k]
        rows.append(io.compact(row))
        if stage == "qualify":
            if index%2 == 0:previous = row
            else:matching.append(match_pair(previous,row));previous = None
    same(next(records,None),None);same(pending,None);same(next(private,None),None)
    same(summary["rows"],rows);same(summary["lifecycle"],ledger)
    for k,v in identity.items():same(summary[k],v)
    same(summary["stage"],stage);same(summary["status"],"COLLECTED_FOR_INDEPENDENT_AUDIT");same(summary["failure"],None)
    same(summary["completed_executions"],len(rows));same(summary["controlled_steps"],costs["total_steps"])
    same(summary["event_count"],event_count);same(summary["private_witness_records"],3*len(rows))
    same(summary["new_api_calls"],0);same(summary["policy_updates"],0)
    same(ledger["counts"]["reset_completed"],51*len(rows));same(ledger["by_phase"]["CONTROLLED_RESET"]["reset_completed"],len(rows))
    same(ledger["counts"]["simulation_frames_completed"],25500*len(rows)+5*costs["total_steps"])
    require(costs["total_steps"] <= caps["scheduled_maximum_control_steps"] <= caps["maximum_environment_steps"],"control cap exceeded")
    require(ledger["counts"]["simulation_frames_attempted"] <= caps["maximum_simulation_frames"],"frame cap exceeded")
    require(integer(summary["collection_started_ns"]) < integer(summary["collection_closed_ns"]),"invalid collection interval")
    integer(summary["wall_ns"])
    return {"stage":stage,"executions":len(rows),"rows":rows,"event_count":event_count,"matched_pairs":matching,
        "private_witness_records":3*len(rows),"witness_construction_wall_ns":witness_wall,"audit_computations":computed,
        "context_arrays_and_counters_reconstructed":True,
        "costs":{**costs,"new_control_steps":costs["total_steps"],"lifecycle":ledger,"collection_wall_ns":summary["wall_ns"],"new_api_calls":0}}


def audit(path, stage):
    if stage not in io.STAGES:raise ValueError("registered stage required")
    started = perf_counter_ns();manifest,models = io.load(path);folder = path.parent/stage
    identity = {k:manifest[k] for k in io.IDENTITY};completion = io.read(folder/"completion.json")
    for k,v in identity.items():same(completion[k],v)
    same(completion["stage"],stage);same(completion["status"],"COLLECTED_FOR_INDEPENDENT_AUDIT")
    require(set(completion["artifact_sha256"]) == {"events.jsonl.gz","cases.jsonl.gz","state_witnesses.jsonl.gz","status.json","summary.json"},"incomplete artifact set")
    for name,value in completion["artifact_sha256"].items():same(io.sha(folder/name),value)
    output = path.parent/(stage+"_audit");output.mkdir()
    try:
        summary = io.read(folder/"summary.json");same(io.read(folder/"status.json"),{k:v for k,v in summary.items() if k != "rows"})
        if stage == "train":same(summary["model_bank_sha256"],None);same(summary["model_audit_sha256"],None)
        else:
            bank,done = io.bank(path)
            for k,v in identity.items():same(bank[k],v);same(done[k],v)
            same(summary["model_bank_sha256"],done["models_sha256"])
            same(summary["model_audit_sha256"],done["model_audit_sha256"])
            require(integer(done["model_audit_completed_ns"]) < integer(summary["collection_started_ns"]),"qualification ran before model audit")
        result = audit_stream(manifest,models,stage,iter(lines(folder/"cases.jsonl.gz")),iter(lines(folder/"events.jsonl.gz")),
            iter(lines(folder/"state_witnesses.jsonl.gz")),summary)
        result = {**identity,"integrity":"PASSED",**result,"collection_artifact_sha256":completion["artifact_sha256"],
            "physical_response_qualified":False,"task_utility_demonstrated":False,"audit_wall_ns":perf_counter_ns()-started}
        io.write(output/"record_audit.json",result)
    except BaseException as error:
        io.write(output/"failed_audit.json",{**identity,"integrity":"FAILED","stage":stage,"error":type(error).__name__,"message":str(error),"wall_ns":perf_counter_ns()-started})
        raise
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("stage",choices=io.STAGES);parser.add_argument("--manifest",required=True,type=Path)
    args = parser.parse_args();result = audit(args.manifest.resolve(),args.stage)
    print(json.dumps({k:result[k] for k in ("integrity","stage","executions","event_count")}))
