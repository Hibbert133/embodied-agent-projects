"""Independent reverse-lag / clip-axis audit using already reconstructed step arrays."""
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_movement_failure_diagnostic_v1 import close, correlation, read, require, rows, sha
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard


def main():
    start = perf_counter_ns()
    base = ROOT/"outputs/movement_task/diagnostic_v1"
    folder = ROOT/"outputs/movement_task/diagnostic_supplement_v1"
    complete = read(folder/"completion.json")
    require(complete["base_completion_sha256"] == sha(base/"completion.json"), "wrong supplement source")
    require(complete["source_sha256"] == sha(ROOT/"scripts/supplement_movement_failure_diagnostic_v1.py"), "supplement implementation changed")
    for name, expected in complete["files"].items():
        require(sha(folder/name) == expected, "supplement output changed")
    clips = {(r["unit"], r["variant"], r["period"]):r for r in read(folder/"clip_axes.json")}
    canonical = {}
    clip_count = 0
    for path in sorted((base/"steps").glob("*.gz")):
        cases = {}
        for step in rows(path):
            cases.setdefault((step["unit"], step["variant"]), []).append(step)
        for key, steps in cases.items():
            is_canonical = key[1].endswith("MOVE_ARX_KEEP")
            movement = [r for r in steps if r["phase"] == "REPOSITION"]
            if is_canonical:
                canonical[key] = movement
            for period, selected in (("ALL_STEPS",steps), ("OWN_TASK",[r for r in steps if r["phase"] == "TASK_AFTER_MOVEMENT"]), ("COMMON_MOVEMENT",movement)):
                if period == "COMMON_MOVEMENT" and not is_canonical:
                    continue
                saved = clips[key+(period,)]
                require(saved["n"] == len(selected), "clip-axis denominator differs")
                xy = None if not selected else float(np.mean([max(abs(np.array(r["actuator_noisy"][:2])))>1 for r in selected]))
                z = None if not selected else float(np.mean([abs(r["actuator_noisy"][2])>1 for r in selected]))
                close(saved["actuator_clip_xy"], xy, "XY actuator clipping")
                close(saved["actuator_clip_z"], z, "Z actuator clipping")
                clip_count += 1
    count = 0
    for row in rows(folder/"reverse_lag_correlations.jsonl.gz"):
        steps = canonical[row["unit"], row["variant"]]
        lo, hi = {"ALL":(1,64),"1_8":(1,8),"9_16":(9,16),"17_32":(17,32),"33_64":(33,64)}[row["bin"]]
        index = {s["step"]:s for s in steps if (row["stage"] == "ALL" or s["movement_stage"] == row["stage"]) and lo <= s["movement_step"] <= hi}
        a, b = row["pair"].split("_past__"); b = b.removesuffix("_current")
        x, y = [], []
        for t, current in index.items():
            prior = index.get(t-row["lag"])
            if prior:
                x.append(None if prior[a] is None else prior[a][row["axis"]])
                y.append(None if current[b] is None else current[b][row["axis"]])
        n, r = correlation(x, y)
        require(row["n"] == n, "reverse-lag pair count differs")
        close(row["r"], r, "reverse-lag correlation")
        count += 1
    require(count == complete["reverse_lag_rows"] == 174960 and clip_count == complete["clip_axis_rows"] == 2916, "supplement population differs")
    receipt = {"integrity":"PASSED", "completion_sha256":sha(folder/"completion.json"), "auditor_sha256":sha(Path(__file__)),
        "reverse_lag_rows_checked":count, "clip_axis_rows_checked":clip_count, "new_environment_steps":0,
        "new_all_resets":0,"new_api_calls":0,"new_model_fits":0,"wall_ns":perf_counter_ns()-start}
    with (folder/"independent_audit.json").open("x", encoding="utf-8", newline="\n") as f:
        json.dump(receipt,f,indent=2);f.write("\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    with read_only_analysis_guard():
        main()
