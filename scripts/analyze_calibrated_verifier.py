"""Analyze calibration or prospective Calibrated Verifier v2 artifacts."""

from __future__ import annotations

import argparse
import csv
from itertools import product
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem.regime_memory import SIGNATURE_FIELDS, ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory  # noqa: E402
from src.probemem_verifier.applicability import ApplicabilityThresholds, assess_applicability  # noqa: E402
from src.probemem_verifier.calibrated_override_guard import CalibratedGuardThresholds, decide_calibrated_override  # noqa: E402
from src.probemem_verifier.candidate_verifier import DeterministicBayesianVerifier, build_candidate_memory_summaries  # noqa: E402
from src.probemem_verifier.posterior_comparison import compare_posteriors, derive_comparison_seed  # noqa: E402
from src.probemem_verifier.weighted_posterior import QueryConditionedCalibratedVerifier  # noqa: E402

ORDER = {"REJECTED": 0, "INCONCLUSIVE": 1, "ACCEPTED": 2}
COMP, RETRY = "BOUNDED_PLANAR_COMPENSATION", "INDEPENDENT_STOCHASTIC_RETRY"


def analyze(run_dir: Path) -> dict[str, Any]:
    manifest = _json(run_dir / "immutable_manifest.json")
    config = _config(manifest)
    summary = _json(run_dir / "summary.json")
    decisions = _csv(run_dir / "decisions.csv")
    outcomes = _csv(run_dir / "candidate_outcomes.csv")
    episodes = _json(run_dir / "episodes.json")
    methods = sorted({row["method"] for row in decisions})
    method_metrics = {method: _method_metrics([row for row in decisions if row["method"] == method], outcomes) for method in methods}
    reference = _reference_calibration(config, episodes)
    result: dict[str, Any] = {
        "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"], "stage": manifest["stage"],
        "population": {"initial_units": summary["initial_units"], "operational_cases": summary["operational_cases"], "exclusive_recovery_cases": summary["exclusive_recovery_cases"]},
        "methods": method_metrics, "reference_calibration": reference,
        "credible_interval_parameter_coverage": "N/A_SINGLE_REALIZATION",
        "integrity": {key: summary[key] for key in summary if key.endswith("violations") or key in {"oracle_leakage_events", "future_memory_access", "counterfactual_memory_writes", "invalid_memory_ids", "invalid_skill_executions"}},
    }
    if manifest["stage"] == "calibration":
        calibration = _calibrate(config, manifest, episodes, summary)
        result["calibration_selection"] = calibration
        (run_dir / "calibration_grid_results.json").write_text(json.dumps(calibration.pop("grid_results"), indent=2) + "\n", encoding="utf-8")
        (run_dir / "calibration_result.json").write_text(json.dumps(calibration, indent=2) + "\n", encoding="utf-8")
    else:
        result["promotion_gate"] = _promotion_gate(config, result)
    (run_dir / "analysis_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def _calibrate(config: dict[str, Any], manifest: dict[str, Any], episodes: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    complete = int(summary["operational_cases"]) >= int(config["minimum_operational_cases"]) and int(summary["exclusive_recovery_cases"]) >= int(config["minimum_exclusive_recovery_cases"])
    if not complete:
        return {"status": "INCOMPLETE_POPULATION", "selected_thresholds": None, "eligible_combinations": 0, "grid_results": []}
    grid = config["calibration_grid"]
    names = tuple(grid)
    combinations = [dict(zip(names, values)) for values in product(*(grid[name] for name in names))]
    bootstrap = _load_bootstrap(ROOT / config["memory"]["bootstrap_records"])
    verifier = _weighted_verifier(config)
    cache: dict[tuple[int, tuple[str, ...]], tuple[Any, Any, Any, str]] = {}
    states = [{"history": (), "helpful": 0, "harmful": 0, "tie": 0, "accepted": 0, "overrides": 0} for _ in combinations]
    for index, episode in enumerate(episodes):
        default = RETRY if float(episode["score"]) > float(config["frozen_variance_threshold"]) else COMP
        alternative = COMP if default == RETRY else RETRY
        for config_index, thresholds in enumerate(combinations):
            state = states[config_index]
            key = (index, state["history"])
            if key not in cache:
                memory = _memory_for_history(bootstrap, episodes[:index], state["history"], manifest)
                signature = _signature(episode)
                summaries = build_candidate_memory_summaries(memory, signature, episode_id=int(episode["episode_id"]))
                from src.probemem_verifier.candidate_verifier import inspect_admission_memory
                from src.probemem_verifier.admission import assess_admission
                signals = inspect_admission_memory(summaries)
                admitted = assess_admission(abs(float(episode["score"]) - float(config["frozen_variance_threshold"])), signals.memory_conflict, signals.memory_coverage, ambiguity_margin=float(config["admission"]["ambiguity_margin"]), recent_contradiction=signals.recent_contradiction).verifier_called
                if admitted:
                    posteriors = verifier.verify_both(memory, signature, episode_id=int(episode["episode_id"]))
                    seed = derive_comparison_seed(int(config["posterior"]["comparison_seed"]), stage="calibration", method="calibration_grid", episode_id=int(episode["episode_id"]))
                    comparison = compare_posteriors(posteriors[default].global_posterior, posteriors[alternative].global_posterior, sampling_seed=seed)
                else:
                    posteriors, comparison = None, None
                cache[key] = (posteriors, comparison, admitted, default)
            posteriors, comparison, admitted, _ = cache[key]
            selected = default
            if admitted:
                app_thresholds = ApplicabilityThresholds(float(thresholds["minimum_effective_sample_size"]), float(thresholds["maximum_nearest_distance"]), float(thresholds["minimum_weighted_coverage"]), float(thresholds["maximum_weighted_contradiction_rate"]))
                applicability = assess_applicability(posteriors, app_thresholds)
                guard = decide_calibrated_override(default_skill=default, verifier_called=True, candidates=posteriors, applicability=applicability, comparison=comparison, thresholds=CalibratedGuardThresholds(float(thresholds["minimum_superiority_probability"]), float(thresholds["minimum_expected_utility_gain"]), float(thresholds["minimum_effective_sample_size"])))
                selected = guard.final_skill
            selected_status = episode["candidate_outcomes"][selected]["verification_status"]
            default_status = episode["candidate_outcomes"][default]["verification_status"]
            state["accepted"] += selected_status == "ACCEPTED"
            if selected != default:
                state["overrides"] += 1
                delta = ORDER[selected_status] - ORDER[default_status]
                state["helpful" if delta > 0 else "harmful" if delta < 0 else "tie"] += 1
            state["history"] = (*state["history"], selected)
    rows = []
    selection = config["calibration_selection"]
    for thresholds, state in zip(combinations, states):
        decisive = state["helpful"] + state["harmful"]
        precision = None if decisive == 0 else state["helpful"] / decisive
        eligible = decisive >= int(selection["minimum_decisive_overrides"]) and precision is not None and precision >= float(selection["minimum_override_precision"]) and state["helpful"] - state["harmful"] >= int(selection["minimum_net_helpful_overrides"])
        rows.append({**thresholds, **{key: state[key] for key in ("helpful", "harmful", "tie", "accepted", "overrides")}, "decisive_overrides": decisive, "override_precision": precision, "net_helpful_overrides": state["helpful"] - state["harmful"], "eligible": eligible})
    eligible_rows = [row for row in rows if row["eligible"]]
    if not eligible_rows:
        return {"status": "NO_ELIGIBLE_THRESHOLD_COMBINATION", "selected_thresholds": None, "eligible_combinations": 0, "grid_results": rows}
    selected = max(eligible_rows, key=_selection_key)
    thresholds = {name: selected[name] for name in names}
    return {"status": "CALIBRATION_PASSED", "selected_thresholds": thresholds, "selected_metrics": {key: selected[key] for key in ("helpful", "harmful", "tie", "accepted", "overrides", "decisive_overrides", "override_precision", "net_helpful_overrides")}, "eligible_combinations": len(eligible_rows), "grid_size": len(rows), "calibration_manifest_id": manifest["manifest_id"], "calibration_source_commit": manifest["source_git_commit"], "grid_results": rows}


def _selection_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (row["override_precision"], row["net_helpful_overrides"], row["accepted"], -row["harmful"], -row["overrides"], row["minimum_superiority_probability"], row["minimum_expected_utility_gain"], row["minimum_effective_sample_size"], row["minimum_weighted_coverage"], -row["maximum_nearest_distance"], -row["maximum_weighted_contradiction_rate"])


def _memory_for_history(bootstrap: tuple[RegimeActionExperience, ...], prior_episodes: list[dict[str, Any]], history: tuple[str, ...], manifest: dict[str, Any]) -> RegimeActionMemory:
    memory = RegimeActionMemory(bootstrap)
    for episode, skill in zip(prior_episodes, history):
        outcome = episode["candidate_outcomes"][skill]
        memory.append_after_verification(RegimeActionExperience(1, f"grid_episode{episode['episode_id']}", int(episode["episode_id"]), int(episode["episode_id"]) + 1, _signature(episode), InterventionSkill(skill), None, None, str(outcome["verification_status"]), float(outcome["observed_progress"]), float(outcome["final_object_goal_distance"]), int(outcome["steps"]), manifest["experiment_run_id"], manifest["manifest_id"], "CALIBRATION_GRID_SELECTED_ACTION_ONLY"))
    return memory


def _reference_calibration(config: dict[str, Any], episodes: list[dict[str, Any]]) -> dict[str, Any]:
    memory = RegimeActionMemory(_load_bootstrap(ROOT / config["memory"]["bootstrap_records"]))
    unweighted = DeterministicBayesianVerifier()
    weighted = _weighted_verifier(config)
    values = {"unweighted": {"default": [], "alternative": [], "pooled": []}, "weighted": {"default": [], "alternative": [], "pooled": []}}
    widths, overlaps = [], []
    for episode in episodes:
        signature = _signature(episode)
        episode_id = int(episode["episode_id"])
        default = RETRY if float(episode["score"]) > float(config["frozen_variance_threshold"]) else COMP
        alternative = COMP if default == RETRY else RETRY
        summaries = build_candidate_memory_summaries(memory, signature, episode_id=episode_id)
        old = unweighted.verify_both(summaries)
        new = weighted.verify_both(memory, signature, episode_id=episode_id)
        for role, skill in (("default", default), ("alternative", alternative)):
            outcome = 1.0 if episode["candidate_outcomes"][skill]["verification_status"] == "ACCEPTED" else 0.5 if episode["candidate_outcomes"][skill]["verification_status"] == "INCONCLUSIVE" else 0.0
            values["unweighted"][role].append((old[skill].predicted_accept_probability, outcome))
            values["weighted"][role].append((new[skill].global_posterior.posterior_mean, outcome))
            values["unweighted"]["pooled"].append((old[skill].predicted_accept_probability, outcome))
            values["weighted"]["pooled"].append((new[skill].global_posterior.posterior_mean, outcome))
            widths.append(new[skill].global_posterior.credible_upper - new[skill].global_posterior.credible_lower)
        overlaps.append(new[default].global_posterior.credible_upper >= new[alternative].global_posterior.credible_lower and new[alternative].global_posterior.credible_upper >= new[default].global_posterior.credible_lower)
        outcome = episode["candidate_outcomes"][default]
        memory.append_after_verification(RegimeActionExperience(1, f"reference_episode{episode_id}", episode_id, episode_id + 1, signature, InterventionSkill(default), None, None, str(outcome["verification_status"]), float(outcome["observed_progress"]), float(outcome["final_object_goal_distance"]), int(outcome["steps"]), "reference", "reference", "FROZEN_SELECTED_ACTION_ONLY"))
    return {name: {role: _calibration_metrics(rows) for role, rows in roles.items()} for name, roles in values.items()} | {"weighted_interval_mean_width": None if not widths else sum(widths) / len(widths), "weighted_interval_overlap_rate": None if not overlaps else sum(overlaps) / len(overlaps)}


def _calibration_metrics(rows: list[tuple[float, float]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "brier": None, "negative_log_likelihood": None, "ece": None}
    clip = 1e-6
    brier = sum((p - y) ** 2 for p, y in rows) / len(rows)
    nll = -sum(y * math.log(min(1 - clip, max(clip, p))) + (1 - y) * math.log(min(1 - clip, max(clip, 1 - p))) for p, y in rows) / len(rows)
    bins = []
    for index in range(10):
        lower, upper = index / 10, (index + 1) / 10
        selected = [(p, y) for p, y in rows if lower <= p < upper or index == 9 and p == 1]
        if selected:
            bins.append((len(selected), sum(p for p, _ in selected) / len(selected), sum(y for _, y in selected) / len(selected)))
    ece = sum(count / len(rows) * abs(mean_p - mean_y) for count, mean_p, mean_y in bins)
    return {"count": len(rows), "brier": brier, "negative_log_likelihood": nll, "ece": ece}


def _method_metrics(rows: list[dict[str, str]], outcomes: list[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        return {"cases": 0}
    by_candidate = {(int(row["episode_id"]), row["candidate_skill"]): row for row in outcomes}
    helpful = harmful = tie = 0
    for row in rows:
        if not _bool(row.get("override_applied")) or _bool(row.get("evaluator_only")):
            continue
        baseline = by_candidate[(int(row["episode_id"]), row["default_skill"])]
        delta = ORDER[row["verification_status"]] - ORDER[baseline["verification_status"]]
        if delta > 0: helpful += 1
        elif delta < 0: harmful += 1
        else: tie += 1
    decisive = helpful + harmful
    return {"cases": len(rows), "accepted_recovery": sum(row["verification_status"] == "ACCEPTED" for row in rows), "verifier_calls": sum(_bool(row.get("verifier_called")) for row in rows), "overrides": sum(_bool(row.get("override_applied")) for row in rows), "helpful_overrides": helpful, "harmful_overrides": harmful, "tie_overrides": tie, "override_precision": None if decisive == 0 else helpful / decisive, "net_helpful_overrides": helpful - harmful, "mean_final_distance": sum(float(row["final_object_goal_distance"]) for row in rows) / len(rows), "environment_steps": sum(int(row["environment_steps"]) for row in rows)}


def _promotion_gate(config: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    methods = result["methods"]
    calibrated = methods["CALIBRATED_SELECTIVE_VERIFIER_V2"]
    frozen = methods["FROZEN_DETERMINISTIC"]
    unweighted = methods["UNWEIGHTED_VERIFIER_V1"]
    integrity = all(value == 0 for value in result["integrity"].values())
    brier = result["reference_calibration"]
    brier_better = brier["weighted"]["pooled"]["brier"] < brier["unweighted"]["pooled"]["brier"]
    precision = calibrated["override_precision"] is not None and calibrated["override_precision"] >= 0.75
    net = calibrated["helpful_overrides"] >= calibrated["harmful_overrides"] + 2
    route_a = calibrated["accepted_recovery"] >= frozen["accepted_recovery"] + 2
    route_b = calibrated["accepted_recovery"] >= frozen["accepted_recovery"] - 1 and calibrated["harmful_overrides"] <= unweighted["harmful_overrides"] * 0.5
    return {"evaluated": True, "passed": integrity and brier_better and precision and net and (route_a or route_b), "integrity": integrity, "brier_better_than_unweighted": brier_better, "override_precision_at_least_0_75": precision, "helpful_at_least_harmful_plus_2": net, "route_a": route_a, "route_b": route_b}


def _weighted_verifier(config: dict[str, Any]) -> QueryConditionedCalibratedVerifier:
    p = config["posterior"]
    return QueryConditionedCalibratedVerifier(top_k=int(p["top_k"]), recent_count=int(p["recent_count"]), prior_alpha=float(p["prior_alpha"]), prior_beta=float(p["prior_beta"]), credible_level=float(p["credible_level"]))


def _signature(episode: dict[str, Any]) -> ProbeRegimeSignature:
    value = episode["signature"]
    return ProbeRegimeSignature(int(value["schema_version"]), str(value["evidence_id"]), int(value["episode_id"]), tuple(float(value["features"][name]) for name in SIGNATURE_FIELDS))


def _load_bootstrap(path: Path) -> tuple[RegimeActionExperience, ...]:
    return tuple(RegimeActionExperience.from_dict(row) for row in _json(path))


def _config(manifest: dict[str, Any]) -> dict[str, Any]:
    config = _json(ROOT / manifest["config_path"])
    if manifest["stage"] == "prospective_development":
        config = {**_json(ROOT / "configs/probemem_verifier/calibrated_v2_calibration.json"), **config}
    return config


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.run_dir.resolve())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
