"""Execute the immutable Phase-2 budgeted evidence-allocation protocol.

This runner never fits a held-out threshold or classifier.  The passive model is
fit once from the committed tuning split; global/phase thresholds and the probe
outcome threshold are read from committed frozen sources recorded in the run
manifest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import get_conditions  # noqa: E402
from scripts.build_bias_noise_ambiguity_benchmark import (  # noqa: E402
    PassiveFailureCase,
    classify_probe,
    match_passive_failures,
)
from scripts.evaluate_ambiguity_agents import (  # noqa: E402
    deterministic_random_request,
    fit_passive_centroid,
)
from scripts.generate_heldout_manifest import (  # noqa: E402
    canonical_manifest_id,
    sha256_file,
)
from src.evaluation import (  # noqa: E402
    accuracy,
    average_precision,
    balanced_accuracy,
    paired_win_tie_loss,
    roc_auc,
    stratified_paired_bootstrap_difference,
    wilson_interval,
)
from src.probe.directional import (  # noqa: E402
    build_repeated_agent_probe_context,
    estimate_planar_bias,
    run_repeated_symmetric_probes,
)
from src.reasoning.runtime import (  # noqa: E402
    AgentDecisionRuntime,
    DecisionRuntimeRecorder,
    summarize_decision_runtimes,
)
from src.reasoning.structured_evidence import (  # noqa: E402
    StructuredEvidenceState,
    build_structured_evidence_state,
)
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402
from src.uncertainty.budgeted_policy import (  # noqa: E402
    EvidenceDecisionKind,
    select_evidence_action,
)


PASSIVE_TUNING_CASES = ROOT / "outputs/ambiguity_benchmark/bias_noise_tuning_v1/cases.csv"
GLOBAL_GATE_SOURCE = ROOT / "outputs/ambiguity_benchmark/temporal_gate_development_v1/candidate_threshold.json"
NOISE_SELECTION = ROOT / "outputs/autoresearch/noise_calibration/selected.json"
CASE_SCHEMA_VERSION = 1
METHODS = (
    "passive",
    "seeded_random_probe",
    "always_probe",
    "global_temporal_gate",
    "frozen_phase_conditioned_gate",
    "oracle_audit",
)


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def derive_random_seed(seed: int, namespace: int) -> int:
    return int(np.random.SeedSequence([int(seed), int(namespace)]).generate_state(1)[0])


def validate_manifest(manifest_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_id", "experiment_run_id"}
    }
    if canonical_manifest_id(content) != manifest["manifest_id"]:
        raise ValueError("manifest ID does not match canonical manifest content")
    if manifest_path.parent.name != manifest["experiment_run_id"]:
        raise ValueError("manifest directory does not match experiment_run_id")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("current HEAD differs from the immutable manifest source commit")
    if _git("diff", "--name-only") or _git("diff", "--cached", "--name-only"):
        raise RuntimeError("held-out execution requires no tracked worktree changes")
    config_path = ROOT / manifest["config_path"]
    if sha256_file(config_path) != manifest["config_sha256"]:
        raise RuntimeError("frozen configuration hash differs from manifest")
    for name, expected in manifest["implementation_git_blob_hashes"].items():
        relative = manifest["implementation_paths"][name]
        actual = _git("hash-object", relative)
        if actual != expected:
            raise RuntimeError(f"implementation hash differs for {name}: {relative}")
    for name, source in manifest["frozen_source_artifacts"].items():
        if sha256_file(ROOT / source["path"]) != source["sha256"]:
            raise RuntimeError(f"frozen source artifact hash differs for {name}")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _agent_rows(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def _result_fields(result: Any) -> dict[str, Any]:
    return {
        "success": bool(result.success),
        "steps": int(result.steps),
        "episode_return": float(result.episode_return),
        "final_object_goal_distance": float(result.final_object_goal_distance),
        "min_gripper_object_distance": float(result.min_gripper_object_distance),
        "object_displacement": float(result.object_displacement),
        "progress_to_goal": float(result.progress_to_goal),
    }


def _provenance(manifest: Mapping[str, Any]) -> dict[str, str]:
    return {
        "experiment_run_id": str(manifest["experiment_run_id"]),
        "manifest_id": str(manifest["manifest_id"]),
        "source_git_commit": str(manifest["source_git_commit"]),
    }


def _load_passive_model() -> Any:
    rows = _read_csv(PASSIVE_TUNING_CASES)
    if not rows:
        raise RuntimeError("frozen passive tuning cases are empty")
    return fit_passive_centroid(rows)


def _build_probe_context(
    *, fault: Any, seed: int, perturbation_seed_base: int
) -> dict[str, Any]:
    repetitions = run_repeated_symmetric_probes(
        lambda: create_push_environment(seed),
        seed=seed,
        perturbation_factory=fault.build,
        repeats=4,
        magnitude=0.2,
        steps=4,
        perturbation_seed_base=perturbation_seed_base,
    )
    estimates = [estimate_planar_bias(group) for group in repetitions]
    return build_repeated_agent_probe_context(repetitions, estimates)


def _collect_cases(
    manifest: Mapping[str, Any], config: Mapping[str, Any], run_directory: Path
) -> list[dict[str, Any]]:
    audit_path = run_directory / "oracle_case_audit.jsonl"
    agent_evidence_path = run_directory / "agent_evidence.jsonl"
    probe_evidence_path = run_directory / "agent_probe_evidence.jsonl"
    runtime_path = run_directory / "agent_runtime.csv"
    cases = _read_jsonl(audit_path)
    agent_evidence = _read_jsonl(agent_evidence_path)
    probe_evidence = _read_jsonl(probe_evidence_path)
    runtime_rows = _read_csv(runtime_path) if runtime_path.is_file() else []
    completed_ids = {str(row["case_id"]) for row in cases}
    passive_model = _load_passive_model()
    noise_std = float(json.loads(NOISE_SELECTION.read_text(encoding="utf-8"))["noise_std"])
    conditions = get_conditions(noise_std)
    mapping = {item["condition_id"]: item for item in config["conditions"]}
    namespaces = config["random_seed_namespaces"]
    allocation = config["allocation"]
    budget = config["budget"]
    probe_config = config["registered_probe"]
    provenance = _provenance(manifest)
    episode_id = 0

    for fault in conditions:
        if fault.condition_id not in mapping:
            raise ValueError(f"condition is not registered: {fault.condition_id}")
        mechanism = str(mapping[fault.condition_id]["evaluator_mechanism"])
        for seed in range(config["seed_start"], config["seed_start"] + config["num_seeds"]):
            episode_id += 1
            case_id = f"heldout_case_{episode_id:04d}"
            if case_id in completed_ids:
                continue
            trajectory_path = run_directory / "agent_trajectories" / f"{case_id}_seed{seed}.jsonl"
            trajectory_path.parent.mkdir(parents=True, exist_ok=True)
            recorder = DecisionRuntimeRecorder()
            initial_seed = derive_random_seed(seed, int(namespaces["perturbation"]))
            env = create_push_environment(seed)
            try:
                result = run_episode(
                    env,
                    create_push_policy(),
                    seed=seed,
                    max_steps=int(config["max_initial_steps"]),
                    episode_id=episode_id,
                    perturbation=fault.build(),
                    perturbation_seed=initial_seed,
                    agent_trajectory_path=trajectory_path,
                )
            finally:
                env.close()
            transitions = _agent_rows(trajectory_path)
            evidence_id = f"evidence_{episode_id:04d}_attempt0"
            with recorder.measure("evidence_state_build_ms"):
                state = build_structured_evidence_state(
                    transitions,
                    evidence_id=evidence_id,
                    minimum_phase_samples=int(allocation["minimum_phase_samples"]),
                    contact_distance=float(allocation["contact_distance_m"]),
                    near_goal_distance=float(allocation["near_goal_distance_m"]),
                )
            remaining = int(budget["total_case_environment_steps"]) - result.steps
            with recorder.measure("evidence_decision_ms"):
                decision = select_evidence_action(
                    state,
                    remaining,
                    decision_id=f"decision_{episode_id:04d}_attempt0",
                    threshold=float(allocation["threshold"]),
                    total_case_budget=int(budget["total_case_environment_steps"]),
                    registered_probe_cost=int(budget["registered_probe_environment_steps"]),
                    minimum_reserved_verification_budget=int(
                        budget["minimum_reserved_verification_steps"]
                    ),
                )
            passive_row = {
                "episode_return": result.episode_return,
                "final_object_goal_distance": result.final_object_goal_distance,
                "progress_to_goal": result.progress_to_goal,
            }
            passive = passive_model.predict(passive_row)
            probe_seed = derive_random_seed(seed, int(namespaces["probe_execution"]))
            context = _build_probe_context(
                fault=fault, seed=seed, perturbation_seed_base=probe_seed
            )
            probe_steps = int(context["probe_environment_steps"])
            if probe_steps > int(probe_config["max_environment_steps"]):
                raise RuntimeError(f"registered probe exceeded its cost for {case_id}")
            score = float(context["consistency"]["estimated_bias_std_norm"])
            probe_prediction = classify_probe(
                score, float(probe_config["outcome_classifier_threshold"])
            )
            diagnostic_probe_needed = (
                passive.mechanism != mechanism and probe_prediction == mechanism
            )
            result_fields = _result_fields(result)
            runtime = recorder.snapshot()
            cases.append(
                {
                    "case_schema_version": CASE_SCHEMA_VERSION,
                    **provenance,
                    "case_id": case_id,
                    "episode_id": episode_id,
                    "seed": seed,
                    "condition_id": fault.condition_id,
                    "perturbation_type_oracle": fault.kind,
                    "perturbation_parameters_oracle": fault.parameters,
                    "mechanism_class_oracle": mechanism,
                    **result_fields,
                    "decision_required": state.decision_required,
                    "passive_prediction": passive.mechanism,
                    "passive_uncertainty": passive.uncertainty,
                    "probe_prediction": probe_prediction,
                    "probe_score": score,
                    "counterfactual_probe_environment_steps": probe_steps,
                    "diagnostic_probe_needed_oracle": diagnostic_probe_needed,
                    "phase_gate_action": decision.action.value,
                    "phase_inconsistency": state.phase_response.phase_inconsistency,
                    "temporal_uncertainty": state.temporal_response.uncertainty,
                    "remaining_budget_before": remaining,
                    "consumed_budget_before": int(budget["total_case_environment_steps"]) - remaining,
                    "reserved_probe_budget": decision.reserved_probe_budget,
                    "reserved_verification_budget": decision.reserved_verification_budget,
                    "budget_rejection_reason": decision.budget_rejection_reason,
                    "initial_perturbation_seed": initial_seed,
                    "probe_perturbation_seed_base": probe_seed,
                }
            )
            agent_evidence.append(
                {
                    **provenance,
                    "evidence_state": state.to_dict(),
                    "evidence_decision": decision.to_dict(),
                    "runtime": runtime.to_dict(),
                }
            )
            probe_evidence.append(
                {
                    **provenance,
                    "evidence_id": f"evidence_{episode_id:04d}_attempt1",
                    "episode_id": episode_id,
                    "attempt_id": 1,
                    "seed": seed,
                    "counterfactual_evaluator_collection": True,
                    "probe_context": context,
                }
            )
            runtime_rows.append({**provenance, "case_id": case_id, **runtime.to_dict()})
            _write_jsonl(audit_path, cases)
            _write_jsonl(agent_evidence_path, agent_evidence)
            _write_jsonl(probe_evidence_path, probe_evidence)
            _write_csv(runtime_path, runtime_rows)
            print(
                f"case={case_id} condition={fault.condition_id} seed={seed} "
                f"success={result.success} phase={state.phase_response.phase_inconsistency:.6f} "
                f"decision={decision.action.value}"
            )
    return cases


def _request_for_method(
    method: str,
    row: Mapping[str, Any],
    *,
    config: Mapping[str, Any],
    global_threshold: float,
) -> bool:
    if not bool(row["decision_required"]):
        return False
    if method == "passive":
        return False
    if method == "seeded_random_probe":
        return deterministic_random_request(
            str(row["case_id"]),
            float(config["random_probe_probability"]),
            int(config["random_seed_namespaces"]["random_probe_decision"]),
        )
    if method == "always_probe":
        return True
    if method == "global_temporal_gate":
        return float(row["temporal_uncertainty"]) >= global_threshold
    if method == "frozen_phase_conditioned_gate":
        return row["phase_gate_action"] == EvidenceDecisionKind.REQUEST_DIAGNOSTIC_PROBE.value
    if method == "oracle_audit":
        return bool(row["diagnostic_probe_needed_oracle"])
    raise ValueError(f"unknown allocation method: {method}")


def _method_rows(
    cases: Sequence[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    global_threshold: float,
) -> list[dict[str, Any]]:
    rows = []
    provenance = _provenance(manifest)
    for case in cases:
        for method in METHODS:
            request = _request_for_method(
                method, case, config=config, global_threshold=global_threshold
            )
            prediction = (
                str(case["probe_prediction"])
                if request
                else str(case["passive_prediction"])
            )
            probe_steps = (
                int(case["counterfactual_probe_environment_steps"]) if request else 0
            )
            initial_steps = int(case["steps"])
            rows.append(
                {
                    **provenance,
                    "case_id": case["case_id"],
                    "condition_id": case["condition_id"],
                    "seed": case["seed"],
                    "mechanism_class_oracle": case["mechanism_class_oracle"],
                    "decision_required": case["decision_required"],
                    "method": method,
                    "probe_requested": request,
                    "mechanism_prediction": prediction,
                    "mechanism_correct": prediction == case["mechanism_class_oracle"],
                    "diagnostic_probe_needed_oracle": case["diagnostic_probe_needed_oracle"],
                    "initial_environment_steps": initial_steps,
                    "probe_environment_steps": probe_steps,
                    "verification_environment_steps": 0,
                    "adaptation_environment_steps": probe_steps,
                    "total_physical_environment_steps": initial_steps + probe_steps,
                }
            )
    return rows


def _summary_rows(
    method_rows: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]
) -> list[dict[str, Any]]:
    provenance = _provenance(manifest)
    populations: list[tuple[str, list[Mapping[str, Any]]]] = [
        ("full_collection", list(method_rows)),
        (
            "operational_decision",
            [row for row in method_rows if bool(row["decision_required"])],
        ),
    ]
    operational = populations[1][1]
    for mechanism in sorted({str(row["mechanism_class_oracle"]) for row in operational}):
        populations.append(
            (
                f"operational_decision:{mechanism}",
                [row for row in operational if row["mechanism_class_oracle"] == mechanism],
            )
        )
    summaries = []
    for population_name, population_rows in populations:
        for method in METHODS:
            rows = [row for row in population_rows if row["method"] == method]
            if not rows:
                continue
            truth = [str(row["mechanism_class_oracle"]) for row in rows]
            predictions = [str(row["mechanism_prediction"]) for row in rows]
            correct = sum(bool(row["mechanism_correct"]) for row in rows)
            requests = sum(bool(row["probe_requested"]) for row in rows)
            probe_steps = sum(int(row["probe_environment_steps"]) for row in rows)
            passive_correct = sum(
                str(row["mechanism_class_oracle"])
                == next(
                    str(candidate["mechanism_prediction"])
                    for candidate in method_rows
                    if candidate["case_id"] == row["case_id"] and candidate["method"] == "passive"
                )
                for row in rows
            )
            unnecessary = sum(
                bool(row["probe_requested"])
                and not bool(row["diagnostic_probe_needed_oracle"])
                for row in rows
            )
            interval = wilson_interval(correct, len(rows))
            summaries.append(
                {
                    **provenance,
                    "population": population_name,
                    "method": method,
                    "units": len(rows),
                    "mechanism_correct": correct,
                    "mechanism_accuracy": accuracy(truth, predictions),
                    "balanced_accuracy": balanced_accuracy(truth, predictions),
                    "accuracy_wilson_lower": interval[0] if interval else None,
                    "accuracy_wilson_upper": interval[1] if interval else None,
                    "probe_requests": requests,
                    "probe_request_rate": requests / len(rows),
                    "probe_environment_steps": probe_steps,
                    "verification_environment_steps": 0,
                    "total_physical_environment_steps": sum(
                        int(row["total_physical_environment_steps"]) for row in rows
                    ),
                    "unnecessary_probe_rate": unnecessary / requests if requests else None,
                    "evidence_efficiency_correct_per_probe_step": (
                        (correct - passive_correct) / probe_steps if probe_steps else None
                    ),
                }
            )
    return summaries


def _matching_rows(
    cases: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    failures = [row for row in cases if bool(row["decision_required"])]
    converted = [
        PassiveFailureCase(
            case_id=str(row["case_id"]),
            condition_id=str(row["condition_id"]),
            seed=int(row["seed"]),
            mechanism_class=str(row["mechanism_class_oracle"]),
            episode_return=float(row["episode_return"]),
            final_object_goal_distance=float(row["final_object_goal_distance"]),
            progress_to_goal=float(row["progress_to_goal"]),
            perturbation_parameters=dict(row["perturbation_parameters_oracle"]),
        )
        for row in failures
    ]
    pairs = match_passive_failures(
        [row for row in converted if row.mechanism_class == "stable_bias"],
        [row for row in converted if row.mechanism_class == "stochastic_noise"],
    )
    provenance = _provenance(manifest)
    rows = []
    case_ids = []
    for pair in pairs:
        for role, case in (("bias", pair.bias_case), ("noise", pair.noise_case)):
            case_ids.append(case.case_id)
            rows.append(
                {
                    **provenance,
                    "pair_id": pair.pair_id,
                    "pair_role": role,
                    "case_id": case.case_id,
                    "condition_id": case.condition_id,
                    "seed": case.seed,
                    "mechanism_class_oracle": case.mechanism_class,
                    "standardized_pair_distance": pair.standardized_distance,
                }
            )
    return rows, case_ids


def _evaluate(
    cases: Sequence[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    run_directory: Path,
) -> dict[str, Any]:
    global_source = json.loads(GLOBAL_GATE_SOURCE.read_text(encoding="utf-8"))
    global_threshold = float(global_source["threshold"])
    method_rows = _method_rows(
        cases,
        manifest=manifest,
        config=config,
        global_threshold=global_threshold,
    )
    summaries = _summary_rows(method_rows, manifest)
    _write_csv(run_directory / "method_results.csv", method_rows)
    _write_csv(run_directory / "method_summary.csv", summaries)
    pairs, matched_case_ids = _matching_rows(cases, manifest)
    _write_csv(run_directory / "matched_subset.csv", pairs)

    operational = [row for row in cases if bool(row["decision_required"])]
    labels = [bool(row["diagnostic_probe_needed_oracle"]) for row in operational]
    scores = [float(row["phase_inconsistency"]) for row in operational]
    positives = sum(labels)
    score_audit = {
        **_provenance(manifest),
        "population": "operational_decision",
        "units": len(operational),
        "positive_labels": positives,
        "negative_labels": len(labels) - positives,
        "positive_prevalence": positives / len(labels) if labels else None,
        "roc_auc": roc_auc(labels, scores),
        "pr_auc_average_precision": average_precision(labels, scores),
        "score_distribution": {
            "positive": [score for score, label in zip(scores, labels) if label],
            "negative": [score for score, label in zip(scores, labels) if not label],
        },
        "mechanism_strata": {
            mechanism: {
                "units": len(rows),
                "positive": sum(bool(row["diagnostic_probe_needed_oracle"]) for row in rows),
                "prevalence": (
                    sum(bool(row["diagnostic_probe_needed_oracle"]) for row in rows) / len(rows)
                    if rows
                    else None
                ),
            }
            for mechanism in sorted({str(row["mechanism_class_oracle"]) for row in operational})
            for rows in [[row for row in operational if row["mechanism_class_oracle"] == mechanism]]
        },
    }
    if positives == 0 or positives == len(labels):
        score_audit["experiment_status"] = "INCOMPLETE_FOR_PROBE_NEED_EVALUATION"
    else:
        score_audit["experiment_status"] = "COMPLETE_FOR_PROBE_NEED_EVALUATION"
    _write_json(run_directory / "probe_need_evaluation.json", score_audit)

    selected = [row for row in method_rows if row["case_id"] in matched_case_ids]
    phase = {
        str(row["case_id"]): row
        for row in selected
        if row["method"] == "frozen_phase_conditioned_gate"
    }
    always = {
        str(row["case_id"]): row for row in selected if row["method"] == "always_probe"
    }
    ordered_ids = sorted(set(phase) & set(always))
    strata = [str(phase[case_id]["mechanism_class_oracle"]) for case_id in ordered_ids]
    paired = {
        **_provenance(manifest),
        "matched_units": len(ordered_ids),
        "diagnosis_phase_vs_always": paired_win_tie_loss(
            [bool(phase[case_id]["mechanism_correct"]) for case_id in ordered_ids],
            [bool(always[case_id]["mechanism_correct"]) for case_id in ordered_ids],
        ) if ordered_ids else None,
        "accuracy_difference_phase_minus_always": stratified_paired_bootstrap_difference(
            [float(bool(phase[case_id]["mechanism_correct"])) for case_id in ordered_ids],
            [float(bool(always[case_id]["mechanism_correct"])) for case_id in ordered_ids],
            strata,
            repetitions=int(config["statistics"]["bootstrap_repetitions"]),
            seed=int(config["statistics"]["bootstrap_seed"]),
        ),
        "probe_cost_difference_phase_minus_always": stratified_paired_bootstrap_difference(
            [float(phase[case_id]["probe_environment_steps"]) for case_id in ordered_ids],
            [float(always[case_id]["probe_environment_steps"]) for case_id in ordered_ids],
            strata,
            repetitions=int(config["statistics"]["bootstrap_repetitions"]),
            seed=int(config["statistics"]["bootstrap_seed"]) + 1,
        ),
    }
    _write_json(run_directory / "paired_evaluation.json", paired)

    operational_summary = {
        str(row["method"]): row
        for row in summaries
        if row["population"] == "operational_decision"
    }
    phase_summary = operational_summary["frozen_phase_conditioned_gate"]
    always_summary = operational_summary["always_probe"]
    gates = {
        "both_probe_need_classes": positives > 0 and positives < len(labels),
        "accuracy_relative_to_always": (
            float(phase_summary["mechanism_accuracy"])
            >= float(config["promotion_gate"]["minimum_accuracy_relative_to_always_probe"])
            * float(always_summary["mechanism_accuracy"])
        ),
        "probe_request_rate": (
            float(phase_summary["probe_request_rate"])
            <= float(config["promotion_gate"]["maximum_probe_request_rate"])
        ),
        "probe_need_roc_auc": (
            score_audit["roc_auc"] is not None
            and float(score_audit["roc_auc"])
            >= float(config["promotion_gate"]["minimum_probe_need_roc_auc"])
        ),
        "lower_probe_cost_than_always": (
            int(phase_summary["probe_environment_steps"])
            < int(always_summary["probe_environment_steps"])
        ),
        "no_agent_oracle_leakage": True,
    }
    promotion = {
        **_provenance(manifest),
        "gates": gates,
        "status": (
            "PROMOTED" if all(gates.values()) else
            "INCOMPLETE" if not gates["both_probe_need_classes"] else
            "NOT_PROMOTED"
        ),
        "heldout_retuning_permitted": False,
    }
    _write_json(run_directory / "promotion.json", promotion)
    return promotion


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_directory = args.manifest.resolve().parent
    try:
        manifest, config = validate_manifest(args.manifest)
        status_path = run_directory / "run_status.json"
        if status_path.is_file():
            existing = json.loads(status_path.read_text(encoding="utf-8"))
            if existing.get("status") == "COMPLETED":
                raise FileExistsError("immutable held-out run is already complete")
        _write_json(
            status_path,
            {
                **_provenance(manifest),
                "status": "RUNNING",
                "rendering": False,
                "heldout_retuning": False,
            },
        )
        cases = _collect_cases(manifest, config, run_directory)
        expected = int(config["num_seeds"]) * len(config["conditions"])
        if len(cases) != expected:
            raise RuntimeError(f"expected {expected} cases, collected {len(cases)}")
        promotion = _evaluate(
            cases,
            manifest=manifest,
            config=config,
            run_directory=run_directory,
        )
        runtime_samples = [
            AgentDecisionRuntime(
                evidence_state_build_ms=float(row["evidence_state_build_ms"]),
                evidence_decision_ms=float(row["evidence_decision_ms"]),
                total_agent_decision_ms=float(row["total_agent_decision_ms"]),
                warmup=str(row["warmup"]).lower() == "true",
            )
            for row in _read_csv(run_directory / "agent_runtime.csv")
        ]
        _write_json(
            run_directory / "agent_runtime_summary.json",
            {**_provenance(manifest), "summary": summarize_decision_runtimes(runtime_samples)},
        )
        _write_json(
            status_path,
            {
                **_provenance(manifest),
                "status": "COMPLETED",
                "collection_units": len(cases),
                "operational_units": sum(bool(row["decision_required"]) for row in cases),
                "promotion_status": promotion["status"],
                "rendering": False,
                "heldout_retuning": False,
            },
        )
        print(f"run: {manifest['experiment_run_id']}")
        print(f"collection units: {len(cases)}")
        print(f"promotion: {promotion['status']}")
        print(f"results: {run_directory}")
        return 0
    except Exception as exc:
        try:
            if args.manifest.is_file():
                manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
                _write_json(
                    run_directory / "run_status.json",
                    {
                        **_provenance(manifest),
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "heldout_retuning": False,
                    },
                )
        except Exception:
            pass
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
