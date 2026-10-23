"""Independent group, ridge-equation, choice and realized-cost checks.

The strict evidence feature builder and original recorded-state matching helpers
are explicitly reused. This does not resimulate physics or establish novelty.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_task_value_learner as runner
from src.probe.task_value_learner import LENGTHS, TASKS


def close(a, b):
    if np.asarray(a).shape != np.asarray(b).shape or not np.allclose(a, b, atol=1e-9, rtol=1e-10):
        raise ValueError("saved numerical value differs")


def equation(saved, x, y):
    if set(saved) != {"mean", "scale", "support", "bandwidth_squared", "target_mean", "weights"}:
        raise ValueError("foreign fitted model field")
    x, y = np.asarray(x, float), np.asarray(y, float)
    arrays = {k: np.asarray(v, float) for k, v in saved.items()}
    mean, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
    support = (x - mean) / scale
    distance = ((support[:, None] - support[None, :]) ** 2).sum(axis=2)
    nonzero = distance[np.triu_indices(len(x), 1)]
    nonzero = nonzero[nonzero > 1e-12]
    bandwidth = float(np.median(nonzero)) if len(nonzero) else 1.
    for name, expected in (("mean", mean), ("scale", scale), ("support", support),
                           ("bandwidth_squared", bandwidth), ("target_mean", y.mean(axis=0))):
        close(arrays[name], expected)
    weights = arrays["weights"]
    if weights.shape != y.shape or not np.isfinite(weights).all():
        raise ValueError("invalid fitted weights")
    kernel = np.exp(-distance / (2 * bandwidth))
    close((kernel + np.eye(len(x))) @ weights, y - y.mean(axis=0))
    return saved


def predict(saved, evidence):
    feature = evidence.features()
    query = (feature - np.asarray(saved["mean"])) / np.asarray(saved["scale"])
    support = np.asarray(saved["support"])
    kernel = np.exp(-((support - query) ** 2).sum(axis=1) / (2 * saved["bandwidth_squared"]))
    return np.asarray(saved["target_mean"]) + kernel @ np.asarray(saved["weights"])


def checked_post(saved, evidence, decision):
    value = 500 * float(predict(saved, evidence)[0])
    expected = "UPDATE" if evidence.fit_valid and value < 0 else "KEEP"
    if decision["action"] != expected or decision["evidence_digest"] != evidence.digest or decision["remaining_steps"] != evidence.remaining_steps:
        raise ValueError("post action not driven by current saved prediction")
    close(decision["update_minus_keep_loss_prediction"], value)
    return expected


def checked_pre(saved, evidence, decision):
    values = [0., *(500 * predict(saved, evidence)).tolist()]
    expected = ("CACHE_CONTINUE", "PROBE8_WIDE", "PROBE16_WIDE")[min(range(3), key=lambda i: (values[i], i))]
    if decision["action"] != expected or decision["evidence_digest"] != evidence.digest or decision["remaining_steps"] != evidence.remaining_steps:
        raise ValueError("pre action not driven by current saved prediction")
    close(decision["loss_difference_predictions"], values)
    return expected


def policy_checks(policy, rows):
    ids = [r.case_id for r in rows]
    if policy["training_case_ids"] != ids:
        raise ValueError("outer held group or foreign case entered training")
    groups = sorted({r.group for r in rows})
    inner = policy["inner"]
    if [part["excluded_group"] for part in inner] != groups:
        raise ValueError("missing or duplicate inner held group")
    targets = {}
    equations = 0
    for part in inner:
        train = [r for r in rows if r.group != part["excluded_group"]]
        held = [r for r in rows if r.group == part["excluded_group"]]
        if part["training_case_ids"] != [r.case_id for r in train] or [d["case_id"] for d in part["decisions"]] != [r.case_id for r in held]:
            raise ValueError("inner label or source group contamination")
        for length in LENGTHS:
            equation(part["models"][str(length)], [r.post[length].features() for r in train],
                     [[(r.outcomes[f"MID{length}_WIDE"]["loss"] - r.outcomes[f"MID{length}_WIDE_KEEP"]["loss"]) / 500] for r in train])
            equations += 1
        for row, decision in zip(held, part["decisions"]):
            values = []
            for length in LENGTHS:
                choice = decision["choices"][str(length)]
                action = checked_post(part["models"][str(length)], row.post[length], choice)
                method = f"MID{length}_WIDE" + ("_KEEP" if action == "KEEP" else "")
                if choice["selected_method"] != method:
                    raise ValueError("inner chosen outcome substituted")
                values.append((row.outcomes[method]["loss"] - row.outcomes["CACHE_CONTINUE"]["loss"]) / 500)
            if row.case_id in targets:
                raise ValueError("duplicate inner target")
            targets[row.case_id] = values
    equation(policy["pre"], [r.pre.features() for r in rows], [targets[r.case_id] for r in rows])
    direct = [[(r.outcomes[f"MID{n}_WIDE"]["loss"] - r.outcomes["CACHE_CONTINUE"]["loss"]) / 500 for n in LENGTHS] for r in rows]
    equation(policy["direct"], [r.pre.features() for r in rows], direct)
    equations += 2
    for length in LENGTHS:
        equation(policy["post"][str(length)], [r.post[length].features() for r in rows],
                 [[(r.outcomes[f"MID{length}_WIDE"]["loss"] - r.outcomes[f"MID{length}_WIDE_KEEP"]["loss"]) / 500] for r in rows])
        equations += 1
    return equations


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def analyze(manifest_path):
    manifest = runner.read(manifest_path); base = manifest_path.parent
    identity = {k: manifest[k] for k in ("run_id", "manifest_id", "source_git_commit")}
    if runner.digest({k: v for k, v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:
        raise ValueError("manifest identity differs")
    if any(runner.source.digest(ROOT / n) != h for n, h in manifest["input_sha256"].items()):
        raise ValueError("frozen learner inputs changed")
    raw_rows, original = runner.extract(manifest["config"])
    dataset = runner.read(base / "dataset.json")
    if any(dataset[k] != v for k, v in identity.items()):
        raise ValueError("foreign dataset identity")
    if dataset["rows"] != json.loads(json.dumps([runner.encode(r) for r in raw_rows])):
        raise ValueError("visible evidence or labels differ from actual source")
    rows = [runner.decode(r) for r in dataset["rows"]]
    folds = {}; equations = 0
    for group in range(8):
        fold = runner.read(base / f"fold_{group:02}.json")
        if fold["excluded_group"] != group or any(fold[k] != v for k, v in identity.items()):
            raise ValueError("foreign outer fold")
        for task in TASKS:
            train = [r for r in rows if r.group != group and r.pre.task == task]
            equations += policy_checks(fold["tasks"][task], train)
        folds[group] = fold
    final = runner.read(base / "models.json")
    if any(final[k] != v for k, v in identity.items()):
        raise ValueError("foreign final model identity")
    for task in TASKS:
        equations += policy_checks(final["tasks"][task], [r for r in rows if r.pre.task == task])
    by_id = {r.case_id: r for r in rows}
    decisions, outcomes = lines(base / "decisions.jsonl"), lines(base / "outcomes.jsonl")
    if len(decisions) != 384 or len(outcomes) != 384 or len({(d["case_id"], d["method"]) for d in decisions}) != 384:
        raise ValueError("incomplete development decision population")
    values = {k: [] for k in ("TWO_STAGE", "DIRECT_VALUE")}; selected = {k: Counter() for k in values}; failures = []
    for decision, outcome in zip(decisions, outcomes):
        row = by_id[decision["case_id"]]
        if decision["excluded_group"] != row.group or any(decision[k] != v or outcome[k] != v for k, v in identity.items()):
            raise ValueError("foreign decision identity or excluded group")
        if runner.digest({k: v for k, v in decision.items() if k != "decision_digest"}) != decision["decision_digest"] or outcome["decision_digest"] != decision["decision_digest"]:
            raise ValueError("outcome not bound to the saved choice")
        method = decision["method"]; direct = method == "DIRECT_VALUE"
        policy = folds[row.group]["tasks"][row.pre.task]
        action = checked_pre(policy["direct" if direct else "pre"], row.pre, decision["pre"])
        chosen = "CACHE_CONTINUE"
        if action != "CACHE_CONTINUE":
            length = 8 if action == "PROBE8_WIDE" else 16
            chosen = f"MID{length}_WIDE"
            if not direct:
                post = checked_post(policy["post"][str(length)], row.post[length], decision["post"])
                chosen += "_KEEP" if post == "KEEP" else ""
            elif decision["post"] is not None:
                raise ValueError("direct baseline gained post choice")
        elif decision["post"] is not None:
            raise ValueError("unselected measurement evidence used")
        expected = row.outcomes[chosen]
        if decision["selected_method"] != chosen or outcome["case_id"] != row.case_id or outcome["method"] != method or any(outcome[k] != v for k, v in expected.items()):
            raise ValueError("chosen physical branch outcome differs")
        values[method].append(expected); selected[method][chosen] += 1
        if not expected["success"]:
            failures.append({"case_id": row.case_id, "method": method, "selected_method": chosen, **expected})
    summary = runner.read(base / "summary.json")
    methods = {k: {"cases": len(v), "successes": sum(r["success"] for r in v), "stops": sum(r["stopped"] for r in v),
                   "mean_historical_selected_steps": sum(r["steps"] for r in v) / len(v),
                   "mean_deadline_loss": sum(r["loss"] for r in v) / len(v)} for k, v in values.items()}
    if any(summary[k] != v for k, v in identity.items()):
        raise ValueError("foreign summary identity")
    if summary["methods"] != methods or summary["selected_methods"] != {k: dict(v) for k, v in selected.items()}:
        raise ValueError("summary arithmetic differs")
    if summary["original_all_baselines"] != original["statistics"]["methods"] or summary["full_paired_source_steps"] != original["controlled_steps"] or summary["full_paired_source_controlled_resets"] != original["controlled_resets"]:
        raise ValueError("full source or baseline fees omitted")
    if summary["new_environment_steps"] != 0 or summary["new_api_calls"] != 0 or summary["independent_confirmation"] or summary["algorithm_novelty_established"]:
        raise ValueError("development scope or cost relabeled")
    if summary["full_prior_nominal_steps"] != 21010 or summary["full_prior_nominal_controlled_resets"] != 288:
        raise ValueError("nominal source fee omitted")
    return {**identity, "integrity": "PASSED", "kind": "DEVELOPMENT_REPLAY", "cases": 192,
            "decisions": 384, "ridge_equations_checked": equations, "methods": methods,
            "selected_methods": {k: dict(v) for k, v in selected.items()}, "failed_cases": failures,
            "original_all_baselines": original["statistics"]["methods"],
            "full_paired_source_steps": original["controlled_steps"], "full_paired_source_controlled_resets": original["controlled_resets"],
            "full_prior_nominal_steps": 21010, "full_prior_nominal_controlled_resets": 288,
            "new_environment_steps": 0, "new_api_calls": 0, "independent_confirmation": False,
            "artifact_sha256": {p.name: runner.source.digest(p) for p in base.iterdir() if p.is_file()},
            "scope": "Independent excluded-group, ridge-equation, saved prediction/action and realized cost checks. Strict feature builder and original state-matching helpers reused. No new online execution or physical/probability/novelty qualification."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or args.manifest.resolve().parent in output.parents:
        raise FileExistsError("new external audit directory required")
    result = analyze(args.manifest.resolve())
    output.mkdir(parents=True, exist_ok=False); runner.write(output / "audit.json", result)
    print(json.dumps({k: result[k] for k in ("integrity", "decisions", "ridge_equations_checked", "methods")}))
