"""Post-hoc traces for two previously reported extreme cases, not agent evidence."""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

from replay_paired_probe_results_v1 import ROOT, STUDY, RECEIPTS, read, sha, verify_saved


SELECTED = {19218: 1, 19493: 24}
PROGRAMS = ("REUSE_OLD", "PROBE_KEEP", "PROBE_UPDATE", "PROBE_UPDATE_KEEP")


def push_mode(observation):
    """Descriptive branch of the bound fixed push policy, from pre-action data."""
    obs = np.asarray(observation, dtype=float)
    adjusted_puck = obs[4:7] + [-.005, 0, 0]
    if np.linalg.norm(obs[:2] - adjusted_puck[:2]) > .02:
        return "ALIGN_XY"
    if abs(obs[2] - adjusted_puck[2]) > .04:
        return "DESCEND"
    return "PUSH_TO_GOAL"


def describe(case, record, trace):
    policies = [x for x in trace if x["phase"] == "POLICY"]
    if len(trace) != record["outcome"]["suffix_steps"]:
        raise ValueError("trace/outcome length differs")
    if len(policies) != record["outcome"]["policy_queries"]:
        raise ValueError("saved policy-query count differs")
    final = record["final_observation"]["observation"]
    if trace[-1]["after"] != record["final_observation"]:
        raise ValueError("final public observation differs")
    if case["task"] == "push-v3":
        modes = [push_mode(x["before"]["observation"]) for x in policies]
        distances = [float(np.linalg.norm(np.asarray(x["before"]["observation"])[4:7] - np.asarray(x["before"]["observation"])[-3:])) for x in policies]
        final_distance = float(np.linalg.norm(np.asarray(final)[4:7] - np.asarray(final)[-3:]))
    else:
        modes = ["REACH" for _ in policies]
        distances = [float(np.linalg.norm(np.asarray(x["before"]["observation"])[:3] - np.asarray(x["before"]["observation"])[-3:])) for x in policies]
        final_distance = float(np.linalg.norm(np.asarray(final)[:3] - np.asarray(final)[-3:]))
    return {
        "future": record["future"], "program": record["program"],
        "outcome": record["outcome"], "fit": record["fit"],
        "policy_modes": modes, "policy_mode_counts": dict(Counter(modes)),
        "last_100_or_fewer_mode_counts": dict(Counter(modes[-100:])),
        "mode_switch_count": sum(a != b for a, b in zip(modes, modes[1:])),
        "target_distance_before_policy_m": distances,
        "final_target_distance_m": final_distance,
        "xy_command_at_bound_count": sum(any(abs(v) == 1 for v in x["command"][:2]) for x in policies),
        "trace": trace,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()) or output == RECEIPTS.resolve() or output.exists():
        parser.error("output must be a new subdirectory inside the replay-receipt directory")
    started = perf_counter_ns()
    manifest, bindings, _ = verify_saved("MAIN")
    cases = {}
    for seed, stream in SELECTED.items():
        with gzip.open(STUDY / "main" / f"cases_{stream:02d}.jsonl.gz", "rt", encoding="utf-8") as handle:
            matches = [row for row in map(json.loads, handle) if row["seed"] == seed]
        if len(matches) != 1 or matches[0]["disposition"] != "WARM_ELIGIBLE":
            raise ValueError("missing or duplicate selected case")
        cases[seed] = matches[0]
    records = {(seed, x["future"], x["program"]): x for seed, case in cases.items() for x in case["evaluations"]}
    if len(records) != 64 or any(key[2] not in PROGRAMS for key in records):
        raise ValueError("complete four-program eight-future cases required")
    traces = {key: [] for key in records}
    commands = {}
    choices = {}
    selected_events = 0
    lines_scanned = 0
    needles = [f'"seed": {seed},'.encode() for seed in SELECTED]
    max_sequence = max(record["end_sequence"] for record in records.values())
    last_seen = -1
    with gzip.open(STUDY / "main/events.jsonl.gz", "rb") as handle:
        for line in handle:
            lines_scanned += 1
            if not any(needle in line for needle in needles):
                continue
            event = json.loads(line)
            if event.get("seed") not in SELECTED or event.get("role") != "EVAL":
                continue
            if event["manifest_id"] != manifest["manifest_id"] or event["sequence"] <= last_seen:
                raise ValueError("event identity or order differs")
            last_seen = event["sequence"]
            key = (event["seed"], event["future"], event["program"])
            if key not in records:
                raise ValueError("unexpected evaluation identity")
            selected_events += 1
            if event["event"] == "AGENT_EVENT":
                payload = event["public_payload"]
                if event["agent_event"] == "COMMAND":
                    commands[event["sequence"]] = payload
                elif event["agent_event"] == "CHOICE":
                    choices[event["sequence"]] = payload
            elif event["event"] == "STEP_COMPLETE":
                command = commands.pop(event["global_command_sequence"])
                if command["at_calls"] != event["logical_step"] or command["command"] != event["command"] or command["raw_policy"] != event["raw_policy"]:
                    raise ValueError("saved command/physical step mismatch")
                traces[key].append({
                    "logical_step": event["logical_step"], "phase": event["phase"],
                    "before": command["before"], "after": event["after"],
                    "command": event["command"], "raw_policy": event["raw_policy"],
                    "command_sequence": event["global_command_sequence"],
                    "step_sequence": event["sequence"],
                    "simulation_time_before": event["simulation_time_before"],
                    "simulation_time_after": event["simulation_time_after"],
                })
            if event["sequence"] == max_sequence:
                break
    if commands or last_seen != max_sequence:
        raise ValueError("unmatched commands or incomplete selected range")
    result = []
    for seed, case in cases.items():
        summaries = []
        for record in case["evaluations"]:
            key = (seed, record["future"], record["program"])
            trace = traces[key]
            expected = list(range(4, record["outcome"]["total_steps"]))
            if [x["logical_step"] for x in trace] != expected:
                raise ValueError("noncontiguous actual suffix")
            if any(a["after"] != b["before"] for a, b in zip(trace, trace[1:])):
                raise ValueError("public observation continuity differs")
            saved = [{"global_sequence": seq, "payload": choices[seq]} for seq in record["choice_global_sequences"]]
            summary = describe(case, record, trace)
            summary["saved_choices"] = saved
            summaries.append(summary)
        pair_checks = []
        for future in range(1, 9):
            p, u, k = [next(x for x in summaries if x["future"] == future and x["program"] == arm) for arm in PROGRAMS[1:]]
            for other in (u, k):
                for x, y in zip(p["trace"][:4], other["trace"][:4]):
                    if any(x[field] != y[field] for field in ("logical_step", "phase", "before", "after", "command")):
                        raise ValueError("common physical probe prefix differs")
            if not u["fit"]["valid"] or u["fit"] != k["fit"] or u["outcome"] != k["outcome"]:
                raise ValueError("selected cases no longer have the reported valid identical U/K")
            for x, y in zip(u["trace"], k["trace"]):
                if any(x[field] != y[field] for field in ("logical_step", "phase", "before", "after", "command", "raw_policy")):
                    raise ValueError("valid U/K trajectories differ")
            first_p = next(x for x in p["trace"] if x["phase"] == "POLICY")
            first_k = next(x for x in k["trace"] if x["phase"] == "POLICY")
            if first_p["before"] != first_k["before"] or first_p["raw_policy"] != first_k["raw_policy"]:
                raise ValueError("first post-probe policy query not matched")
            pair_checks.append({"future": future, "first_policy_logical_step": first_p["logical_step"],
                                "same_observation_and_raw_policy": True,
                                "different_sent_command": first_p["command"] != first_k["command"]})
        result.append({"seed_evaluator_only": seed, "stream_evaluator_only": case["stream"], "task": case["task"],
                       "selection": "Previously reported extreme observed mean effect; post-hoc, not a prospective category.",
                       "cache_before": case["cache_before"], "public_evidence_at4": case["evidence"],
                       "saved_references_at4": {name: {key: value[key] for key in ("action", "reason", "score", "ivr")} for name, value in case["references"].items()},
                       "paired_checks": pair_checks, "programs": summaries})
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError("bound source changed during extraction")
    output.mkdir(parents=True, exist_ok=False)
    with (output / "case_traces.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump({"scope": "Evaluator-only retrospective description; future outcomes and case IDs are not online evidence.", "cases": result}, handle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        handle.write("\n")
    receipt = {
        "schema": "paired_probe_extreme_case_trace_v1", "manifest_id": manifest["manifest_id"],
        "source_events_sha256": sha(STUDY / "main/events.jsonl.gz"),
        "source_case_files_sha256": {f"cases_{stream:02d}.jsonl.gz": sha(STUDY / "main" / f"cases_{stream:02d}.jsonl.gz") for stream in SELECTED.values()},
        "script_sha256": sha(Path(__file__)), "source_verifier_sha256": sha(Path(__file__).with_name("replay_paired_probe_results_v1.py")),
        "python": sys.version, "numpy": np.__version__, "selected_seeds_evaluator_only": list(SELECTED),
        "source_lines_scanned": lines_scanned, "selected_events": selected_events,
        "programs": len(records), "actual_suffix_steps_reconstructed": sum(map(len, traces.values())),
        "source_events_scan_completed_through_sequence": last_seen,
        "common_eight_step_boundary_checks": 16, "identical_valid_update_trajectories": 16,
        "generation_body_wall_ns": perf_counter_ns() - started,
        "new_simulation_steps": 0, "new_api_calls": 0, "new_fits": 0, "new_policy_queries": 0,
        "new_thresholds_or_selectors": 0, "new_confidence_intervals": 0,
        "artifact_sha256": {"case_traces.json": sha(output / "case_traces.json")},
        "scope": "Read existing physical trajectories; no counterfactual execution, new outcome, causal attribution to a parameter component or online method validation.",
    }
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({key: receipt[key] for key in ("programs", "actual_suffix_steps_reconstructed", "selected_events", "generation_body_wall_ns")}))


if __name__ == "__main__":
    main()
