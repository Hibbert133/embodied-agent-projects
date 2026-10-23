"""Collect repeated paired outcomes for ACR utility-identifiability analysis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import get_conditions  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.probemem import InterventionApplicabilitySignature, InterventionSkill  # noqa: E402
from src.planner.evidence_grounded import first_registered_probe_context, select_grounded_intervention  # noqa: E402
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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _validate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"]:
        raise ValueError("utility-stability manifest path differs from run ID")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("HEAD differs from immutable utility-stability manifest")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("utility-stability execution requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("utility-stability config differs from manifest")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"immutable utility-stability input changed: {relative}")
    if len(manifest["population_units"]) != 100:
        raise ValueError("utility-stability manifest requires 100 scannable units")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _load_inputs(config: dict[str, Any]) -> tuple[Any, RecoveryPolicyConfig]:
    noise_std = float(json.loads((ROOT / config["noise_selection"]).read_text(encoding="utf-8"))["noise_std"])
    fault = {item.condition_id: item for item in get_conditions(noise_std)}["fault_05"]
    recovery = RecoveryPolicyConfig.from_mapping(
        json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
    )
    return fault, recovery


def _compensation_is_constructible(
    *, seed: int, probe_context: dict[str, Any], recovery_config: RecoveryPolicyConfig
) -> bool:
    plan = select_grounded_intervention(
        plan_id=f"utility_stability_eligibility_seed{seed}",
        evidence_id=f"utility_stability_probe_seed{seed}",
        mechanism_belief="stable_bias",
        correction_context=first_registered_probe_context(probe_context),
        recovery_config=recovery_config,
        evidence_source="registered_probe",
    )
    return bool(plan.requires_fresh_verification)


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
            raise FileExistsError("utility-stability run already started")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        fault, recovery_config = _load_inputs(config)
        case_rows: list[dict[str, Any]] = []
        candidate_rows: list[dict[str, Any]] = []
        operational = 0
        integrity = {"chronology_violations": 0, "oracle_leakage_events": 0, "budget_violations": 0}

        for unit in manifest["population_units"]:
            if operational >= int(config["stopping_rule"]["target_operational_cases"]):
                break
            episode_id, seed = int(unit["episode_id"]), int(unit["environment_seed"])
            trajectory = run_dir / "initial_trajectories" / f"episode{episode_id:03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, episode_id=episode_id,
                    max_steps=int(config["budget"]["initial_rollout_max_steps"]),
                    perturbation=fault.build(),
                    perturbation_seed=int(unit["initial_perturbation_seed"]),
                    agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory), evidence_id=f"utility_stability_episode{episode_id:03d}_attempt0",
                source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            )
            base = {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
                "episode_id": episode_id,
                "seed": seed,
                "condition_id_oracle": "fault_05",
                "initial_success": initial.success,
                "decision_required": state.decision_required,
                "initial_steps": initial.steps,
                "initial_final_object_goal_distance": initial.final_object_goal_distance,
                "probe_steps": 0,
                "paired_candidate_eligible": False,
                "ineligibility_reason": "initial_success" if initial.success else "not_yet_evaluated",
                "paired_repetitions": 0,
                "evaluator_collection_steps": initial.steps,
            }
            if not state.decision_required:
                case_rows.append(base)
                _write_csv(run_dir / "case_results.csv", case_rows)
                print(f"episode={episode_id} seed={seed} initial=success")
                continue

            probe_context = _probe_context(fault, seed, config, int(unit["diagnostic_probe_seed"]))
            probe_steps = int(probe_context["probe_environment_steps"])
            if probe_steps > int(config["budget"]["registered_probe_max_steps"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("registered probe exceeded utility-stability budget")
            if not _compensation_is_constructible(
                seed=seed, probe_context=probe_context, recovery_config=recovery_config
            ):
                case_rows.append({
                    **base,
                    "probe_steps": probe_steps,
                    "paired_candidate_eligible": False,
                    "ineligibility_reason": "bounded_compensation_not_constructible",
                    "evaluator_collection_steps": initial.steps + probe_steps,
                })
                _write_csv(run_dir / "case_results.csv", case_rows)
                print(f"episode={episode_id} seed={seed} initial=failure candidate=ineligible")
                continue
            operational += 1
            probe_evidence = {
                **state.to_dict(),
                "evidence_id": f"utility_stability_episode{episode_id:03d}_attempt1",
                "attempt_id": 1,
                "source": EvidenceSource.DIAGNOSTIC_PROBE.value,
                "parent_evidence_ids": [state.evidence_id],
                "registered_probe_evidence": probe_context,
            }
            validate_no_oracle_evidence(probe_evidence)
            signature = InterventionApplicabilitySignature.from_agent_evidence(probe_evidence)
            evidence_timestamp = time.perf_counter_ns()
            _append_jsonl(run_dir / "evidence_signatures.jsonl", {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "episode_id": episode_id,
                "seed": seed,
                "evidence_timestamp_ns": evidence_timestamp,
                "evidence_signature": signature.to_dict(),
                "candidate_outcomes_available": False,
            })

            evaluator_steps = initial.steps + probe_steps
            paired_seeds = [int(value) for value in unit["paired_verification_seeds"]]
            if len(paired_seeds) != int(config["verification_repetitions"]) or len(set(paired_seeds)) != len(paired_seeds):
                raise ValueError("paired verification realization seeds are invalid")
            for repetition, paired_seed in enumerate(paired_seeds, start=1):
                for skill in (COMPENSATION, RETRY):
                    result, execution = _run_verification(
                        seed=seed, fault=fault, skill=skill, probe_context=probe_context,
                        recovery_config=recovery_config, perturbation_seed=paired_seed,
                        max_steps=int(config["budget"]["fresh_verification_max_steps_per_candidate"]),
                        initial_distance=initial.final_object_goal_distance,
                    )
                    outcome_timestamp = time.perf_counter_ns()
                    if outcome_timestamp <= evidence_timestamp:
                        integrity["chronology_violations"] += 1
                        raise RuntimeError("candidate outcome preceded evidence persistence")
                    evaluator_steps += result.steps
                    candidate_rows.append({
                        **base,
                        "probe_steps": probe_steps,
                        "paired_candidate_eligible": True,
                        "ineligibility_reason": "",
                        "evaluator_collection_steps": evaluator_steps,
                        "realization_index": repetition,
                        "candidate_id": skill.value,
                        "paired_verification_seed": paired_seed,
                        "verification_status": execution["verification_status"],
                        "verification_success": result.success,
                        "verification_steps": result.steps,
                        "final_object_goal_distance": result.final_object_goal_distance,
                        "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance,
                        "outcome_timestamp_ns": outcome_timestamp,
                    })
                    _write_csv(run_dir / "candidate_results.csv", candidate_rows)
            if evaluator_steps > int(config["budget"]["evaluator_collection_max_steps_per_operational_case"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("repeated paired collection exceeded registered budget")
            case_rows.append({
                **base,
                "probe_steps": probe_steps,
                "paired_candidate_eligible": True,
                "ineligibility_reason": "",
                "paired_repetitions": len(paired_seeds),
                "evaluator_collection_steps": evaluator_steps,
            })
            _write_csv(run_dir / "case_results.csv", case_rows)
            print(f"episode={episode_id} seed={seed} operational={operational}/20 repetitions={len(paired_seeds)}")

        summary = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "initial_units_scanned": len(case_rows),
            "operational_cases": operational,
            "candidate_rollouts": len(candidate_rows),
            "stopping_rule_reads_candidate_outcomes": False,
            **integrity,
            "api_calls": 0,
            "claim_scope": config["claim_scope"],
        }
        completed = operational >= int(config["stopping_rule"]["target_operational_cases"])
        _write_json(run_dir / "collection_summary.json", summary)
        _write_json(status_path, {"status": "COMPLETED" if completed else "INCOMPLETE_POPULATION", **summary})
        print(f"run: {run_dir}")
        return 0 if completed else 2
    except Exception as exc:
        if status_path is not None and manifest is not None:
            _write_json(status_path, {
                "status": "FAILED", "manifest_id": manifest["manifest_id"],
                "error_type": type(exc).__name__, "error": str(exc),
            })
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
