"""Independent FIT statistics, augmented least squares, chronology and group audit."""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import response_training_controls_io_v1 as allocation
from src.analysis import observable_history_io_v1 as io
from src.probe import response_training_controls_v1 as core
from src.probe.observable_history_model_v1 import HistoryTrajectory

STAGES = ("ALL_RESPONSE", "FIXED_PROBE", "PRE_BOUNDARY", "MOVEMENT_ALL", "LIFT", "POST_LIFT", "MEASUREMENT", "POST_TASK")


def independent_arrays(t, feature):
    state = np.asarray([t.initial, *t.observations], dtype=float)
    commands = np.asarray(t.commands, dtype=float).reshape(-1, 4)
    y = state[3:, :2]-state[2:-1, :2]
    if feature == "F43":
        x = np.column_stack((state[2:-1], commands[2:]))
    else:
        hand = state[2:-1, :3]
        x = np.column_stack((hand, state[2:-1, :3]-state[1:-2, :3], state[1:-2, :3]-state[:-3, :3],
            commands[2:], state[2:-1, 3], state[2:-1, 4:7]-hand, state[2:-1, -3:]-hand))
        if feature == "H10":
            x = x[:, 3:13]
    return x, y


def independent_statistics(trajectories, feature, loss):
    arrays = [independent_arrays(t, feature) for t in trajectories]
    w = np.concatenate([np.repeat(1/len(y), len(y)) for x, y in arrays])
    x = np.concatenate([a[0] for a in arrays]); y = np.concatenate([a[1] for a in arrays])
    xm, ym = np.average(x, axis=0, weights=w), np.average(y, axis=0, weights=w)
    xv = np.average((x-xm)**2, axis=0, weights=w); yv = np.average((y-ym)**2, axis=0, weights=w)
    xs = np.sqrt(xv); xs[xs <= 1e-6] = 1
    ys = np.sqrt(yv) if loss == "AXIS" else np.repeat(np.sqrt(yv.sum()/2), 2)
    ys[ys <= 1e-6] = 1
    return xm, xs, ym, ys, x, y, w


def audit_training(folder):
    started = perf_counter_ns(); allocation.load_manifest(folder)
    with allocation.numeric_guard() as counters:
        complete = io.read(folder/"training/completion.json"); index_path = folder/"training/models.json"
        guard = io.read(folder/"train_guard.json")
        io.require(guard["status"] == "PASSED" and not any(guard["counters"].values()), "training guard violations")
        io.require(complete["status"] == "COMPLETE" and complete["models_saved"] == complete["fits_attempted"] == 162 and complete["optimizer_updates"] == 720000,
            "complete fixed training budget required")
        io.require(complete["models_index_sha256"] == io.sha(index_path), "training index changed")
        index = io.read(index_path)["models"]
        data = allocation.read_bundle(folder/"fit_public.json", "FIT")
        banks = {(e["source_bank"], e["task"]): [HistoryTrajectory.from_dict(t) for t in e["trajectories"]] for e in data["entries"]}
        paired = defaultdict(list); schedules = {}; regression_count = 0; maximum = 0.
        for key, entry in index.items():
            path = folder/"training"/entry["file"]
            io.require(io.sha(path) == entry["sha256"], "saved scientific model changed")
            model = io.read(path); trajectories = banks[entry["source"], entry["task"]]
            feature = entry["feature"]
            io.require(model["task"] == entry["task"] and model["feature"] == feature, "model/index mapping differs")
            if entry["kind"] == "GRU":
                io.require(model["loss"] == entry["loss"] and model["window"] == entry["window"], "model factor mapping differs")
            xm, xs, ym, ys, x, y, w = independent_statistics(trajectories, feature, entry.get("loss", "ISO"))
            stats = model["stats"]
            for name, expected in (("input_mean", xm), ("input_scale", xs), ("target_mean", ym), ("target_scale", ys)):
                io.require(np.allclose(stats[name], expected, rtol=1e-9, atol=1e-13), "independent FIT statistics mismatch: "+key+"/"+name)
            if entry["kind"] == "LINEAR":
                a = np.column_stack((np.ones(len(x)), (x-xm)/xs))
                penalty = np.sqrt(.001)*np.eye(a.shape[1]); penalty[0, 0] = 0
                augmented = np.vstack((np.sqrt(w[:, None])*a, penalty))
                output = np.vstack((np.sqrt(w[:, None])*y, np.zeros((a.shape[1], 2))))
                coefficient = np.linalg.lstsq(augmented, output, rcond=None)[0]
                error = float(np.max(abs(coefficient-np.asarray(model["coefficient"]))))
                io.require(error < 1e-9, "independent augmented regression differs")
                maximum = max(maximum, error); regression_count += 1
            else:
                io.require(model["updates"] == 5000 and model["parameter_count"] == 7458 and model["active_parameter_count"] == (5250 if feature == "F20" else 7458), "architecture/update budget")
                replicate = entry["replicate"]
                bank_number = 3*io.PROGRAMS.index(entry["source"])+io.TASKS.index(entry["task"])
                io.require(model["initialization_seed"] == 202610310+6*replicate+bank_number and model["sampling_seed"] == 202610340+6*replicate+bank_number, "registered initializer/sampling seed")
                schedule_key = (entry["source"], entry["task"], replicate)
                if schedule_key not in schedules:
                    rng = np.random.default_rng(model["sampling_seed"]); digest = hashlib.sha256()
                    for _ in range(5000):
                        selected = rng.integers(0, len(trajectories), size=32)
                        positions = np.array([rng.integers(0, len(trajectories[j].commands)-2)+2 for j in selected])
                        digest.update(np.array([selected, positions], dtype="<i8").tobytes())
                    schedules[schedule_key] = digest.hexdigest()
                io.require(model["sampling_schedule_sha256"] == schedules[schedule_key] and model["fit_trajectory_ids_sha256"] == io.digest([t.trajectory_id for t in trajectories]), "chronology or FIT membership mismatch")
                paired[schedule_key].append(model["initial_parameters_sha256"])
                io.require([v["update"] for v in model["checkpoints"]] == [1, *range(500, 5001, 500)], "full fixed optimization checkpoints")
        io.require(regression_count == 18 and len(paired) == 18 and all(len(v) == 8 and len(set(v)) == 1 for v in paired.values()), "all three initializations and eight factorial variants")
        io.write(folder/"training_audit.json", {"integrity": "PASSED", "models_checked": 162, "independent_regression_refits": regression_count,
            "maximum_regression_parameter_error": maximum, "sampling_schedules_rebuilt": len(schedules), "all_eight_variant_initializations_match": True,
            "optimizer_retraining": 0, "guard": counters, "wall_ns": perf_counter_ns()-started, "models_index_sha256": io.sha(index_path),
            "new_environment_steps": 0, "new_api_calls": 0, "source_sha256": io.sha(__file__)})


