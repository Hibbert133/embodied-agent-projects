"""Independently recompute saved endpoint-progress tables from raw events."""

import argparse
from collections import deque
import csv
import gzip
import json
import math
from pathlib import Path
from time import perf_counter_ns

from replay_paired_probe_results_v1 import ROOT, STUDY, RECEIPTS, sha, verify_saved


def check(condition, message):
    if not condition:
        raise ValueError(message)


def distances(obs):
    return {"object_goal_m": math.dist(obs[4:7], obs[-3:]),
            "hand_object_xy_m": math.hypot(obs[0] - (obs[4] - .005), obs[1] - obs[5]),
            "hand_object_abs_z_m": abs(obs[2] - obs[6])}


def quantiles(values):
    values = sorted(values)
    if not values:
        return []
    center = (len(values) - 1) / 2
    lo = int(center)
    return [values[0], values[lo] + (center - lo) * (values[math.ceil(center)] - values[lo]), values[-1]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = (ROOT / args.input).resolve(), (ROOT / args.output).resolve()
    if not source.is_relative_to(RECEIPTS.resolve()) or not output.is_relative_to(RECEIPTS.resolve()) or output.exists():
        parser.error("existing replay source and new replay output required")
    started = perf_counter_ns()
    manifest, bindings, _ = verify_saved("MAIN")
    receipt = json.loads((source / "receipt.json").read_text(encoding="utf-8"))
    for name, expected in receipt["artifact_sha256"].items():
        check(sha(source / name) == expected, "generated artifact hash differs")
    check(receipt["source_manifest_id"] == manifest["manifest_id"], "manifest differs")
    check(sha(STUDY / "main/events.jsonl.gz") == receipt["source_events_sha256"], "raw source differs")
    helper = Path(__file__).with_name("extract_paired_push_progress_20261019.py")
    check(sha(helper) == receipt["script_sha256"], "extractor bytes differ")
    with (source / "tail_progress.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row_map = {(int(r["stream"]), int(r["episode"]), int(r["future"]), r["program"]): r for r in rows}
    check(len(row_map) == len(rows) == 2048, "complete population differs")
    tails = {key: deque(maxlen=100) for key in row_map}
    counts = dict.fromkeys(row_map, 0)
    pending = {}
    lines = vertical = 0
    with gzip.open(STUDY / "main/events.jsonl.gz", "rb") as handle:
        for line in handle:
            lines += 1
            if b'"task": "push-v3"' not in line or b'"role": "EVAL"' not in line:
                continue
            if b'"program": "PROBE_KEEP"' not in line and b'"program": "PROBE_UPDATE_KEEP"' not in line:
                continue
            if b'"phase": "POLICY"' not in line:
                continue
            if b'"event": "STEP_COMPLETE"' not in line and not (b'"event": "AGENT_EVENT"' in line and b'"agent_event": "COMMAND"' in line):
                continue
            event = json.loads(line)
            key = (event["stream"], event["episode"], event["future"], event["program"])
            if event["event"] == "AGENT_EVENT":
                pending[event["sequence"]] = (key, event["public_payload"])
                continue
            owner, command = pending.pop(event["global_command_sequence"])
            check(owner == key and command["command"] == event["command"], "saved command owner/content differs")
            before, after = command["before"]["observation"], event["after"]["observation"]
            if tails[key]:
                check(tails[key][-1]["after"] == before, "policy continuity differs")
            check(event["global_command_sequence"] < event["sequence"], "command follows outcome")
            check(command["command"][2:] == [min(1., max(-1., x)) for x in command["raw_policy"][2:]], "z/gripper changed")
            vertical += 1
            counts[key] += 1
            d = distances(before)
            mode = "ALIGN_XY" if d["hand_object_xy_m"] > .02 else "DESCEND" if d["hand_object_abs_z_m"] > .04 else "PUSH_TO_GOAL"
            tails[key].append({"before": before, "after": after, "mode": mode,
                               "logical": event["logical_step"], "command": event["global_command_sequence"],
                               "step": event["sequence"], "z": command["command"][2]})
    check(not pending, "pending policy commands")
    fields = 0
    max_error = 0.
    for key, row in row_map.items():
        tail = list(tails[key])
        first, last = tail[0], tail[-1]
        exact = {"policy_steps": counts[key], "tail_steps": len(tail),
                 "first_tail_logical_step": first["logical"], "first_tail_command_sequence": first["command"],
                 "last_tail_step_sequence": last["step"],
                 "all_100_descend": len(tail) == 100 and all(t["mode"] == "DESCEND" for t in tail),
                 "tail_sent_z_negative_steps": sum(t["z"] < 0 for t in tail)}
        for mode in ("ALIGN_XY", "DESCEND", "PUSH_TO_GOAL"):
            exact["tail_count_" + mode] = sum(t["mode"] == mode for t in tail)
        numeric = {"tail_actual_hand_z_reduction_m": first["before"][2] - last["after"][2],
                   "tail_actual_object_z_reduction_m": first["before"][6] - last["after"][6]}
        gs = [(distances(t["before"]), distances(t["after"])) for t in tail]
        for metric in gs[0][0]:
            values = [gs[0][0][metric]] + [a[metric] for _, a in gs]
            numeric.update({"start_" + metric: values[0], "end_" + metric: values[-1],
                            "net_reduction_" + metric: values[0] - values[-1],
                            "min_" + metric: min(values), "max_" + metric: max(values)})
            exact["strict_reduction_steps_" + metric] = sum(b[metric] > a[metric] for b, a in gs)
            exact["strict_increase_steps_" + metric] = sum(b[metric] < a[metric] for b, a in gs)
        for name, value in exact.items():
            check(row[name] == str(value), "exact field differs: " + str((key, name)))
            fields += 1
        for name, value in numeric.items():
            error = abs(float(row[name]) - value)
            check(math.isfinite(error) and error <= 1e-12, "numeric field differs: " + str((key, name)))
            max_error = max(max_error, error)
            fields += 1
    summary = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    for group in summary["groups"]:
        selected = [r for r in rows if r["program"] == group["program"] and (r["success"] == "True") == group["success"] and r["all_100_descend"] == "True"]
        check(len(selected) == group["all_100_descend_executions"], "summary denominator differs")
        for key, name in (("net_object_distance_reduction_positive", "net_reduction_object_goal_m"),
                          ("net_hand_object_z_reduction_positive", "net_reduction_hand_object_abs_z_m")):
            check(group[key] == sum(float(r[name]) > 0 for r in selected), "summary sign count differs")
        for key, name in (("object_distance_reduction_min_median_max_m", "net_reduction_object_goal_m"),
                          ("final_object_distance_min_median_max_m", "end_object_goal_m")):
            q = quantiles([float(r[name]) for r in selected])
            check(len(q) == len(group[key]) and all(abs(a - b) <= 1e-12 for a, b in zip(q, group[key])), "summary quantiles differ")
    check(vertical == receipt["policy_steps_reconstructed"] == summary["all_policy_vertical_and_gripper_command_checks"], "policy count differs")
    for path, expected in bindings.items():
        check(sha(path) == expected, "old frozen source changed")
    result = {"schema": "paired_push_public_progress_independent_numeric_v1", "status": "PASSED",
              "source_receipt_sha256": sha(source / "receipt.json"), "auditor_sha256": sha(Path(__file__)),
              "source_events_scanned": lines, "program_rows": len(rows), "row_fields_checked": fields,
              "maximum_absolute_numeric_error": max_error, "vertical_gripper_checks": vertical,
              "groups_checked": len(summary["groups"]), "audit_wall_ns": perf_counter_ns() - started,
              "new_environment_steps": 0, "new_resets": 0, "new_api_calls": 0, "new_fits": 0,
              "new_full_policy_queries": 0,
              "scope": "Separate raw-event recomputation with math.dist/hypot; does not qualify a detector, probability model or new intervention."}
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, allow_nan=False); handle.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
