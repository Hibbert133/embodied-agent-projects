"""Whole-group development summaries; seeds and time steps are never replicates."""
from collections import defaultdict
import numpy as np
from src.analysis import observable_history_io_v1 as io

STAGES = ("ALL_RESPONSE", "FIXED_PROBE", "PRE_BOUNDARY", "MOVEMENT_ALL", "LIFT", "POST_LIFT", "MEASUREMENT", "POST_TASK")


def stage_mask(labels, stage):
    labels = np.asarray(labels, str)
    io.require(stage in STAGES, "registered stage")
    if stage == "ALL_RESPONSE":
        return np.ones(len(labels), bool)
    return np.isin(labels, ("LIFT", "POST_LIFT")) if stage == "MOVEMENT_ALL" else labels == stage


def trajectory_rows(metadata, model_entry, key, predicted, target):
    io.require(predicted.shape == target.shape == (len(metadata["labels"]), 2), "actual target chronology")
    rows = []
    for stage in STAGES:
        mask = stage_mask(metadata["labels"], stage); count = int(mask.sum())
        residual = predicted[mask]-target[mask]
        mse = None if not count else float(np.mean(residual**2))
        rows.append({k: metadata[k] for k in ("case_id", "group", "task", "context", "program", "role")}
            | {"model_key": key, "source": model_entry["source"], "kind": model_entry["kind"], "feature": model_entry["feature"],
                "variant": "LINEAR_"+model_entry["feature"] if model_entry["kind"] == "LINEAR" else f"{model_entry['feature']}_{model_entry['loss']}_W{model_entry['window']}",
                "replicate": model_entry.get("replicate"), "stage": stage, "responses": count, "mse_m2": mse,
                "rmse_m": None if mse is None else float(np.sqrt(mse)), "missing_reason": None if count else "NO_ACTUAL_RESPONSES_IN_STAGE"})
    return rows


def aggregate(rows, keys):
    buckets = defaultdict(list)
    for row in rows:
        buckets[tuple(row[k] for k in keys)].append(row)
    result = []
    for key, part in sorted(buckets.items()):
        # Initialization and source are fixed analyses of one trajectory, not replicas.
        by_case = defaultdict(list)
        for r in part:
            by_case[(r["group"], r["case_id"])].append(r)
        groups = defaultdict(list)
        for (g, case), values in by_case.items():
            valid = [r for r in values if r["rmse_m"] is not None]
            groups[g].append({"case_id": case, "available": bool(valid), "prediction_cells": len(values),
                "rmse_m": None if not valid else float(np.mean([r["rmse_m"] for r in valid])),
                "mse_m2": None if not valid else float(np.mean([r["mse_m2"] for r in valid]))})
        summaries = []
        for g, values in sorted(groups.items()):
            valid = [v for v in values if v["available"]]
            summaries.append({"group": g, "allocated_trajectories": len(values), "available_trajectories": len(valid),
                "rmse_m": None if not valid else float(np.mean([v["rmse_m"] for v in valid])),
                "mse_m2": None if not valid else float(np.mean([v["mse_m2"] for v in valid]))})
        valid = [s for s in summaries if s["available_trajectories"]]
        result.append(dict(zip(keys, key)) | {"allocated_trajectories": len(by_case), "available_trajectories": sum(v["available_trajectories"] for v in summaries),
            "allocated_groups": len(groups), "available_groups": len(valid), "group_values": summaries,
            "rmse_m": None if not valid else float(np.mean([v["rmse_m"] for v in valid])),
            "mse_m2": None if not valid else float(np.mean([v["mse_m2"] for v in valid]))})
    return result


def summarize(rows):
    overall = aggregate(rows, ("role", "variant", "stage"))
    full = aggregate(rows, ("role", "task", "context", "program", "variant", "stage"))
    transfers = aggregate(rows, ("role", "source", "program", "variant", "stage"))
    replicates = aggregate([r for r in rows if r["kind"] == "GRU"], ("role", "variant", "replicate", "stage"))
    primary = {r["variant"]: r for r in overall if r["role"] == "DEV" and r["stage"] == "POST_TASK"}
    first, second = primary["F20_ISO_W16"], primary["F43_AXIS_W16"]
    left = {r["group"]: r["rmse_m"] for r in first["group_values"]}
    right = {r["group"]: r["rmse_m"] for r in second["group_values"]}
    differences = {g: None if left[g] is None or right[g] is None else left[g]-right[g] for g in left}
    available = all(v is not None for v in differences.values())
    interval = None
    if available:
        rng = np.random.default_rng(202610350); draws = []
        for _ in range(10000):
            sample = [g for boundary in range(3) for g in rng.choice([g for g in sorted(differences) if g % 3 == boundary], 2, replace=True)]
            draws.append(np.mean([differences[g] for g in sample]))
        interval = np.quantile(draws, [.025, .975]).tolist()
    return {"scope": "TRAIN_ONLY_DEVELOPMENT_NOT_INDEPENDENT_CONFIRMATION", "overall": overall, "task_context_program": full,
        "source_program_transfer": transfers, "initializations": replicates, "primary": {"difference_by_group_m": differences,
            "mean_difference_m": None if not available else float(np.mean(list(differences.values()))), "group_bootstrap_95_m": interval,
            "all_six_groups_available": available}, "model_selection": "NONE", "independent_qualification": "NOT_ATTEMPTED"}