def independent_aggregate(rows, keys):
    partitions = defaultdict(list)
    for row in rows:
        partitions[tuple(row[k] for k in keys)].append(row)
    result = []
    for key in sorted(partitions):
        group_cases = defaultdict(lambda: defaultdict(list))
        for row in partitions[key]:
            group_cases[row["group"]][row["case_id"]].append(row)
        groups = []
        for group, cases in sorted(group_cases.items()):
            case_values = []
            for values in cases.values():
                finite = [(r["rmse_m"], r["mse_m2"]) for r in values if r["rmse_m"] is not None]
                if finite:
                    case_values.append(np.asarray(finite).mean(axis=0))
            mean = np.mean(case_values, axis=0) if case_values else [None, None]
            groups.append({"group": group, "allocated_trajectories": len(cases), "available_trajectories": len(case_values),
                "rmse_m": None if mean[0] is None else float(mean[0]), "mse_m2": None if mean[1] is None else float(mean[1])})
        finite = [[g["rmse_m"], g["mse_m2"]] for g in groups if g["available_trajectories"]]
        mean = np.mean(finite, axis=0) if finite else [None, None]
        result.append(dict(zip(keys, key)) | {"allocated_trajectories": sum(g["allocated_trajectories"] for g in groups),
            "available_trajectories": sum(g["available_trajectories"] for g in groups), "allocated_groups": len(groups), "available_groups": len(finite),
            "group_values": groups, "rmse_m": None if mean[0] is None else float(mean[0]), "mse_m2": None if mean[1] is None else float(mean[1])})
    return result


def close(a, b):
    if isinstance(a, dict):
        io.require(isinstance(b, dict) and set(a) == set(b), "summary schema")
        for k in a:
            close(a[k], b[k])
    elif isinstance(a, list):
        io.require(isinstance(b, list) and len(a) == len(b), "summary list")
        for x, y in zip(a, b):
            close(x, y)
    elif isinstance(a, float):
        io.require(isinstance(b, (int, float)) and np.isclose(a, b, rtol=1e-9, atol=1e-13), "summary numeric difference")
    else:
        io.require(a == b, "summary metadata difference")


