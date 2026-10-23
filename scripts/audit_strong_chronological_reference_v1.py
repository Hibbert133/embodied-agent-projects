"""Raw physical/noise/owned-history audit without environment construction."""
import argparse
from collections import deque
from dataclasses import asdict
import gzip
import hashlib
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_strong_chronological_reference_v1 as run
from scripts.audit_chronological_cache_reference import verify_record as legacy_verify
from scripts.audit_acquisition_value_v3 import JournalAudit, compiled_clock_units
from scripts.analyze_action_response import verify_git_inputs
from scripts.audit_passive_supported_reference_v1 import verify as passive_verify
from scripts.audit_history_query_execution_v1 import verify as history_verify
from src.probe.cache_acquisition_evidence_v1 import canonical
from src.probe.chronological_cache_reference import VerifiedPoint
from src.probe.history_query_reference_v1 import OwnedQueryHistoryV1
from src.probe.passive_supported_reference_v1 import MODES, OwnedPassiveCacheV1
from src.rollout.chronological_cache_execution import state_view
from src.rollout.task_registry import create_task_policy


def equal(a, b):
    if canonical(a) != canonical(b): raise ValueError("strong-reference physical record, source or ledger differs")


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        import json
        for line in handle: yield json.loads(line)


def verify_new(record, old_model, joint_model, fault, state, past_queries, events, dt):
    equal(record["state_before"], state_view(state))
    agent = record["agent_record"]; method = record["method"]
    equal(agent["initial"], record["initial"])
    equal([agent["task"], agent["episode"], agent["mode"]], [record["task"], record["episode"], method])
    policy = create_task_policy(record["task"])
    if method in MODES:
        old = OwnedPassiveCacheV1(method, state["cache"]) if state["cache"] else None
        equal(agent["state_before"], old.to_dict() if old else None)
        passive_verify(agent, old_model, policy.get_action)
        after = OwnedPassiveCacheV1.from_dict(agent["state_after"]).point if agent["state_after"] else None
        applied_sequence = agent["outcome"]["last_applied_fit_decision_sequence"]
        fit = next((e["payload"]["fit"] for e in agent["events"] if e["sequence"] == applied_sequence), None)
        equal(record["cache_write_error"], None)
    else:
        history_verify(agent, joint_model, state["cache"], past_queries, policy.get_action)
        after = VerifiedPoint.from_dict(agent["state_after"]) if agent["state_after"] else None
        fit = agent["fit"]
        equal(record["cache_write_error"], agent["cache_write_error"])
    equal(record["fit"], fit)
    seed = int(np.random.SeedSequence([record["seed"], 47001]).generate_state(1)[0])
    noise = np.random.default_rng(seed).normal(0, .05, (500, 3)).astype("<f4")
    equal(record["noise_commitment_oracle"], {"full_sha256": hashlib.sha256(noise.tobytes()).hexdigest(), "rows": 500, "namespace": 47001, "dtype": "little-endian-float32"})
    past = hashlib.sha256(); equal(record["initial_noise_hash"], past.hexdigest())
    for kind in ("FACTORY_INTENT", "FACTORY_COMPLETE", "CONTROLLED_INITIAL"):
        item = events.popleft()
        if item["event"] != kind: raise ValueError("factory/controlled initial order differs")
        if kind == "FACTORY_INTENT":
            equal(item["ledger"], record["ledger_before"]); equal(item["noise_commitment_oracle"], record["noise_commitment_oracle"])
        if kind == "CONTROLLED_INITIAL":
            equal(item["initial"], record["initial"]); equal(item["physics_witness_oracle"], record["initial_physics_witness_oracle"]); equal(item["noise_hash"], past.hexdigest())
    current, calls, agent_index, previous_time = record["initial"], 0, 0, None
    mapping, pending, decisions = {}, None, []
    last_decision = None
    while events and events[0]["event"] != "CACHE_STATE_AFTER_OUTCOME":
        item = events.popleft()
        if item["event"] == "AGENT_EVENT":
            envelope = item["agent_event"]
            equal(envelope, agent["events"][agent_index]); agent_index += 1
            mapping[envelope["sequence"]] = item["sequence"]
            if envelope["event"] == "DECISION":
                last_decision = item
                decisions.append({**item, **envelope["payload"]})
            elif envelope["event"] == "STEP_INTENT":
                if pending is not None: raise ValueError("repeated unconsumed agent command")
                pending = item
            elif envelope["event"] == "STEP_COMPLETE":
                if calls < 1 or envelope["payload"]["host_calls"] != calls: raise ValueError("agent completion before physical result")
            elif envelope["event"] != "TASK_OUTCOME_AND_CACHE": raise ValueError("unknown agent event")
            continue
        if item["event"] != "STEP_INTENT" or pending is None or last_decision is None:
            raise ValueError("unrequested physical step/event")
        p, local = pending["agent_event"]["payload"], pending["agent_event"]["sequence"]
        row, visible = record["trace"][calls], agent["trace"][calls]
        for name in ("before", "command", "raw_policy"):
            equal(item[name], p[name]); equal(row[name], p[name]); equal(visible[name], p[name])
        equal(item["before"], current)
        equal([p["at_host_calls"], item["at_host_calls"], row["host_calls"]], [calls, calls, calls+1])
        equal([item["agent_intent_sequence"], row["agent_intent_sequence"], visible["intent_sequence"]], [local, local, local])
        equal([item["decision_sequence"], row["decision_sequence"]], [mapping[p["decision_sequence"]]]*2)
        equal(visible["decision_sequence"], p["decision_sequence"])
        equal([item["phase"], row["phase"]], [p.get("phase", "POLICY")]*2)
        equal(row["after"], visible["after"])
        equal([item["noise_before_hash"], row["noise_before_hash"]], [past.hexdigest()]*2)
        actual = np.asarray(item["command"], np.float32).copy()
        latent = np.asarray(fault["matrix_xy"], np.float32) @ actual[:2]+np.asarray(fault["bias_xy"], np.float32)
        zone = np.asarray(fault["deadzone_xy"], np.float32)
        actual[:2] = np.sign(latent)*np.maximum(np.abs(latent)-zone, 0)/(1-zone)
        actual[:3] += noise[calls]; actual = np.clip(actual, -1, 1)
        equal(row["executed_action_oracle"], actual.tolist())
        past.update(noise[calls].tobytes()); equal(row["noise_after_hash"], past.hexdigest())
        if not last_decision["saved_ns"] < pending["saved_ns"] < item["saved_ns"] < row["execution_started_ns"] < row["completed_ns"]:
            raise ValueError("execution before saved decision or intents")
        equal(row["intent_saved_ns"], item["saved_ns"])
        if not np.isclose(row["simulation_time_after_oracle"]-row["simulation_time_before_oracle"], dt, rtol=1e-10, atol=1e-10) or previous_time is not None and previous_time != row["simulation_time_before_oracle"]:
            raise ValueError("continuous simulator clock differs")
        previous_time = row["simulation_time_after_oracle"]
        equal(row["target_xy"], (np.asarray(row["after"]["observation"])[:2]-np.asarray(current["observation"])[:2]).tolist())
        completed = events.popleft()
        if completed["event"] != "STEP_COMPLETE": raise ValueError("missing physical completion")
        for name, value in row.items(): equal(completed[name], value)
        equal(row["intent_sequence"], item["sequence"])
        current, calls, pending = row["after"], calls+1, None
    if pending is not None or calls != len(record["trace"]) or agent_index != len(agent["events"]): raise ValueError("incomplete physical/agent correspondence")
    equal(record["agent_global_sequences"], [{"agent_sequence": k, "global_sequence": v} for k, v in mapping.items()])
    equal(record["decisions"], decisions)
    resets = record["ledger_after"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)-record["ledger_before"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
    a = agent["outcome"]; probe = 0 if method in MODES else a["fixed_probe_steps"]
    outcome = {"success": current["success"], "stopped": False if method in MODES else a["stopped"], "total_steps": calls,
        "environment_resets": resets, "fixed_probe_steps": probe,
        "policy_measure_steps": (min(calls, 8) if method == "PASSIVE8_KEEP" else calls) if method in MODES else 0,
        "policy_steps": calls-probe, "deadline_loss": calls if current["success"] else 500,
        "noise_rows_consumed": calls, "online_parameter_fits": a["fit_attempts"], "optimizer_nfev": a["optimizer_nfev"], "policy_queries": a["policy_queries"]}
    equal(record["outcome"], outcome)
    if resets != 1 or calls > 500: raise ValueError("physical reset/budget mismatch")
    state["cache"], state["cusum"] = after, 0.
    equal(record["state_after"], state_view(state))
    cache_event = events.popleft(); equal(cache_event, record["cache_event"])
    equal(cache_event["outcome"], outcome); equal(cache_event["state_after"], record["state_after"])
    if cache_event["event"] != "CACHE_STATE_AFTER_OUTCOME" or cache_event["saved_ns"] <= record["trace"][-1]["completed_ns"] or events:
        raise ValueError("cache transaction not after own actual outcome")


def analyze(path, phase, output):
    if output.exists(): raise FileExistsError("preserve record audit")
    m, old, joint = run.load(path); identity = {k: m[k] for k in run.IDENTITY}; folder = path.parent/phase.lower()
    verify_git_inputs(m)
    for name, h in run.read(folder/"completion.json")["artifact_sha256"].items():
        if run.sha(folder/name) != h: raise ValueError("raw completed artifact changed")
    clocks, journal, rows = compiled_clock_units(m), JournalAudit(identity), []
    coverage = {"passive_rejection_continued": False, "passive_valid_update_applied": False, "passive_actual_cache_written": False,
                "passive_actual_cache_reused": False, "history_nonempty_measure_used": False}
    shared_prefix_steps = 0
    for stream in m["population_oracle"][phase]:
        states = {name: {"cache": None, "cusum": 0.} for name in run.METHODS}
        histories = {name: OwnedQueryHistoryV1(name) for name in run.METHODS}
        expected = iter((c, p) for c in stream["cases"] for p in run.METHODS)
        events = iter(lines(folder/f"events_{stream['stream']:02}.jsonl.gz")); references, probe_references = {}, {}
        for record in lines(folder/f"episodes_{stream['stream']:02}.jsonl.gz"):
            case, method = next(expected)
            equal({k: record[k] for k in (*run.IDENTITY, "phase", "stream", "episode", "task", "seed", "method")},
                  {**identity, "phase": phase, "stream": stream["stream"], "episode": case["episode"], "task": case["task"], "seed": case["seed"], "method": method})
            business = deque(); extra = len(record["agent_record"]["events"]) if method in run.NEW_METHODS else len(record["decisions"])
            required = 5+extra+2*len(record["trace"])
            while len(business) < required:
                event = journal.accept(next(events))
                if event is not None: business.append(event)
            if any(any(event[k] != record[k] for k in (*run.IDENTITY, "stream", "episode", "task", "seed", "method")) for event in business): raise ValueError("foreign case event")
            history_event = business.pop()
            equal(history_event, record["query_history_event"])
            history = histories[method]; equal(record["query_history_before_sha256"], history.sha256)
            queries = history.for_task(case["task"], case["episode"])
            equal(record["clock_contract"], {"model_timestep_s": clocks[case["task"]]["compiled_timestep_seconds"], "frame_skip": 5})
            if method in run.NEW_METHODS:
                verify_new(record, old[case["task"]], joint[case["task"]], case["fault_oracle"], states[method], queries, business, clocks[case["task"]]["env_step_seconds"])
            else:
                legacy_verify(record, old[case["task"]], joint[case["task"]], case["fault_oracle"], states[method], business, clocks[case["task"]]["env_step_seconds"])
            history.append_record(record)
            equal(record["query_history_after_sha256"], history.sha256)
            equal(history_event["before_sha256"], record["query_history_before_sha256"]); equal(history_event["after_sha256"], history.sha256)
            if history_event["event"] != "QUERY_HISTORY_AFTER_OUTCOME" or history_event["saved_ns"] <= record["cache_event"]["saved_ns"]: raise ValueError("future/current query history used too early")
            if journal.ledger != record["ledger_after"]: raise ValueError("case lifecycle ledger differs")
            first = references.setdefault(case["episode"], record)
            equal(record["initial"], first["initial"]); equal(record["initial_physics_witness_oracle"], first["initial_physics_witness_oracle"])
            if record["initial_physics_witness_oracle"]["complete_hidden_state_qualification"] is not False: raise ValueError("source hidden-state qualification changed")
            if method == "ALWAYS8": probe_references[case["episode"]] = record
            elif case["episode"] in probe_references:
                base, shared = probe_references[case["episode"]], 0
                for a, b in zip(record["trace"], base["trace"]):
                    if a["command"] != b["command"]: break
                    for key in ("before", "after", "noise_before_hash", "noise_after_hash", "executed_action_oracle", "simulation_time_before_oracle", "simulation_time_after_oracle"): equal(a[key], b[key])
                    shared += 1
                action = record["decisions"][0]["action"]
                required_prefix = 8 if action in ("PROBE8", "PROBE16") else 4 if action == "CHECK4" else 0
                if shared < min(required_prefix, len(record["trace"]), len(base["trace"])): raise ValueError("required fixed probe prefix mismatch")
                for cutoff in (4, 8, 16):
                    if shared >= cutoff: equal(record["boundary_physics_witness_oracle"][str(cutoff)], base["boundary_physics_witness_oracle"][str(cutoff)])
                shared_prefix_steps += shared
            if method in MODES:
                coverage["passive_rejection_continued"] |= any(d["action"] == "REJECT_UPDATE_KEEP" and len(record["trace"]) > d["at_host_calls"] for d in record["decisions"])
                coverage["passive_valid_update_applied"] |= any(d["action"] == "ACCEPT_UPDATE" and len(record["trace"]) > d["at_host_calls"] for d in record["decisions"])
                after = record["state_after"]["cache"]
                coverage["passive_actual_cache_written"] |= after is not None and after["source_episode"] == record["episode"]
                coverage["passive_actual_cache_reused"] |= record["state_before"]["cache"] is not None and len(record["trace"]) > 0
            if method == "TASK_HISTORY_IVR4": coverage["history_nonempty_measure_used"] |= any(bool(d.get("check", {}).get("history_measure", {}).get("past_queries")) for d in record["decisions"])
            rows.append(run.compact_case(record, stream))
        if next(expected, None) is not None or next(events, None) is not None: raise ValueError("missing cases or extra events")
        journal.boundary(); print(f"record audit {phase} stream={stream['stream']}: {len(rows)}", flush=True)
    summary = run.read(folder/"summary.json"); limits = m["config"][phase.lower()]
    expected_status = {**identity, "phase": phase, "status": "COMPLETED_REFERENCE", "executions": len(rows),
        "controlled_steps": sum(r["total_steps"] for r in rows), "controlled_resets": len(rows), "lifecycle": journal.ledger}
    equal(run.read(folder/"status.json"), expected_status)
    for key, value in expected_status.items(): equal(summary[key], value)
    equal(summary["cases"], rows)
    equal(summary["statistics"], run.statistics(rows, phase))
    if len(rows) != limits["executions"] or sum(r["total_steps"] for r in rows) != summary["controlled_steps"]: raise ValueError("complete population or step cost differs")
    counts, parts = journal.ledger["counts"], journal.ledger["by_phase"]
    if any(counts.get(k, 0) for k in ("reset_errors", "simulation_errors", "uncertain_simulation_frames", "frame_budget_rejections")): raise ValueError("unresolved lifecycle error")
    if (parts["CONTROL"]["simulation_completed"] != summary["controlled_steps"] or parts["CONTROL"].get("reset_attempts", 0) or
        parts["CONTROLLED_RESET"]["reset_completed"] != len(rows) or parts["GOAL_GENERATION"]["reset_completed"] != 50*len(rows) or
        counts["simulation_frames_completed"] != 500*counts["reset_completed"]+5*summary["controlled_steps"] or counts["simulation_frames_completed"] > limits["maximum_simulation_frames"]):
        raise ValueError("full reset/frame/control cost mismatch")
    required_coverage = coverage["passive_rejection_continued"] and coverage["history_nonempty_measure_used"]
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {**identity, "phase": phase, "integrity": "PASSED", "executions": len(rows), "events_checked": journal.sequence,
        "coverage": coverage, "required_integrity_coverage": required_coverage,
        "matched_initial_comparisons": len(rows)-sum(len(s["cases"]) for s in m["population_oracle"][phase]),
        "matched_physical_prefix_steps": shared_prefix_steps, "lifecycle": journal.ledger, "summary_sha256": run.sha(folder/"summary.json"),
        "audit_policy_queries": sum(r["policy_queries"] for r in rows), "audit_shared_fitter_attempts": sum(r["online_parameter_fits"] for r in rows),
        "audit_shared_optimizer_nfev": sum(r["optimizer_nfev"] for r in rows), "new_environment_steps": 0, "new_api_calls": 0,
        "script_sha256": run.sha(Path(__file__)), "complete_hidden_state_qualified": False,
        "scope": "Independent physical/noise/journal and saved-control replay; shared legacy actor/fit math, passive numerical fitter, cache/encoder and query provenance store. Independent Woodbury/normal-CDF task-IVR moments. Separate statistics audit required."}
    run.write(output, result, exclusive=True)
    print({k: result[k] for k in ("phase", "integrity", "executions", "required_integrity_coverage")}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--phase", choices=("SMOKE", "MAIN"), required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); analyze(args.manifest.resolve(), args.phase, args.output.resolve())
