"""Run the one-shot frozen second-verification validation collection."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import (  # noqa: E402
    COMPENSATION, RETRY, _compensation_is_constructible, _git, _load_inputs,
    _sha256, _write_csv, _write_json,
)
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.probemem import InterventionApplicabilitySignature  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _validate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.name != "immutable_manifest.json" or path.parent.name != manifest["experiment_run_id"]:
        raise ValueError("validation manifest path differs from immutable run ID")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("HEAD differs from immutable validation manifest")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("validation requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("validation config differs from manifest")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"immutable validation input changed: {relative}")
    seeds = [int(unit["environment_seed"]) for unit in manifest["population_units"]]
    if seeds != [*range(3050, 3100), *range(3200, 3300)]:
        raise ValueError("manifest population differs from frozen validation order")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest: dict[str, Any] | None = None
    status_path: Path | None = None
    try:
        manifest, config = _validate_manifest(args.manifest.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("validation run cannot be started or replaced twice")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        fault, recovery_config = _load_inputs(config)
        case_rows: list[dict[str, Any]] = []
        candidate_rows: list[dict[str, Any]] = []
        eligible = 0
        second_decisions = 0
        ineligible_failures = 0
        integrity = {
            "chronology_violations": 0, "oracle_leakage_events": 0,
            "budget_violations": 0, "random_namespace_violations": 0,
            "manifest_mismatches": 0,
        }
        budget = config["budget"]
        for unit in manifest["population_units"]:
            episode_id, seed = int(unit["episode_id"]), int(unit["environment_seed"])
            streams = {
                int(unit["initial_perturbation_seed"]), int(unit["diagnostic_probe_seed"]),
                int(unit["first_verification_seed"]), int(unit["paired_second_verification_seed"]),
            }
            if len(streams) != 4:
                integrity["random_namespace_violations"] += 1
                raise RuntimeError("validation random streams are not independent")
            trajectory = run_dir / "initial_trajectories" / f"episode{episode_id:03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, episode_id=episode_id,
                    max_steps=int(budget["initial_rollout_max_steps"]), perturbation=fault.build(),
                    perturbation_seed=int(unit["initial_perturbation_seed"]), agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory), evidence_id=f"validation_episode{episode_id:03d}_attempt0",
                source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            )
            base = {
                "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"], "episode_id": episode_id, "seed": seed,
                "condition_id_oracle": config["registered_condition"], "initial_success": initial.success,
                "decision_required": state.decision_required, "initial_steps": initial.steps,
                "initial_final_object_goal_distance": initial.final_object_goal_distance,
                "probe_steps": 0, "eligible_first_attempt": False, "first_attempt_index": 0,
                "first_verification_status": "NOT_EXECUTED", "first_verification_steps": 0,
                "first_final_object_goal_distance": "", "first_observed_progress": "",
                "second_decision_required": False, "second_decision_index": 0,
                "ineligibility_reason": "initial_success" if initial.success else "not_yet_evaluated",
                "online_steps_before_optional_second": initial.steps,
            }
            if not state.decision_required:
                case_rows.append(base)
                _write_csv(run_dir / "case_results.csv", case_rows)
                print(f"episode={episode_id}/150 seed={seed} initial=success", flush=True)
                continue
            probe_context = _probe_context(fault, seed, config, int(unit["diagnostic_probe_seed"]))
            probe_steps = int(probe_context["probe_environment_steps"])
            if probe_steps > int(budget["registered_probe_max_steps"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("registered probe exceeded validation budget")
            if not _compensation_is_constructible(seed=seed, probe_context=probe_context, recovery_config=recovery_config):
                ineligible_failures += 1
                case_rows.append({**base, "probe_steps": probe_steps,
                                  "ineligibility_reason": "bounded_compensation_not_constructible",
                                  "online_steps_before_optional_second": initial.steps + probe_steps})
                _write_csv(run_dir / "case_results.csv", case_rows)
                print(f"episode={episode_id}/150 seed={seed} candidate=ineligible", flush=True)
                continue
            eligible += 1
            probe_evidence = {
                **state.to_dict(), "evidence_id": f"validation_episode{episode_id:03d}_attempt1",
                "attempt_id": 1, "source": EvidenceSource.DIAGNOSTIC_PROBE.value,
                "parent_evidence_ids": [state.evidence_id], "registered_probe_evidence": probe_context,
            }
            validate_no_oracle_evidence(probe_evidence)
            signature = InterventionApplicabilitySignature.from_agent_evidence(probe_evidence)
            evidence_timestamp = time.perf_counter_ns()
            first_result, first_execution = _run_verification(
                seed=seed, fault=fault, skill=RETRY, probe_context=probe_context,
                recovery_config=recovery_config, perturbation_seed=int(unit["first_verification_seed"]),
                max_steps=int(budget["first_verification_max_steps"]),
                initial_distance=initial.final_object_goal_distance,
            )
            first_timestamp = time.perf_counter_ns()
            if first_timestamp <= evidence_timestamp:
                integrity["chronology_violations"] += 1
                raise RuntimeError("first verification preceded persisted decision evidence")
            first_status = str(first_execution["verification_status"])
            online_before_second = initial.steps + probe_steps + first_result.steps
            if online_before_second > int(budget["online_max_steps_per_case"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("first verification exceeded online budget")
            first_base = {
                **base, "probe_steps": probe_steps, "eligible_first_attempt": True,
                "first_attempt_index": eligible, "first_verification_status": first_status,
                "first_verification_steps": first_result.steps,
                "first_final_object_goal_distance": first_result.final_object_goal_distance,
                "first_observed_progress": initial.final_object_goal_distance - first_result.final_object_goal_distance,
                "ineligibility_reason": "", "online_steps_before_optional_second": online_before_second,
            }
            _append_jsonl(run_dir / "first_verification_evidence.jsonl", {
                "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
                "episode_id": episode_id, "seed": seed, "first_attempt_index": eligible,
                "evidence_timestamp_ns": evidence_timestamp, "evidence_signature": signature.to_dict(),
                "first_verification_timestamp_ns": first_timestamp, "first_verification_status": first_status,
                "second_candidate_outcomes_available": False,
            })
            if first_status == "ACCEPTED":
                case_rows.append(first_base)
                _write_csv(run_dir / "case_results.csv", case_rows)
                print(f"episode={episode_id}/150 seed={seed} first=ACCEPTED stop", flush=True)
                continue
            second_decisions += 1
            paired_seed = int(unit["paired_second_verification_seed"])
            evaluator_steps = online_before_second
            for skill in (COMPENSATION, RETRY):
                result, execution = _run_verification(
                    seed=seed, fault=fault, skill=skill, probe_context=probe_context,
                    recovery_config=recovery_config, perturbation_seed=paired_seed,
                    max_steps=int(budget["second_verification_max_steps"]),
                    initial_distance=initial.final_object_goal_distance,
                )
                outcome_timestamp = time.perf_counter_ns()
                if outcome_timestamp <= first_timestamp:
                    integrity["chronology_violations"] += 1
                    raise RuntimeError("second outcome preceded first verification")
                evaluator_steps += result.steps
                candidate_rows.append({
                    **first_base, "second_decision_required": True,
                    "second_decision_index": second_decisions, "candidate_id": skill.value,
                    "paired_second_verification_seed": paired_seed,
                    "verification_status": execution["verification_status"],
                    "verification_success": result.success, "verification_steps": result.steps,
                    "final_object_goal_distance": result.final_object_goal_distance,
                    "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance,
                    "outcome_timestamp_ns": outcome_timestamp,
                })
            if evaluator_steps > int(budget["evaluator_paired_collection_max_steps_per_case"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("paired collection exceeded evaluator budget")
            case_rows.append({**first_base, "second_decision_required": True,
                              "second_decision_index": second_decisions})
            _write_csv(run_dir / "case_results.csv", case_rows)
            _write_csv(run_dir / "second_candidate_results.csv", candidate_rows)
            print(f"episode={episode_id}/150 seed={seed} first={first_status} second={second_decisions}", flush=True)
        population_complete = (
            len(case_rows) == int(config["population"]["expected_initial_units"])
            and eligible >= int(config["population"]["eligible_first_attempts_minimum"])
            and second_decisions >= int(config["population"]["second_decision_cases_minimum"])
        )
        summary = {
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"], "initial_units_scanned": len(case_rows),
            "eligible_first_attempts": eligible, "first_verification_accepted": eligible - second_decisions,
            "second_decision_cases": second_decisions, "ineligible_failures": ineligible_failures,
            "second_candidate_rollouts": len(candidate_rows), "ran_all_frozen_units": len(case_rows) == 150,
            "heldout_seeds_executed": 0, "stopping_rule_reads_second_outcomes": False,
            **integrity, "api_calls": 0, "claim_scope": config["claim_scope"],
        }
        status = "COMPLETED" if population_complete and not any(integrity.values()) else "INCOMPLETE_FOR_VALIDATION"
        _write_json(run_dir / "collection_summary.json", summary)
        _write_json(status_path, {"status": status, **summary})
        print(f"run: {run_dir}", flush=True)
        return 0 if status == "COMPLETED" else 2
    except Exception as exc:
        if status_path is not None and manifest is not None:
            _write_json(status_path, {"status": "FAILED", "manifest_id": manifest["manifest_id"],
                                      "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
