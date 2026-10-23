"""Evaluator-only posthoc arrays. No environment, online interface, fit or network."""
from collections import Counter
import hashlib
import json
import math

import numpy as np

VERSION = "MOVEMENT_FAILURE_POSTHOC_V1"
METHODS = ("DIRECT_C8", "MOVE_KEEP_C8", "MOVE_INTEGRAL", "MOVE_ARX_KEEP")
TASKS = ("push-v3", "reach-v3", "door-open-v3")
CONDITIONS = ("UNCHANGED", "CHANGED")
BINS = (("1_8", 1, 8), ("9_16", 9, 16), ("17_32", 17, 32), ("33_64", 33, 64))


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def finite(value):
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [finite(v) for v in value]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    return value


def noise_tape(seed):
    key = int(np.random.SeedSequence([seed, 47001]).generate_state(1)[0])
    return np.random.default_rng(key).normal(0., .05, (500, 3)).astype("<f4")


def actuator_trace(sent, fault, noise):
    """Independent float32 host chain, deliberately without early clipping."""
    command = np.asarray(sent, dtype=np.float32)
    require(command.shape == (4,) and np.isfinite(command).all() and np.max(abs(command)) <= 1, "bounded sent command required")
    matrix = np.asarray(fault["matrix_xy"], np.float32)
    bias = np.asarray(fault["bias_xy"], np.float32)
    zone = np.asarray(fault["deadzone_xy"], np.float32)
    require(matrix.shape == (2, 2) and bias.shape == zone.shape == (2,) and np.all((zone >= 0) & (zone < 1)), "invalid fault arrays")
    latent = matrix @ command[:2] + bias
    transformed = command.copy()
    transformed[:2] = np.sign(latent)*np.maximum(np.abs(latent)-zone, 0)/(1-zone)
    noisy = transformed.copy()
    noisy[:3] += np.asarray(noise, np.float32)
    applied = np.clip(noisy, -1, 1)
    wrong_order = np.clip(transformed, -1, 1)
    wrong_order[:3] += np.asarray(noise, np.float32)
    wrong_order = np.clip(wrong_order, -1, 1)
    return transformed, noisy, applied, wrong_order


def check_actuator(row, fault, noise, expected_step):
    require(row["logical_step"] == expected_step and row["noise_cursor_after"] == expected_step+1,
            "noise cursor / logical step mismatch")
    result = actuator_trace(row["command"], fault, noise)
    require(np.array_equal(result[2], np.asarray(row["executed_action_oracle"], np.float32)),
            "float32 actuator chain mismatch (noise cursor, mapping or clip order)")
    return result


def active_fault(case, step):
    transition = case.get("fault_transition")
    return transition["active_fault_oracle"] if transition and step >= transition["at_calls"] else case["fault_oracle"]


class CausalHistory:
    def __init__(self, initial):
        require(np.shape(initial) == (39,) and np.isfinite(initial).all(), "real initial observation required")
        self.observations = [np.asarray(initial, float)]
        self.pending = False

    def request(self, step):
        require(not self.pending and step == len(self.observations)-1, "future / repeated history request")
        self.pending = True
        if step < 2:
            return None
        a, b, c = self.observations[-3:]
        return c[:3]-b[:3], b[:3]-a[:3]

    def observe(self, step, after):
        require(self.pending and step == len(self.observations)-1, "response requires the current request")
        require(np.shape(after) == (39,) and np.isfinite(after).all(), "complete actual observation required")
        self.observations.append(np.asarray(after, float))
        self.pending = False


def prediction(model, history, command):
    require(history is not None, "two real displacements required; zero padding forbidden")
    values = np.r_[history[0], history[1], np.asarray(command, float)]
    require(values.shape == (10,) and np.max(np.abs(command)) <= 1, "bounded existing model inputs required")
    return np.r_[1., (values-np.asarray(model["mean"]))/np.asarray(model["scale"])] @ np.asarray(model["coefficients"])


