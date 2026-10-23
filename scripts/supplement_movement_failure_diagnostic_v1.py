"""Posthoc reverse-lag feedback correlations and XY/Z clip breakdown; saved arrays only."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def correlations(steps):
    index = {s["step"]: s for s in steps}
    pairs = (("last", "command"), ("noise", "command"), ("error_true", "command"),
             ("noise", "last"), ("error_true", "last"), ("noise", "error_true"))
    out = []
    for a, b in pairs:
        for lag in (0, 1, 2):
            for axis in (0, 1):
                values = [(index[t-lag][a][axis], now[b][axis]) for t, now in index.items()
                          if t-lag in index and index[t-lag][a] is not None and now[b] is not None]
                r, reason = None, "FEWER_THAN_THREE_PAIRED_VALUES"
                if len(values) >= 3:
                    x, y = np.array(values).T
                    if np.std(x) > 0 and np.std(y) > 0:
                        r = float(np.corrcoef(x, y)[0, 1]); reason = None
                    else:
                        reason = "CONSTANT_VARIABLE"
                out.append({"pair": a+"_past__"+b+"_current", "lag": lag, "axis": axis,
                            "n": len(values), "r": r, "reason": reason})
    return out


def run():
    started = perf_counter_ns()
    base = ROOT/"outputs/movement_task/diagnostic_v1"
    output = ROOT/"outputs/movement_task/diagnostic_supplement_v1"
    output.mkdir(parents=True, exist_ok=False)
    registry = json.loads((base/"trajectory_registry.json").read_text(encoding="utf-8"))
    ids = {(r["unit"], r["variant"]): {k:r[k] for k in ("unit", "variant", "task", "condition", "method", "group")} for r in registry}
    clip_rows = []
    correlation_count = 0
    with gzip.open(output/"reverse_lag_correlations.jsonl.gz", "xt", encoding="utf-8") as target:
        for path in sorted((base/"steps").glob("*.gz")):
            cases = {}
            with gzip.open(path, "rt", encoding="utf-8") as f:
                for line in f:
                    s = json.loads(line)
                    cases.setdefault((s["unit"], s["variant"]), []).append(s)
            for key, steps in cases.items():
                ident = ids[key]
                for period, selected in (("ALL_STEPS", steps), ("OWN_TASK", [s for s in steps if s["phase"] == "TASK_AFTER_MOVEMENT"]),
                                          ("COMMON_MOVEMENT", [s for s in steps if s["phase"] == "REPOSITION"])):
                    if period == "COMMON_MOVEMENT" and ident["method"] != "MOVE_ARX_KEEP":
                        continue
                    clip_rows.append({**ident, "period": period, "n": len(selected),
                        "actuator_clip_xy": None if not selected else float(np.mean([any(abs(x)>1 for x in s["actuator_noisy"][:2]) for s in selected])),
                        "actuator_clip_z": None if not selected else float(np.mean([abs(s["actuator_noisy"][2])>1 for s in selected]))})
                if ident["method"] != "MOVE_ARX_KEEP":
                    continue
                for stage in ("ALL", "LIFT", "POST_LIFT"):
                    for bin_name, lo, hi in (("ALL",1,64),("1_8",1,8),("9_16",9,16),("17_32",17,32),("33_64",33,64)):
                        selected = [s for s in steps if s["phase"] == "REPOSITION" and (stage == "ALL" or s["movement_stage"] == stage) and lo <= s["movement_step"] <= hi]
                        for c in correlations(selected):
                            target.write(json.dumps({**ident, "stage": stage, "bin": bin_name, **c}, separators=(",", ":"))+"\n")
                            correlation_count += 1
    (output/"clip_axes.json").write_text(json.dumps(clip_rows, indent=2)+"\n", encoding="utf-8")
    receipt = {"status": "COMPLETE_POSTHOC_SAVED_ARRAY_SUPPLEMENT", "base_completion_sha256": sha(base/"completion.json"),
        "source_sha256": sha(Path(__file__)), "files": {p.name:sha(p) for p in output.iterdir()},
        "reverse_lag_rows": correlation_count, "clip_axis_rows": len(clip_rows), "wall_ns": perf_counter_ns()-started,
        "scope": "Reverse direction includes noise_(t-lag) versus command_t; all same strata retained. No model or threshold selected.",
        "new_environment_steps": 0, "new_all_resets": 0, "new_api_calls": 0, "new_model_fits": 0}
    (output/"completion.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    with read_only_analysis_guard():
        run()
