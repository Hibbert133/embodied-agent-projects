"""One-shot offline crossed-cache predictive diagnostic; no environment execution."""
import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_cold_start_task_bridge as bridge
from src.probe.cold_start_response import ColdPrefix, TASKS
from src.probe.cold_cache_prediction import ALPHA, LOOKS, MODES, PredictionQuery, digest, forecast, score, source_belief

CONFIG = ROOT/"configs/cross_task_cache_validity/development_v1.json"
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
OWN_INPUTS = ("src/probe/cold_cache_prediction.py", "scripts/run_cross_task_cache_validity.py",
              "scripts/audit_cross_task_cache_validity.py", "tests/test_cold_cache_prediction.py",
              "configs/cross_task_cache_validity/development_v1.json",
              "docs/protocols/cross_task_cache_validity_development_v1.md",
              "docs/research/cross_task_cache_validity_question_v1.md")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(config):
    for key in ("bridge_manifest", "bridge_audit", "bridge_costs"):
        if file_digest(ROOT/config[key]) != config[key+"_sha256"]:
            raise ValueError("bound source changed: "+key)
    manifest = bridge.load(ROOT/config["bridge_manifest"])
    audit = read(ROOT/config["bridge_audit"])
    if audit["integrity"] != "PASSED" or audit["episodes"] != 2688:
        raise ValueError("complete audited source required")
    parent = (ROOT/config["bridge_manifest"]).parent
    for name, sha in audit["artifact_sha256"].items():
        if file_digest(parent/name) != sha:
            raise ValueError("bound source artifact changed: "+name)
    models = read(ROOT/manifest["config"]["response_model_path"])["joint"]
    return manifest, parent, models, audit


def load_prefixes(parent):
    cells = {}; duplicates = 0; joint_rows = 0
    for path in sorted(parent.glob("episodes_*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                if record["method"] != "JOINT8":
                    continue
                joint_rows += 1
                trace = record["trace"][:8]
                if len(trace) != 8 or any(row["phase"] != "FIXED_PROBE" for row in trace):
                    raise ValueError("complete actual initial probe required")
                prefix = ColdPrefix(record["task"], tuple(record["initial"]["observation"]),
                                    tuple(tuple(row["command"]) for row in trace),
                                    tuple(tuple(row["after"]["observation"]) for row in trace), True)
                fits = [row["fit"] for row in record["decisions"] if row.get("fit") is not None]
                if len(fits) != 1 or not fits[0]["valid"]:
                    raise ValueError("source JOINT8 point is not available")
                parameters = tuple(np.column_stack((fits[0]["matrix_xy"], fits[0]["bias_xy"])).ravel())
                key = record["stream"], record["task"]
                value = prefix, parameters
                if key in cells:
                    if cells[key] != value:
                        raise ValueError("future duplicates have different initial evidence or saved point")
                    duplicates += 1
                else:
                    cells[key] = value
    if joint_rows != 336 or len(cells) != 168 or duplicates != 168 or set(cells) != {(s, t) for s in range(56) for t in TASKS}:
        raise ValueError("missing, extra or dependent-prefix source")
    return cells


def prepare():
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT).strip():
        raise ValueError("commit clean implementation before preparation")
    config = read(CONFIG); parent, _, _, audit = sources(config)
    if config["prefix_steps"] != list(LOOKS) or config["modes"] != list(MODES) or config["nominal_alpha"] != ALPHA:
        raise ValueError("registered reference differs")
    output = ROOT/config["output_root"]
    if list(output.glob("*/manifest.json")):
        raise FileExistsError("one-shot diagnostic already prepared")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    run_id = "cross_task_cache_validity_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    value = {"experiment_run_id": run_id, "source_git_commit": commit, "config": config,
             "input_sha256": {name: file_digest(ROOT/name) for name in OWN_INPUTS},
             "source_run_id": parent["experiment_run_id"], "source_manifest_id": parent["manifest_id"],
             "source_artifact_sha256": audit["artifact_sha256"],
             "analysis_status": "POSTHOC_OFFLINE_CROSSED_DIAGNOSTIC", "physical_probability_qualified": False}
    value["manifest_id"] = digest(value)
    target = output/run_id; target.mkdir(parents=True)
    write(target/"manifest.json", value)
    print(str((target/"manifest.json").relative_to(ROOT)))