def working_input(command, matrix, bias):
    value = np.asarray(command, float).copy()
    mapped = np.asarray(matrix, float) @ value[:2] + bias
    value[:2] = np.clip(mapped, -1, 1)
    return value, mapped


def inverse_controller(matrix, bias):
    inverse = np.linalg.inv(np.asarray(matrix, float))
    return {"matrix_xy": inverse.tolist(), "offset": [*(-inverse @ np.asarray(bias)).tolist(), 0., 0.]}


def controller_trace(raw, controller):
    desired = np.clip(np.asarray(raw, np.float32), -1, 1).astype(float)
    pre = desired.copy()
    pre[:2] = np.asarray(controller["matrix_xy"]) @ desired[:2] + np.asarray(controller["offset"])[:2]
    return desired, pre, np.clip(pre, -1, 1).astype(np.float32)


def ensure_saved_before(fit_record, row):
    estimate = fit_record["estimate"]
    require(estimate["decision_step"] <= row["logical_step"] and fit_record["at_calls"] == estimate["decision_step"]
            and fit_record["saved_ns"] < row["execution_started_ns"], "future parameter or future history used for prediction")


def initial_observation(case):
    events = case["prefix"]["public"]["events"]
    first = next(e["payload"] for e in events if e["kind"] == "PREFIX_PROGRAM")
    return first["initial"]["observation"]


def public_movement(case):
    return None if case.get("movement") is None else case["movement"]["public"]


def case_identity(case):
    condition, method = case["variant"].split("_", 1)
    return {"unit": case["unit"], "group": case["unit"]//3, "task": case["task"],
            "condition": condition, "method": method, "variant": case["variant"], "seed": case["seed"],
            "planned_boundary": case["planned_boundary"]}


def movement_signature(case):
    rows = [r for r in case["physical_rows"] if r["phase"] == "REPOSITION"]
    content = [{k: r[k] for k in ("logical_step", "phase", "command", "executed_action_oracle", "after",
                   "noise_cursor_after", "simulation_time_before", "simulation_time_after")} for r in rows]
    public = public_movement(case)
    witnesses = [w for w in case["state_witnesses"] if w["label"] == "POST_MOVEMENT"]
    return {"steps": len(rows), "trajectory_sha256": digest(content),
        "context_sha256": None if public is None else digest(public["context"]),
        "history_sha256": None if public is None or public["history"] is None else digest(public["history"]["history"]),
        "post_movement_sha256": witnesses[0]["witness"]["comparison_python_sha256"] if witnesses else None,
        "post_movement_native_sha256": witnesses[0]["witness"]["native_sha256"] if witnesses else None}


def canonical_context(case):
    public = public_movement(case)
    result = {**case_identity(case), "movement_signature": movement_signature(case),
        "fit_record": None if public is None else public["fit"], "start": None if public is None else public["start"]}
    if public is not None:
        first = next((r for r in case["physical_rows"] if r["phase"] == "TASK_AFTER_MOVEMENT"), None)
        result["first_task"] = None if first is None else {"raw_policy": first["raw_policy"],
            "before": public["history"]["history"]["transitions"][-1]["after"]["observation"] if public["history"] and public["history"]["history"]["transitions"] else public["start"]["current"]["observation"]}
    else:
        result["first_task"] = None
    return result


def input_design(commands):
    if not commands:
        return {"rank": None, "condition": None, "reason": "ZERO_LENGTH_MOVEMENT"}
    x = np.c_[np.asarray(commands)[:, :2], np.ones(len(commands))]
    scale = np.sqrt(np.mean(x*x, axis=0))
    condition = float(np.linalg.cond(x/np.where(scale > 1e-12, scale, 1.)))
    return {"rank": int(np.linalg.matrix_rank(x)), "condition": finite(condition),
            "reason": "NONFINITE_CONDITION" if not math.isfinite(condition) else None}


