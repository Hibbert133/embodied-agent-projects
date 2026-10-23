"""Collect the frozen within-fault_05 ACR retry-utility replication."""

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
from scripts.run_probemem_v2_smoke import _append_jsonl, _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.probemem import InterventionApplicabilitySignature, InterventionSkill  # noqa: E402
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


def _validate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"]:
        raise ValueError("replication manifest path differs from run ID")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("HEAD differs from immutable replication manifest")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("replication execution requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("replication config differs from manifest")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"immutable replication input changed: {relative}")
    if len(manifest["population_units"]) != 100:
        raise ValueError("replication manifest requires exactly 100 units")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    return manifest, config


def _load_registered_inputs(config: dict[str, Any]) -> tuple[Any, RecoveryPolicyConfig]:
    noise_std = float(
        json.loads((ROOT / config["noise_selection"]).read_text(encoding="utf-8"))["noise_std"]
    )
    fault = {item.condition_id: item for item in get_conditions(noise_std)}["fault_05"]
    recovery = RecoveryPolicyConfig.from_mapping(
        json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
    )
    return fault, recovery


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
            raise FileExistsError("replication run already started")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        fault, recovery_config = _load_registered_inputs(config)
        case_rows: list[dict[str, Any]] = []
        candidate_rows: list[dict[str, Any]] = []
        budget_violations = 0

        for unit in manifest["population_units"]:
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
                _read_jsonl(trajectory), evidence_id=f"retry_rep_episode{episode_id:03d}_attempt0",
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
                "paired_comparable": False,
                "probe_steps": 0,
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
                budget_violations += 1
                raise RuntimeError("registered probe exceeded replication budget")
            probe_evidence = {
                **state.to_dict(),
                "evidence_id": f"retry_rep_episode{episode_id:03d}_attempt1",
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
            for skill in (COMPENSATION, RETRY):
                result, execution = _run_verification(
                    seed=seed, fault=fault, skill=skill, probe_context=probe_context,
                    recovery_config=recovery_config,
                    perturbation_seed=int(unit["paired_verification_seed"]),
                    max_steps=int(config["budget"]["fresh_verification_max_steps_per_candidate"]),
                    initial_distance=initial.final_object_goal_distance,
                )
                outcome_timestamp = time.perf_counter_ns()
                if outcome_timestamp <= evidence_timestamp:
                    raise RuntimeError("candidate outcome preceded evidence persistence")
                evaluator_steps += result.steps
                candidate_rows.append({
                    **base,
                    "paired_comparable": True,
                    "probe_steps": probe_steps,
                    "evaluator_collection_steps": evaluator_steps,
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
                raise RuntimeError("replication paired collection exceeded budget")
            case_rows.append({
                **base,
                "paired_comparable": True,
                "probe_steps": probe_steps,
                "evaluator_collection_steps": evaluator_steps,
            })
            _write_csv(run_dir / "case_results.csv", case_rows)
            _write_csv(run_dir / "candidate_results.csv", candidate_rows)
            print(f"episode={episode_id} seed={seed} operational=paired")

        summary = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "initial_units": len(case_rows),
            "operational_cases": sum(bool(row["decision_required"]) for row in case_rows),
            "paired_comparable_cases": sum(bool(row["paired_comparable"]) for row in case_rows),
            "condition_id_oracle": "fault_05",
            "chronology_violations": 0,
            "oracle_leakage_events": 0,
            "budget_violations": budget_violations,
            "api_calls": 0,
            "claim_scope": config["claim_scope"],
        }
        _write_json(run_dir / "collection_summary.json", summary)
        _write_json(status_path, {"status": "COMPLETED", **summary})
        print(f"run: {run_dir}")
        return 0
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