def load(path):
    manifest = read(path)
    if digest({k: v for k, v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:
        raise ValueError("diagnostic manifest changed")
    for name, sha in manifest["input_sha256"].items():
        if file_digest(ROOT/name) != sha:
            raise ValueError("frozen diagnostic input changed: "+name)
    _, parent, models, audit = sources(manifest["config"])
    if audit["artifact_sha256"] != manifest["source_artifact_sha256"]:
        raise ValueError("bound source audit differs")
    return manifest, parent, models


def rows_csv(path, rows):
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def statistics(rows, pair_rows, config):
    draws = np.random.default_rng(config["bootstrap_seed"]).integers(0, 7, size=(config["bootstrap_samples"], 7))
    def cell(selected, flag):
        counts = np.array([sum(row[flag] for row in selected if row["block"] == block) for block in range(7)])
        sizes = np.array([sum(row["block"] == block for row in selected) for block in range(7)])
        sample = counts[draws].sum(axis=1)/sizes[draws].sum(axis=1)
        return {"cases": len(selected), "alarms": int(counts.sum()), "alarm_rate": float(counts.sum()/sizes.sum()),
                "descriptive_block_percentile_95": np.quantile(sample, [.025, .975]).tolist(),
                "block_alarm_counts": counts.tolist(), "block_cases": sizes.tolist()}
    marginal = []; sequential = []
    for mode in MODES:
        for changed in (False, True):
            for n in LOOKS:
                selected = [r for r in rows if r["mode"] == mode and r["context_changed"] == changed and r["prefix_steps"] == n]
                marginal.append({"mode": mode, "context_changed": changed, "prefix_steps": n, **cell(selected, "alarm_95")})
            selected = [r for r in pair_rows if r["mode"] == mode and r["context_changed"] == changed]
            sequential.append({"mode": mode, "context_changed": changed, **cell(selected, "any_three_look_alarm")})
    return {"marginal": marginal, "three_look_bonferroni": sequential}


def execute(path):
    manifest, parent, models = load(path); identity = {key: manifest[key] for key in IDENTITY}
    target = path.parent
    if (target/"predictions_scores.jsonl.gz").exists():
        raise FileExistsError("preserve completed or partial one-shot scores")
    cells = load_prefixes(parent); beliefs = {}
    for key, (prefix, parameters) in cells.items():
        beliefs[key] = source_belief(models[key[1]], prefix, parameters)
    write(target/"source_beliefs.json", {**identity, "beliefs": [{"stream": s, "task": t, "belief": asdict(beliefs[s, t])} for s, t in sorted(cells)]})
    with gzip.open(target/"unique_prefixes.jsonl.gz", "xt", encoding="utf-8") as handle:
        for (s, t), (prefix, parameters) in sorted(cells.items()):
            handle.write(json.dumps({"stream": s, "task": t, "prefix": asdict(prefix), "saved_parameters": parameters})+"\n")
    all_rows = []; pair_rows = []; sequence = 0
    operators = bridge.operators(read(ROOT/manifest["config"]["bridge_manifest"])["config"])
    with gzip.open(target/"predictions_scores.jsonl.gz", "xt", encoding="utf-8") as events:
        for stream in range(56):
            for source_task in TASKS:
                for target_task in TASKS:
                    if source_task == target_task:
                        continue
                    for changed in (False, True):
                        target_stream = stream//8*8+(stream+1)%8 if changed else stream
                        if changed and operators[stream]["matrix_xy"] == operators[target_stream]["matrix_xy"] and operators[stream]["bias_xy"] == operators[target_stream]["bias_xy"]:
                            raise ValueError("changed pairing has identical hidden parameters")
                        prefix = cells[target_stream, target_task][0]; cached = beliefs[stream, source_task]
                        meta = {"block": stream//8, "source_stream": stream, "source_task": source_task, "target_stream": target_stream,
                                "target_task": target_task, "context_changed": changed, "active_source_bound": cached.active_parameter_bound}
                        for mode in MODES:
                            results = []
                            for n in LOOKS:
                                query = PredictionQuery(target_task, prefix.initial_observation, prefix.commands[:n], True)
                                prediction = forecast(models[target_task], query, cached, mode)
                                sequence += 1
                                event = {**identity, "event": "PREDICTION", "sequence": sequence, "saved_ns": perf_counter_ns(),
                                         "pair_evaluator": meta, "query": asdict(query), "prediction": prediction}
                                events.write(json.dumps(event)+"\n"); events.flush()
                                observed = ColdPrefix(target_task, prefix.initial_observation, prefix.commands[:n], prefix.observations[:n], True)
                                result = score(prediction, observed)
                                events.write(json.dumps({**identity, "event": "SCORE", "prediction_sequence": sequence, "saved_ns": perf_counter_ns(),
                                                         "observed": asdict(observed), "score": result})+"\n")
                                row = {**identity, **meta, "mode": mode, "prefix_steps": n, **result}
                                all_rows.append(row); results.append(row)
                            pair_rows.append({**identity, **meta, "mode": mode,
                                              "any_marginal_alarm": any(row["alarm_95"] for row in results),
                                              "any_three_look_alarm": any(row["three_look_alarm"] for row in results)})
            print("Scored source condition "+str(stream+1)+"/56", flush=True)
    if len(all_rows) != 4032 or len(pair_rows) != 1344 or sequence != 4032:
        raise ValueError("incomplete fixed diagnostic population")
    rows_csv(target/"all_scores.csv", all_rows); rows_csv(target/"all_pairs.csv", pair_rows)
    costs = read(ROOT/manifest["config"]["bridge_costs"])
    summary = {**identity, "status": "COMPLETED_UNQUALIFIED_DIAGNOSTIC", "unique_prefixes": 168, "duplicate_future_prefixes_checked": 168,
               "constructed_pairs": 672, "forecast_scores": 4032, "pair_mode_rows": 1344,
               "active_source_bounds": sum(b.active_parameter_bound for b in beliefs.values()),
               "statistics": statistics(all_rows, pair_rows, manifest["config"]),
               "costs": {"new_environment_steps": 0, "new_reset_calls": 0, "new_controller_fits": 0, "new_policy_updates": 0,
                         "api_calls": 0, "new_local_covariance_calculations": 168, "new_forecast_scores": 4032,
                         "reused_full_source_bank_steps": costs["new_environment_steps"], "reused_full_source_bank_controlled_resets": costs["new_controlled_resets"],
                         "reused_full_source_bank_lifecycle": costs["lifecycle"],
                         "reused_joint_model_source_steps": costs["response_source_environment_steps"],
                         "reused_joint_model_source_controlled_resets": costs["response_source_controlled_resets"],
                         "reused_joint_source_lifecycle": costs["response_source_lifecycle"],
                         "historical_old_model_source_steps": 21010, "historical_old_model_source_controlled_resets": 288,
                         "historical_old_factory_cost_known": False},
               "physical_probability_qualified": False, "new_method_or_task_gain_claim": False}
    write(target/"summary.json", summary)
    write(target/"completion.json", {**identity, "status": summary["status"],
                                   "artifact_sha256": {p.name: file_digest(p) for p in target.iterdir() if p.is_file()}})
    print(json.dumps({"status": summary["status"], "scores": len(all_rows), "new_environment_steps": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "run")); parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.manifest is None:
        parser.error("--manifest is required for run")
    else:
        try:
            execute(args.manifest.resolve())
        except Exception as error:
            failure = args.manifest.resolve().parent/"failure.json"
            if not failure.exists():
                write(failure, {"status": "FAILED_PRESERVE_PARTIAL", "error_type": type(error).__name__, "error": str(error)})
            raise