def pearson(x, y):
    pairs = [(a, b) for a, b in zip(x, y) if a is not None and b is not None and math.isfinite(a) and math.isfinite(b)]
    if len(pairs) < 3:
        return {"n": len(pairs), "r": None, "reason": "FEWER_THAN_THREE_PAIRED_VALUES"}
    a, b = np.asarray(pairs).T
    if np.std(a) == 0 or np.std(b) == 0:
        return {"n": len(pairs), "r": None, "reason": "CONSTANT_VARIABLE"}
    return {"n": len(pairs), "r": float(np.corrcoef(a, b)[0, 1]), "reason": None}


def correlations(steps):
    result = []
    pairs = (("command", "last"), ("command", "noise"), ("command", "error_true"),
             ("last", "noise"), ("last", "error_true"), ("error_true", "noise"))
    index = {s["step"]: s for s in steps}
    for left, right in pairs:
        for lag in (0, 1, 2):
            for axis in (0, 1):
                x, y = [], []
                for t, row in index.items():
                    previous = index.get(t-lag)
                    if previous is not None:
                        x.append(None if previous.get(left) is None else previous[left][axis])
                        y.append(None if row.get(right) is None else row[right][axis])
                result.append({"pair": left+"_past__"+right+"_current", "lag": lag, "axis": axis, **pearson(x, y)})
    return result


def rms(values):
    available = [v for v in values if v is not None]
    return None if not available else float(np.sqrt(np.mean(np.asarray(available)**2)))


def mean(values):
    values = [v for v in values if v is not None]
    return None if not values else float(np.mean(values))


def summarize_steps(steps):
    result = {"n": len(steps), "missing_reason": "ZERO_LENGTH_SEGMENT" if not steps else None}
    for key in ("error_saved", "error_true", "error_applied", "error_zero", "input_noise_component", "interface_component"):
        result[key+"_rmse"] = rms([s[key] for s in steps])
        result[key+"_n"] = sum(s[key] is not None for s in steps)
    for key in ("policy_clip", "correction_clip", "actuator_clip", "transformed_oos", "early_clip_difference",
                "command_delta", "pre_command_delta", "c8_clip", "arx_clip", "hand_object_distance",
                "object_displacement", "near_object", "grasp_success", "hand_x", "hand_y", "hand_z"):
        result[key+"_mean"] = mean([s[key] for s in steps])
        result[key+"_available"] = sum(s[key] is not None for s in steps)
    return result


def stage_cells(identity, steps):
    out = []
    movement = [s for s in steps if s["phase"] == "REPOSITION"]
    for stage in ("ALL", "LIFT", "POST_LIFT"):
        for name, low, high in (("ALL", 1, 64), *BINS):
            selected = [s for s in movement if (stage == "ALL" or s["movement_stage"] == stage) and low <= s["movement_step"] <= high]
            out.append({**identity, "period": "COMMON_MOVEMENT", "stage": stage, "bin": name, **summarize_steps(selected)})
    task = [s for s in steps if s["phase"] == "TASK_AFTER_MOVEMENT"]
    out.append({**identity, "period": "OWN_TASK", "stage": "ALL", "bin": "ALL", **summarize_steps(task)})
    return out


