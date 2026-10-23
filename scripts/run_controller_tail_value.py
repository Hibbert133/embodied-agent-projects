"""Frozen offline development cross-fitting; never constructs a robot environment."""
import os
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis.controller_tail_dataset import extract, matched_sixteen
from src.probe.controller_tail_value import (TASKS, KINDS, REGRESSORS, REFERENCES,
    feature_map, sufficient_statistics, solve_statistics)

CONFIG = ROOT / "configs/controller_tail_value/development_v1.json"
DOCUMENTS = ("docs/protocols/controller_tail_value_development_v1.md",
             "docs/research/controller_tail_value_question_v1.md", "AGENTS.md", ".gitattributes", "requirements.txt")
OLD_UNTRACKED = {
    "outputs/action_response/development_v1/action_response_20261014T104928Z_1c3798544481/events.jsonl.gz",
    "reports/action_response_development_v1.md", "reports/action_response_development_v2.md"}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def authenticate_source(c):
    base = ROOT / c["source_root"]
    names = [f"{c['source_root']}/{name}" for name in ("manifest.json", "status.json", "summary.json")]
    names += [f"{c['source_root']}/{kind}_{i:02d}.jsonl.gz" for i in range(16) for kind in ("episodes", "events")]
    names.append(c["source_audit"])
    commit = c["source_results_commit"]
    tree = git("ls-tree", "-r", "--format=%(objectname) %(path)", commit, "--", *names)
    objects = {line.split(" ", 1)[1]: line.split(" ", 1)[0] for line in tree.splitlines()}
    if set(objects) != set(names):
        raise ValueError("source results commit misses a registered artifact")
    hashes = {}
    for name in names:
        data = (ROOT / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != objects[name]:
            raise ValueError("changed committed source artifact: " + name)
        hashes[name] = hashlib.sha256(data).hexdigest()
    m = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    audit = json.loads((ROOT / c["source_audit"]).read_text(encoding="utf-8"))
    if m["manifest_id"] != c["source_manifest_id"] or audit["manifest_id"] != m["manifest_id"] or audit["integrity"] != "PASSED" or audit["episodes"] != c["episodes"]:
        raise ValueError("source audit/manifest not qualified")
    # Two repository metadata files have additive new protocol overlays. Verify
    # their historical bytes; every scientific old input must still match locally.
    for name, expected in m["input_sha256"].items():
        if name in ("AGENTS.md", ".gitattributes"):
            data = subprocess.check_output(["git", "show", m["source_git_commit"] + ":" + name], cwd=ROOT)
            actual = hashlib.sha256(data).hexdigest()
        else:
            actual = digest(ROOT / name)
        if actual != expected:
            raise ValueError("old frozen input changed: " + name)
    if audit["controlled_steps"] != c["source_steps"] or audit["controlled_resets"] != c["source_controlled_resets"]:
        raise ValueError("source cost mismatch")
    return {"source_artifact_sha256": hashes, "source_git_blobs": objects,
            "source_frozen_inputs_checked": len(m["input_sha256"]),
            "old_audit_integrity": audit["integrity"], "source_manifest_id": m["manifest_id"],
            "source_lifecycle": audit["lifecycle"]}


def prepare():
    status = git("status", "--porcelain", "--untracked-files=all").splitlines()
    if any(not line.startswith("?? ") or line[3:].replace("\\", "/") not in OLD_UNTRACKED for line in status):
        raise ValueError("freeze requires clean tracked inputs; unrelated old files stay untracked")
    c = json.loads(CONFIG.read_text(encoding="utf-8"))
    if c["groups"] != 16 or c["episodes"] != 960 or c["feature_dimension"] != 90 or c["random_features"] != 256 or c["feature_seed"] != 20261016 or c["ridge"] != 1.0 or c["stride"] != 4:
        raise ValueError("fixed development protocol changed")
    parent = ROOT / c["output_root"]
    if list(parent.glob("*/manifest.json")):
        raise FileExistsError("this protocol already prepared; do not silently refit")
    proof = authenticate_source(c)
    names = git("ls-files", "src", "scripts", "tests").splitlines()
    names += [CONFIG.relative_to(ROOT).as_posix(), *DOCUMENTS]
    commit = git("rev-parse", "HEAD")
    run_id = f"controller_tail_value_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{commit[:12]}"
    m = {"experiment_run_id": run_id, "source_git_commit": commit, "config": c,
         "input_sha256": {name: digest(ROOT/name) for name in sorted(set(names))},
         "source_proof": proof,
         "versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "metaworld")}}
    m["manifest_id"] = hashlib.sha256(canonical(m)).hexdigest()
    output = parent / run_id
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", m)
    print(output / "manifest.json", flush=True)


def load_manifest(path):
    m = json.loads(path.read_text(encoding="utf-8")); candidate = dict(m); candidate.pop("manifest_id")
    if hashlib.sha256(canonical(candidate)).hexdigest() != m["manifest_id"]:
        raise ValueError("manifest digest changed")
    if any(digest(ROOT/name) != expected for name, expected in m["input_sha256"].items()):
        raise ValueError("frozen implementation changed")
    if any(importlib.metadata.version(name) != version for name, version in m["versions"].items()):
        raise ValueError("frozen runtime changed")
    if authenticate_source(m["config"]) != m["source_proof"]:
        raise ValueError("source binding changed")
    return m


def assemble(m, output):
    c = m["config"]; rows = []; episodes = []; pairs = []
    for stream in range(c["groups"]):
        path = ROOT / c["source_root"] / f"episodes_{stream:02d}.jsonl.gz"
        with gzip.open(path, "rt", encoding="utf-8") as source:
            records = [json.loads(line) for line in source]
        if len(records) != 60:
            raise ValueError("incomplete source stream")
        keyed = {}
        for record in records:
            if record["stream"] != stream or record["manifest_id"] != c["source_manifest_id"]:
                raise ValueError("foreign source row")
            episode_id = len(episodes); start = len(rows)
            extracted, metadata = extract(record, episode_id)
            rows.extend(extracted)
            metadata.update(sample_start=start, sample_end=len(rows))
            episodes.append(metadata)
            key = (record["task"], record["replicate"], record["method"])
            if key in keyed:
                raise ValueError("duplicate source episode")
            keyed[key] = (record, metadata)
        for task in TASKS:
            for replicate in range(2):
                keep, km = keyed[(task, replicate, "KEEP_G8_AFTER16")]
                update, um = keyed[(task, replicate, "UPDATE_G16")]
                eligible = matched_sixteen(keep, update) and km["eligible"] and um["eligible"]
                if eligible and (km["stable_start"] != 16 or um["stable_start"] != 16):
                    raise ValueError("matched qualification point moved")
                pairs.append({"stream": stream, "task": task, "replicate": replicate,
                              "keep_episode": km["episode_id"], "update_episode": um["episode_id"],
                              "eligible": bool(eligible), "prefix_steps_checked": 16,
                              "physical_witness_checked": True})
        print(json.dumps({"stage": "extract", "stream": stream, "episodes": len(episodes), "samples": len(rows)}), flush=True)
    if len(episodes) != c["episodes"] or len(pairs) != 96:
        raise ValueError("registered extraction population differs")
    data = {"x": np.array([r["x"] for r in rows]), "target": np.array([r["target"] for r in rows]),
            "weight": np.array([r["weight"] for r in rows]), "remaining": np.array([r["remaining"] for r in rows]),
            "step": np.array([r["step"] for r in rows]), "episode_id": np.array([r["episode_id"] for r in rows]),
            "group": np.array([r["group"] for r in rows]), "task": np.array([TASKS.index(r["task"]) for r in rows]),
            "kind": np.array([KINDS.index(r["kind"]) for r in rows]),
            "evidence_digest": np.array([r["evidence_digest"] for r in rows], dtype="U64")}
    np.savez_compressed(output / "dataset.npz", **data)
    write_json(output / "episodes.json", episodes); write_json(output / "pairs.json", pairs)
    return data, episodes, pairs


def fit(data, episodes, c):
    rng = np.random.default_rng(c["feature_seed"])
    omega = rng.normal(size=(90, 256)); phase = rng.uniform(0, 2*np.pi, 256)
    models = {"omega": omega, "phase": phase}; predictions = {}; folds = []
    first = np.array([e["sample_start"] for e in episodes if e["eligible"]])
    is_first = np.zeros(len(data["x"]), bool); is_first[first] = True
    for name in REGRESSORS:
        z = feature_map(data["x"], name, omega, phase)
        all_coef = np.empty((3, 16, z.shape[1])); pred = np.empty(len(z))
        full_coef = []
        for task in range(3):
            mask = data["task"] == task
            stats = []
            for group in range(16):
                train = mask & (data["group"] == group)
                if name == "PREFIX_ONLY_RFF":
                    train &= is_first
                w = np.ones(train.sum()) if name == "PREFIX_ONLY_RFF" else data["weight"][train]
                stats.append(sufficient_statistics(z[train], data["target"][train], w))
            all_a = sum(s[0] for s in stats); all_b = sum(s[1] for s in stats)
            for group in range(16):
                coef = solve_statistics(all_a-stats[group][0], all_b-stats[group][1])
                held = mask & (data["group"] == group)
                all_coef[task, group] = coef; pred[held] = np.clip(z[held] @ coef, 0, 1)
                training_ids = [e["episode_id"] for e in episodes if e["eligible"] and e["task"] == TASKS[task] and e["stream"] != group]
                held_ids = [e["episode_id"] for e in episodes if e["eligible"] and e["task"] == TASKS[task] and e["stream"] == group]
                folds.append({"model": name, "task": TASKS[task], "heldout_stream": group,
                              "training_episode_ids": training_ids, "heldout_episode_ids": held_ids})
            if name == "DENSE_RFF":
                full_coef.append(solve_statistics(all_a, all_b))
        models["coef_"+name] = all_coef; predictions[name] = pred
        if name == "DENSE_RFF":
            models["full_source_main_non_deployed"] = np.array(full_coef)
        print(json.dumps({"stage": "fit", "model": name, "cross_fits": 48}), flush=True)
    for name in REFERENCES:
        predictions[name] = np.empty(len(data["x"]))
        for task in range(3):
            for group in range(16):
                for kind in range(3) if name == "TASK_KIND_CONSTANT" else (None,):
                    held = (data["task"] == task) & (data["group"] == group)
                    train = (data["task"] == task) & (data["group"] != group)
                    if kind is not None:
                        held &= data["kind"] == kind; train &= data["kind"] == kind
                    if held.any() and not train.any():
                        raise ValueError("constant reference missing training support")
                    if held.any():
                        predictions[name][held] = np.average(data["target"][train], weights=data["weight"][train])
    return models, predictions, folds


def metrics(data, predictions, episodes, pairs):
    report = {"prediction": {}, "paired": {}}
    first = np.array([e["sample_start"] for e in episodes if e["eligible"]])
    def score(pred, mask):
        error = pred[mask]-data["target"][mask]; weights = data["weight"][mask]
        return {"fraction_rmse": float(np.sqrt(np.average(error**2, weights=weights))),
                "remaining_steps_rmse": float(np.sqrt(np.average((error*data["remaining"][mask])**2, weights=weights)))}
    for name, pred in predictions.items():
        report["prediction"][name] = {**score(pred, np.ones(len(pred), bool)),
            "first_remaining_steps_rmse": float(np.sqrt(np.mean(((pred[first]-data["target"][first])*data["remaining"][first])**2))),
            "by_task": {task: score(pred, data["task"] == t) for t, task in enumerate(TASKS)},
            "by_stream": {str(g): score(pred, data["group"] == g) for g in range(16)}}
        details = []
        for pair in pairs:
            keep = episodes[pair["keep_episode"]]; update = episodes[pair["update_episode"]]
            if pair["eligible"]:
                ia, ib = keep["sample_start"], update["sample_start"]
                delta = float(484*(pred[ia]-pred[ib])); selected = keep if delta < 0 else update
            else:
                delta = None; selected = update
            truth = keep["outcome"]["deadline_loss"]-update["outcome"]["deadline_loss"]
            details.append({**pair, "predicted_keep_minus_update": delta, "realized_keep_minus_update": truth,
                            "selected_method": selected["method"], "selected_loss": selected["outcome"]["deadline_loss"],
                            "selected_success": selected["outcome"]["success"]})
        eligible = [p for p in details if p["eligible"]]
        report["paired"][name] = {"cases": len(details), "eligible": len(eligible),
            "difference_mae": float(np.mean([abs(p["predicted_keep_minus_update"]-p["realized_keep_minus_update"]) for p in eligible])),
            "selected_keep": sum(p["selected_method"] == "KEEP_G8_AFTER16" for p in details),
            "offline_selected_successes": sum(p["selected_success"] for p in details),
            "offline_selected_mean_loss": float(np.mean([p["selected_loss"] for p in details])), "details": details}
    update = [episodes[p["update_episode"]]["outcome"] for p in pairs]
    keep = [episodes[p["keep_episode"]]["outcome"] for p in pairs]
    report["always_update"] = {"successes": sum(o["success"] for o in update), "mean_loss": float(np.mean([o["deadline_loss"] for o in update]))}
    report["always_keep"] = {"successes": sum(o["success"] for o in keep), "mean_loss": float(np.mean([o["deadline_loss"] for o in keep]))}
    report["zero_difference_mae"] = float(np.mean([abs(p["realized_keep_minus_update"]) for p in report["paired"]["DENSE_RFF"]["details"] if p["eligible"]]))
    main = report["paired"]["DENSE_RFF"]
    gate = {"remaining_rmse_better_than_kind_constant": report["prediction"]["DENSE_RFF"]["remaining_steps_rmse"] < report["prediction"]["TASK_KIND_CONSTANT"]["remaining_steps_rmse"],
            "paired_mae_better_than_zero": main["difference_mae"] < report["zero_difference_mae"],
            "offline_loss_no_worse_than_update": main["offline_selected_mean_loss"] <= report["always_update"]["mean_loss"],
            "offline_success_no_worse_than_update": main["offline_selected_successes"] >= report["always_update"]["successes"]}
    report["qualification"] = {"requirements": gate, "passed": all(gate.values()), "scope": "WITHIN_SOURCE_COMPONENT_ONLY"}
    return report


def execute(path):
    m = load_manifest(path); output = path.parent; c = m["config"]
    if (output / "started.json").exists():
        raise FileExistsError("frozen fit already started; preserve it")
    identity = {k: m[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    write_json(output / "started.json", {**identity, "started_utc": datetime.now(timezone.utc).isoformat()})
    started = time.perf_counter()
    try:
        data, episodes, pairs = assemble(m, output); extracted = time.perf_counter()
        models, predictions, folds = fit(data, episodes, c); fitted = time.perf_counter()
        np.savez_compressed(output / "models.npz", **models)
        np.savez_compressed(output / "predictions.npz", **predictions)
        write_json(output / "folds.json", folds)
        report = metrics(data, predictions, episodes, pairs)
        report.update(identity)
        report["population"] = {"episodes": len(episodes), "eligible_episodes": sum(e["eligible"] for e in episodes),
                                "samples": len(data["x"]), "groups": 16, "paired_cases": len(pairs)}
        report["cost"] = {"new_environment_steps": 0, "new_resets": 0, "api_calls": 0,
                          "policy_weight_training": 0, "controller_fits": 0, "cross_fitted_value_ridge_fits": len(folds),
                          "full_source_non_deployed_value_ridge_fits": 3,
                          "source_steps": c["source_steps"], "source_controlled_resets": c["source_controlled_resets"],
                          "source_lifecycle": m["source_proof"]["source_lifecycle"],
                          "nominal_source_steps": c["nominal_source_steps"], "nominal_source_controlled_resets": c["nominal_source_controlled_resets"],
                          "extraction_seconds": extracted-started, "fitting_seconds": fitted-extracted,
                          "elapsed_seconds": time.perf_counter()-started,
                          "model_archive_bytes": (output / "models.npz").stat().st_size}
        write_json(output / "report.json", report)
        write_json(output / "status.json", {**identity, "status": "COMPLETED_COMPONENT_PASSED" if report["qualification"]["passed"] else "COMPLETED_COMPONENT_FAILED"})
        print(json.dumps({"status": "completed", "population": report["population"], "qualification": report["qualification"], "cost": report["cost"]}), flush=True)
    except Exception as error:
        write_json(output / "status.json", {**identity, "status": "INCOMPLETE_ERROR", "error": type(error).__name__ + ": " + str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--prepare", action="store_true"); parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.prepare == bool(args.manifest):
        parser.error("choose --prepare or --manifest")
    prepare() if args.prepare else execute(args.manifest)
