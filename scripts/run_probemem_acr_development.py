"""Run the frozen chronological ProbeMem-ACR paired development campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import get_conditions  # noqa: E402
from scripts.run_probemem_v2_smoke import (  # noqa: E402
    _append_jsonl,
    _probe_context,
    _read_jsonl,
    _run_verification,
    _write_csv,
)
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.probemem import (  # noqa: E402
    ActionOutcomeMemory,
    ActionOutcomeRecord,
    ActionRecordOrigin,
    CoverageAwareInterventionMemory,
    DeterministicActionConditionalEstimator,
    InterventionApplicabilitySignature,
    InterventionSkill,
    MemoryApplicabilityAction,
    VerifiedInterventionEpisode,
    build_action_conditional_evidence_pack,
    standardized_rms_distance,
    unique_episode_scales,
)
from src.probemem.intervention_selector import RelativeProbeVariationSelector  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _validate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"]:
        raise ValueError("ACR manifest directory differs from run ID")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("current HEAD differs from immutable ACR manifest")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("ACR execution requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("ACR config differs from immutable manifest")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"immutable ACR input changed: {relative}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if len(manifest["population_units"]) != 100:
        raise ValueError("ACR manifest must contain exactly 100 initial units")
    return manifest, config


def _load_verified_snapshot(path: Path) -> list[VerifiedInterventionEpisode]:
    return [
        VerifiedInterventionEpisode.from_dict(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _state_only_nearest(memory: ActionOutcomeMemory, query: InterventionApplicabilitySignature) -> dict[str, Any]:
    prior = memory.prior_records(query.episode_id)
    accepted = [item for item in prior if item.observed_status == "ACCEPTED"]
    if not accepted:
        return {"selected_skill": None, "reason": "ABSTAIN_NO_PRIOR_ACCEPTED", "record_id": None}
    scales = unique_episode_scales(prior)
    nearest = min(
        accepted,
        key=lambda item: (
            standardized_rms_distance(query, item.evidence_signature, scales),
            item.source_episode_id,
            item.record_id,
        ),
    )
    return {
        "selected_skill": nearest.intervention_skill.value,
        "reason": "COPY_NEAREST_PRIOR_ACCEPTED_SKILL",
        "record_id": nearest.record_id,
        "distance": standardized_rms_distance(query, nearest.evidence_signature, scales),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    status_path: Path | None = None
    manifest: dict[str, Any] | None = None
    try:
        manifest, config = _validate_manifest(args.manifest.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("ACR run directory has already been executed")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        noise_std = float(json.loads((ROOT / config["noise_selection"]).read_text(encoding="utf-8"))["noise_std"])
        conditions = {item.condition_id: item for item in get_conditions(noise_std)}
        recovery_config = RecoveryPolicyConfig.from_mapping(
            json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
        )
        memory = ActionOutcomeMemory()
        estimator = DeterministicActionConditionalEstimator()
        selector = RelativeProbeVariationSelector()
        snapshot = _load_verified_snapshot(ROOT / config["v2_coverage_baseline"]["snapshot"])
        coverage = CoverageAwareInterventionMemory(
            snapshot,
            neighbor_count=3,
            coverage_quantile=0.9,
            reserved_verification_steps=500,
            development_protocol_authorized=True,
        )
        case_rows: list[dict[str, Any]] = []
        candidate_rows: list[dict[str, Any]] = []
        chronology_violations = 0
        budget_violations = 0

        for unit in manifest["population_units"]:
            episode_id = int(unit["episode_id"])
            seed = int(unit["environment_seed"])
            fault = conditions[str(unit["condition_id_oracle"])]
            trajectory = run_dir / "initial_trajectories" / f"episode{episode_id:03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env,
                    create_push_policy(),
                    seed=seed,
                    episode_id=episode_id,
                    max_steps=int(config["budget"]["initial_rollout_max_steps"]),
                    perturbation=fault.build(),
                    perturbation_seed=int(unit["initial_perturbation_seed"]),
                    agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory),
                evidence_id=f"acr_episode{episode_id:03d}_attempt0",
                source=EvidenceSource.FAILED_ROLLOUT,
                attempt_id=0,
            )
            base = {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
                "episode_id": episode_id,
                "seed": seed,
                "initial_success": initial.success,
                "decision_required": state.decision_required,
                "initial_steps": initial.steps,
                "initial_final_object_goal_distance": initial.final_object_goal_distance,
            }
            if not state.decision_required:
                case_rows.append({
                    **base,
                    "condition_id_oracle": fault.condition_id,
                    "paired_comparable": False,
                    "probe_steps": 0,
                    "evaluator_collection_steps": initial.steps,
                })
                _write_csv(run_dir / "case_results.csv", case_rows)
                print(f"episode={episode_id} seed={seed} condition={fault.condition_id} initial=success")
                continue

            probe_context = _probe_context(fault, seed, config, int(unit["diagnostic_probe_seed"]))
            probe_steps = int(probe_context["probe_environment_steps"])
            if probe_steps > int(config["budget"]["registered_probe_max_steps"]):
                budget_violations += 1
                raise RuntimeError("registered probe exceeded ACR budget")
            probe_evidence = {
                **state.to_dict(),
                "evidence_id": f"acr_episode{episode_id:03d}_attempt1",
                "attempt_id": 1,
                "source": EvidenceSource.DIAGNOSTIC_PROBE.value,
                "parent_evidence_ids": [state.evidence_id],
                "registered_probe_evidence": probe_context,
            }
            validate_no_oracle_evidence(probe_evidence)
            query = InterventionApplicabilitySignature.from_agent_evidence(probe_evidence)
            pack = build_action_conditional_evidence_pack(memory, query)
            if any(item >= episode_id for item in pack.standardization_episode_ids):
                chronology_violations += 1
                raise RuntimeError("ACR standardization accessed current or future episode")
            acr = estimator.predict(pack)
            state_only = _state_only_nearest(memory, query)
            coverage_decision = coverage.decide(query, remaining_budget_steps=500)
            single = selector.select(query)
            predecision_timestamp = time.perf_counter_ns()
            methods = {
                "always_compensation": COMPENSATION.value,
                "always_retry": RETRY.value,
                "state_only_nearest_accepted": state_only["selected_skill"],
                "v2_fixed_coverage_aware": (
                    coverage_decision.selected_skill.value
                    if coverage_decision.action is MemoryApplicabilityAction.USE_VERIFIED_EPISODE
                    and coverage_decision.selected_skill
                    else None
                ),
                "frozen_single_feature_selector": single.value,
                "deterministic_action_conditional": (
                    acr.selected_skill.value if acr.selected_skill else None
                ),
            }
            predecision = {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "episode_id": episode_id,
                "seed": seed,
                "evidence_id": query.evidence_id,
                "pre_execution_timestamp_ns": predecision_timestamp,
                "memory_cutoff_episode_id": episode_id,
                "maximum_history_episode_id": max(pack.standardization_episode_ids, default=None),
                "development_counterfactual_history": True,
                "action_conditional_evidence_pack": pack.to_dict(),
                "action_conditional_decision": acr.to_dict(),
                "state_only_decision": state_only,
                "v2_coverage_decision": {
                    "action": coverage_decision.action.value,
                    "reason": coverage_decision.reason,
                    "selected_skill": (
                        coverage_decision.selected_skill.value if coverage_decision.selected_skill else None
                    ),
                    "retrieved_record_ids": list(coverage_decision.retrieved_record_ids),
                    "nearest_distance": coverage_decision.nearest_distance,
                    "coverage_radius": coverage_decision.coverage_radius,
                },
                "method_selections": methods,
            }
            validate_no_oracle_evidence(predecision)
            _append_jsonl(run_dir / "pre_execution_decisions.jsonl", predecision)

            outcomes: dict[InterventionSkill, tuple[Any, dict[str, Any]]] = {}
            evaluator_steps = initial.steps + probe_steps
            for skill in (COMPENSATION, RETRY):
                result, execution = _run_verification(
                    seed=seed,
                    fault=fault,
                    skill=skill,
                    probe_context=probe_context,
                    recovery_config=recovery_config,
                    perturbation_seed=int(unit["paired_verification_seed"]),
                    max_steps=int(config["budget"]["fresh_verification_max_steps_per_candidate"]),
                    initial_distance=initial.final_object_goal_distance,
                )
                outcome_timestamp = time.perf_counter_ns()
                if outcome_timestamp <= predecision_timestamp:
                    chronology_violations += 1
                    raise RuntimeError("candidate outcome preceded persisted prediction")
                outcomes[skill] = (result, execution)
                evaluator_steps += result.steps
                candidate_rows.append({
                    **base,
                    "candidate_id": skill.value,
                    "verification_status": execution["verification_status"],
                    "verification_success": result.success,
                    "verification_steps": result.steps,
                    "final_object_goal_distance": result.final_object_goal_distance,
                    "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance,
                    "paired_verification_seed": int(unit["paired_verification_seed"]),
                    "outcome_timestamp_ns": outcome_timestamp,
                })
            if evaluator_steps > int(config["budget"]["evaluator_paired_collection_max_steps"]):
                budget_violations += 1
                raise RuntimeError("ACR evaluator collection exceeded budget")
            memory_append_timestamp = time.perf_counter_ns()
            for skill in (COMPENSATION, RETRY):
                result, execution = outcomes[skill]
                prediction = acr.predictions[skill]
                item = ActionOutcomeRecord(
                    schema_version=1,
                    record_id=f"acr_episode{episode_id:03d}_{skill.value.lower()}",
                    source_episode_id=episode_id,
                    available_from_episode_id=episode_id + 1,
                    source_run_id=manifest["experiment_run_id"],
                    source_manifest_id=manifest["manifest_id"],
                    source_git_commit=manifest["source_git_commit"],
                    evidence_signature=query,
                    intervention_skill=skill,
                    predicted_status=prediction.predicted_status,
                    predicted_progress=prediction.predicted_progress,
                    observed_status=execution["verification_status"],
                    observed_progress=initial.final_object_goal_distance - result.final_object_goal_distance,
                    final_object_goal_distance=result.final_object_goal_distance,
                    verification_steps=result.steps,
                    interaction_cost=initial.steps + probe_steps + result.steps,
                    probe_used=True,
                    record_origin=ActionRecordOrigin.DEVELOPMENT_COUNTERFACTUAL,
                    operational_retrieval_eligible=False,
                )
                memory.record(item)
                _append_jsonl(run_dir / "action_outcomes.jsonl", {
                    **item.to_dict(),
                    "memory_append_timestamp_ns": memory_append_timestamp,
                })
            case_rows.append({
                **base,
                "condition_id_oracle": fault.condition_id,
                "paired_comparable": True,
                "probe_steps": probe_steps,
                "evaluator_collection_steps": evaluator_steps,
                **{f"selection_{name}": selection for name, selection in methods.items()},
            })
            _write_csv(run_dir / "case_results.csv", case_rows)
            _write_csv(run_dir / "candidate_results.csv", candidate_rows)
            print(f"episode={episode_id} seed={seed} condition={fault.condition_id} operational=paired")

        condition_counts = Counter(row["condition_id_oracle"] for row in case_rows)
        operational = [row for row in case_rows if bool(row["decision_required"])]
        summary = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "initial_units": len(case_rows),
            "condition_initial_unit_counts_oracle": dict(sorted(condition_counts.items())),
            "operational_cases": len(operational),
            "paired_comparable_cases": sum(bool(row["paired_comparable"]) for row in operational),
            "chronology_violations": chronology_violations,
            "oracle_leakage_events": 0,
            "budget_violations": budget_violations,
            "api_calls": 0,
            "rendering": False,
            "claim_scope": "development paired counterfactual feasibility only",
        }
        _write_json(run_dir / "collection_summary.json", summary)
        _write_json(status_path, {"status": "COMPLETED", **summary})
        print(f"run: {run_dir}")
        print(f"summary: {run_dir / 'collection_summary.json'}")
        return 0
    except Exception as exc:
        if status_path is not None and manifest is not None:
            _write_json(status_path, {
                "status": "FAILED",
                "manifest_id": manifest["manifest_id"],
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