def audit_evaluation(folder):
    started = perf_counter_ns(); allocation.load_manifest(folder)
    with allocation.numeric_guard() as counters:
        output = folder/"evaluation"; complete = io.read(output/"completion.json")
        io.require(io.read(folder/"forward_audit.json")["integrity"] == "PASSED", "independent Torch forward audit required")
        guard = io.read(folder/"forward_guard.json")
        io.require(guard["status"] == "PASSED" and not any(guard["counters"].values()), "forward guard violations")
        for name, digest in complete["artifact_sha256"].items():
            io.require(io.sha(output/name) == digest, "evaluation artifact changed")
        index = io.read(folder/"training/models.json")["models"]
        trajectories = {raw["trajectory_id"]: HistoryTrajectory.from_dict(raw) for role in ("FIT", "DEV") for e in allocation.read_bundle(folder/(role.lower()+"_public.json"), role)["entries"] for raw in e["trajectories"]}
        metadata = io.read(folder/"evaluation_metadata.json")
        expected_rows = []; prediction_count = 0
        stream = iter(io.rows(output/"step_predictions.jsonl.gz"))
        for key, entry in index.items():
            model = io.read(folder/"training"/entry["file"])
            for identifier, t in trajectories.items():
                if t.task != entry["task"]:
                    continue
                for feature in ("F20", "F43"):
                    x, y = independent_arrays(t, feature)
                    io.require(np.allclose(x, core.feature_array(t, feature), rtol=0, atol=1e-15), "independent feature construction")
                predicted = core.predict(model, t); residual = np.empty_like(y)
                for i in range(len(y)):
                    saved = next(stream)
                    io.require(saved["case_id"] == identifier and saved["model_key"] == key and saved["step"] == i+2, "future/trajectory/order mismatch")
                    io.require(np.allclose(saved["prediction"], predicted[i], rtol=1e-9, atol=1e-13) and np.array_equal(saved["target"], y[i]), "saved real prediction/target mismatch")
                    residual[i] = np.asarray(saved["prediction"])-y[i]; prediction_count += 1
                labels = metadata[identifier]["labels"]
                for stage in STAGES:
                    indices = [i for i, label in enumerate(labels) if stage == "ALL_RESPONSE" or label == stage or stage == "MOVEMENT_ALL" and label in ("LIFT", "POST_LIFT")]
                    mse = float(np.sum(residual[indices]**2)/(2*len(indices))) if indices else None
                    meta = metadata[identifier]
                    expected_rows.append({k: meta[k] for k in ("case_id", "group", "task", "context", "program", "role")} | {
                        "model_key": key, "source": entry["source"], "kind": entry["kind"], "feature": entry["feature"],
                        "variant": "LINEAR_"+entry["feature"] if entry["kind"] == "LINEAR" else f"{entry['feature']}_{entry['loss']}_W{entry['window']}",
                        "replicate": entry.get("replicate"), "stage": stage, "responses": len(indices), "mse_m2": mse,
                        "rmse_m": None if mse is None else float(mse**.5), "missing_reason": None if indices else "NO_ACTUAL_RESPONSES_IN_STAGE"})
        io.require(next(stream, None) is None and prediction_count == complete["predictions"], "complete prediction stream")
        close(expected_rows, io.read(output/"trajectory_metrics.json"))
        statistics = io.read(output/"statistics.json")
        for name, keys, selected in (("overall", ("role", "variant", "stage"), expected_rows),
                ("task_context_program", ("role", "task", "context", "program", "variant", "stage"), expected_rows),
                ("source_program_transfer", ("role", "source", "program", "variant", "stage"), expected_rows),
                ("initializations", ("role", "variant", "replicate", "stage"), [r for r in expected_rows if r["kind"] == "GRU"])):
            close(independent_aggregate(selected, keys), statistics[name])
        overall = {r["variant"]: r for r in statistics["overall"] if r["role"] == "DEV" and r["stage"] == "POST_TASK"}
        group_values = {v: {g["group"]: g["rmse_m"] for g in overall[v]["group_values"]} for v in ("F20_ISO_W16", "F43_AXIS_W16")}
        differences = {g: None if group_values["F20_ISO_W16"][g] is None or group_values["F43_AXIS_W16"][g] is None else group_values["F20_ISO_W16"][g]-group_values["F43_AXIS_W16"][g] for g in range(12, 18)}
        available = all(v is not None for v in differences.values()); interval = None
        if available:
            rng = np.random.default_rng(202610350)
            draws = []
            for _ in range(10000):
                sampled = np.concatenate([rng.choice(np.array([g for g in differences if g % 3 == j]), 2) for j in range(3)])
                draws.append(sum(differences[int(g)] for g in sampled)/6)
            interval = np.quantile(draws, [.025, .975]).tolist()
        close({"difference_by_group_m": {str(k): v for k, v in differences.items()}, "mean_difference_m": None if not available else float(np.mean(list(differences.values()))),
            "group_bootstrap_95_m": interval, "all_six_groups_available": available}, statistics["primary"])
        io.require(len(trajectories) == 216 and len(expected_rows) == 93312 and statistics["independent_qualification"] == "NOT_ATTEMPTED", "full diagnostic population and scope")
        io.write(folder/"evaluation_audit.json", {"integrity": "PASSED", "predictions_checked": prediction_count, "trajectory_stage_cells_checked": len(expected_rows),
            "all_group_tables_independently_rebuilt": True, "new_model_fits": 0, "guard": counters, "wall_ns": perf_counter_ns()-started,
            "new_environment_steps": 0, "new_api_calls": 0, "source_sha256": io.sha(__file__), "statistics_sha256": io.sha(output/"statistics.json")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("training", "evaluation")); parser.add_argument("folder", type=Path)
    args = parser.parse_args(); {"training": audit_training, "evaluation": audit_evaluation}[args.mode](args.folder.resolve())
