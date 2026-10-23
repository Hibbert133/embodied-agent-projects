"""Independent feature/index/normal-equation/statistics audit of tail regression.

Shares source authentication, public controller command mathematics and NumPy;
does not import the feature encoder, sampler, extraction, fit or report helpers.
"""
import os
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_controller_tail_value import load_manifest, digest, write_json
from src.probe.gaussian_response_reference import bounded_command
from src.probe.operator_identification import encode_controller

TASKS = ("push-v3", "reach-v3", "door-open-v3")
KINDS = ("IDENTITY", "AFFINE", "GAUSSIAN")
NAMES = ("DENSE_RFF", "LINEAR_DENSE", "PREFIX_ONLY_RFF", "NO_CONTROLLER_RFF", "TASK_CONSTANT", "TASK_KIND_CONSTANT")


def send(saved, raw):
    return bounded_command(saved, raw) if saved.get("kind") == "LOCAL_GAUSSIAN_BOX" else encode_controller(saved, raw)


def independent_features(record, t, controller):
    prefix = record["trace"][t-8:t]
    obs = np.array([r["before"]["observation"] for r in prefix] + [record["trace"][t]["before"]["observation"]])
    u = np.array([r["command"] for r in prefix])
    raw = np.clip(np.asarray(record["trace"][t]["raw_policy"], np.float32), -1, 1)
    queries = ([0, 0, 0, 0], [1, 0, 0, 0], [-1, 0, 0, 0], [0, 1, 0, 0], [0, -1, 0, 0])
    field = np.array([send(controller, q)[:2] for q in queries])
    sent = send(controller, raw)
    kind = "GAUSSIAN" if controller.get("kind") == "LOCAL_GAUSSIAN_BOX" else "IDENTITY" if controller["source"] == "UNCORRECTED" else "AFFINE"
    result = np.zeros(90); result[:39] = obs[-1]
    result[39:42] = (obs[-1, 36:39]-obs[-1, :3])*10
    result[42:45] = (obs[-1, 36:39]-obs[-1, 4:7])*10
    result[45:48] = (obs[-1, 4:7]-obs[-1, :3])*10
    result[48:51] = (obs[-2, :3]-obs[-3, :3])*100
    result[51:54] = (obs[-1, :3]-obs[-2, :3])*100
    result[54:58] = raw; result[58:62] = sent; result[62:72] = field.ravel()
    ys = np.array([(obs[k+1, :2]-obs[k, :2])*100 for k in range(8)])
    mx, my = u[:, :2].sum(axis=0)/8, ys.sum(axis=0)/8
    sx = np.zeros((2, 2)); sy = np.zeros((2, 2)); xy = np.zeros((2, 2))
    for command, motion in zip(u[:, :2], ys):
        sx += np.outer(command-mx, command-mx)/8
        sy += np.outer(motion-my, motion-my)/8
        xy += np.outer(command-mx, motion-my)/8
    result[72:76] = np.r_[mx, my]
    result[76:79] = [sx[0, 0], sx[0, 1], sx[1, 1]]
    result[79:82] = [sy[0, 0], sy[0, 1], sy[1, 1]]
    result[82:86] = xy.ravel(); result[86] = (500-t)/500
    result[87+KINDS.index(kind)] = 1
    evidence = {"task": record["task"], "observations": obs.tolist(), "commands": u.tolist(),
                "raw_policy": raw.astype(float).tolist(), "candidate_command": sent.astype(float).tolist(),
                "controller_field": field.astype(float).tolist(), "controller_kind": kind, "remaining_steps": 500-t}
    evidence_hash = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return result, evidence_hash, kind


