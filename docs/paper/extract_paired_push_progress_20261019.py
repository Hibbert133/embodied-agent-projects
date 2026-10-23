"""Post-hoc public-observation progress accounting, never an online detector."""

import argparse
from collections import deque
import csv
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

from replay_paired_probe_results_v1 import ROOT, STUDY, RECEIPTS, sha, verify_saved
from extract_paired_probe_case_trace_20261019 import push_mode


PROGRAMS = ("PROBE_KEEP", "PROBE_UPDATE_KEEP")
WINDOW = 100  # Previously reported retrospective window; not a new trigger.


def geometry(observation):
    obs = np.asarray(observation, dtype=float)
    if obs.shape != (39,) or not np.isfinite(obs).all():
        raise ValueError("finite public observation required")
    puck = obs[4:7] + [-.005, 0, 0]
    return {"object_goal_m": float(np.linalg.norm(obs[4:7] - obs[-3:])),
            "hand_object_xy_m": float(np.linalg.norm(obs[:2] - puck[:2])),
            "hand_object_abs_z_m": float(abs(obs[2] - puck[2]))}


def summarize_tail(key, state):
    tail = list(state["tail"])
    if not tail:
        raise ValueError("population contains a zero-policy continuation")
    case, record = state["case"], state["record"]
    result = record["outcome"]
    if state["steps"] != result["suffix_steps"] or state["policy_steps"] != result["policy_queries"]:
        raise ValueError("saved step/query counts differ")
    if state["last_after"] != record["final_observation"]["observation"]:
        raise ValueError("final observation differs")
    begin = geometry(tail[0]["before"])
    end = geometry(tail[-1]["after"])
    row = {"stream": key[0], "episode": key[1], "future": key[2], "program": key[3],
           "seed_evaluator_only": case["seed"], "success": result["success"],
           "deadline_loss": result["deadline_loss"], "total_steps": result["total_steps"],
           "policy_steps": state["policy_steps"], "tail_steps": len(tail),
           "first_tail_logical_step": tail[0]["logical_step"],
           "first_tail_command_sequence": tail[0]["command_sequence"],
           "last_tail_step_sequence": tail[-1]["step_sequence"],
           "all_100_descend": len(tail) == WINDOW and all(t["mode"] == "DESCEND" for t in tail)}
    for mode in ("ALIGN_XY", "DESCEND", "PUSH_TO_GOAL"):
        row["tail_count_" + mode] = sum(t["mode"] == mode for t in tail)
    metrics = [(geometry(t["before"]), geometry(t["after"])) for t in tail]
    for name in begin:
        increments = [a[name] - b[name] for a, b in metrics]
        row["start_" + name] = begin[name]
        row["end_" + name] = end[name]
        row["net_reduction_" + name] = begin[name] - end[name]
        row["strict_reduction_steps_" + name] = sum(x > 0 for x in increments)
        row["strict_increase_steps_" + name] = sum(x < 0 for x in increments)
        row["min_" + name] = min([begin[name]] + [b[name] for _, b in metrics])
        row["max_" + name] = max([begin[name]] + [b[name] for _, b in metrics])
        if abs(sum(increments) - (begin[name] - end[name])) > 1e-12:
            raise ValueError("public progress fails telescoping identity")
    row["tail_sent_z_negative_steps"] = sum(t["sent_z"] < 0 for t in tail)
    row["tail_actual_hand_z_reduction_m"] = tail[0]["before"][2] - tail[-1]["after"][2]
    row["tail_actual_object_z_reduction_m"] = tail[0]["before"][6] - tail[-1]["after"][6]
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()) or output == RECEIPTS.resolve() or output.exists():
        parser.error("output must be a new subdirectory inside replay receipts")
    started = perf_counter_ns()
    manifest, bindings, _ = verify_saved("MAIN")
    population = RECEIPTS / "push_mode_population_v1"
    prior = json.loads((population / "receipt.json").read_text(encoding="utf-8"))
    for name, expected in prior["artifact_sha256"].items():
        if sha(population / name) != expected:
            raise ValueError("prior descriptive population changed")
    policy = ROOT / ".venv/Lib/site-packages/metaworld/policies/sawyer_push_v3_policy.py"
    if sha(policy) != manifest["policy_sha256"]["push-v3"]:
        raise ValueError("source policy binding changed")
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
                        raise ValueError("duplicate program")
                    records[key] = {"case": case, "record": record, "steps": 0, "policy_steps": 0,
                                    "last_after": case["evidence"]["prefix"]["observations"][-1],
                                    "tail": deque(maxlen=WINDOW)}
    if len(records) != 2048 or len({k[:2] for k in records}) != 128:
        raise ValueError("complete push population required")
    lines = selected = actual = vertical_checks = 0
    last_sequence = -1
    pending = {}
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
                raise ValueError("source identity/order differs")
            last_sequence = event["sequence"]
            key = (event["stream"], event["episode"], event["future"], event["program"])
            state = records[key]
            selected += 1
            if event["event"] == "AGENT_EVENT":
                pending[event["sequence"]] = (key, event["public_payload"])
                continue
            owner, command = pending.pop(event["global_command_sequence"])
            if owner != key or command["at_calls"] != 4 + state["steps"] or event["logical_step"] != command["at_calls"]:
                raise ValueError("command owner/step differs")
            if command["command"] != event["command"] or command["raw_policy"] != event["raw_policy"] or command["before"]["observation"] != state["last_after"]:
                raise ValueError("saved command/continuous observation differs")
            state["steps"] += 1
            actual += 1
            state["last_after"] = event["after"]["observation"]
            if event["phase"] != "POLICY":
                continue
            state["policy_steps"] += 1
            raw = np.asarray(command["raw_policy"], np.float32)
            if command["command"][2:] != np.clip(raw, -1, 1)[2:].tolist():
                raise ValueError("vertical/gripper command differs from bounded nominal policy")
            vertical_checks += 1
            before = command["before"]["observation"]
            state["tail"].append({"before": before, "after": state["last_after"],
                                  "mode": push_mode(before), "sent_z": command["command"][2],
                                  "logical_step": event["logical_step"],
                                  "command_sequence": event["global_command_sequence"],
                                  "step_sequence": event["sequence"]})
    if pending:
        raise ValueError("unexecuted commands")
    rows = [summarize_tail(key, state) for key, state in sorted(records.items())]
    with (population / "program_modes.csv").open(encoding="utf-8", newline="") as handle:
        old = {(int(r["stream"]), int(r["episode"]), int(r["future"]), r["program"]): r for r in csv.DictReader(handle)}
    for row in rows:
        source = old[(row["stream"], row["episode"], row["future"], row["program"])]
        if row["success"] != (source["success"] == "True") or row["all_100_descend"] != (source["last_100_all_descent"] == "True"):
            raise ValueError("prior population category differs")
    groups = []
    for program in PROGRAMS:
        for success in (True, False):
            group = [r for r in rows if r["program"] == program and r["success"] == success and r["all_100_descend"]]
            groups.append({"program": program, "success": success, "all_100_descend_executions": len(group),
                           "net_object_distance_reduction_positive": sum(r["net_reduction_object_goal_m"] > 0 for r in group),
                           "object_distance_reduction_min_median_max_m": np.quantile([r["net_reduction_object_goal_m"] for r in group], [0, .5, 1]).tolist() if group else [],
                           "final_object_distance_min_median_max_m": np.quantile([r["end_object_goal_m"] for r in group], [0, .5, 1]).tolist() if group else [],
                           "net_hand_object_z_reduction_positive": sum(r["net_reduction_hand_object_abs_z_m"] > 0 for r in group)})
    summary = {"scope": "Retrospective endpoint-aligned progress description, not causal detector performance or an intervention evaluation.",
               "population": {"states": 128, "programs": len(rows), "futures_per_state": 8},
               "window": WINDOW, "window_selected_in_prior_description": True, "groups": groups,
               "successful_all_100_descend": [r for r in rows if r["success"] and r["all_100_descend"]],
               "all_policy_vertical_and_gripper_command_checks": vertical_checks,
               "no_threshold_search_no_confidence_intervals": True}
    if any(sha(p) != expected for p, expected in bindings.items()):
        raise ValueError("bound source changed during replay")
    output.mkdir(parents=True, exist_ok=False)
    with (output / "tail_progress.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    with (output / "summary.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(summary, handle, indent=2, ensure_ascii=False, allow_nan=False); handle.write("\n")
    receipt = {"schema": "paired_push_public_progress_v1", "source_manifest_id": manifest["manifest_id"],
               "source_events_sha256": sha(STUDY / "main/events.jsonl.gz"),
               "prior_population_receipt_sha256": sha(population / "receipt.json"),
               "script_sha256": sha(Path(__file__)), "mode_helper_sha256": sha(Path(__file__).with_name("extract_paired_probe_case_trace_20261019.py")),
               "policy_sha256": sha(policy), "source_lines_scanned": lines, "selected_events": selected,
               "actual_suffix_steps_reconstructed": actual, "policy_steps_reconstructed": vertical_checks,
               "generation_body_wall_ns": perf_counter_ns() - started, "python": sys.version, "numpy": np.__version__,
               "new_environment_steps": 0, "new_resets": 0, "new_api_calls": 0, "new_fits": 0,
               "new_full_policy_queries": 0, "new_thresholds_or_selectors": 0,
               "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
               "scope": summary["scope"]}
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, indent=2, allow_nan=False); handle.write("\n")
    print(json.dumps({"population": summary["population"], "groups": groups}))


if __name__ == "__main__":
    main()