def analyze_case(case, model, paired_context):
    identity = case_identity(case)
    public = public_movement(case)
    fit_record = paired_context["fit_record"] if identity["method"].startswith("MOVE_") else None
    estimate = None if fit_record is None else fit_record["estimate"]
    fit = None if estimate is None else estimate["fit"]
    parameters = fit is not None and "matrix_xy" in fit
    valid = bool(fit and fit["valid"])
    arx = inverse_controller(fit["matrix_xy"], fit["bias_xy"]) if valid else None
    prefix_choices = [e["payload"] for e in case["prefix"]["public"]["events"]
                      if e["kind"] == "CHOICE" and e["payload"].get("purpose") == "CURRENT_POLICY_CONTROLLER"]
    c8 = prefix_choices[-1]["controller"] if prefix_choices else None
    decision = None if public is None else next((e["payload"] for e in public["events"] if e["kind"] == "MOVEMENT_TASK_DECISION"), None)
    actual_controller = None if decision is None else decision["controller"]
    move_updates = {} if public is None else {e["payload"]["at_calls"]: e["payload"]["integral_after"] for e in public["events"] if e["kind"] == "INTEGRAL_UPDATE"}
    anchor = None if public is None else np.asarray(next(e["payload"]["anchor"] for e in public["events"] if e["kind"] == "MOVEMENT_TASK_CHOICE"))
    move_initial = None if public is None else np.asarray(public["start"]["current"]["observation"])
    lifted = False if anchor is None else move_initial[2] >= anchor[2]-.015
    history = CausalHistory(initial_observation(case))
    tape, steps = noise_tape(case["seed"]), []
    movement_step = 0
    previous_move = None
    algebra_max = 0.
    first_task = None
    for i, row in enumerate(case["physical_rows"]):
        before = history.observations[-1]
        h = history.request(i)
        after = np.asarray(row["after"]["observation"])
        fault = active_fault(case, i)
        pre_act, noisy, applied, wrong = check_actuator(row, fault, tape[i], i)
        command = np.asarray(row["command"])
        raw = row["raw_policy"]
        phase = row["phase"]
        movement_stage = None
        correction_pre = None
        if phase == "REPOSITION":
            movement_step += 1
            movement_stage = "POST_LIFT" if lifted else "LIFT"
            target = anchor if lifted else np.r_[move_initial[:2], anchor[2]]
            velocity = np.zeros(3) if previous_move is None else before[:3]-previous_move[:3]
            feedback = 8.*(target-before[:3])-16.*velocity
            desired = np.r_[np.clip(feedback+np.r_[move_updates[i], 0.], -.5, .5), -1.]
            correction_pre = desired.copy()
            correction_pre[:2] = np.asarray(c8["matrix_xy"]) @ desired[:2]+np.asarray(c8["offset"])[:2]
            require(np.array_equal(np.clip(correction_pre, -1, 1).astype(np.float32), np.asarray(row["command"], np.float32)), "movement correction reconstruction mismatch")
            previous_move = before.copy()
            lifted = lifted or after[2] >= anchor[2]-.015
        elif raw is not None:
            chosen = actual_controller if phase == "TASK_AFTER_MOVEMENT" else c8
            if chosen is not None:
                _, correction_pre, replay_sent = controller_trace(raw, chosen)
                require(np.array_equal(replay_sent, np.asarray(command, np.float32)), "saved actual controller or inverse mapping mismatch")
        if phase == "TASK_AFTER_MOVEMENT" and first_task is None:
            first_task = {"before": before.tolist(), "raw_policy": raw}
            if identity["method"].startswith("MOVE_") and paired_context["first_task"] is not None:
                require(first_task == paired_context["first_task"], "common post-movement first policy/state differs")
        saved_prediction = true_prediction = applied_prediction = zero_prediction = None
        if h is not None:
            true_input, _ = working_input(command, fault["matrix_xy"], fault["bias_xy"])
            true_prediction = prediction(model, h, true_input)
            applied_prediction = prediction(model, h, applied)
            zero_prediction = prediction(model, h, np.clip(pre_act, -1, 1))
            if identity["method"] == "MOVE_ARX_KEEP" and parameters and phase in ("REPOSITION", "TASK_AFTER_MOVEMENT"):
                if phase == "TASK_AFTER_MOVEMENT":
                    ensure_saved_before(fit_record, row)
                inp, _ = working_input(command, fit["matrix_xy"], fit["bias_xy"])
                saved_prediction = prediction(model, h, inp)
        y = after[:2]-before[:2]
        error = lambda p: None if p is None else (y-p).tolist()
        noise_component = None if h is None else (applied_prediction-zero_prediction).tolist()
        interface_component = None if h is None else (zero_prediction-true_prediction).tolist()
        if h is not None:
            difference = (y-true_prediction)-((y-applied_prediction)+np.array(noise_component)+interface_component)
            algebra_max = max(algebra_max, float(np.max(abs(difference))))
        c8_pre = c8_sent = arx_pre = arx_sent = None
        if raw is not None and c8 is not None:
            _, c8_pre, c8_sent = controller_trace(raw, c8)
            if arx is not None and phase == "TASK_AFTER_MOVEMENT":
                _, arx_pre, arx_sent = controller_trace(raw, arx)
        unavailable = None if h is not None else "FEWER_THAN_TWO_REAL_DISPLACEMENTS"
        s = {"step": i, "phase": phase, "movement_step": movement_step if phase == "REPOSITION" else None,
            "movement_stage": movement_stage, "before_xyz": before[:3].tolist(), "after_xyz": after[:3].tolist(),
            "last": None if h is None else h[0].tolist(), "prior": None if h is None else h[1].tolist(),
            "command": command.tolist(), "raw_policy": raw, "noise": tape[i].tolist(),
            "actuator_pre": pre_act.tolist(), "actuator_noisy": noisy.tolist(), "applied": applied.tolist(),
            "error_saved": error(saved_prediction), "error_true": error(true_prediction),
            "error_applied": error(applied_prediction), "error_zero": error(zero_prediction),
            "input_noise_component": noise_component, "interface_component": interface_component,
            "history_missing_reason": unavailable,
            "saved_error_semantics": "POSTHOC_IN_SAMPLE" if saved_prediction is not None and phase == "REPOSITION" else "FROZEN_FUTURE_ONE_STEP" if saved_prediction is not None else None,
            "policy_clip": None if raw is None else bool(np.any(abs(np.asarray(raw, np.float32)) > 1)),
            "correction_clip": None if correction_pre is None else bool(np.any(abs(correction_pre) > 1)),
            "correction_pre": None if correction_pre is None else correction_pre.tolist(),
            "actuator_clip": bool(np.any(abs(noisy) > 1)), "transformed_oos": bool(np.any(abs(pre_act) > 1)),
            "early_clip_difference": not np.array_equal(applied, wrong),
            "c8_pre": None if c8_pre is None else c8_pre.tolist(), "c8_sent": None if c8_sent is None else c8_sent.tolist(),
            "arx_pre": None if arx_pre is None else arx_pre.tolist(), "arx_sent": None if arx_sent is None else arx_sent.tolist(),
            "command_delta": None if arx_sent is None else float(np.linalg.norm(arx_sent[:2]-c8_sent[:2])),
            "pre_command_delta": None if arx_pre is None else float(np.linalg.norm(arx_pre[:2]-c8_pre[:2])),
            "c8_clip": None if c8_pre is None else bool(np.any(abs(c8_pre[:2]) > 1)),
            "arx_clip": None if arx_pre is None else bool(np.any(abs(arx_pre[:2]) > 1)),
            "hand_object_distance": float(np.linalg.norm(before[:3]-before[4:7])),
            "object_displacement": float(np.linalg.norm(after[4:7]-before[4:7])),
            "near_object": row["info"].get("near_object"), "grasp_success": row["info"].get("grasp_success"),
            "hand_x": float(before[0]), "hand_y": float(before[1]), "hand_z": float(before[2])}
        steps.append(s)
        history.observe(i, after)
    require(len(steps) == case["total_steps"] and movement_step == case["reposition_steps"], "case step / movement denominator mismatch")
    movement = [s for s in steps if s["phase"] == "REPOSITION"]
    fitted_summary = summarize_steps(movement)
    if fit and "residual_rmse_m" in fit and identity["method"] == "MOVE_ARX_KEEP":
        require(np.isclose(fitted_summary["error_saved_rmse"], fit["residual_rmse_m"], rtol=1e-7, atol=1e-12), "saved fit residual changed")
    reason = "NO_LIVE_BOUNDARY" if not case["boundary_ready"] else "NOT_ARX_PROGRAM" if identity["method"] != "MOVE_ARX_KEEP" else "ENDED_BEFORE_FIT" if fit is None else fit["reason"]
    truth = active_fault(case, case["planned_boundary"])
    parameter_error = None
    if parameters and identity["method"] == "MOVE_ARX_KEEP":
        a, b = np.asarray(fit["matrix_xy"]), np.asarray(fit["bias_xy"])
        ta, tb = np.asarray(truth["matrix_xy"]), np.asarray(truth["bias_xy"])
        parameter_error = {"matrix_frobenius": float(np.linalg.norm(a-ta)), "matrix_relative": float(np.linalg.norm(a-ta)/np.linalg.norm(ta)),
                           "bias_l2": float(np.linalg.norm(b-tb)), "bias_relative": None if np.linalg.norm(tb) == 0 else float(np.linalg.norm(b-tb)/np.linalg.norm(tb))}
    cells = stage_cells(identity, steps)
    summary = {**identity, **{k: case[k] for k in ("completed", "success", "total_steps", "deadline_loss", "action", "stopped", "boundary_ready")},
        "record_rows": len(steps), "history_unavailable_steps": sum(s["last"] is None for s in steps),
        "fit_available": estimate is not None if identity["method"] == "MOVE_ARX_KEEP" else False,
        "fit_valid": valid if identity["method"] == "MOVE_ARX_KEEP" and fit is not None else None,
        "missing_or_fit_reason": reason, "parameter_error": parameter_error,
        "input_design": input_design([s["command"] for s in movement]),
        "movement": fitted_summary, "own_task": cells[-1], "first_task": first_task,
        "first_command_delta": next((s["command_delta"] for s in steps if s["phase"] == "TASK_AFTER_MOVEMENT"), None),
        "actual_actuator_steps_checked": len(steps), "algebra_max_abs": algebra_max,
        "common_movement_weight": identity["method"] == "MOVE_ARX_KEEP",
        "arx_command_semantics": "SAVED_ACTUAL_ESTIMATE" if identity["method"] == "MOVE_ARX_KEEP" else "POSTHOC_COMMON_DATA_COMMAND_COMPARISON_ONLY"}
    if fit and identity["method"] == "MOVE_ARX_KEEP" and "design_rank" in fit:
        require(summary["input_design"]["rank"] == fit["design_rank"], "saved rank differs")
        condition = summary["input_design"]["condition"]
        require(condition is None and fit["scaled_condition"] is None or condition is not None and
                fit["scaled_condition"] is not None and np.isclose(condition, fit["scaled_condition"]), "saved condition differs")
    return finite(summary), finite(steps), finite(cells)


def grouped_means(rows, fields):
    """Trajectory first, group second; never pool timesteps."""
    groups = sorted({r["group"] for r in rows})
    output = {}
    for field in fields:
        group_values = [mean([r.get(field) for r in rows if r["group"] == g]) for g in groups]
        output[field] = {"mean": mean(group_values), "available_trajectories": sum(r.get(field) is not None for r in rows),
            "available_groups": sum(v is not None for v in group_values), "groups_total": len(groups)}
    return output


def pair_outcomes(registry):
    index = {(r["unit"], r["condition"], r["method"]): r for r in registry}
    pairs = []
    for row in registry:
        if row["method"] != "MOVE_ARX_KEEP":
            continue
        keep = index[row["unit"], row["condition"], "MOVE_KEEP_C8"]
        diff = row["deadline_loss"]-keep["deadline_loss"]
        pairs.append({"unit": row["unit"], "group": row["group"], "task": row["task"], "condition": row["condition"],
            "delta_loss": diff, "harmful_update": diff > 0, "improvement": diff < 0, "tie": diff == 0,
            "success_to_failure": bool(keep["success"] and not row["success"]),
            "failure_to_success": bool(row["success"] and not keep["success"]), "action": row["action"]})
    return pairs
