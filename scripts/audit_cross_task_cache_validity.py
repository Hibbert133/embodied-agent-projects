"""Independent SVD/normal-CDF/gamma-function audit of crossed cache diagnostics.

Shares source parsing and digest helpers, not forecast, score or statistics code.
It checks offline program ordering, not chronology of historical physical runs.
"""
import argparse
import csv
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys
import numpy as np
from scipy.special import ndtr, gammaincc, gammainccinv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_cross_task_cache_validity as source
from src.probe.cold_start_response import TASKS


def response_reference(model, commands, parameters):
    n = len(commands); x = np.ones((n, 3)); x[:, :2] = np.asarray(commands)[:, :2]
    latent = x @ np.asarray(parameters).reshape(2, 3).T
    a = (-1-latent)/.05; b = (1-latent)/.05
    cdf_a, cdf_b = ndtr(a), ndtr(b); slope = cdf_b-cdf_a
    phi_a = np.exp(-a*a/2)/np.sqrt(2*np.pi); phi_b = np.exp(-b*b/2)/np.sqrt(2*np.pi)
    clipped = latent*slope+.05*(phi_a-phi_b)+1-cdf_b-cdf_a
    impulse = np.asarray(model["impulse"])[:2*n, :2*n]
    mean = np.asarray(model["offset"])[:2*n]+impulse @ clipped.reshape(-1)
    jacobian = np.empty((2*n, 6))
    for column in range(6):
        derivative = np.zeros((n, 2)); axis, component = divmod(column, 3)
        derivative[:, axis] = x[:, component]*slope[:, axis]
        jacobian[:, column] = impulse @ derivative.reshape(-1)
    return mean, jacobian, np.asarray(model["covariance"])[:2*n, :2*n]


