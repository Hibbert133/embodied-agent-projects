"""Independently verify report exports, equal-group aggregation and PID clipping."""
from collections import defaultdict
import csv
import json
from pathlib import Path
import re
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_movement_failure_diagnostic_v1 import close, correlation, read, require, rows, sha
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard


def avg(values):
    values = [v for v in values if v is not None]
    return None if not values else float(np.mean(values))


def main():
    start = perf_counter_ns()
    base = ROOT/"outputs/movement_task/diagnostic_v1"
    folder = ROOT/"outputs/movement_task/diagnostic_reporting_v1"
    receipt = read(folder/"receipt.json")
    for name, expected in receipt["sources"].items():
        require(sha(ROOT/name) == expected, "report source changed")
    report = ROOT/receipt["report"]
    require(sha(report) == receipt["report_sha256"], "report bytes changed")
    for name, expected in receipt["exports"].items():
        require(sha(folder/name) == expected, "report export changed")
    registry = read(base/"trajectory_registry.json")
    with (folder/"all_1296_cases.csv").open(encoding="utf-8-sig", newline="") as f:
        inventory = list(csv.DictReader(f))
    require(len(inventory) == 1296, "full CSV registry required")
    for row, saved in zip(inventory, registry, strict=True):
        for key, value in row.items():
            require(value == ("" if saved[key] is None else str(saved[key])), "CSV inventory values differ")
    fields = None
    keys = ("task", "condition", "period", "method", "stage", "bin")
    buckets = defaultdict(list)
    for cell in rows(base/"trajectory_segments.jsonl.gz"):
        if cell["period"] == "OWN_TASK" or cell["method"] == "MOVE_ARX_KEEP":
            buckets[tuple(cell[k] for k in keys)].append(cell)
    metric_count = 0
    for saved in read(base/"stratified_summary.json"):
        part = buckets[tuple(saved[k] for k in keys)]
        groups = sorted({x["group"] for x in part})
        require(saved["trajectories_total"] == len(part) and saved["empty_trajectories"] == sum(r["n"] == 0 for r in part), "stratum trajectory denominator")
        require(saved["steps_descriptive_only"] == sum(r["n"] for r in part), "stratum physical step count")
        for key, value in saved["metrics"].items():
            group_values = [avg([c[key] for c in part if c["group"] == g]) for g in groups]
            close(value["mean"], avg(group_values), "equal-group metric")
            require(value["available_trajectories"] == sum(c[key] is not None for c in part) and value["available_groups"] == sum(v is not None for v in group_values), "group metric availability")
            metric_count += 1
    corr_keys = ("task", "condition", "stage", "bin", "pair", "lag", "axis")
    corr_buckets = defaultdict(list)
    for path in (base/"lag_correlations.jsonl.gz", ROOT/"outputs/movement_task/diagnostic_supplement_v1/reverse_lag_correlations.jsonl.gz"):
        for r in rows(path):
            corr_buckets[tuple(str(r[k]) for k in corr_keys)].append(r)
    with (folder/"all_lag_correlation_summary.csv").open(encoding="utf-8-sig", newline="") as f:
        summaries = list(csv.DictReader(f))
    require(len(summaries) == len(corr_buckets), "all correlation strata required")
    for saved in summaries:
        part = corr_buckets[tuple(saved[k] for k in corr_keys)]
        groups = sorted({x["group"] for x in part})
        expected = avg([avg([r["r"] for r in part if r["group"] == g]) for g in groups])
        absolute = avg([avg([None if r["r"] is None else abs(r["r"]) for r in part if r["group"] == g]) for g in groups])
        close(None if saved["mean_r"] == "" else float(saved["mean_r"]), expected, "signed correlation group mean")
        close(None if saved["mean_absolute_r"] == "" else float(saved["mean_absolute_r"]), absolute, "absolute correlation group mean")
        require(int(saved["full_trajectories"]) == len(part) and int(saved["available_trajectories"]) == sum(r["r"] is not None for r in part), "correlation summary denominator")
    source = ROOT/read(ROOT/"configs/movement_task/diagnostic_v1.json")["source_run"]
    current_group = None
    cache = None
    pid_commands = 0
    for case in rows(source/"collection/cases.jsonl.gz"):
        group = case["unit"]//3
        if group != current_group:
            current_group = group
            cache = {(s["unit"],s["variant"],s["step"]):s for s in rows(base/"steps"/f"group-{group:02d}.jsonl.gz")}
        public = None if case["movement"] is None else case["movement"]["public"]
        if public is None:
            continue
        anchor = np.array(next(e["payload"]["anchor"] for e in public["events"] if e["kind"] == "MOVEMENT_TASK_CHOICE"))
        position0 = np.array(public["start"]["current"]["observation"][:3])
        lifted = position0[2] >= anchor[2]-.015
        updates = {e["payload"]["at_calls"]:e["payload"]["integral_after"] for e in public["events"] if e["kind"] == "INTEGRAL_UPDATE"}
        previous = None
        for row in case["physical_rows"]:
            if row["phase"] != "REPOSITION":
                continue
            s = cache[case["unit"],case["variant"],row["logical_step"]]
            position = np.array(s["before_xyz"])
            target = anchor if lifted else np.array([position0[0],position0[1],anchor[2]])
            velocity = np.zeros(3) if previous is None else position-previous
            control = 8.*(target-position)-16.*velocity
            base_command = np.r_[np.clip(control+np.r_[updates[row["logical_step"]],0.],-.5,.5),-1.]
            pre = base_command.copy()
            pre[:2] = np.array(public["start"]["correction_xy"]) @ base_command[:2]+public["start"]["offset_xy"]
            close(s["correction_pre"],pre,"independent PID correction preclip")
            require(s["correction_clip"] == bool(np.any(abs(pre)>1)), "independent PID clip flag")
            require(np.array_equal(np.clip(pre,-1,1).astype(np.float32),np.array(row["command"],np.float32)), "independent PID actual sent command")
            previous = position
            lifted = lifted or row["after"]["observation"][2] >= anchor[2]-.015
            pid_commands += 1
    text = report.read_text(encoding="utf-8")
    broken = []
    for target in re.findall(r"\]\(([^)]+)\)",text):
        if not target.startswith(("https://","http://","#")) and not (report.parent/target.split('#')[0]).exists():
            broken.append(target)
    require(not broken, "broken report artifact links")
    require(text.count("事后描述性分析") >= 1 and "190" in text and "28" in text and "106" in text, "required report status/counts missing")
    result = {"integrity":"PASSED","report_sha256":sha(report),"source_receipt_sha256":sha(folder/"receipt.json"),
        "auditor_sha256":sha(Path(__file__)),"case_csv_rows":len(inventory),"equal_group_metrics_checked":metric_count,
        "correlation_strata_checked":len(summaries),"pid_commands_checked":pid_commands,"broken_local_links":broken,
        "new_environment_steps":0,"new_all_resets":0,"new_api_calls":0,"new_model_fits":0,"wall_ns":perf_counter_ns()-start}
    with (folder/"independent_export_audit.json").open("x",encoding="utf-8",newline="\n") as f:
        json.dump(result,f,indent=2);f.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    with read_only_analysis_guard():
        main()
