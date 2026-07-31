"""Run matched compensation/retry verification on a chronological dev stream."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
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
    _seed,
    _write_csv,
)
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.evaluation.intervention_utility import (  # noqa: E402
    CandidateUtilityOutcome,
    best_candidate_ids,
)
from src.probemem import (  # noqa: E402
    InterventionApplicabilitySignature,
    InterventionSkill,
)
from src.reasoning import (  # noqa: E402
    EvidenceSource,
    build_structured_evidence_state,
    validate_no_oracle_evidence,
)
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
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
        raise ValueError("manifest directory does not match experiment_run_id")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("current HEAD differs from immutable paired manifest")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("paired execution requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("paired utility config differs from its manifest")
    for relative, expected in manifest["implementation_sha256"].items():
        if _sha256(ROOT / relative) != expected:
            raise RuntimeError(f"implementation differs from manifest: {relative}")
    for relative, expected in manifest["input_sha256"].items():
        if _sha256(ROOT / relative) != expected:
            raise RuntimeError(f"registered input differs from manifest: {relative}")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _candidate_outcome(candidate_id: str, result: Any, execution: dict[str, Any]) -> CandidateUtilityOutcome:
    return CandidateUtilityOutcome.from_mapping(
        {
            "candidate_id": candidate_id,
            "verification_status": execution["verification_status"],
            "verification_steps": result.steps,
            "final_object_goal_distance": result.final_object_goal_distance,
        }
    )


def validate_stopping_rule(config: dict[str, Any]) -> int:
    """Return the label-blind coverage target, or zero for a fixed stream."""
    stopping_rule = config.get("stopping_rule")
    if stopping_rule is None:
        return 0
    seed_start, seed_stop = (int(item) for item in config["seed_range"])
    target_pairs = int(stopping_rule["target_paired_operational_units"])
    maximum_units = int(stopping_rule["maximum_initial_units"])
    if (
        target_pairs <= 0
        or maximum_units != seed_stop - seed_start + 1
        or bool(stopping_rule["may_read_candidate_outcome"])
        or bool(stopping_rule["may_read_winner_label"])
        or stopping_rule["stop_signal"] != "paired candidate executability only"
    ):
        raise ValueError("invalid label-blind paired coverage stopping rule")
    return target_pairs


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
            raise FileExistsError("paired utility run directory was already executed")
        _write_json(
            status_path,
            {"status": "RUNNING", "manifest_id": manifest["manifest_id"]},
        )
        noise_std = float(
            json.loads((ROOT / config["noise_selection"]).read_text(encoding="utf-8"))[
                "noise_std"
            ]
        )
        conditions = {item.condition_id: item for item in get_conditions(noise_std)}
        cycle = tuple(str(item) for item in config["condition_cycle"])
        candidates = tuple(InterventionSkill(item) for item in config["candidates"])
        if candidates != (
            InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
            InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY,
        ):
            raise ValueError("paired v1 requires exactly compensation and retry")
        recovery_config = RecoveryPolicyConfig.from_mapping(
            json.loads(
                (ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8")
            )
        )
        namespaces = config["random_seed_namespaces"]
        budget = config["budget"]
        seed_start, seed_stop = (int(item) for item in config["seed_range"])
        target_pairs = validate_stopping_rule(config)
        case_rows: list[dict[str, Any]] = []
        candidate_rows: list[dict[str, Any]] = []

        for index, seed in enumerate(range(seed_start, seed_stop + 1)):
            if target_pairs and sum(
                bool(row["paired_comparable"]) for row in case_rows
            ) >= target_pairs:
                break
            episode_id = index + 1
            fault = conditions[cycle[index % len(cycle)]]
            trajectory = (
                run_dir
                / "initial_trajectories"
                / f"episode{episode_id:03d}_seed{seed}.jsonl"
            )
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            initial_seed = _seed(seed, int(namespaces["initial_rollout"]))
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env,
                    create_push_policy(),
                    seed=seed,
                    episode_id=episode_id,
                    max_steps=int(budget["initial_rollout_max_steps"]),
                    perturbation=fault.build(),
                    perturbation_seed=initial_seed,
                    agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory),
                evidence_id=f"paired_utility_episode{episode_id:03d}_attempt0",
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
                case_rows.append(
                    {
                        **base,
                        "condition_id_oracle": fault.condition_id,
                        "paired_comparable": False,
                        "winner_candidate_ids_oracle": "",
                        "registered_probe_steps": 0,
                        "evaluator_collection_steps": initial.steps,
                    }
                )
                _append_jsonl(
                    run_dir / "agent_evidence.jsonl",
                    {
                        **{key: base[key] for key in (
                            "experiment_run_id", "manifest_id", "episode_id", "seed",
                            "decision_required", "initial_success",
                        )},
                        "structured_evidence_state": state.to_dict(),
                    },
                )
                _append_jsonl(
                    run_dir / "oracle_audit.jsonl",
                    {
                        **base,
                        "condition_id_oracle": fault.condition_id,
                        "perturbation_type_oracle": fault.kind,
                        "perturbation_parameters_oracle": fault.parameters,
                    },
                )
                _write_csv(run_dir / "case_results.csv", case_rows)
                print(f"episode={episode_id} seed={seed} initial=success")
                continue

            probe_context = _probe_context(
                fault,
                seed,
                config,
                _seed(seed, int(namespaces["diagnostic_probe"])),
            )
            probe_steps = int(probe_context["probe_environment_steps"])
            if probe_steps > int(budget["registered_probe_max_steps"]):
                raise RuntimeError("registered probe exceeded paired protocol budget")
            probe_evidence = {
                **state.to_dict(),
                "evidence_id": f"paired_utility_episode{episode_id:03d}_attempt1",
                "attempt_id": 1,
                "source": EvidenceSource.DIAGNOSTIC_PROBE.value,
                "parent_evidence_ids": [state.evidence_id],
                "registered_probe_evidence": probe_context,
            }
            validate_no_oracle_evidence(probe_evidence)
            signature = InterventionApplicabilitySignature.from_agent_evidence(
                probe_evidence
            )
            agent_record = {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "episode_id": episode_id,
                "seed": seed,
                "decision_required": True,
                "applicability_signature": signature.to_dict(),
                "structured_evidence_state": probe_evidence,
            }
            validate_no_oracle_evidence(agent_record)
            _append_jsonl(run_dir / "agent_evidence.jsonl", agent_record)

            shared_verification_seed = _seed(
                seed, int(namespaces["shared_paired_verification"])
            )
            outcomes: list[CandidateUtilityOutcome] = []
            oracle_outcomes: dict[str, Any] = {}
            verification_steps = 0
            for skill in candidates:
                try:
                    result, execution = _run_verification(
                        seed=seed,
                        fault=fault,
                        skill=skill,
                        probe_context=probe_context,
                        recovery_config=recovery_config,
                        perturbation_seed=shared_verification_seed,
                        max_steps=int(budget["fresh_verification_max_steps_per_candidate"]),
                        initial_distance=initial.final_object_goal_distance,
                    )
                    outcome = _candidate_outcome(skill.value, result, execution)
                    outcomes.append(outcome)
                    verification_steps += result.steps
                    row = {
                        **base,
                        "candidate_id": skill.value,
                        "verification_status": execution["verification_status"],
                        "verification_success": result.success,
                        "verification_steps": result.steps,
                        "final_object_goal_distance": result.final_object_goal_distance,
                        "goal_distance_change": (
                            initial.final_object_goal_distance
                            - result.final_object_goal_distance
                        ),
                        "shared_verification_perturbation_seed": shared_verification_seed,
                    }
                    candidate_rows.append(row)
                    oracle_outcomes[skill.value] = {
                        **row,
                        "host_execution": execution,
                    }
                except ValueError as exc:
                    candidate_rows.append(
                        {
                            **base,
                            "candidate_id": skill.value,
                            "verification_status": "NOT_RUN",
                            "verification_success": False,
                            "verification_steps": 0,
                            "final_object_goal_distance": "",
                            "goal_distance_change": "",
                            "shared_verification_perturbation_seed": shared_verification_seed,
                            "host_rejection": str(exc),
                        }
                    )
                    oracle_outcomes[skill.value] = {"host_rejection": str(exc)}

            paired = len(outcomes) == 2
            winners = best_candidate_ids(outcomes) if paired else ()
            evaluator_steps = initial.steps + probe_steps + verification_steps
            if evaluator_steps > int(budget["evaluator_paired_collection_max_steps"]):
                raise RuntimeError("paired evaluator collection exceeded its budget")
            case_rows.append(
                {
                    **base,
                    "condition_id_oracle": fault.condition_id,
                    "paired_comparable": paired,
                    "winner_candidate_ids_oracle": "|".join(winners),
                    "registered_probe_steps": probe_steps,
                    "evaluator_collection_steps": evaluator_steps,
                }
            )
            _append_jsonl(
                run_dir / "oracle_audit.jsonl",
                {
                    **base,
                    "condition_id_oracle": fault.condition_id,
                    "perturbation_type_oracle": fault.kind,
                    "perturbation_parameters_oracle": fault.parameters,
                    "winner_candidate_ids_oracle": list(winners),
                    "candidate_outcomes_oracle": oracle_outcomes,
                },
            )
            _write_csv(run_dir / "case_results.csv", case_rows)
            _write_csv(run_dir / "candidate_results.csv", candidate_rows)
            print(
                f"episode={episode_id} seed={seed} condition={fault.condition_id} "
                f"winner={','.join(winners) if winners else 'UNAVAILABLE'}"
            )

        operational = [row for row in case_rows if bool(row["decision_required"])]
        comparable = [row for row in operational if bool(row["paired_comparable"])]
        winner_counts = Counter(
            row["winner_candidate_ids_oracle"] for row in comparable
        )
        candidate_counts = Counter(
            (row["candidate_id"], row["verification_status"])
            for row in candidate_rows
            if row["verification_status"] != "NOT_RUN"
        )
        summary = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "full_collection_units": len(case_rows),
            "operational_units": len(operational),
            "paired_comparable_units": len(comparable),
            "winner_counts_oracle": dict(sorted(winner_counts.items())),
            "candidate_verification_counts": {
                f"{candidate}:{status}": count
                for (candidate, status), count in sorted(candidate_counts.items())
            },
            "api_calls": 0,
            "rendering": False,
            "actionable_memory_writes": 0,
            "principles_generated": 0,
            "target_paired_operational_units": target_pairs or None,
            "coverage_target_reached": (
                len(comparable) >= target_pairs if target_pairs else None
            ),
            "claim_scope": "development paired action-utility collection only",
        }
        _write_json(run_dir / "summary.json", summary)
        _write_json(
            status_path,
            {
                "status": "COMPLETED",
                "manifest_id": manifest["manifest_id"],
                "full_collection_units": len(case_rows),
                "operational_units": len(operational),
                "paired_comparable_units": len(comparable),
                "target_paired_operational_units": target_pairs or None,
                "coverage_target_reached": (
                    len(comparable) >= target_pairs if target_pairs else None
                ),
            },
        )
        print(f"run: {run_dir}")
        print(f"summary: {run_dir / 'summary.json'}")
        return 0
    except Exception as exc:
        if status_path is not None and manifest is not None:
            _write_json(
                status_path,
                {
                    "status": "FAILED",
                    "manifest_id": manifest["manifest_id"],
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
