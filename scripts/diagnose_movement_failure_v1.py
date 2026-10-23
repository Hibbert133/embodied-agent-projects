"""Versioned read-only posthoc diagnostic. Does not import a simulator or fitter."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import movement_failure_diagnostic_v1 as d
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard

CONFIG = ROOT/"configs/movement_task/diagnostic_v1.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(d.finite(value), f, ensure_ascii=False, indent=2, allow_nan=False); f.write("\n")


def cases(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def source_check(config):
    run = ROOT/config["source_run"]
    d.require(sha(run/"manifest.json") == config["manifest_sha256"], "source manifest changed")
    manifest = read(run/"manifest.json")
    d.require(d.digest({k:v for k,v in manifest.items() if k != "manifest_id"}) == manifest["manifest_id"], "manifest identity changed")
    for name, expected in manifest["input_sha256"].items():
        d.require(sha(ROOT/name) == expected, "frozen source changed: "+name)
    pins = read(ROOT/"outputs/movement_task/reporting_v1/report_sources.json")["source_artifact_sha256"]
    for name, expected in pins.items():
        d.require(sha(run/name) == expected, "audited source changed: "+name)
    d.require(pins["analysis/summary.json"] == config["analysis_summary_sha256"], "six original comparisons changed")
    d.require(read(run/"audit/record_audit.json")["integrity"] == read(run/"statistics_audit/check.json")["integrity"] == "PASSED", "both old audits required")
    d.require(sha(ROOT/config["source_models"]) == config["source_models_sha256"], "frozen models changed")
    stats = read(run/"analysis/summary.json")["statistics"]
    d.require(len(stats["contrasts"]) == 6, "all original contrasts required")
    return run, manifest, pins


def rollups(registry, cells):
    selected = [c for c in cells if c["period"] == "OWN_TASK" or c["method"] == "MOVE_ARX_KEEP"]
    keys = ("task", "condition", "period", "method", "stage", "bin")
    buckets = defaultdict(list)
    for c in selected:
        buckets[tuple(c[k] for k in keys)].append(c)
    fields = [k for k in selected[0] if k.endswith(("_rmse", "_mean"))] if selected else []
    result = []
    for key, part in sorted(buckets.items()):
        result.append({**dict(zip(keys, key)), "trajectories_total": len(part), "empty_trajectories": sum(c["n"] == 0 for c in part),
            "steps_descriptive_only": sum(c["n"] for c in part), "metrics": d.grouped_means(part, fields)})
    return result


def associations(registry, paired):
    canonical = {(r["unit"], r["condition"]): r for r in registry if r["method"] == "MOVE_ARX_KEEP"}
    rows = []
    for p in paired:
        c = canonical[p["unit"], p["condition"]]
        rows.append({**p, "fit_rmse": c["movement"]["error_saved_rmse"], "true_rmse": c["movement"]["error_true_rmse"],
            "applied_rmse": c["movement"]["error_applied_rmse"], "future_rmse": c["own_task"]["error_saved_rmse"],
            "command_delta": c["own_task"]["command_delta_mean"], "correction_clip": c["own_task"]["correction_clip_mean"],
            "matrix_error": None if c["parameter_error"] is None else c["parameter_error"]["matrix_relative"],
            "condition_number": c["input_design"]["condition"], "first_command_delta": c["first_command_delta"]})
    out = []
    subsets = [("ALL", rows)] + [(task+"/"+condition, [r for r in rows if r["task"] == task and r["condition"] == condition]) for task in d.TASKS for condition in d.CONDITIONS]
    measures = ("fit_rmse", "true_rmse", "applied_rmse", "future_rmse", "command_delta", "matrix_error", "correction_clip", "first_command_delta", "condition_number")
    for name, part in subsets:
        groups = sorted({r["group"] for r in part})
        for feature in measures:
            for target in ("delta_loss", "harmful_update", "success_to_failure"):
                x = [d.mean([r[feature] for r in part if r["group"] == g]) for g in groups]
                y = [d.mean([r[target] for r in part if r["group"] == g]) for g in groups]
                out.append({"stratum": name, "feature": feature, "target": target, "full_cases": len(part),
                    "missing_feature_cases": sum(r[feature] is None for r in part), "unit": "INDEPENDENT_GROUP_MEANS", **d.pearson(x, y)})
    return rows, out


def run(output):
    started = perf_counter_ns()
    config = read(CONFIG)
    source, manifest, pins = source_check(config)
    output.mkdir(parents=True, exist_ok=False)
    write(output/"analysis_start.json", {"scope": "POSTHOC_DESCRIPTIVE_ONLY", "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_manifest_id": manifest["manifest_id"], "new_environment_steps": 0, "new_api_calls": 0, "new_model_fits": 0})
    model_bank = read(ROOT/config["source_models"])["models"]
    models = {task: model_bank[task]["LINEAR_ARX"] for task in d.TASKS}
    canonical, signatures = {}, {}
    rows_path = source/"collection/cases.jsonl.gz"
    count = 0
    for case in cases(rows_path):
        identity = d.case_identity(case)
        key = (case["unit"], identity["condition"])
        count += 1
        if identity["method"].startswith("MOVE_"):
            signatures[key+(identity["method"],)] = d.movement_signature(case)
        if identity["method"] == "MOVE_ARX_KEEP":
            d.require(key not in canonical, "duplicate canonical case")
            canonical[key] = d.canonical_context(case)
    d.require(count == 1296 and len(canonical) == 324, "full population required")
    common_checks = []
    for key, context in canonical.items():
        for method in ("MOVE_KEEP_C8", "MOVE_INTEGRAL"):
            d.require(context["movement_signature"] == signatures[key+(method,)], "common MOVE trajectory / physical witness differs")
            common_checks.append({"unit": key[0], "condition": key[1], "method": method, "signature": context["movement_signature"]})
    write(output/"canonical_contexts.json", list(canonical.values()))
    write(output/"common_movement_checks.json", common_checks)
    print(json.dumps({"phase": "SOURCES_AND_COMMON_MOVEMENT_CHECKED", "cases": count, "common_pairs": len(common_checks)}), flush=True)
    registry, cells, correlation_rows = [], [], []
    step_dir = output/"steps"
    step_dir.mkdir()
    handle = None
    group_now = None
    try:
        for case in cases(rows_path):
            ident = d.case_identity(case)
            key = case["unit"], ident["condition"]
            summary, step_rows, current_cells = d.analyze_case(case, models[case["task"]], canonical[key])
            if ident["group"] != group_now:
                if handle is not None:
                    handle.close()
                group_now = ident["group"]
                handle = gzip.open(step_dir/f"group-{group_now:02d}.jsonl.gz", "xt", encoding="utf-8", compresslevel=6)
            for s in step_rows:
                handle.write(json.dumps({"unit": case["unit"], "variant": case["variant"], **s}, separators=(",", ":"), allow_nan=False)+"\n")
            registry.append(summary)
            cells.extend(current_cells)
            if ident["method"] == "MOVE_ARX_KEEP":
                movement = [s for s in step_rows if s["phase"] == "REPOSITION"]
                for stage in ("ALL", "LIFT", "POST_LIFT"):
                    for name, lo, hi in (("ALL", 1, 64), *d.BINS):
                        selected = [s for s in movement if (stage == "ALL" or s["movement_stage"] == stage) and lo <= s["movement_step"] <= hi]
                        for corr in d.correlations(selected):
                            correlation_rows.append({**ident, "stage": stage, "bin": name, **corr})
                state_errors = [None if s["error_applied"] is None else float(np.linalg.norm(s["error_applied"])) for s in movement]
                summary["state_error_correlations"] = {k: d.pearson([s[k] for s in movement], state_errors)
                    for k in ("hand_x", "hand_y", "hand_z", "hand_object_distance", "object_displacement", "near_object", "grasp_success")}
            if len(registry) % 24 == 0:
                print(json.dumps({"phase": "READ_ONLY_DIAGNOSTICS", "cases": len(registry), "group": group_now}), flush=True)
    finally:
        if handle is not None:
            handle.close()
    original_rows = read(source/"analysis/all_cases.json")
    d.require(len(registry) == len(original_rows) == 1296, "registry incomplete")
    for old, new in zip(original_rows, registry):
        d.require(all(new[k] == old[k] for k in ("unit", "variant", "success", "deadline_loss", "total_steps", "action", "stopped", "completed", "boundary_ready")), "original outcomes changed")
    paired = d.pair_outcomes(registry)
    pair_metrics, relation = associations(registry, paired)
    write(output/"trajectory_registry.json", registry)
    write(output/"paired_task_outcomes.json", pair_metrics)
    write(output/"group_associations.json", relation)
    write(output/"stratified_summary.json", rollups(registry, cells))
    for filename, values in (("trajectory_segments.jsonl.gz", cells), ("lag_correlations.jsonl.gz", correlation_rows)):
        with gzip.open(output/filename, "xt", encoding="utf-8", compresslevel=6) as f:
            for r in values:
                f.write(json.dumps(r, separators=(",", ":"), allow_nan=False)+"\n")
    canonical_rows = [r for r in registry if r["method"] == "MOVE_ARX_KEEP"]
    write(output/"missing_reasons.json", {"all_cases": dict(Counter(r["missing_or_fit_reason"] for r in registry)),
        "canonical_cases": dict(Counter(r["missing_or_fit_reason"] for r in canonical_rows)),
        "history_missing_total_steps": sum(r["history_unavailable_steps"] for r in registry),
        "empty_canonical_movement_segments": sum(c["n"] == 0 for c in cells if c["method"] == "MOVE_ARX_KEEP" and c["period"] == "COMMON_MOVEMENT"),
        "rule": "Unavailable errors, parameters and correlations remain null; never zero-filled."})
    for name, expected in pins.items():
        d.require(sha(source/name) == expected, "source modified during analysis")
    code_files = [CONFIG, Path(__file__), ROOT/"src/analysis/movement_failure_diagnostic_v1.py", ROOT/"src/analysis/movement_diagnostic_guard_v1.py",
                  ROOT/"docs/protocols/movement_failure_diagnostic_v1.md"]
    artifacts = {p.relative_to(output).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(output.rglob("*")) if p.is_file()}
    completion = {"status": "COMPLETE_POSTHOC_DESCRIPTIVE_DIAGNOSTICS_PENDING_INDEPENDENT_AUDIT", "version": d.VERSION,
        "source_run_id": manifest["experiment_run_id"], "source_manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"],
        "source_artifact_sha256": pins, "implementation_sha256": {p.relative_to(ROOT).as_posix(): sha(p) for p in code_files},
        "model_file_sha256": config["source_models_sha256"], "artifacts": artifacts,
        "executions": len(registry), "canonical_cases": len(canonical_rows), "canonical_live_movement_cases": sum(r["movement"]["n"] > 0 for r in canonical_rows),
        "actual_control_steps_checked": sum(r["record_rows"] for r in registry), "groups": 54, "common_movement_pairs": len(common_checks),
        "new_environment_steps": 0, "new_all_resets": 0, "new_environment_creations": 0, "new_api_calls": 0,
        "new_model_fits": 0, "new_policy_queries": 0, "new_simulation_frames": 0,
        "guard": "Simulator/network/optimizer imports, socket and subprocess audit events forbidden during analysis.",
        "wall_ns": perf_counter_ns()-started}
    write(output/"completion.json", completion)
    print(json.dumps({k:v for k,v in completion.items() if k not in ("artifacts", "source_artifact_sha256", "implementation_sha256")}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT/"outputs/movement_task/diagnostic_v1")
    args = p.parse_args()
    with read_only_analysis_guard():
        run(args.output.resolve())
