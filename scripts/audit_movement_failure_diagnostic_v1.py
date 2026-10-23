"""Independent full-population array audit; no diagnostic calculator reuse or fitting."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda: f.read(1048576), b""):
            result.update(data)
    return result.hexdigest()


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def close(actual, expected, message, atol=2e-13):
    if expected is None:
        require(actual is None, message+": missing value was filled")
    else:
        require(actual is not None and np.shape(actual) == np.shape(expected) and np.allclose(actual, expected, rtol=1e-10, atol=atol), message)


def predict(model, last, prior, command):
    # Existing predictor standardizes float64 features even for float32 actions.
    values = [float(v) for v in (*last, *prior, *command)]
    return np.array([model["coefficients"][0][j]+sum((values[k]-model["mean"][k])/model["scale"][k]*model["coefficients"][k+1][j] for k in range(10)) for j in range(2)])


def sent_trace(raw, controller):
    clipped = np.clip(np.array(raw, dtype=np.float32), -1., 1.).astype(float)
    unm = clipped.copy()
    unm[:2] = np.array(controller["matrix_xy"]) @ clipped[:2] + np.array(controller["offset"])[:2]
    return unm, np.clip(unm, -1., 1.).astype(np.float32)


def correlation(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None and math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return len(pairs), None
    a, b = np.array(pairs).T
    if np.std(a) == 0 or np.std(b) == 0:
        return len(pairs), None
    return len(pairs), float(np.corrcoef(a, b)[0, 1])


def aggregate(values):
    values = [v for v in values if v is not None]
    return None if not values else float(np.mean(values))


def check_segment(saved, selected):
    require(saved["n"] == len(selected), "segment count differs")
    require(saved["missing_reason"] == (None if selected else "ZERO_LENGTH_SEGMENT"), "empty segment reason differs")
    for key in saved:
        if key.endswith("_rmse"):
            field = key[:-5]
            values = [s[field] for s in selected if s[field] is not None]
            expected = None if not values else float(np.sqrt(np.mean(np.array(values)**2)))
            close(saved[key], expected, "segment residual "+key)
            require(saved[field+"_n"] == len(values), "residual availability differs")
        elif key.endswith("_mean"):
            field = key[:-5]
            values = [s[field] for s in selected if s[field] is not None]
            close(saved[key], aggregate(values), "segment mean "+key)
            require(saved[field+"_available"] == len(values), "segment metric availability differs")


def check(output, audit_output):
    started = perf_counter_ns()
    config = read(ROOT/"configs/movement_task/diagnostic_v1.json")
    source = ROOT/config["source_run"]
    completion = read(output/"completion.json")
    for name, value in completion["artifacts"].items():
        require(sha(output/name) == value["sha256"] and (output/name).stat().st_size == value["bytes"], "diagnostic artifact changed: "+name)
    for name, expected in completion["source_artifact_sha256"].items():
        require(sha(source/name) == expected, "original source changed")
    for name, expected in completion["implementation_sha256"].items():
        require(sha(ROOT/name) == expected, "diagnostic implementation changed")
    bank = read(ROOT/config["source_models"])["models"]
    require(sha(ROOT/config["source_models"]) == config["source_models_sha256"], "source model changed")
    contexts = {(c["unit"], c["condition"]): c for c in read(output/"canonical_contexts.json")}
    registry = read(output/"trajectory_registry.json")
    segments = iter(rows(output/"trajectory_segments.jsonl.gz"))
    corrs = iter(rows(output/"lag_correlations.jsonl.gz"))
    old_rows = read(source/"analysis/all_cases.json")
    total = cases = segments_checked = correlations_checked = commands_checked = future_checked = 0
    step_iterator = None
    group = None
    arx_accepted = success_accepted = common_checks = 0
    stage_counts = Counter()
    for raw_case, summary, old in zip(rows(source/"collection/cases.jsonl.gz"), registry, old_rows, strict=True):
        unit = raw_case["unit"]; condition, method = raw_case["variant"].split("_", 1)
        context = contexts[unit, condition]
        for k in ("unit", "variant", "success", "deadline_loss", "total_steps", "action", "stopped", "completed", "boundary_ready"):
            require(summary[k] == old[k] == raw_case[k], "case registry differs")
        if unit//3 != group:
            if step_iterator is not None:
                require(next(step_iterator, None) is None, "extra step shard rows")
            group = unit//3
            step_iterator = iter(rows(output/"steps"/f"group-{group:02d}.jsonl.gz"))
        public = None if raw_case["movement"] is None else raw_case["movement"]["public"]
        if method.startswith("MOVE_"):
            movement_rows = [{k:r[k] for k in ("logical_step", "phase", "command", "executed_action_oracle", "after", "noise_cursor_after", "simulation_time_before", "simulation_time_after")}
                             for r in raw_case["physical_rows"] if r["phase"] == "REPOSITION"]
            canonical_sha = lambda x: hashlib.sha256(json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            source_signature = context["movement_signature"]
            require(source_signature["trajectory_sha256"] == canonical_sha(movement_rows) and source_signature["steps"] == len(movement_rows), "common full movement sequence differs")
            require(source_signature["context_sha256"] == (None if public is None else canonical_sha(public["context"])), "common pre-movement history differs")
            require(source_signature["history_sha256"] == (None if public is None or public["history"] is None else canonical_sha(public["history"]["history"])), "common complete movement history differs")
            post = next((w["witness"] for w in raw_case["state_witnesses"] if w["label"] == "POST_MOVEMENT"), None)
            require(source_signature["post_movement_sha256"] == (None if post is None else post["comparison_python_sha256"]) and
                    source_signature["post_movement_native_sha256"] == (None if post is None else post["native_sha256"]), "common physical world witness differs")
        saved_fit = context["fit_record"]
        fit = None if saved_fit is None else saved_fit["estimate"]["fit"]
        own_fit = fit if method == "MOVE_ARX_KEEP" else None
        c8_choices = [e["payload"]["controller"] for e in raw_case["prefix"]["public"]["events"] if e["kind"] == "CHOICE" and e["payload"].get("purpose") == "CURRENT_POLICY_CONTROLLER"]
        c8 = c8_choices[-1] if c8_choices else None
        decision = None if public is None else next(e["payload"] for e in public["events"] if e["kind"] == "MOVEMENT_TASK_DECISION")
        current = next(e["payload"]["initial"]["observation"] for e in raw_case["prefix"]["public"]["events"] if e["kind"] == "PREFIX_PROGRAM")
        observations = [np.array(current)]
        key = int(np.random.SeedSequence([raw_case["seed"], 47001]).generate_state(1)[0])
        tape = np.random.default_rng(key).normal(0, .05, (500, 3)).astype("<f4")
        fit_controller = None
        if fit and fit["valid"]:
            a, b = np.array(fit["matrix_xy"]), np.array(fit["bias_xy"])
            determinant = a[0,0]*a[1,1]-a[0,1]*a[1,0]
            inverse = np.array([[a[1,1], -a[0,1]], [-a[1,0], a[0,0]]])/determinant
            fit_controller = {"matrix_xy": inverse, "offset": [*(-inverse@b), 0., 0.]}
        step_data = []
        move_i = 0
        if public is not None:
            anchor = np.array(next(e["payload"]["anchor"] for e in public["events"] if e["kind"] == "MOVEMENT_TASK_CHOICE"))
            lifted = public["start"]["current"]["observation"][2] >= anchor[2]-.015
        first_task_seen = False
        for i, row in enumerate(raw_case["physical_rows"]):
            s = next(step_iterator)
            require((s["unit"], s["variant"], s["step"]) == (unit, raw_case["variant"], i), "step shard order differs")
            require(row["logical_step"] == i and row["noise_cursor_after"] == i+1, "noise cursor mismatch")
            fault = raw_case["fault_oracle"]
            if raw_case["fault_transition"] and i >= raw_case["fault_transition"]["at_calls"]:
                fault = raw_case["fault_transition"]["active_fault_oracle"]
            u = np.array(row["command"], np.float32)
            affine = np.array(fault["matrix_xy"], np.float32) @ u[:2]+np.array(fault["bias_xy"], np.float32)
            zone = np.array(fault["deadzone_xy"], np.float32)
            transformed = u.copy()
            transformed[:2] = np.sign(affine)*np.maximum(np.abs(affine)-zone, 0)/(1-zone)
            with_noise = transformed.copy(); with_noise[:3] += tape[i]
            actual = np.clip(with_noise, -1, 1)
            require(np.array_equal(actual, np.array(row["executed_action_oracle"], np.float32)), "oracle action reconstruction mismatch")
            require(np.array_equal(actual, np.array(s["applied"], np.float32)), "diagnostic applied input mismatch")
            close(s["actuator_pre"], transformed, "actuator transformed action")
            close(s["actuator_noisy"], with_noise, "actuator noisy action")
            close(s["noise"], tape[i], "actual noise")
            require(s["actuator_clip"] == bool(np.any(abs(with_noise)>1)) and s["transformed_oos"] == bool(np.any(abs(transformed)>1)), "clip/support flags differ")
            wrong = np.clip(transformed, -1, 1); wrong[:3] += tape[i]; wrong = np.clip(wrong, -1, 1)
            require(s["early_clip_difference"] == (not np.array_equal(wrong, actual)), "clip-order difference flag differs")
            before = observations[-1]
            after = np.array(row["after"]["observation"])
            close(s["before_xyz"], before[:3], "before observation")
            close(s["after_xyz"], after[:3], "after observation")
            close(s["command"], u, "actual sent command")
            require(s["raw_policy"] == row["raw_policy"] and s["phase"] == row["phase"], "raw policy / phase mismatch")
            if row["phase"] == "REPOSITION":
                move_i += 1
                require(s["movement_step"] == move_i and s["movement_stage"] == ("POST_LIFT" if lifted else "LIFT"), "movement stage mismatch")
                lifted = lifted or after[2] >= anchor[2]-.015
                stage_counts[s["movement_stage"]] += int(method == "MOVE_ARX_KEEP")
            if i < 2:
                require(s["last"] is None and s["prior"] is None and s["error_true"] is None, "fabricated initial history")
            else:
                last = observations[-1][:3]-observations[-2][:3]
                prior = observations[-2][:3]-observations[-3][:3]
                close(s["last"], last, "last actual displacement")
                close(s["prior"], prior, "prior actual displacement")
                true_in = u.astype(float); true_in[:2] = np.clip(np.array(fault["matrix_xy"]) @ u[:2]+fault["bias_xy"], -1, 1)
                model = bank[raw_case["task"]]["LINEAR_ARX"]
                pred_t = predict(model, last, prior, true_in)
                pred_a = predict(model, last, prior, actual)
                pred_z = predict(model, last, prior, np.clip(transformed, -1, 1))
                delta = after[:2]-before[:2]
                for field, expected in (("error_true", delta-pred_t), ("error_applied", delta-pred_a), ("error_zero", delta-pred_z),
                                        ("input_noise_component", pred_a-pred_z), ("interface_component", pred_z-pred_t)):
                    close(s[field], expected, "one-step "+field)
                close(s["error_true"], np.array(s["error_applied"])+s["input_noise_component"]+np.array(s["interface_component"]), "noise algebra identity")
                if own_fit and "matrix_xy" in own_fit and row["phase"] in ("REPOSITION", "TASK_AFTER_MOVEMENT"):
                    est_in = u.astype(float); est_in[:2] = np.clip(np.array(own_fit["matrix_xy"]) @ u[:2]+own_fit["bias_xy"], -1, 1)
                    close(s["error_saved"], delta-predict(model, last, prior, est_in), "frozen saved-parameter error")
                    if row["phase"] == "TASK_AFTER_MOVEMENT":
                        require(saved_fit["estimate"]["decision_step"] <= i and saved_fit["saved_ns"] < row["execution_started_ns"], "future parameter leakage")
                        require(s["saved_error_semantics"] == "FROZEN_FUTURE_ONE_STEP", "future prediction labeling")
                        future_checked += 1
                    else:
                        require(s["saved_error_semantics"] == "POSTHOC_IN_SAMPLE", "in-sample labeling")
                else:
                    require(s["error_saved"] is None, "unavailable or other-program fit supplied")
            if row["raw_policy"] is not None:
                raw = row["raw_policy"]
                require(s["policy_clip"] == bool(np.any(abs(np.array(raw, np.float32)) > 1)), "policy clipping differs")
                chosen = decision["controller"] if row["phase"] == "TASK_AFTER_MOVEMENT" else c8
                if chosen is not None:
                    pre_cmd, sent = sent_trace(raw, chosen)
                    close(s["correction_pre"], pre_cmd, "actual correction preclip")
                    require(np.array_equal(sent, u), "actual correction sent action")
                    require(s["correction_clip"] == bool(np.any(abs(pre_cmd)>1)), "correction clipping differs")
                    commands_checked += 1
                if c8:
                    pre_c8, sent_c8 = sent_trace(raw, c8)
                    close(s["c8_pre"], pre_c8, "C8 preclip")
                    close(s["c8_sent"], sent_c8, "C8 sent")
                    if fit_controller and method.startswith("MOVE_") and row["phase"] == "TASK_AFTER_MOVEMENT":
                        pre_arx, sent_arx = sent_trace(raw, fit_controller)
                        close(s["arx_pre"], pre_arx, "ARX inverse preclip", atol=1e-10)
                        close(s["arx_sent"], sent_arx, "ARX sent", atol=2e-7)
                        close(s["command_delta"], np.linalg.norm(sent_arx[:2]-sent_c8[:2]), "bounded command delta", atol=2e-7)
            close(s["hand_object_distance"], np.linalg.norm(before[:3]-before[4:7]), "contact distance proxy")
            close(s["object_displacement"], np.linalg.norm(after[4:7]-before[4:7]), "object motion proxy")
            for field in ("near_object", "grasp_success"):
                close(s[field], row["info"].get(field), "contact saved flag")
            if row["phase"] == "TASK_AFTER_MOVEMENT" and not first_task_seen:
                first_task_seen = True
                if method.startswith("MOVE_"):
                    require(context["first_task"] == {"before": before.tolist(), "raw_policy": row["raw_policy"]}, "common first command context differs")
                    common_checks += int(method != "MOVE_ARX_KEEP")
            observations.append(after)
            total += 1
            step_data.append(s)
        for j in range(16):
            cell = next(segments)
            require((cell["unit"], cell["variant"]) == (unit, raw_case["variant"]), "trajectory segment identity differs")
            if j == 15:
                selected = [s for s in step_data if s["phase"] == "TASK_AFTER_MOVEMENT"]
            else:
                lo, hi = {"ALL": (1, 64), "1_8": (1, 8), "9_16": (9, 16), "17_32": (17, 32), "33_64": (33, 64)}[cell["bin"]]
                selected = [s for s in step_data if s["phase"] == "REPOSITION" and (cell["stage"] == "ALL" or s["movement_stage"] == cell["stage"]) and lo <= s["movement_step"] <= hi]
            check_segment(cell, selected)
            if j == 0:
                require(all(summary["movement"][k] == cell[k] for k in summary["movement"]), "registry movement summary differs from independently checked cells")
            if j == 15:
                require(all(summary["own_task"][k] == cell[k] for k in summary["own_task"]), "registry task summary differs from independently checked cells")
            segments_checked += 1
            if method == "MOVE_ARX_KEEP" and j < 15:
                index = {s["step"]: s for s in selected}
                for _ in range(36):
                    corr = next(corrs)
                    require((corr["unit"], corr["variant"], corr["stage"], corr["bin"]) == (unit, raw_case["variant"], cell["stage"], cell["bin"]), "correlation segment identity differs")
                    left, right = corr["pair"].split("_past__"); right = right.removesuffix("_current")
                    axis, lag = corr["axis"], corr["lag"]
                    xs, ys = [], []
                    for t, now in index.items():
                        previous = index.get(t-lag)
                        if previous:
                            xs.append(None if previous[left] is None else previous[left][axis])
                            ys.append(None if now[right] is None else now[right][axis])
                    n, r = correlation(xs, ys)
                    require(corr["n"] == n, "correlation denominator differs")
                    close(corr["r"], r, "lag correlation", atol=1e-10)
                    correlations_checked += 1
        require(summary["record_rows"] == len(step_data) and summary["history_unavailable_steps"] == min(2, len(step_data)), "registry availability differs")
        movement_data = [s for s in step_data if s["phase"] == "REPOSITION"]
        if movement_data:
            x = np.array([[*s["command"][:2], 1.] for s in movement_data])
            scale = np.sqrt(np.mean(x*x, axis=0))
            condition_value = float(np.linalg.cond(x/np.where(scale > 1e-12, scale, 1.)))
            require(summary["input_design"]["rank"] == int(np.linalg.matrix_rank(x)), "input design rank differs")
            close(summary["input_design"]["condition"], condition_value if math.isfinite(condition_value) else None, "input design condition")
        else:
            require(summary["input_design"]["rank"] is None and summary["input_design"]["condition"] is None, "zero movement rank filled")
        if method == "MOVE_ARX_KEEP":
            errors = [None if s["error_applied"] is None else float(np.linalg.norm(s["error_applied"])) for s in movement_data]
            for variable, saved in summary["state_error_correlations"].items():
                n, r = correlation([s[variable] for s in movement_data], errors)
                require(saved["n"] == n, "state-error correlation denominator differs")
                close(saved["r"], r, "state-error correlation")
        if method == "MOVE_ARX_KEEP" and own_fit and "matrix_xy" in own_fit:
            condition_fault = raw_case["fault_transition"]["active_fault_oracle"]
            param = summary["parameter_error"]
            a, b = np.array(own_fit["matrix_xy"]), np.array(own_fit["bias_xy"])
            ta, tb = np.array(condition_fault["matrix_xy"]), np.array(condition_fault["bias_xy"])
            close(param["matrix_relative"], np.linalg.norm(a-ta)/np.linalg.norm(ta), "parameter relative error")
            close(param["bias_l2"], np.linalg.norm(b-tb), "parameter bias error")
        if raw_case["action"] == "RUN_SAVED_ARX":
            arx_accepted += 1; success_accepted += raw_case["success"]
        cases += 1
        if cases % 216 == 0:
            print(json.dumps({"phase": "INDEPENDENT_ARRAY_AUDIT", "cases": cases, "steps": total}), flush=True)
    require(next(step_iterator, None) is None and next(segments, None) is None and next(corrs, None) is None, "extra diagnostic rows")
    require((cases, total, arx_accepted, success_accepted) == (1296, 236431, 242, 112), "full audit denominator differs")
    paired = read(output/"paired_task_outcomes.json")
    idx = {(r["unit"], r["variant"]): r for r in old_rows}
    for p in paired:
        arx = idx[p["unit"], p["condition"]+"_MOVE_ARX_KEEP"]
        keep = idx[p["unit"], p["condition"]+"_MOVE_KEEP_C8"]
        require(p["delta_loss"] == arx["deadline_loss"]-keep["deadline_loss"], "paired actual loss differs")
        require(p["harmful_update"] == (p["delta_loss"] > 0) and p["improvement"] == (p["delta_loss"] < 0) and p["tie"] == (p["delta_loss"] == 0), "paired update label differs")
        require(p["success_to_failure"] == (keep["success"] and not arx["success"]) and p["failure_to_success"] == (arx["success"] and not keep["success"]), "paired success transition differs")
    require(len(paired) == 324, "pair denominator changed")
    for association in read(output/"group_associations.json"):
        part = paired if association["stratum"] == "ALL" else [r for r in paired if r["task"]+"/"+r["condition"] == association["stratum"]]
        groups = sorted({r["group"] for r in part})
        x = [aggregate([r[association["feature"]] for r in part if r["group"] == g]) for g in groups]
        y = [aggregate([r[association["target"]] for r in part if r["group"] == g]) for g in groups]
        n, r = correlation(x, y)
        require(association["n"] == n and association["full_cases"] == len(part), "group association denominator differs")
        close(association["r"], r, "independent-group association")
    for name, expected in completion["source_artifact_sha256"].items():
        require(sha(source/name) == expected, "source changed during audit")
    result = {"integrity": "PASSED", "scope": "INDEPENDENT_POSTHOC_ARRAY_RECONSTRUCTION_NOT_NEW_PHYSICAL_VALIDATION",
        "diagnostic_completion_sha256": sha(output/"completion.json"), "auditor_sha256": sha(Path(__file__)),
        "executions_checked": cases, "actuator_steps_checked": total, "policy_commands_checked": commands_checked,
        "frozen_future_predictions_checked": future_checked, "segments_checked": segments_checked,
        "lag_correlations_checked": correlations_checked, "common_first_command_pairs_checked": common_checks,
        "canonical_movement_stage_steps": dict(stage_counts), "original_six_comparisons_sha256": config["analysis_summary_sha256"],
        "new_environment_creations": 0, "new_environment_steps": 0, "new_all_resets": 0, "new_simulation_frames": 0,
        "new_api_calls": 0, "new_model_fits": 0, "wall_ns": perf_counter_ns()-started}
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    with audit_output.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, indent=2); f.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=ROOT/"outputs/movement_task/diagnostic_v1")
    p.add_argument("--output", type=Path, default=ROOT/"outputs/movement_task/diagnostic_audit_v1/check.json")
    args = p.parse_args()
    with read_only_analysis_guard():
        check(args.input.resolve(), args.output.resolve())
