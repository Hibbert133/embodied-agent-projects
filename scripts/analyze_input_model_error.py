"""Evaluator-only decomposition of audited inputs; no simulator, refitting or API.

The exact injected command is unavailable to an online agent. Supplying it to a
frozen nominal predictor isolates an input-conditioned prediction residual, not
an observable detector or a causal classification of physical failure sources.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TASKS = ("push-v3", "reach-v3", "door-open-v3")
OPERATORS = ("NOMINAL", "GAIN_COUPLED", "ROTATED_GAIN", "REFLECTED_SHEAR")
METHODS = ("NO_PROBE", "PROBE8_NO_CORRECTION", "PROBE16_NO_CORRECTION", "DYNAMIC_OLS16",
           "PRIOR_AFFINE16", "PRIOR_NEAREST16", "FWD_LINEAR8", "FWD_LINEAR16",
           "FWD_QUADRATIC8", "FWD_QUADRATIC16", "PASSIVE_LINEAR", "ORACLE16")
MODELS = ("LINEAR_ARX", "QUADRATIC_STATE")
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
MODEL_KEYS = {"method", "training_samples", "mean", "scale", "physical_response_qualified",
              "probability_guarantee", "coefficients", "ridge", "feature_count", "training_rmse"}
SOURCE_RUN = "forward_operator_20261014T081128Z_37eee13f9943"
SOURCE_AUDIT_SHA256 = "cef41058d1053bc4d59e0cfafab07a6bd5fc2eff06bb5fcaf673f2d6d3ff5b69"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rng_hash(rng):
    return hashlib.sha256(json.dumps(rng.bit_generator.state, sort_keys=True).encode()).hexdigest()


def checked_array(values, shape):
    result = np.asarray(values, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError("invalid evaluator numeric array")
    return result


def reconstruct_inputs(record, operator, noise_std):
    """Reproduce float32 affine/noise/clip arithmetic and verify every RNG link."""
    task_index = TASKS.index(record["task"])
    operator_index = OPERATORS.index(record["operator_oracle"])
    seed = int(np.random.SeedSequence([record["seed"], task_index, operator_index, 0xF091]).generate_state(1)[0])
    rng = np.random.default_rng(seed)
    matrix = checked_array(operator["matrix_xy"], (2, 2)).astype(np.float32)
    bias = checked_array(operator["bias_xy"], (2,)).astype(np.float32)
    previous = record["initial"]
    mean_inputs, actual_inputs = [], []
    for index, row in enumerate(record["trace"], 1):
        if row["before"] != previous or row["host_calls"] != index or row["rng_before"] != rng_hash(rng):
            raise ValueError("evaluator state/RNG prefix changed")
        sent = checked_array(row["command"], (4,)).astype(np.float32)
        if np.any(np.abs(sent) > 1) or row["phase"] not in ("PROBE", "POLICY"):
            raise ValueError("invalid sent command/phase")
        no_noise = sent.copy()
        no_noise[:2] = matrix @ sent[:2] + bias
        acted = no_noise.copy()
        acted[:3] += rng.normal(0, noise_std, 3).astype(np.float32)
        if row["rng_after"] != rng_hash(rng):
            raise ValueError("evaluator noise sequence changed")
        # Identical to LiveHost: all four coordinates are clipped after injection.
        mean_inputs.append(np.clip(no_noise, -1, 1))
        actual_inputs.append(np.clip(acted, -1, 1))
        previous = row["after"]
    return np.asarray(mean_inputs).reshape(-1, 4), np.asarray(actual_inputs).reshape(-1, 4)


def predict_batch(model, observations, deltas, commands):
    """Independent feature expansion; exactly two completed displacement warmups."""
    kind = model.get("method")
    if set(model) != MODEL_KEYS or kind not in MODELS or model["physical_response_qualified"] is not False or model["probability_guarantee"] is not False:
        raise ValueError("unqualified frozen nominal model required")
    n = len(commands)
    observations = checked_array(observations, (n, 39))
    deltas = checked_array(deltas, (n, 3))
    commands = checked_array(commands, (n, 4))
    size = 10 if kind == "LINEAR_ARX" else 20
    mean = checked_array(model["mean"], (size,))
    scale = checked_array(model["scale"], (size,))
    count = 11 if size == 10 else 231
    coefficient = checked_array(model["coefficients"], (count, 2))
    if np.any(scale <= 0) or model["feature_count"] != count or model["ridge"] != 1e-3:
        raise ValueError("frozen model scaling/design changed")
    if n < 3:
        return np.empty((0, 2))
    past, prior, sent, state = deltas[1:-1], deltas[:-2], commands[2:], observations[2:]
    if kind == "LINEAR_ARX":
        inputs = np.concatenate((past, prior, sent), axis=1)
    else:
        hand = state[:, :3]
        inputs = np.concatenate((hand, past, prior, sent, state[:, 3:4],
                                 state[:, 4:7] - hand, state[:, -3:] - hand), axis=1)
    z = (inputs - mean) / scale
    columns = [np.ones((len(z), 1)), z]
    if kind == "QUADRATIC_STATE":
        i, j = np.triu_indices(size)
        columns.append(z[:, i] * z[:, j])
    result = np.concatenate(columns, axis=1) @ coefficient
    if not np.isfinite(result).all():
        raise ValueError("nonfinite evaluator prediction")
    return result


def residual_metrics(mean_prediction, actual_input_prediction, observed):
    total = np.asarray(mean_prediction) - np.asarray(observed)
    model = np.asarray(actual_input_prediction) - np.asarray(observed)
    input_component = np.asarray(mean_prediction) - np.asarray(actual_input_prediction)
    if total.shape != model.shape or total.shape != input_component.shape or total.ndim != 2 or total.shape[1] != 2:
        raise ValueError("invalid paired decomposition")
    if not all(np.isfinite(x).all() for x in (total, model, input_component)):
        raise ValueError("nonfinite paired decomposition")
    if not np.allclose(total, model + input_component, atol=1e-12, rtol=1e-12):
        raise ValueError("signed residual identity failed")
    n = len(total)
    result = {"samples": n, "cross_sum": float(2 * np.sum(model * input_component))}
    for name, value in (("total", total), ("model", model), ("input", input_component)):
        result[name + "_squared_sum"] = float(np.sum(value * value))
        result[name + "_rmse_m"] = float(np.sqrt(np.mean(value * value))) if n else None
        result[name + "_max_abs_m"] = float(np.max(np.abs(value))) if n else None
    if not np.isclose(result["total_squared_sum"], result["model_squared_sum"] + result["input_squared_sum"] + result["cross_sum"], atol=1e-12, rtol=1e-10):
        raise ValueError("squared residual identity failed")
    return result


def passive_fit_changes(record):
    """Compare only accepted saved point estimates; rejected updates stay rejected."""
    if record["method"] != "PASSIVE_LINEAR":
        return []
    previous = None
    pairs = []
    for declaration in record["decisions"]:
        choice = declaration["choice"]
        fit = choice["fit"]
        if fit is None or not fit["valid"] or choice["status"] != "READY_POINT_ESTIMATE":
            continue
        current = np.column_stack((checked_array(fit["matrix_xy"], (2, 2)), checked_array(fit["bias_xy"], (2,))))
        controller = choice["controller"]
        inverse = checked_array(controller["matrix_xy"], (2, 2))
        recovered = np.linalg.inv(inverse)
        bias = -recovered @ checked_array(controller["offset"], (4,))[:2]
        if not np.allclose(current, np.column_stack((recovered, bias)), atol=1e-10, rtol=1e-10):
            raise ValueError("accepted fit differs from executed saved controller")
        if previous is not None:
            before, parameters = previous
            pairs.append({"from_sequence": before["sequence"], "to_sequence": declaration["sequence"],
                          "from_step": before["at_host_calls"], "to_step": declaration["at_host_calls"],
                          "max_parameter_change": float(np.max(np.abs(current - parameters))),
                          "true_operator_change_oracle": 0.0})
        previous = (declaration, current)
    return pairs


def episode_diagnostics(record, models, operator, noise_std):
    mean_inputs, actual_inputs = reconstruct_inputs(record, operator, noise_std)
    trace = record["trace"]
    before = np.array([r["before"]["observation"] for r in trace], dtype=float).reshape(-1, 39)
    after = np.array([r["after"]["observation"] for r in trace], dtype=float).reshape(-1, 39)
    deltas = after[:, :3] - before[:, :3]
    identity = {k: record[k] for k in ("episode_index", "seed", "task", "operator_oracle", "method")}
    rows = []
    for kind in MODELS:
        mean = predict_batch(models[kind], before, deltas, mean_inputs)
        actual = predict_batch(models[kind], before, deltas, actual_inputs)
        for phase in ("PROBE", "POLICY"):
            mask = np.array([r["phase"] == phase for r in trace[2:]], dtype=bool)
            rows.append({**identity, "predictor": kind, "phase": phase,
                         **residual_metrics(mean[mask], actual[mask], deltas[2:, :2][mask])})
    changes = [{**identity, **p} for p in passive_fit_changes(record)]
    return rows, changes


def aggregate(rows):
    selected = [r for r in rows if r["samples"]]
    samples = sum(r["samples"] for r in selected)
    result = {"episodes_with_samples": len(selected), "samples": samples,
              "cross_sum": sum(r["cross_sum"] for r in selected)}
    for name in ("total", "model", "input"):
        squared = sum(r[name + "_squared_sum"] for r in selected)
        maxima = [r[name + "_max_abs_m"] for r in selected]
        result[name + "_step_weighted_rmse_m"] = float(np.sqrt(squared / (2 * samples))) if samples else None
        result[name + "_mean_episode_max_m"] = float(np.mean(maxima)) if maxima else None
        result[name + "_episode_max_p90_m"] = float(np.quantile(maxima, .9)) if maxima else None
        result[name + "_squared_sum"] = squared
    return result


def verify_files(directory, expected):
    if any(sha(directory / name) != expected_sha for name, expected_sha in expected.items()):
        raise ValueError("audited source bytes changed")


def analyze(manifest_path, audit_path):
    if sha(audit_path) != SOURCE_AUDIT_SHA256:
        raise ValueError("registered immutable primary audit changed")
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    a = json.loads(audit_path.read_text(encoding="utf-8"))
    if m["experiment_run_id"] != SOURCE_RUN or a["integrity"] != "PASSED" or any(a[k] != m[k] for k in IDENTITY) or a["episodes"] != 1152 or a["physical_steps"] != 235479:
        raise ValueError("matching complete original audit required")
    expected_files = {"manifest.json", "decisions.jsonl", "status.json", "summary.json"} | {"episodes_" + method + ".jsonl.gz" for method in METHODS}
    if set(a["artifact_sha256"]) != expected_files or m["config"]["protocol_id"] != "forward_operator_task_utility_v1":
        raise ValueError("unexpected source population/artifacts")
    verify_files(manifest_path.parent, a["artifact_sha256"])
    model_path = ROOT / m["config"]["forward_model_path"]
    if sha(model_path) != m["config"]["forward_model_sha256"]:
        raise ValueError("frozen forward bank changed")
    bank = json.loads(model_path.read_text(encoding="utf-8"))["models"]
    seen = set()
    rows, changes = [], []
    counted_steps = 0
    for method in METHODS:
        with gzip.open(manifest_path.parent / ("episodes_" + method + ".jsonl.gz"), "rt", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                key = (record["seed"], record["task"], record["operator_oracle"], record["method"])
                if key in seen or record["method"] != method or any(record[k] != m[k] for k in IDENTITY):
                    raise ValueError("duplicate/foreign source episode")
                seen.add(key)
                operator = next(o for o in m["config"]["operators_oracle"] if o["id"] == record["operator_oracle"])
                case_rows, case_changes = episode_diagnostics(record, bank[record["task"]], operator, m["config"]["noise_std"])
                rows.extend(case_rows)
                changes.extend(case_changes)
                counted_steps += len(record["trace"])
        print(f"Replayed evaluator inputs: {method}", flush=True)
    expected = {(s, t, o, method) for s in range(10600, 10608) for t in TASKS for o in OPERATORS for method in METHODS}
    if seen != expected or counted_steps != a["physical_steps"]:
        raise ValueError("source population/cost incomplete")
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["method"], row["task"], row["predictor"], row["phase"])].append(row)
    summary = [{"method": method, "task": task, "predictor": kind, "phase": phase, **aggregate(selected)}
               for (method, task, kind, phase), selected in sorted(grouped.items())]
    primary = [s for s in summary if s["method"] == "NO_PROBE" and s["phase"] == "POLICY"]
    magnitudes = [r["max_parameter_change"] for r in changes]
    return {**{k: m[k] for k in IDENTITY}, "analysis_protocol_id": "input_model_error_audit_v1",
            "primary_audit_sha256": sha(audit_path), "forward_bank_sha256": sha(model_path),
            "source_artifact_sha256": a["artifact_sha256"], "input_reconstruction": "PASSED",
            "replayed_episodes": len(seen), "replayed_environment_steps": counted_steps,
            "two_step_warmups": 2 * len(seen), "predicted_steps_per_model": counted_steps - 2 * len(seen),
            "episode_metrics": rows, "grouped_metrics": summary, "primary_no_probe": primary,
            "static_passive_fit_changes": changes,
            "static_passive_change_summary": {"pairs": len(changes), "episodes": len({r["episode_index"] for r in changes}),
                "median_max_parameter_change": float(np.median(magnitudes)) if magnitudes else None,
                "p90_max_parameter_change": float(np.quantile(magnitudes, .9)) if magnitudes else None,
                "maximum_parameter_change": max(magnitudes) if magnitudes else None,
                "true_operator_change": 0.0},
            "new_environment_steps": 0, "new_environment_resets": 0, "new_api_calls": 0, "model_refits": 0,
            "physical_response_qualified": False, "probability_guarantee": False, "algorithm_novelty_established": False,
            "scope": "Evaluator-only paired prediction on the same observed histories, exact signed-error decomposition and static accepted-fit drift. No dynamics resimulation, observable detector or causal source classification."}


def report(result):
    lines = ["# 输入噪声与名义模型误差的只读分解", "",
             "已知实际加噪输入仍存在的误差，是当前冻结模型在当前可见历史下的预测残差；它不是代理可直接得到的信号。", "",
             "| 未纠正政策任务 | 预测器 | 轨迹数 | 总误差均值最大 mm | 已知实际输入后均值最大 mm | 输入影响均值最大 mm |",
             "|---|---|---:|---:|---:|---:|"]
    for r in result["primary_no_probe"]:
        lines.append(f"| {r['task']} | {r['predictor']} | {r['episodes_with_samples']} | {1000*r['total_mean_episode_max_m']:.4f} | {1000*r['model_mean_episode_max_m']:.4f} | {1000*r['input_mean_episode_max_m']:.4f} |")
    p = result["static_passive_change_summary"]
    lines += ["", f"静态执行器下，共 {p['pairs']} 对有效被动更新，来自 {p['episodes']} 个相关方法案例。",
              f"相邻有效点估计的最大系数变化中位／p90／最大为 {p['median_max_parameter_change']}／{p['p90_max_parameter_change']}／{p['maximum_parameter_change']}；真实算子变化为零。",
              "参数更新包含估计噪声、支持变化及模型误差；这些量没有被归因分开，不可作为执行器变点标签。", "",
              "有符号分解 r_total = r_model + r_input 严格成立；平方误差还含 2〈r_model,r_input〉。各分量的最大值不是可相加的比例或独立因果归因。",
              "不加噪输入是在截断后构造的确定性参考，不是截断加噪输入的期望。z 噪声也计入输入影响；夹爪不加噪。",
              "每轨迹前两步建立真实位移历史，仍保留在成本中。任务／方法历史和长度不同，仅作描述；独立种子簇仍为八个。", "",
              f"重放 {result['replayed_episodes']} 轨迹／{result['replayed_environment_steps']:,} 原始步；每预测器 {result['predicted_steps_per_model']:,} 个有历史的预测。",
              "新增物理步、重置、API 与拟合均为零；不修改旧成功率、失败门或保留种子。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.resolve()
    source = args.manifest.resolve()
    if target.exists() or target == source.parent or source.parent in target.parents:
        raise FileExistsError("analysis must use a new directory outside immutable collection")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("commit the analysis source before replay")
    result = analyze(source, args.audit.resolve())
    result.update(analysis_source_git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  analysis_source_sha256=sha(Path(__file__)), analyzed_at_utc=datetime.now(timezone.utc).isoformat())
    target.mkdir(parents=True, exist_ok=False)
    (target / "diagnostics.json").write_bytes((json.dumps(result, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    (target / "report.md").write_bytes(report(result).encode("utf-8"))
    print(report(result))
