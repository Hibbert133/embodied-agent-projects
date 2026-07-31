"""Run a paired development audit of mechanism-to-intervention identifiability."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import get_conditions  # noqa: E402
from scripts.build_bias_noise_ambiguity_benchmark import classify_probe  # noqa: E402
from scripts.run_frozen_heldout_allocation import (  # noqa: E402
    _build_probe_context,
    _load_passive_model,
    derive_random_seed,
)
from scripts.run_frozen_heldout_intervention import (  # noqa: E402
    _execute_plan,
)
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.evaluation.intervention_utility import (  # noqa: E402
    CandidateUtilityOutcome,
    UtilityComparison,
    best_candidate_ids,
    compare_candidate_utility,
)
from src.planner.evidence_grounded import (  # noqa: E402
    first_registered_probe_context,
    select_grounded_intervention,
)
from src.reasoning.evidence import validate_no_oracle_evidence  # noqa: E402
from src.reasoning.structured_evidence import build_structured_evidence_state  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs/autoresearch/intervention_identifiability_development_v2.json"
NOISE_SELECTION = ROOT / "outputs/autoresearch/noise_calibration/selected.json"
COMPENSATION = "probe_grounded_compensation"
RETRY = "stochastic_retry"


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    temporary.replace(path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_development_config(config: Mapping[str, Any]) -> None:
    if config.get("split") != "development":
        raise ValueError("identifiability audit must use the development split")
    seeds = set(
        range(int(config["seed_start"]), int(config["seed_start"]) + int(config["num_seeds"]))
    )
    if not seeds or seeds & set(range(330, 340)):
        raise ValueError("development seeds must not overlap frozen held-out seeds 330--339")
    if list(config["candidates"]) != [COMPENSATION, RETRY]:
        raise ValueError("v1 requires exactly the two registered candidates")
    if config.get("rendering") is not False or int(config.get("api_calls", -1)) != 0:
        raise ValueError("development timing audit cannot render or call an API")
    condition_ids = [str(item["condition_id"]) for item in config["conditions"]]
    registered_all = [f"fault_{index:02d}" for index in range(1, 6)]
    if condition_ids not in (registered_all, ["fault_05"]):
        raise ValueError("development audit must use all conditions or noise-only fault_05")
    if config.get("study_kind") == "noise_stratum_extension":
        seeds = set(
            range(
                int(config["seed_start"]),
                int(config["seed_start"]) + int(config["num_seeds"]),
            )
        )
        if condition_ids != ["fault_05"] or seeds & set(range(400, 410)):
            raise ValueError("noise extension must use fault_05 and fresh post-409 seeds")
    if config.get("study_kind") == "noise_stratum_coverage":
        target = int(config.get("target_paired_comparable_operational_units", 0))
        stopping = config.get("stopping_rule", {})
        if (
            condition_ids != ["fault_05"]
            or int(config["seed_start"]) < 430
            or target <= 0
            or int(stopping.get("target", -1)) != target
            or bool(stopping.get("may_read_utility_label", True))
            or int(stopping.get("maximum_initial_units", -1)) != int(config["num_seeds"])
        ):
            raise ValueError("coverage study requires a label-blind bounded stop rule")
    handling = config.get("unavailable_candidate_handling")
    if int(config.get("protocol_version", 1)) >= 2 and (
        not isinstance(handling, Mapping)
        or handling.get("abstain_is_executable") is not False
        or handling.get("execute_remaining_candidates") is not True
    ):
        raise ValueError("v2 must preserve abstention and report remaining candidates")


def _agent_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _candidate_from_mechanism(mechanism: str) -> str:
    if mechanism == "stable_bias":
        return COMPENSATION
    if mechanism == "stochastic_noise":
        return RETRY
    raise ValueError(f"unsupported mechanism: {mechanism}")


def _outcome(candidate_id: str, value: Mapping[str, Any]) -> CandidateUtilityOutcome:
    return CandidateUtilityOutcome.from_mapping({"candidate_id": candidate_id, **value})


def _selected_comparison(
    passive_candidate: str,
    probe_candidate: str,
    outcomes: Mapping[str, CandidateUtilityOutcome],
) -> UtilityComparison:
    if passive_candidate == probe_candidate:
        return UtilityComparison.TIE
    return compare_candidate_utility(
        outcomes[probe_candidate], outcomes[passive_candidate]
    )


def _summary(
    cases: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    operational = [row for row in cases if bool(row["decision_required"])]
    comparable = [row for row in operational if bool(row.get("paired_comparable"))]
    candidate_summary: dict[str, Any] = {}
    for candidate_id in (COMPENSATION, RETRY):
        selected = [row for row in candidates if row["candidate_id"] == candidate_id]
        candidate_summary[candidate_id] = {
            "units": len(selected),
            "accepted": sum(row["verification_status"] == "ACCEPTED" for row in selected),
            "recovery_rate": (
                sum(row["verification_status"] == "ACCEPTED" for row in selected)
                / len(selected)
                if selected
                else None
            ),
            "mean_verification_steps": mean(row["verification_steps"] for row in selected)
            if selected
            else None,
            "mean_final_object_goal_distance": mean(
                row["final_object_goal_distance"] for row in selected
            )
            if selected
            else None,
        }
    strata: dict[str, Any] = {}
    for field in ("condition_id", "mechanism_class_oracle"):
        strata[field] = {}
        for value in sorted({str(row[field]) for row in comparable}):
            selected = [row for row in comparable if str(row[field]) == value]
            strata[field][value] = {
                "units": len(selected),
                "compensation_best": sum(
                    COMPENSATION in str(row["best_candidate_ids"]).split(",")
                    for row in selected
                ),
                "retry_best": sum(
                    RETRY in str(row["best_candidate_ids"]).split(",")
                    for row in selected
                ),
                "oracle_mechanism_alignment_rate": mean(
                    bool(row["oracle_mechanism_candidate_is_best"])
                    for row in selected
                ),
                "probe_belief_alignment_rate": mean(
                    bool(row["probe_candidate_is_best"]) for row in selected
                ),
            }
    return {
        "full_collection_units": len(cases),
        "operational_units": len(operational),
        "paired_comparable_units": len(comparable),
        "compensation_unavailable_units": sum(
            not bool(row.get("compensation_available")) for row in operational
        ),
        "paired_coverage": len(comparable) / len(operational) if operational else None,
        "winner_counts": {
            COMPENSATION: sum(row["best_candidate_ids"] == COMPENSATION for row in comparable),
            RETRY: sum(row["best_candidate_ids"] == RETRY for row in comparable),
            "tie": sum("," in str(row["best_candidate_ids"]) for row in comparable),
        },
        "oracle_mechanism_alignment_rate": mean(
            bool(row["oracle_mechanism_candidate_is_best"]) for row in comparable
        )
        if comparable
        else None,
        "passive_belief_alignment_rate": mean(
            bool(row["passive_candidate_is_best"]) for row in comparable
        )
        if comparable
        else None,
        "probe_belief_alignment_rate": mean(
            bool(row["probe_candidate_is_best"]) for row in comparable
        )
        if comparable
        else None,
        "belief_change_count": sum(bool(row["belief_changed"]) for row in operational),
        "probe_selected_outcome_improved_count": sum(
            row["probe_vs_passive_selected_outcome"] == UtilityComparison.LEFT.value
            for row in operational
        ),
        "probe_selected_outcome_worsened_count": sum(
            row["probe_vs_passive_selected_outcome"] == UtilityComparison.RIGHT.value
            for row in operational
        ),
        "candidate_summary": candidate_summary,
        "stratified_summary": strata,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "outputs/intervention_identifiability/runs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_directory: Path | None = None
    manifest: dict[str, Any] | None = None
    try:
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        validate_development_config(config)
        if _git("diff", "--name-only") or _git("diff", "--cached", "--name-only"):
            raise RuntimeError("commit protocol and implementation before development execution")
        source_commit = _git("rev-parse", "HEAD")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"development_{timestamp}_{source_commit[:12]}"
        run_directory = args.output_root.resolve() / run_id
        if run_directory.exists():
            raise FileExistsError(f"run directory already exists: {run_directory}")
        run_directory.mkdir(parents=True)
        manifest = {
            "experiment_run_id": run_id,
            "protocol_id": config["protocol_id"],
            "source_git_commit": source_commit,
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha256(config_path),
            "execution_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "seed_range": [
                int(config["seed_start"]),
                int(config["seed_start"]) + int(config["num_seeds"]) - 1,
            ],
            "dependencies": {
                name: importlib.metadata.version(name)
                for name in ("metaworld", "mujoco", "gymnasium", "numpy")
            },
            "split": "development",
            "heldout_retuning": False,
        }
        _write_json(run_directory / "manifest.json", manifest)
        _write_json(run_directory / "run_status.json", {**manifest, "status": "RUNNING"})

        recovery_config = RecoveryPolicyConfig.from_mapping(
            json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
        )
        passive_model = _load_passive_model()
        noise_std = float(json.loads(NOISE_SELECTION.read_text(encoding="utf-8"))["noise_std"])
        registered_condition_ids = {
            str(item["condition_id"]) for item in config["conditions"]
        }
        faults = [
            fault
            for fault in get_conditions(noise_std)
            if fault.condition_id in registered_condition_ids
        ]
        mechanism_by_condition = {
            str(item["condition_id"]): str(item["evaluator_mechanism"])
            for item in config["conditions"]
        }
        namespaces = config["random_seed_namespaces"]
        evidence_config = config["structured_evidence"]
        probe_config = config["registered_probe"]
        case_rows: list[dict[str, Any]] = []
        candidate_rows: list[dict[str, Any]] = []
        agent_rows: list[dict[str, Any]] = []
        oracle_rows: list[dict[str, Any]] = []
        episode_id = 0
        target_comparable = int(
            config.get("target_paired_comparable_operational_units", 0)
        )

        with tempfile.TemporaryDirectory(prefix="identifiability_agent_view_") as temporary:
            temporary_dir = Path(temporary)
            for fault in faults:
                mechanism = mechanism_by_condition[fault.condition_id]
                for seed in range(
                    int(config["seed_start"]),
                    int(config["seed_start"]) + int(config["num_seeds"]),
                ):
                    if target_comparable and sum(
                        bool(row.get("paired_comparable")) for row in case_rows
                    ) >= target_comparable:
                        break
                    episode_id += 1
                    case_id = f"development_case_{episode_id:04d}"
                    trajectory_path = temporary_dir / f"{case_id}.jsonl"
                    initial_seed = derive_random_seed(
                        seed, int(namespaces["initial_perturbation"])
                    )
                    environment = create_push_environment(seed)
                    try:
                        initial = run_episode(
                            environment,
                            create_push_policy(),
                            seed=seed,
                            episode_id=episode_id,
                            max_steps=int(config["max_initial_steps"]),
                            perturbation=fault.build(),
                            perturbation_seed=initial_seed,
                            agent_trajectory_path=trajectory_path,
                        )
                    finally:
                        environment.close()
                    state = build_structured_evidence_state(
                        _agent_rows(trajectory_path),
                        evidence_id=f"{case_id}_attempt0",
                        minimum_phase_samples=int(evidence_config["minimum_phase_samples"]),
                        contact_distance=float(evidence_config["contact_distance_m"]),
                        near_goal_distance=float(evidence_config["near_goal_distance_m"]),
                    )
                    base = {
                        "experiment_run_id": run_id,
                        "source_git_commit": source_commit,
                        "case_id": case_id,
                        "episode_id": episode_id,
                        "seed": seed,
                        "decision_required": bool(state.decision_required),
                        "initial_success": bool(initial.success),
                        "initial_steps": int(initial.steps),
                        "initial_return": float(initial.episode_return),
                        "initial_final_object_goal_distance": float(
                            initial.final_object_goal_distance
                        ),
                    }
                    if not state.decision_required:
                        case_rows.append(
                            {
                                **base,
                                "paired_comparable": False,
                                "compensation_available": "",
                                "best_candidate_ids": "",
                            }
                        )
                        oracle_rows.append(
                            {
                                **base,
                                "condition_id": fault.condition_id,
                                "mechanism_class_oracle": mechanism,
                                "perturbation_type_oracle": fault.kind,
                                "perturbation_parameters_oracle": fault.parameters,
                            }
                        )
                        _write_csv(run_directory / "case_results.csv", case_rows)
                        _write_jsonl(run_directory / "oracle_audit.jsonl", oracle_rows)
                        print(f"case={case_id} condition={fault.condition_id} seed={seed} initial=success")
                        continue

                    passive = passive_model.predict(
                        {
                            "episode_return": initial.episode_return,
                            "final_object_goal_distance": initial.final_object_goal_distance,
                            "progress_to_goal": initial.progress_to_goal,
                        }
                    )
                    probe_seed = derive_random_seed(seed, int(namespaces["registered_probe"]))
                    probe_context = _build_probe_context(
                        fault=fault, seed=seed, perturbation_seed_base=probe_seed
                    )
                    if int(probe_context["probe_environment_steps"]) > int(
                        probe_config["max_environment_steps"]
                    ):
                        raise RuntimeError(f"registered probe exceeded budget: {case_id}")
                    probe_score = float(
                        probe_context["consistency"]["estimated_bias_std_norm"]
                    )
                    probe_prediction = classify_probe(
                        probe_score,
                        float(probe_config["outcome_classifier_threshold"]),
                    )
                    compensation = select_grounded_intervention(
                        plan_id=f"{case_id}_{COMPENSATION}",
                        evidence_id=state.evidence_id,
                        mechanism_belief="stable_bias",
                        correction_context=first_registered_probe_context(probe_context),
                        recovery_config=recovery_config,
                        evidence_source="registered_probe",
                    )
                    retry = select_grounded_intervention(
                        plan_id=f"{case_id}_{RETRY}",
                        evidence_id=state.evidence_id,
                        mechanism_belief="stochastic_noise",
                        correction_context=None,
                        recovery_config=recovery_config,
                        evidence_source="initial_rollout",
                    )
                    compensation_available = compensation.requires_fresh_verification
                    plans = {RETRY: retry}
                    if compensation_available:
                        plans = {COMPENSATION: compensation, RETRY: retry}
                    verification_seed = derive_random_seed(
                        seed, int(namespaces["paired_verification"])
                    )
                    case_oracle = {
                        "case_id": case_id,
                        "seed": seed,
                        "condition_id": fault.condition_id,
                        "perturbation_type_oracle": fault.kind,
                        "perturbation_parameters_oracle": fault.parameters,
                        "final_object_goal_distance": initial.final_object_goal_distance,
                    }
                    outcomes: dict[str, CandidateUtilityOutcome] = {}
                    raw_outcomes: dict[str, dict[str, Any]] = {}
                    for candidate_id, plan in plans.items():
                        raw = _execute_plan(
                            case_oracle,
                            plan,
                            verification_seed=verification_seed,
                            maximum_steps=int(config["max_verification_steps"]),
                        )
                        raw_outcomes[candidate_id] = raw
                        outcomes[candidate_id] = _outcome(candidate_id, raw)
                        candidate_rows.append(
                            {
                                **base,
                                "condition_id": fault.condition_id,
                                "mechanism_class_oracle": mechanism,
                                "candidate_id": candidate_id,
                                "schedule": plan.schedule,
                                "correction_x": plan.correction[0],
                                "correction_y": plan.correction[1],
                                **raw,
                                "registered_probe_environment_steps": int(
                                    probe_context["probe_environment_steps"]
                                ),
                                "verification_perturbation_seed": verification_seed,
                            }
                        )
                    passive_candidate = _candidate_from_mechanism(passive.mechanism)
                    probe_candidate = _candidate_from_mechanism(probe_prediction)
                    oracle_candidate = _candidate_from_mechanism(mechanism)
                    paired_comparable = len(outcomes) == 2
                    winners = (
                        best_candidate_ids(list(outcomes.values()))
                        if paired_comparable
                        else ()
                    )
                    selected_comparison = (
                        _selected_comparison(passive_candidate, probe_candidate, outcomes)
                        if paired_comparable
                        else None
                    )
                    case_result = {
                        **base,
                        "condition_id": fault.condition_id,
                        "mechanism_class_oracle": mechanism,
                        "passive_prediction": passive.mechanism,
                        "probe_prediction": probe_prediction,
                        "probe_score": probe_score,
                        "probe_relative_bias_std": float(
                            probe_context["consistency"]["relative_bias_std"]
                        ),
                        "probe_mean_estimation_residual": float(
                            probe_context["consistency"]["mean_estimation_residual"]
                        ),
                        "probe_sign_disagreement": 1.0
                        - float(
                            probe_context["consistency"][
                                "dominant_axis_sign_agreement"
                            ]
                        ),
                        "phase_inconsistency": state.phase_response.phase_inconsistency,
                        "temporal_uncertainty": state.temporal_response.uncertainty,
                        "passive_candidate": passive_candidate,
                        "probe_candidate": probe_candidate,
                        "oracle_mechanism_candidate": oracle_candidate,
                        "best_candidate_ids": ",".join(winners),
                        "paired_comparable": paired_comparable,
                        "compensation_available": compensation_available,
                        "compensation_unavailable_reason": (
                            "registered_recovery_policy_abstained"
                            if not compensation_available
                            else ""
                        ),
                        "passive_candidate_is_best": (
                            passive_candidate in winners if paired_comparable else ""
                        ),
                        "probe_candidate_is_best": (
                            probe_candidate in winners if paired_comparable else ""
                        ),
                        "oracle_mechanism_candidate_is_best": (
                            oracle_candidate in winners if paired_comparable else ""
                        ),
                        "belief_changed": passive.mechanism != probe_prediction,
                        "intervention_changed": passive_candidate != probe_candidate,
                        "probe_vs_passive_selected_outcome": (
                            selected_comparison.value if selected_comparison is not None else "UNAVAILABLE"
                        ),
                        "registered_probe_environment_steps": int(
                            probe_context["probe_environment_steps"]
                        ),
                        "initial_perturbation_seed": initial_seed,
                        "probe_perturbation_seed_base": probe_seed,
                        "verification_perturbation_seed": verification_seed,
                    }
                    case_rows.append(case_result)
                    agent_record = {
                        "experiment_run_id": run_id,
                        "case_id": case_id,
                        "episode_id": episode_id,
                        "seed": seed,
                        "structured_evidence_state": state.to_dict(),
                        "registered_probe_context": probe_context,
                        "passive_mechanism_belief": passive.mechanism,
                        "post_probe_mechanism_belief": probe_prediction,
                    }
                    validate_no_oracle_evidence(agent_record)
                    agent_rows.append(agent_record)
                    oracle_rows.append(
                        {
                            **case_result,
                            "perturbation_type_oracle": fault.kind,
                            "perturbation_parameters_oracle": fault.parameters,
                            "candidate_outcomes_oracle": raw_outcomes,
                        }
                    )
                    _write_csv(run_directory / "case_results.csv", case_rows)
                    _write_csv(run_directory / "candidate_results.csv", candidate_rows)
                    _write_jsonl(run_directory / "agent_evidence.jsonl", agent_rows)
                    _write_jsonl(run_directory / "oracle_audit.jsonl", oracle_rows)
                    print(
                        f"case={case_id} condition={fault.condition_id} seed={seed} "
                        f"winner={','.join(winners)} passive={passive_candidate} probe={probe_candidate}"
                    )

        summary = {**manifest, **_summary(case_rows, candidate_rows)}
        summary["target_paired_comparable_operational_units"] = (
            target_comparable or None
        )
        summary["coverage_target_reached"] = (
            summary["paired_comparable_units"] >= target_comparable
            if target_comparable
            else None
        )
        _write_json(run_directory / "summary.json", summary)
        _write_json(
            run_directory / "run_status.json",
            {
                **manifest,
                "status": "COMPLETED",
                "full_collection_units": len(case_rows),
                "operational_units": summary["operational_units"],
                "paired_comparable_units": summary["paired_comparable_units"],
                "coverage_target_reached": summary["coverage_target_reached"],
            },
        )
        print(f"run: {run_id}")
        print(f"results: {run_directory}")
        return 0
    except Exception as exc:
        if run_directory is not None and run_directory.exists():
            _write_json(
                run_directory / "run_status.json",
                {
                    **(manifest or {}),
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