def audit(path, output):
    started = time.perf_counter(); m = load_manifest(path); base = path.parent
    if output.exists():
        raise FileExistsError("audit output already exists")
    data = dict(np.load(base / "dataset.npz", allow_pickle=False))
    model = dict(np.load(base / "models.npz", allow_pickle=False))
    predictions = dict(np.load(base / "predictions.npz", allow_pickle=False))
    episodes = json.loads((base / "episodes.json").read_text(encoding="utf-8"))
    pairs = json.loads((base / "pairs.json").read_text(encoding="utf-8"))
    report = json.loads((base / "report.json").read_text(encoding="utf-8"))
    folds = json.loads((base / "folds.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(20261016)
    np.testing.assert_array_equal(model["omega"], rng.normal(size=(90, 256)))
    np.testing.assert_array_equal(model["phase"], rng.uniform(0, 2*np.pi, 256))
    count = 0; ep_id = 0; source_steps = 0; max_feature_error = 0.; checked_pairs = 0
    for stream in range(16):
        with gzip.open(ROOT / m["config"]["source_root"] / f"episodes_{stream:02d}.jsonl.gz", "rt", encoding="utf-8") as source:
            records = [json.loads(line) for line in source]
        indexed = {}
        for record in records:
            meta = episodes[ep_id]; source_steps += len(record["trace"])
            assert meta["episode_id"] == ep_id and meta["stream"] == stream and meta["method"] == record["method"]
            assert meta["outcome"] == record["outcome"]
            selected = [d for d in record["decisions"] if d.get("controller") is not None]
            if not selected:
                assert not meta["eligible"]; ep_id += 1; continue
            final = selected[-1]; start = max(8, final["at_host_calls"])
            wanted = list(range(start, len(record["trace"]), 4))
            if len(record["trace"]) > start and len(record["trace"])-1 not in wanted:
                wanted.append(len(record["trace"])-1)
            assert meta["samples"] == len(wanted) and meta["stable_start"] == start
            assert meta["sample_start"] == count
            for t in wanted:
                expected, evidence_hash, kind = independent_features(record, t, final["controller"])
                error = float(np.max(np.abs(expected-data["x"][count])))
                max_feature_error = max(max_feature_error, error)
                np.testing.assert_allclose(expected, data["x"][count], atol=2e-12, rtol=2e-12)
                assert data["evidence_digest"][count] == evidence_hash
                assert data["episode_id"][count] == ep_id and data["group"][count] == stream
                assert data["task"][count] == TASKS.index(record["task"]) and data["kind"][count] == KINDS.index(kind)
                assert data["step"][count] == t and data["remaining"][count] == 500-t
                assert data["target"][count] == (record["outcome"]["deadline_loss"]-t)/(500-t)
                assert data["weight"][count] == 1/len(wanted)
                current = record["trace"][t]
                assert current["phase"] == "POLICY" and current["decision_sequence"] == final["sequence"]
                assert current["decision_sequence"] == final["sequence"] and current["intent_saved_ns"] < current["execution_started_ns"] < current["completed_ns"]
                assert final["saved_ns"] < current["intent_saved_ns"]
                for left, right in zip(record["trace"][t-8:t], record["trace"][t-7:t+1]):
                    assert left["after"] == right["before"]
                count += 1
            assert meta["sample_end"] == count
            indexed[(record["task"], record["replicate"], record["method"])] = record
            ep_id += 1
        for task in TASKS:
            for future in range(2):
                a = indexed[(task, future, "KEEP_G8_AFTER16")]; b = indexed[(task, future, "UPDATE_G16")]
                assert a["initial"] == b["initial"] and a["sixteen_physics_witness_oracle"] == b["sixteen_physics_witness_oracle"]
                for left, right in zip(a["trace"][:16], b["trace"][:16]):
                    for key in ("before", "after", "command", "raw_policy", "noise_before_hash", "noise_after_hash", "executed_action_oracle", "phase", "simulation_time_before_oracle", "simulation_time_after_oracle"):
                        assert left[key] == right[key]
                checked_pairs += 1
        print(json.dumps({"audit_stream": stream, "samples": count}), flush=True)
    assert count == len(data["x"]) and ep_id == 960 and source_steps == 180930 and checked_pairs == 96
    weights = np.bincount(data["episode_id"], weights=data["weight"], minlength=960)
    np.testing.assert_allclose(weights, np.array([int(e["eligible"]) for e in episodes]), atol=2e-14, rtol=0)
    first = np.array([e["sample_start"] for e in episodes if e["eligible"]])
    first_mask = np.zeros(count, bool); first_mask[first] = True
    max_normal_residual = 0.; checked_fits = 0; max_prediction_error = 0.
    for name in NAMES:
        values = data["x"].copy()
        if name == "NO_CONTROLLER_RFF":
            values[:, 58:72] = 0; values[:, 87:90] = 0
        if name not in ("TASK_CONSTANT", "TASK_KIND_CONSTANT"):
            values /= np.sqrt(90)
            mapped = values if name == "LINEAR_DENSE" else np.sqrt(2/256)*np.cos(values @ model["omega"]+model["phase"])
            z = np.c_[np.ones(count), mapped]
            for task in range(3):
                total_g = np.zeros((z.shape[1], z.shape[1])); total_b = np.zeros(z.shape[1]); stats = []
                for group in range(16):
                    mask = (data["task"] == task) & (data["group"] == group)
                    if name == "PREFIX_ONLY_RFF": mask &= first_mask
                    w = np.ones(mask.sum()) if name == "PREFIX_ONLY_RFF" else data["weight"][mask]
                    # Square-root weighted least squares, independently assembled.
                    design = z[mask]*np.sqrt(w[:, None]); target = data["target"][mask]*np.sqrt(w)
                    g, b = design.T @ design, design.T @ target
                    stats.append((g, b)); total_g += g; total_b += b
                for group in range(16):
                    a, b = total_g-stats[group][0], total_b-stats[group][1]
                    a += np.diag(np.r_[0., np.ones(z.shape[1]-1)])
                    coefficient = model["coef_"+name][task, group]
                    residual = float(np.max(np.abs(a @ coefficient-b)))
                    max_normal_residual = max(max_normal_residual, residual)
                    assert residual <= 5e-10
                    fold = next(f for f in folds if f["model"] == name and f["task"] == TASKS[task] and f["heldout_stream"] == group)
                    train_ids = [e["episode_id"] for e in episodes if e["eligible"] and e["task"] == TASKS[task] and e["stream"] != group]
                    test_ids = [e["episode_id"] for e in episodes if e["eligible"] and e["task"] == TASKS[task] and e["stream"] == group]
                    assert fold["training_episode_ids"] == train_ids and fold["heldout_episode_ids"] == test_ids
                    assert not set(train_ids) & set(test_ids)
                    held = (data["task"] == task) & (data["group"] == group)
                    pred = np.maximum(0, np.minimum(1, z[held] @ coefficient))
                    delta = float(np.max(np.abs(pred-predictions[name][held])))
                    max_prediction_error = max(max_prediction_error, delta)
                    assert delta < 1e-12
                    checked_fits += 1
                if name == "DENSE_RFF":
                    total_g += np.diag(np.r_[0., np.ones(z.shape[1]-1)])
                    residual = float(np.max(np.abs(total_g @ model["full_source_main_non_deployed"][task]-total_b)))
                    max_normal_residual = max(max_normal_residual, residual); assert residual < 5e-10
                    checked_fits += 1
        else:
            for task in range(3):
                for group in range(16):
                    for kind in range(3) if name == "TASK_KIND_CONSTANT" else (None,):
                        train = (data["task"] == task) & (data["group"] != group)
                        test = (data["task"] == task) & (data["group"] == group)
                        if kind is not None:
                            train &= data["kind"] == kind; test &= data["kind"] == kind
                        if test.any():
                            expected = np.sum(data["target"][train]*data["weight"][train])/np.sum(data["weight"][train])
                            np.testing.assert_allclose(predictions[name][test], expected, atol=1e-14, rtol=0)
        def independently_score(mask):
            error = predictions[name][mask]-data["target"][mask]; w = data["weight"][mask]
            return {"fraction_rmse": float(np.sqrt(np.dot(error**2, w)/w.sum())),
                    "remaining_steps_rmse": float(np.sqrt(np.dot((error*data["remaining"][mask])**2, w)/w.sum()))}
        def compare(expected, saved):
            for key, value in expected.items(): assert abs(value-saved[key]) < 1e-9
        compare(independently_score(np.ones(count, bool)), report["prediction"][name])
        early = float(np.sqrt(np.mean(((predictions[name][first]-data["target"][first])*data["remaining"][first])**2)))
        assert abs(early-report["prediction"][name]["first_remaining_steps_rmse"]) < 1e-9
        for task in range(3): compare(independently_score(data["task"] == task), report["prediction"][name]["by_task"][TASKS[task]])
        for group in range(16): compare(independently_score(data["group"] == group), report["prediction"][name]["by_stream"][str(group)])
        selected = []; absolute = []; differences = []
        assert len(pairs) == len(report["paired"][name]["details"]) == 96
        for pair, saved in zip(pairs, report["paired"][name]["details"]):
            keep, update = episodes[pair["keep_episode"]], episodes[pair["update_episode"]]
            for key in ("stream", "task", "replicate"):
                assert pair[key] == keep[key] == update[key]
            assert keep["method"] == "KEEP_G8_AFTER16" and update["method"] == "UPDATE_G16"
            assert pair["eligible"] == (keep["eligible"] and update["eligible"])
            if pair["eligible"]:
                a, b = keep["sample_start"], update["sample_start"]
                difference = float((predictions[name][a]-predictions[name][b])*484)
                assert abs(difference-saved["predicted_keep_minus_update"]) < 1e-10
                truth = keep["outcome"]["deadline_loss"]-update["outcome"]["deadline_loss"]
                assert truth == saved["realized_keep_minus_update"]
                absolute.append(abs(difference-truth)); differences.append(difference)
                choice = keep if difference < 0 else update
            else: choice = update
            assert choice["method"] == saved["selected_method"]
            assert choice["outcome"]["deadline_loss"] == saved["selected_loss"]
            assert choice["outcome"]["success"] == saved["selected_success"]
            selected.append(choice["outcome"])
        p = report["paired"][name]
        assert abs(float(np.mean(absolute))-p["difference_mae"]) < 1e-9
        assert sum(o["success"] for o in selected) == p["offline_selected_successes"]
        assert abs(float(np.mean([o["deadline_loss"] for o in selected]))-p["offline_selected_mean_loss"]) < 1e-9
        if name in ("TASK_CONSTANT", "TASK_KIND_CONSTANT", "NO_CONTROLLER_RFF"):
            assert max(abs(d) for d in differences) < 1e-12
        print(json.dumps({"audit_model": name, "fits_checked_so_far": checked_fits}), flush=True)
    assert checked_fits == 195 and len(folds) == 192
    updates = [episodes[p["update_episode"]]["outcome"] for p in pairs]
    keeps = [episodes[p["keep_episode"]]["outcome"] for p in pairs]
    for outcomes, key in ((updates, "always_update"), (keeps, "always_keep")):
        assert sum(o["success"] for o in outcomes) == report[key]["successes"]
        assert abs(sum(o["deadline_loss"] for o in outcomes)/96-report[key]["mean_loss"]) < 1e-10
    eligible_outcomes = [(a, b) for a, b, p in zip(keeps, updates, pairs) if p["eligible"]]
    zero_mae = sum(abs(a["deadline_loss"]-b["deadline_loss"]) for a, b in eligible_outcomes)/len(eligible_outcomes)
    assert abs(zero_mae-report["zero_difference_mae"]) < 1e-10
    assert report["cost"]["source_lifecycle"] == m["source_proof"]["source_lifecycle"]
    assert report["population"] == {"episodes": 960, "eligible_episodes": sum(e["eligible"] for e in episodes),
                                      "samples": count, "groups": 16, "paired_cases": 96}
    for key in ("new_environment_steps", "new_resets", "api_calls", "policy_weight_training", "controller_fits"):
        assert report["cost"][key] == 0
    assert report["cost"]["cross_fitted_value_ridge_fits"] == 192 and report["cost"]["full_source_non_deployed_value_ridge_fits"] == 3
    requirements = {
        "remaining_rmse_better_than_kind_constant": report["prediction"]["DENSE_RFF"]["remaining_steps_rmse"] < report["prediction"]["TASK_KIND_CONSTANT"]["remaining_steps_rmse"],
        "paired_mae_better_than_zero": report["paired"]["DENSE_RFF"]["difference_mae"] < report["zero_difference_mae"],
        "offline_loss_no_worse_than_update": report["paired"]["DENSE_RFF"]["offline_selected_mean_loss"] <= report["always_update"]["mean_loss"],
        "offline_success_no_worse_than_update": report["paired"]["DENSE_RFF"]["offline_selected_successes"] >= report["always_update"]["successes"]}
    assert requirements == report["qualification"]["requirements"] and all(requirements.values()) == report["qualification"]["passed"]
    identity = {k: m[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    result = {**identity, "integrity": "PASSED", "episodes_checked": ep_id, "samples_checked": count,
              "feature_numbers_checked": count*90, "paired_prefixes_checked": checked_pairs,
              "ridge_fits_checked": checked_fits, "max_feature_error": max_feature_error,
              "max_normal_equation_residual": max_normal_residual, "max_prediction_error": max_prediction_error,
              "source_artifacts_checked": len(m["source_proof"]["source_artifact_sha256"]),
              "old_frozen_inputs_checked": m["source_proof"]["source_frozen_inputs_checked"],
              "new_environment_steps": 0, "new_resets": 0, "api_calls": 0,
              "elapsed_seconds": time.perf_counter()-started,
              "result_sha256": {p.name: digest(p) for p in sorted(base.iterdir()) if p.is_file()},
              "shared_helpers": ["source authentication", "saved public controller command math", "NumPy"]}
    output.parent.mkdir(parents=True, exist_ok=True); write_json(output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("result_sha256",)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); audit(args.manifest, args.output)
