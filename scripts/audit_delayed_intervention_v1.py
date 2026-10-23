"""Read-only independent grammar replay of the live step-16 qualification.

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
from src.analysis import delayed_qualification_io_v1 as io
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
ROW_KEYS = ("unit", "task", "seed", "variant", "completed", "success", "stopped", "total_steps",
            "deadline_loss", "boundary_ready", "host_attempts", "host_returned", "policy_queries",
            "parameter_fit_attempts", "parameter_fit_results", "optimizer_nfev", "optimizer_nfev_complete")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "strict nonnegative integer required")
    return value


def audit_case(events, record, identity, fault, model, *, initial_ledger=None,
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
    check_ledger(ledger);ledger_before = deepcopy(ledger)
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

    def move(choice, command=None, namespace="AGENT_EVENT", direct=False):
        nonlocal ledger, clock, current, steps, queries
        require(live() and steps < 500, "step after termination or exhausted budget")
        if command is None:
            phase = "POLICY";raw = np.asarray(policy.get_action(np.array(current["observation"], copy=True)), np.float32).tolist()
            controller = choice["candidate_map"][choice["action_id"]] if namespace == "DELAYED_AGENT_EVENT" else choice["controller"]
            command = encode_controller(controller, raw).tolist();queries += 1
        else:
            phase = "FIXED_PROBE";raw = None
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
    intervention = None;end_witness = boundary_witness;variant = identity["variant"]

    def provenance(choice):
        return {"source_global_sequence": source_global[choice["sequence"]], "source_public_sequence": choice["sequence"],
                "available_at_calls": choice["at_calls"], "source_choice_sha256": digest(choice)}

    if ready and variant == "DIRECT_CURRENT":
        branch = {"role": "DIRECT_CONTINUATION", "future": 0, "program": variant}
        row = event("DIRECT_CONTINUATION_START", {"at_calls": 16,
            "source_choice_global_sequence": source_global[current_choice["sequence"]], **boundary_witness}, branched=True)
        while live() and steps < 500: move(current_choice, direct=True)
        row = take("DIRECT_CONTINUATION_COMPLETE", ("completed_steps", "success", "deadline_loss", "end_witness"), branched=True)
        end_witness = witness(row["end_witness"])
        require(set(row["end_witness"]) == set(WITNESS), "strict final witness required")
        intervention = {"completed_steps": steps, "success": current["success"],
                        "deadline_loss": steps if current["success"] else 500, "end_witness": end_witness}
        for key, value in intervention.items(): same(row[key], value)
    elif ready:
        branch = {"role": "DELAYED_INTERVENTION", "future": 0, "program": variant}
        before_suffix = deepcopy(ledger)
        current_provenance = provenance(current_choice);saved_provenance = provenance(saved_choice)
        suffix_start = event("DELAYED_INTERVENTION_START", {"logical_step": 16,
            "current_provenance": current_provenance, "saved_provenance": saved_provenance,
            "ledger": ledger, "reset_before": reset_before, **boundary_witness}, branched=True)
        catalog = {"CONTINUE_CURRENT": current_choice["controller"], "RUN_UNCORRECTED": identity_controller(),
                   "STOP": None, "SWITCH_SAVED": saved_choice["controller"]}
        _, choice = public("CHOICE", {"action_id": variant, "at_calls": 16, "boundary_observation": current,
            "task": identity["task"], "remaining_budget": 484, "candidate_map": catalog,
            "candidate_map_sha256": digest(catalog)}, "DELAYED_AGENT_EVENT")
        if variant != "STOP":
            while live() and steps < 500: move(choice, namespace="DELAYED_AGENT_EVENT")
        actor = {"status": "STOPPED" if variant == "STOP" else "COMPLETED", "failure": None,
            "initial_completed_steps": 16, "completed_steps": steps, "charged_steps": steps, "remaining_budget": 500 - steps,
            "step_attempts": steps - 16, "accepted_step_receipts": steps - 16, "unconfirmed_step_attempts": 0,
            "policy_queries_attempted": steps - 16, "policy_queries_completed": steps - 16,
            "last_confirmed_observation": current, "choice": choice, "success": current["success"],
            "deadline_loss": steps if current["success"] else 500, "events": delayed}
        row = take("DELAYED_INTERVENTION_COMPLETE", ("start_sequence", "actor", "ledger_before", "ledger_after",
            "host_completed_suffix_steps", "host_policy_queries", "end_witness", "current_provenance", "saved_provenance"), branched=True)
        require(set(row["end_witness"]) == set(WITNESS), "strict final witness required")
        end_witness = witness(row["end_witness"])
        if variant == "STOP": same(end_witness, boundary_witness)
        expected = {**branch, "start_sequence": suffix_start["sequence"], "actor": actor, "ledger_before": before_suffix,
            "ledger_after": ledger, "host_completed_suffix_steps": steps - 16, "host_policy_queries": steps - 16,
            "end_witness": end_witness, "current_provenance": current_provenance, "saved_provenance": saved_provenance}
        for key, value in expected.items(): same(row[key], value)
        intervention = {**expected, "end_sequence": row["sequence"]}
    require(cursor == len(events), "unexpected trailing event, reset, snapshot or replay")
    expected_record = {**identity, "fault_oracle": fault, "completed": True, "error": None, "close_error": None,
        "environment_closed": True, "ledger_before": ledger_before, "prefix": prepared, "intervention": intervention,
        "physical_rows": physical, "host_attempts": steps, "host_returned": steps, "policy_queries": queries,
        "captures": 0, "restores": 0, "computation_counters_complete": True, "initial_witness": initial_witness,
        "success": current["success"], "total_steps": steps, "deadline_loss": steps if current["success"] else 500,
        "boundary_ready": ready, "stopped": (ready and variant == "STOP") or reason in ("INVALID_FOUR", "INVALID_EIGHT"),
        "end_witness": end_witness, "final_observation": current, "ledger_before_close": ledger, "ledger_after_close": ledger,
        "parameter_fit_attempts": len(fits), "parameter_fit_results": len(fits), "optimizer_nfev": nfev, "optimizer_nfev_complete": True}
    same(record, expected_record)
    return {"ledger": ledger, "last_sequence": sequence, "last_saved_ns": stamp,
            "recomputed_policy_queries": queries, "recomputed_parameter_fits": len(fits), "recomputed_optimizer_nfev": nfev}


def compare_population(records, config):
    """Descriptive fixed-population gate; no tuning, confidence intervals or selection."""
    expected = [(i, spec["task"], spec["seed"], v) for i, spec in enumerate(config["tasks_and_seeds"]) for v in config["variants"]]
    require([(r["unit"], r["task"], r["seed"], r["variant"]) for r in records] == expected, "incomplete or reordered allocated population")
    checks = [];distinct_tasks = 0;direct_tasks = 0
    for unit, spec in enumerate(config["tasks_and_seeds"]):
        group = {r["variant"]: r for r in records if r["unit"] == unit}
        first = group["CONTINUE_CURRENT"];ready = all(r["boundary_ready"] for r in group.values())
        matched = ready and all(digest(r["initial_witness"]) == digest(first["initial_witness"])
            and digest(r["prefix"]["boundary_witness"]) == digest(first["prefix"]["boundary_witness"])
            and digest(r["prefix"]["public"]["events"][0]["payload"]["initial"]) == digest(first["prefix"]["public"]["events"][0]["payload"]["initial"])
            and physical_rows_equal(r["physical_rows"], first["physical_rows"], 16) for r in group.values())
        other = group["DIRECT_CURRENT"]
        direct = ready and first["total_steps"] == other["total_steps"] and physical_rows_equal(first["physical_rows"], other["physical_rows"], first["total_steps"])
        direct = direct and all(digest(first[k]) == digest(other[k]) for k in ("end_witness", "final_observation", "host_attempts", "host_returned", "policy_queries"))
        direct_tasks += int(direct)
        movers = [group[v] for v in ("CONTINUE_CURRENT", "SWITCH_SAVED", "RUN_UNCORRECTED")]
        distinct = ready and all(len(r["physical_rows"]) > 16 for r in movers) and len({digest(r["physical_rows"][16]["command"]) for r in movers}) == 3
        distinct_tasks += int(distinct)
        stopped = group["STOP"]
        checks.append({**spec, "all_boundaries_ready": ready, "matched_prefixes": matched,
            "direct_loop_equal": direct, "three_distinct_first_commands": distinct,
            "stop_has_zero_suffix": stopped["boundary_ready"] and stopped["total_steps"] == 16})
    qualified = all(c[k] for c in checks for k in ("all_boundaries_ready", "matched_prefixes", "direct_loop_equal", "stop_has_zero_suffix"))
    qualified = qualified and direct_tasks == config["required_direct_comparison_tasks"] and distinct_tasks >= config["minimum_tasks_with_three_distinct_first_commands"]
    table = []
    for variant in config["variants"]:
        rows = [r for r in records if r["variant"] == variant]
        table.append({"variant": variant, "executions": len(rows), "successes": sum(r["success"] for r in rows),
            "failures": sum(not r["success"] for r in rows), "stops": sum(r["stopped"] for r in rows),
            "unavailable_boundaries": sum(not r["boundary_ready"] for r in rows),
            "control_steps": sum(r["total_steps"] for r in rows), "deadline_loss_total": sum(r["deadline_loss"] for r in rows),
            "historical_nominal_cost": config["historical_nominal_cost"],
            "historical_steps_amortized_per_unit": config["historical_nominal_cost"]["environment_steps"] / config["source_amortization_units_per_variant"]})
    return {"qualification": "QUALIFIED" if qualified else "NOT_QUALIFIED", "task_checks": checks, "methods": table,
            "execution_rows": [{k: r[k] for k in ROW_KEYS} for r in records],
            "failures": [{k: r[k] for k in ROW_KEYS} for r in records if not r["success"]],
            "unavailable_boundaries": [{"task": r["task"], "variant": r["variant"], "reason": r["prefix"]["public"]["reason"]}
                                       for r in records if not r["boundary_ready"]]}


def read_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def audit(path):
    manifest, models = io.load(path);config = manifest["config"]
    folder = path.parent / "collection";output = path.parent / "audit";output.mkdir()
    identity = {k: manifest[k] for k in io.IDENTITY};started = perf_counter_ns()
    result = {**identity, "integrity": "FAILED", "qualification": "NOT_ESTABLISHED", "failure": None}
    try:
        completion = io.read(folder / "completion.json")
        require(completion["status"] == "COLLECTED_FOR_INDEPENDENT_AUDIT", "partial collection cannot qualify")
        for key in io.IDENTITY: same(completion[key], identity[key])
        require(set(completion["artifact_sha256"]) == {"events.jsonl.gz", "cases.jsonl.gz", "summary.json", "status.json"}, "complete collection bindings required")
        for name, expected in completion["artifact_sha256"].items(): same(io.sha(folder / name), expected)
        records = read_lines(folder / "cases.jsonl.gz");events = read_lines(folder / "events.jsonl.gz")
        expected_keys = [(i, spec["task"], spec["seed"], v) for i, spec in enumerate(config["tasks_and_seeds"]) for v in config["variants"]]
        same([(r["unit"], r["task"], r["seed"], r["variant"]) for r in records], expected_keys)
        position = 0;ledger = {"counts": {}, "by_phase": {}};sequence = stamp = -1;computations = []
        for key, row in zip(expected_keys, records):
            allocation = dict(zip(("unit", "task", "seed", "variant"), key));group = []
            while position < len(events) and all(events[position].get(k) == v for k, v in allocation.items()):
                group.append(events[position]);position += 1
            checked = audit_case(group, row, {**identity, **allocation}, config["fault_oracle"], models[row["task"]],
                initial_ledger=ledger, previous_sequence=sequence, previous_saved_ns=stamp)
            ledger = checked["ledger"];sequence = checked["last_sequence"];stamp = checked["last_saved_ns"]
            computations.append({k: v for k, v in checked.items() if k.startswith("recomputed_")})
        require(position == len(events), "foreign or trailing execution events")
        summary = io.read(folder / "summary.json");check_ledger(ledger)
        for key in io.IDENTITY: same(summary[key], identity[key])
        same(summary["status"], "COLLECTED_FOR_INDEPENDENT_AUDIT");same(summary["failure"], None)
        same(summary["rows"], [{k: r[k] for k in ROW_KEYS} for r in records])
        same(summary["lifecycle"], ledger);same(summary["completed_executions"], 15)
        controls = sum(r["total_steps"] for r in records);same(summary["controlled_steps"], controls)
        require(controls <= config["maximum_environment_steps"], "control budget exceeded")
        same(ledger["counts"]["reset_completed"], 765)
        same(ledger["by_phase"]["CONTROLLED_RESET"]["reset_completed"], config["maximum_controlled_resets"])
        same(ledger["counts"]["simulation_frames_completed"], 15 * 25500 + controls * 5)
        require(ledger["counts"]["simulation_frames_attempted"] <= config["maximum_simulation_frames"], "frame budget exceeded")
        for key in ("new_api_calls", "new_nominal_training", "new_selector_fits", "policy_updates"): same(summary[key], 0)
        integer(summary["wall_ns"])
        same(io.read(folder / "status.json"), {k: v for k, v in summary.items() if k != "rows"})
        result.update(integrity="PASSED", **compare_population(records, config), event_count=len(events), executions=len(records),
            costs={"new_control_steps": controls, "lifecycle": ledger, "collection_wall_ns": summary["wall_ns"],
                "host_attempts": sum(r["host_attempts"] for r in records), "host_returned": sum(r["host_returned"] for r in records),
                "policy_queries": sum(r["policy_queries"] for r in records), "parameter_fit_attempts": sum(r["parameter_fit_attempts"] for r in records),
                "parameter_fit_results": sum(r["parameter_fit_results"] for r in records), "optimizer_nfev": sum(r["optimizer_nfev"] for r in records),
                "historical_nominal_cost_paid_once": config["historical_nominal_cost"], "historical_design_preparation": config["historical_design_preparation"],
                "new_api_calls": 0, "new_nominal_training": 0, "new_selector_fits": 0, "policy_updates": 0},
            audit_computations={k: sum(c[k] for c in computations) for k in computations[0]},
            collection_artifact_sha256={**completion["artifact_sha256"], "completion.json": io.sha(folder / "completion.json")},
            limitations=["NATIVE_HASHES_ARE_HOST_WITNESSES", "SHARED_FIXED_POLICY_ESTIMATORS_AND_ENCODING",
                "ONLY_THREE_QUALIFICATION_STATES_NOT_METHOD_UTILITY", "C4_WAS_UNUSED_CANDIDATE_NOT_PREVIOUSLY_ACCEPTED_MEMORY"])
    except BaseException as error:
        result["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        result["audit_wall_ns"] = perf_counter_ns() - started
        io.write(output / "record_audit.json", result)
    write_report(output, result)
    return result


def write_report(output, result):
    """Chinese descriptive report from the audited complete population only."""
    require(result["integrity"] == "PASSED", "report requires independently reconstructed complete records")
    costs = result["costs"];source = costs["historical_nominal_cost_paid_once"]
    lines = ["# 中途干预执行资格结果", "",
        "本报告只验证保存的选择能否从真实当前状态驱动后续动作。没有在线触发器或 LLM，不检验新算法任务收益。",
        "", f"- 日志完整性：**{result['integrity']}**。",
        f"- 执行资格：**{result['qualification']}**。",
        f"- 完整分配：{result['executions']} 次执行，{result['event_count']} 条事件。",
        f"- 来源提交：`{result['source_git_commit']}`；清单：`{result['manifest_id']}`。", "",
        "## 方法和结果", "",
        "先用四步探测保存尚未应用的 C4，再用八步数据估计 C8；C8 实际控制到第16步。每种操作独立支付完整前缀。",
        "CONTINUE_CURRENT 继续 C8；SWITCH_SAVED 换成保存的 C4；RUN_UNCORRECTED 去掉纠正；STOP 停止；DIRECT_CURRENT 用普通循环继续 C8，检查干预接口是否保持原行为。", "",
        "|操作|成功/分母|失败|停止|边界不可用|实际控制步总数|平均截止损失|历史控制步/单元|",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["methods"]:
        lines.append(f"|{row['variant']}|{row['successes']}/{row['executions']}|{row['failures']}|{row['stops']}|{row['unavailable_boundaries']}|{row['control_steps']}|{row['deadline_loss_total']/row['executions']:.6f}|{row['historical_steps_amortized_per_unit']:.0f}|")
    lines += ["", "失败或停止的截止损失均为500；提前成功按实际步数计。停止始终保留在分母中。三个资格状态不能支持方法优越性、等效或非劣结论。", "",
        "## 全部案例", "", "|任务|种子|操作|成功|停止|边界可用|实际步数|截止损失|", "|---|---:|---|---|---|---|---:|---:|"]
    yes = lambda value: "是" if value else "否"
    for row in result["execution_rows"]:
        lines.append(f"|{row['task']}|{row['seed']}|{row['variant']}|{yes(row['success'])}|{yes(row['stopped'])}|{yes(row['boundary_ready'])}|{row['total_steps']}|{row['deadline_loss']}|")
    lines += ["", "## 匹配和真实消费检查", "",
        "|任务|五个边界均可用|16步前缀匹配|干预继续与普通循环一致|三种首条命令不同|停止后零步|",
        "|---|---|---|---|---|---|"]
    for row in result["task_checks"]:
        lines.append("|" + row["task"] + "|" + "|".join(yes(row[k]) for k in ("all_boundaries_ready", "matched_prefixes", "direct_loop_equal", "three_distinct_first_commands", "stop_has_zero_suffix")) + "|")
    for row in result["unavailable_boundaries"]:
        lines.append(f"\n边界不可用：{row['task']} / {row['variant']}，原因 `{row['reason']}`；未替换案例。")
    lines += ["", "## 完整费用", "",
        f"新增控制步骤 {costs['new_control_steps']}，控制尝试/返回 {costs['host_attempts']}/{costs['host_returned']}。",
        f"实际政策查询 {costs['policy_queries']}，参数拟合尝试/完成 {costs['parameter_fit_attempts']}/{costs['parameter_fit_results']}，优化器 nfev {costs['optimizer_nfev']}。",
        f"全部重置 {costs['lifecycle']['counts']['reset_completed']}，其中受控初始重置 {costs['lifecycle']['by_phase']['CONTROLLED_RESET']['reset_completed']}；请求和完成仿真帧 {costs['lifecycle']['counts']['simulation_frames_attempted']}/{costs['lifecycle']['counts']['simulation_frames_completed']}。",
        f"采集主体耗时 {costs['collection_wall_ns']/1e9:.6f} 秒；只读审计耗时 {result['audit_wall_ns']/1e9:.6f} 秒。审计另付重算政策查询 {result['audit_computations']['recomputed_policy_queries']}、拟合 {result['audit_computations']['recomputed_parameter_fits']}、nfev {result['audit_computations']['recomputed_optimizer_nfev']}，不产生新环境步骤。",
        f"历史名义数据实际收集过一次：{source['environment_steps']} 控制步、{source['controlled_resets']} 受控重置、{source['all_reset_calls']} 全部重置、{source['simulation_frames']} 帧。各变体均计完整来源，按各自三个单元摊销；没有除以15而稀释费用。历史设计3次枚举、432个候选，本次不重做。",
        "新增 API 调用、名义训练、选择器拟合和政策权重更新均为0。上述采集/审计主体计时不包含进程启动；软件测试物理费用见冻结前 software_v1 回执，不能算作 MetaWorld 任务数据。", "",
        "## 结论边界", "",
        "日志重建核对了候选来源、保存与执行顺序、固定政策输出、纠正映射、实际噪声消费、物理时钟和完整成本。原生及语义哈希由主机生成，是一致性见证，不是独立外部物理真实性证明。",
        "C4 是同一任务中计算但此前未用于任务动作的候选；切换到 C4 不等于恢复过去物理状态，也不证明自然记忆或跨任务回退能力。估计来自受控初始重置后的前四/八步，不证明接触阶段中途重新辨识有效。",
        "无论执行资格是否通过，本轮均不作为算法创新或 CCF A 发表证据。仍需合法历史上的决策方法、强基线、独立任务验证、消融和完整论文。", ""]
    report = output / "report_zh.md"
    with report.open("x", encoding="utf-8", newline="\n") as handle: handle.write("\n".join(lines))
    io.write(output / "report_receipt.json", {**{k: result[k] for k in io.IDENTITY}, "integrity": result["integrity"],
        "qualification": result["qualification"], "record_audit_sha256": io.sha(output / "record_audit.json"),
        "report_sha256": io.sha(report), "report_source_sha256": io.sha(Path(__file__)), "execution_rows": len(result["execution_rows"])})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args();result = audit(args.manifest.resolve())
    print(json.dumps({k: result[k] for k in ("integrity", "qualification", "executions", "event_count", "audit_wall_ns")}))