def audit(path, output):
    if output.exists():
        raise FileExistsError("preserve independent audit")
    manifest, parent, models = source.load(path)
    identity = {key: manifest[key] for key in source.IDENTITY}
    folder = path.parent; cells = source.load_prefixes(parent)
    completion = source.read(folder/"completion.json")
    for name, sha in completion["artifact_sha256"].items():
        if source.file_digest(folder/name) != sha:
            raise ValueError("completed diagnostic artifact changed: "+name)
    count = 0; maximum = 0.
    def close(actual, expected):
        nonlocal count, maximum
        x, y = np.asarray(actual, dtype=float), np.asarray(expected, dtype=float)
        if x.shape != y.shape or not np.isfinite(x).all() or not np.isfinite(y).all() or not np.allclose(x, y, rtol=1e-9, atol=1e-8):
            raise ValueError("independent numerical reconstruction differs")
        count += x.size
        if x.size: maximum = max(maximum, float(np.max(np.abs(x-y))))
    cache_record = source.read(folder/"source_beliefs.json")
    cached = {(row["stream"], row["task"]): row["belief"] for row in cache_record["beliefs"]}
    if set(cached) != set(cells) or len(cache_record["beliefs"]) != 168 or any(cache_record[k] != identity[k] for k in identity):
        raise ValueError("source belief population differs")
    with gzip.open(folder/"unique_prefixes.jsonl.gz", "rt", encoding="utf-8") as handle:
        prefix_rows = [json.loads(line) for line in handle]
    if len(prefix_rows) != 168 or {(r["stream"], r["task"]) for r in prefix_rows} != set(cells):
        raise ValueError("archived unique-prefix population differs")
    for row in prefix_rows:
        prefix, parameters = cells[row["stream"], row["task"]]
        if row["prefix"] != json.loads(json.dumps(asdict(prefix))) or row["saved_parameters"] != list(parameters):
            raise ValueError("archived visible prefix or saved point differs")
    variances = {}
    for key, (prefix, parameters) in cells.items():
        _, jacobian, covariance = response_reference(models[key[1]], prefix.commands, parameters)
        whitened = np.linalg.solve(np.linalg.cholesky(covariance), jacobian)
        _, singular, right = np.linalg.svd(whitened, full_matrices=False)
        if min(singular) <= 0: raise ValueError("rank-deficient source")
        variance = (right.T/(singular**2)) @ right
        close(cached[key]["parameters"], parameters); close(cached[key]["covariance"], variance)
        if cached[key]["evidence_sha256"] != source.digest(asdict(prefix)):
            raise ValueError("source evidence digest differs")
        active = bool(np.any(np.array([2, 2, .3, 2, 2, .3])-np.abs(parameters) <= 1e-6))
        if cached[key]["active_parameter_bound"] != active or cached[key]["task"] != key[1]:
            raise ValueError("source metadata differs")
        variances[key] = variance
    expected = []
    for stream in range(56):
        for source_task in TASKS:
            for target_task in TASKS:
                if source_task == target_task: continue
                for changed in (False, True):
                    target_stream = stream//8*8+(stream+1)%8 if changed else stream
                    for mode in ("PLUGIN", "SOURCE_UNCERTAINTY"):
                        for n in (2, 4, 8):
                            expected.append((stream, source_task, target_stream, target_task, changed, mode, n))
    actual_rows = []; pair_groups = {}; previous_time = 0
    with gzip.open(folder/"predictions_scores.jsonl.gz", "rt", encoding="utf-8") as handle:
        for index, (stream, st, target_stream, tt, changed, mode, n) in enumerate(expected, 1):
            prediction_event, result_event = json.loads(next(handle)), json.loads(next(handle))
            for event in (prediction_event, result_event):
                if any(event[k] != identity[k] for k in identity): raise ValueError("foreign diagnostic event")
                if event["saved_ns"] <= previous_time: raise ValueError("offline prediction/score ordering differs")
                previous_time = event["saved_ns"]
            if prediction_event["event"] != "PREDICTION" or prediction_event["sequence"] != index or result_event["event"] != "SCORE" or result_event["prediction_sequence"] != index:
                raise ValueError("missing or reordered forecast/score")
            prefix = cells[target_stream, tt][0]
            query = {"task": tt, "initial_observation": list(prefix.initial_observation), "commands": [list(c) for c in prefix.commands[:n]], "controlled_reset_completed": True}
            if prediction_event["query"] != query:
                raise ValueError("future or unrelated evidence in request")
            meta = {"block": stream//8, "source_stream": stream, "source_task": st, "target_stream": target_stream, "target_task": tt,
                    "context_changed": changed, "active_source_bound": cached[stream, st]["active_parameter_bound"]}
            if prediction_event["pair_evaluator"] != meta: raise ValueError("crossed mapping differs")
            mean, jacobian, covariance = response_reference(models[tt], prefix.commands[:n], cells[stream, st][1])
            if mode == "SOURCE_UNCERTAINTY": covariance = covariance+jacobian @ variances[stream, st] @ jacobian.T
            prediction = prediction_event["prediction"]
            if prediction["query_sha256"] != source.digest(query) or prediction["source_belief_sha256"] != source.digest(cached[stream, st]) or prediction["steps"] != n or prediction["mode"] != mode or prediction["physical_probability_qualified"] is not False:
                raise ValueError("prediction is not bound to visible request/cache")
            close(prediction["mean"], mean); close(prediction["covariance"], covariance)
            observed = {**query, "observations": [list(row) for row in prefix.observations[:n]]}
            if result_event["observed"] != observed:
                raise ValueError("unrequested or substituted response")
            values = np.asarray((prefix.initial_observation, *prefix.observations[:n]))
            residual = np.diff(values[:, :2], axis=0).reshape(-1)-mean
            statistic = float(residual @ np.linalg.solve(covariance, residual))
            nominal = float(2*gammainccinv(n, .05)); multiple = float(2*gammainccinv(n, .05/3))
            ref = {"statistic": statistic, "degrees_of_freedom": 2*n, "nominal_tail_probability": float(gammaincc(n, statistic/2)),
                   "nominal_threshold_95": nominal, "alarm_95": statistic > nominal,
                   "nominal_three_look_threshold": multiple, "three_look_alarm": statistic > multiple,
                   "physical_probability_qualified": False}
            result = result_event["score"]
            if set(ref) != set(result): raise ValueError("score schema differs")
            for name, value in ref.items():
                if type(value) is bool:
                    if result[name] != value: raise ValueError("alarm classification differs")
                else: close(result[name], value)
            row = {**identity, **meta, "mode": mode, "prefix_steps": n, **ref}; actual_rows.append(row)
            key = stream, st, target_stream, tt, changed, mode
            pair_groups.setdefault(key, []).append(row)
        if next(handle, None) is not None: raise ValueError("extra diagnostic events")
    pair_rows = []
    for grouped in pair_groups.values():
        first = grouped[0]; keys = (*identity, "block", "source_stream", "source_task", "target_stream", "target_task", "context_changed", "active_source_bound", "mode")
        pair_rows.append({**{key: first[key] for key in keys}, "any_marginal_alarm": any(r["alarm_95"] for r in grouped),
                          "any_three_look_alarm": any(r["three_look_alarm"] for r in grouped)})
    for name, rows in (("all_scores.csv", actual_rows), ("all_pairs.csv", pair_rows)):
        with (folder/name).open(encoding="utf-8", newline="") as handle: table = list(csv.DictReader(handle))
        if len(table) != len(rows): raise ValueError("CSV population differs")
        for saved, reference in zip(table, rows):
            if set(saved) != set(reference): raise ValueError("CSV columns differ")
            for key, value in reference.items():
                if isinstance(value, (str, bool)):
                    if saved[key] != str(value): raise ValueError("CSV categorical field differs")
                else: close(float(saved[key]), value)
    summary = source.read(folder/"summary.json")
    for key, value in (("unique_prefixes", 168), ("duplicate_future_prefixes_checked", 168), ("constructed_pairs", 672),
                       ("forecast_scores", 4032), ("pair_mode_rows", 1344), ("active_source_bounds", sum(b["active_parameter_bound"] for b in cached.values()))):
        close(summary[key], value)
    if len(summary["statistics"]["marginal"]) != 12 or len(summary["statistics"]["three_look_bonferroni"]) != 4:
        raise ValueError("missing registered summary comparison")
    draws = np.random.default_rng(20261018).integers(0, 7, size=(10000, 7))
    for category, rows, flag in (("marginal", actual_rows, "alarm_95"), ("three_look_bonferroni", pair_rows, "any_three_look_alarm")):
        for cell in summary["statistics"][category]:
            chosen = [r for r in rows if r["mode"] == cell["mode"] and r["context_changed"] == cell["context_changed"] and (category != "marginal" or r["prefix_steps"] == cell["prefix_steps"])]
            counts = np.bincount([r["block"] for r in chosen], weights=[int(r[flag]) for r in chosen], minlength=7)
            sizes = np.bincount([r["block"] for r in chosen], minlength=7)
            rates = counts[draws].sum(axis=1)/sizes[draws].sum(axis=1)
            for key, value in (("cases", len(chosen)), ("alarms", sum(r[flag] for r in chosen)), ("alarm_rate", np.mean([r[flag] for r in chosen])),
                               ("block_alarm_counts", counts), ("block_cases", sizes), ("descriptive_block_percentile_95", np.percentile(rates, [2.5, 97.5]))):
                close(cell[key], value)
    costs = summary["costs"]; source_costs = source.read(ROOT/manifest["config"]["bridge_costs"])
    for key in ("new_environment_steps", "new_reset_calls", "new_controller_fits", "new_policy_updates", "api_calls"):
        if costs[key] != 0: raise ValueError("unexpected new physical/model/API cost")
    if costs["reused_full_source_bank_lifecycle"] != source_costs["lifecycle"] or costs["reused_joint_source_lifecycle"] != source_costs["response_source_lifecycle"]:
        raise ValueError("source lifecycle omitted or changed")
    if costs["historical_old_factory_cost_known"] is not False:
        raise ValueError("unknown historical factory costs relabeled")
    for key, value in (("reused_full_source_bank_steps", 440012), ("reused_full_source_bank_controlled_resets", 2688), ("reused_joint_model_source_steps", 3840),
                       ("reused_joint_model_source_controlled_resets", 480), ("new_local_covariance_calculations", 168), ("new_forecast_scores", 4032),
                       ("historical_old_model_source_steps", 21010), ("historical_old_model_source_controlled_resets", 288)):
        close(costs[key], value)
    if summary["physical_probability_qualified"] is not False or summary["new_method_or_task_gain_claim"] is not False:
        raise ValueError("unqualified diagnostic promoted")
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {**identity, "integrity": "PASSED", "source_beliefs_checked": 168, "forecast_scores_checked": 4032,
              "offline_events_checked": 8064, "pair_mode_rows_checked": 1344, "numeric_fields_checked": count,
              "max_absolute_difference": maximum, "source_artifacts_checked": len(manifest["source_artifact_sha256"]),
              "summary_sha256": source.file_digest(folder/"summary.json"), "script_sha256": source.file_digest(Path(__file__)),
              "scope": "Shared source parsing/digests; independent SVD, moments, gamma tails, rows and block summaries. Offline order only; no new physical execution.",
              "new_environment_steps": 0}
    source.write(output, result)
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); audit(args.manifest.resolve(), args.output.resolve())
