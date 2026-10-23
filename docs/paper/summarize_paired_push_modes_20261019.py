"""Exploratory full-push-population mode accounting from existing P/K records."""

import argparse
from collections import Counter, deque
import csv
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

from replay_paired_probe_results_v1 import ROOT, STUDY, RECEIPTS, read, sha, verify_saved
from extract_paired_probe_case_trace_20261019 import push_mode


PROGRAMS = ("PROBE_KEEP", "PROBE_UPDATE_KEEP")
MODES = ("ALIGN_XY", "DESCEND", "PUSH_TO_GOAL")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()) or output == RECEIPTS.resolve() or output.exists():
        parser.error("output must be a new subdirectory inside the replay-receipt directory")
    started = perf_counter_ns()
    manifest, bindings, _ = verify_saved("MAIN")
    policy = ROOT / ".venv/Lib/site-packages/metaworld/policies/sawyer_push_v3_policy.py"
    if sha(policy) != manifest["policy_sha256"]["push-v3"]:
        raise ValueError("fixed-policy implementation differs from source")
    records = {}
    for path in sorted((STUDY / "main").glob("cases_*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for case in map(json.loads, handle):
                if case["task"] != "push-v3" or case["disposition"] != "WARM_ELIGIBLE":
                    continue
                for record in case["evaluations"]:
                    if record["program"] not in PROGRAMS:
                        continue
                    key = (case["stream"], case["episode"], record["future"], record["program"])
                    if key in records:
                        raise ValueError("duplicate actual evaluation")
                    records[key] = {"case": case, "record": record, "steps": 0, "policy_steps": 0,
                                    "last_after": case["evidence"]["prefix"]["observations"][-1],
                                    "counts": Counter(), "longest": Counter(), "current_mode": None,
                                    "current_run": 0, "switches": 0, "tail": deque(maxlen=100)}
    if len(records) != 2048 or len({key[:2] for key in records}) != 128:
        raise ValueError("complete saved push population required")
    pending = {}
    lines = selected = actual = 0
    last_sequence = -1
    with gzip.open(STUDY / "main/events.jsonl.gz", "rb") as handle:
        for line in handle:
            lines += 1
            if b'"task": "push-v3"' not in line or b'"role": "EVAL"' not in line:
                continue
            if not any(('"program": "' + name + '"').encode() in line for name in PROGRAMS):
                continue
            if b'"event": "STEP_COMPLETE"' not in line and not (b'"event": "AGENT_EVENT"' in line and b'"agent_event": "COMMAND"' in line):
                continue
            event = json.loads(line)
            if event["manifest_id"] != manifest["manifest_id"] or event["sequence"] <= last_sequence:
                raise ValueError("source event identity or order differs")
            last_sequence = event["sequence"]
            key = (event["stream"], event["episode"], event["future"], event["program"])
            state = records[key]
            selected += 1
            if event["event"] == "AGENT_EVENT":
                pending[event["sequence"]] = (key, event["public_payload"])
                continue
            command_key, command = pending.pop(event["global_command_sequence"])
            if command_key != key or command["at_calls"] != 4 + state["steps"] or event["logical_step"] != command["at_calls"]:
                raise ValueError("actual command owner or chronological step differs")
            if command["command"] != event["command"] or command["raw_policy"] != event["raw_policy"] or command["before"]["observation"] != state["last_after"]:
                raise ValueError("saved command or observation continuity differs")
            state["steps"] += 1
            actual += 1
            state["last_after"] = event["after"]["observation"]
            if event["phase"] == "POLICY":
                state["policy_steps"] += 1
                mode = push_mode(command["before"]["observation"])
                state["counts"][mode] += 1
                state["tail"].append(mode)
                if mode != state["current_mode"]:
                    state["switches"] += int(state["current_mode"] is not None)
                    state["current_mode"] = mode
                    state["current_run"] = 0
                state["current_run"] += 1
                state["longest"][mode] = max(state["longest"][mode], state["current_run"])
    if pending:
        raise ValueError("unexecuted selected commands")
    rows = []
    for key, state in sorted(records.items()):
        case, record = state["case"], state["record"]
        result = record["outcome"]
        if state["steps"] != result["suffix_steps"] or state["policy_steps"] != result["policy_queries"] or state["last_after"] != record["final_observation"]["observation"]:
            raise ValueError("reconstructed complete suffix disagrees with saved result")
        fit = record["fit"]
        row = {"stream": key[0], "episode": key[1], "future": key[2], "program": key[3],
               "seed_evaluator_only": case["seed"], "success": result["success"], "stopped": result["stopped"],
               "deadline_loss": result["deadline_loss"], "total_steps": result["total_steps"],
               "suffix_steps": state["steps"], "policy_steps": state["policy_steps"],
               "last_requested_mode": state["current_mode"] or "NO_POLICY_STEP",
               "mode_switches": state["switches"], "tail_steps": len(state["tail"]),
               "last_100_all_descent": len(state["tail"]) == 100 and all(x == "DESCEND" for x in state["tail"]),
               "fit_valid": None if fit is None else fit["valid"],
               "fit_residual_rmse_m": None if fit is None else fit.get("residual_rmse_m")}
        for mode in MODES:
            row["count_" + mode] = state["counts"][mode]
            row["longest_" + mode] = state["longest"][mode]
        rows.append(row)
    with (STUDY / "main_analysis_v1/all_program_executions.csv").open(encoding="utf-8-sig", newline="") as handle:
        source_rows = [row for row in csv.DictReader(handle) if row["task"] == "push-v3" and row["role"] == "EVAL" and row["program"] in PROGRAMS]
    if len(source_rows) != len(rows):
        raise ValueError("CSV source population differs")
    by_key = {(int(row["stream"]), int(row["episode"]), int(row["future"]), row["program"]): row for row in source_rows}
    for row in rows:
        source = by_key[(row["stream"], row["episode"], row["future"], row["program"])]
        if row["success"] != (source["success"] == "True") or row["deadline_loss"] != int(source["deadline_loss"]):
            raise ValueError("outcomes differ from delivered CSV")
    groups = []
    for program in PROGRAMS:
        for success in (True, False):
            part = [row for row in rows if row["program"] == program and row["success"] == success]
            longest = [row["longest_DESCEND"] for row in part]
            residuals = [row["fit_residual_rmse_m"] for row in part if row["fit_residual_rmse_m"] is not None]
            groups.append({"program": program, "success": success, "executions": len(part),
                           "source_states_represented": len({(row["stream"], row["episode"]) for row in part}),
                           "last_requested_mode_counts": dict(Counter(row["last_requested_mode"] for row in part)),
                           "last_100_all_descent_count": sum(row["last_100_all_descent"] for row in part),
                           "longest_descent_min_q25_median_q75_max": np.quantile(longest, [0, .25, .5, .75, 1]).tolist() if longest else [],
                           "fit_residual_min_median_max_m": np.quantile(residuals, [0, .5, 1]).tolist() if residuals else []})
    paired = []
    row_map = {(row["stream"], row["episode"], row["future"], row["program"]): row for row in rows}
    for stream, episode, future in sorted({key[:3] for key in row_map}):
        p, k = [row_map[(stream, episode, future, program)] for program in PROGRAMS]
        label = ("BOTH_SUCCESS" if k["success"] else "P_SUCCESS_K_FAILURE") if p["success"] else ("P_FAILURE_K_SUCCESS" if k["success"] else "BOTH_FAILURE")
        paired.append({"stream": stream, "episode": episode, "future": future, "outcome_pair": label,
                       "K_last_requested_mode": k["last_requested_mode"], "K_last_100_all_descent": k["last_100_all_descent"],
                       "P_minus_K_deadline_loss": p["deadline_loss"] - k["deadline_loss"]})
    summary = {"scope": "Exploratory complete-push-population description. Outcome groups and final-window summaries are retrospective, not online decision rules or independent samples.",
               "states": 128, "futures_per_state": 8, "executions": len(rows), "groups": groups,
               "paired_outcome_counts": dict(Counter(row["outcome_pair"] for row in paired)),
               "harmful_update_last_mode_counts": dict(Counter(row["K_last_requested_mode"] for row in paired if row["outcome_pair"] == "P_SUCCESS_K_FAILURE")),
               "harmful_update_last_100_descent_count": sum(row["K_last_100_all_descent"] for row in paired if row["outcome_pair"] == "P_SUCCESS_K_FAILURE"),
               "mean_P_minus_K_deadline_loss": float(np.mean([row["P_minus_K_deadline_loss"] for row in paired])),
               "no_new_confidence_intervals": True, "tail_window_is_posthoc_descriptive": True}
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError("bound source changed during full-population accounting")
    output.mkdir(parents=True, exist_ok=False)
    for name, values in (("program_modes.csv", rows), ("paired_modes.csv", paired)):
        with (output / name).open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
    with (output / "summary.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    receipt = {"schema": "paired_push_mode_description_v1", "manifest_id": manifest["manifest_id"],
               "source_events_sha256": sha(STUDY / "main/events.jsonl.gz"),
               "source_outcomes_sha256": sha(STUDY / "main_analysis_v1/all_program_executions.csv"),
               "source_bound_policy_sha256": sha(policy), "script_sha256": sha(Path(__file__)),
               "mode_helper_sha256": sha(Path(__file__).with_name("extract_paired_probe_case_trace_20261019.py")),
               "python": sys.version, "numpy": np.__version__, "source_lines_scanned": lines,
               "selected_command_and_step_events": selected, "actual_suffix_steps_reconstructed": actual,
               "generation_body_wall_ns": perf_counter_ns() - started,
               "new_simulation_steps": 0, "new_api_calls": 0, "new_fits": 0, "new_policy_queries": 0,
               "new_thresholds_or_selectors": 0, "new_confidence_intervals": 0,
               "artifact_sha256": {path.name: sha(path) for path in output.iterdir() if path.is_file()},
               "scope": summary["scope"]}
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({key: summary[key] for key in ("states", "executions", "paired_outcome_counts", "harmful_update_last_mode_counts")}))


if __name__ == "__main__":
    main()
