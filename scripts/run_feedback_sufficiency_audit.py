"""Collect repeated first feedback and paired second outcomes."""

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
    _compensation_is_constructible, _git, _load_inputs, _sha256, _write_csv, _write_json,
)
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.probemem import InterventionApplicabilitySignature, InterventionSkill  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def _validate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.name != "immutable_manifest.json" or path.parent.name != manifest["experiment_run_id"]:
        raise ValueError("manifest path differs from run ID")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("HEAD differs from immutable manifest")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("execution requires clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("config differs from manifest")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"immutable input changed: {relative}")
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
            raise FileExistsError("audit run cannot be restarted or overwritten")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        fault, recovery = _load_inputs(config)
        budget = config["budget"]
        target = int(config["stopping_rule"]["target_eligible_initial_states"])
        cases: list[dict[str, Any]] = []
        branches: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        eligible = 0
        integrity = {"chronology_violations": 0, "oracle_leakage_events": 0, "budget_violations": 0, "random_namespace_violations": 0, "reset_violations": 0}
        for unit in manifest["population_units"]:
            if eligible >= target:
                break
            episode_id, seed = int(unit["episode_id"]), int(unit["environment_seed"])
            streams = [int(unit["initial_perturbation_seed"]), int(unit["diagnostic_probe_seed"]), *map(int, unit["first_verification_seeds"]), *map(int, unit["paired_second_verification_seeds"])]
            if len(streams) != len(set(streams)):
                integrity["random_namespace_violations"] += 1
                raise RuntimeError("random streams are not independent")
            trajectory = run_dir / "initial_trajectories" / f"episode{episode_id:03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(env, create_push_policy(), seed=seed, episode_id=episode_id,
                                      max_steps=int(budget["initial_rollout_max_steps"]), perturbation=fault.build(),
                                      perturbation_seed=int(unit["initial_perturbation_seed"]), agent_trajectory_path=trajectory)
            finally:
                env.close()
            state = build_structured_evidence_state(_read_jsonl(trajectory), evidence_id=f"feedback_episode{episode_id:03d}_attempt0", source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0)
            base = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "episode_id": episode_id, "seed": seed, "condition_id_oracle": "fault_05", "initial_success": initial.success, "initial_steps": initial.steps, "initial_final_object_goal_distance": initial.final_object_goal_distance, "probe_steps": 0, "eligible_state": False, "ineligibility_reason": "initial_success" if initial.success else "not_yet_evaluated", "eligible_state_index": 0, "realizations": 0, "evaluator_collection_steps": initial.steps}
            if not state.decision_required:
                cases.append(base); _write_csv(run_dir / "case_results.csv", cases)
                print(f"episode={episode_id} seed={seed} initial=success", flush=True); continue
            probe = _probe_context(fault, seed, config, int(unit["diagnostic_probe_seed"]))
            probe_steps = int(probe["probe_environment_steps"])
            if probe_steps > int(budget["registered_probe_max_steps"]):
                integrity["budget_violations"] += 1; raise RuntimeError("probe budget exceeded")
            if not _compensation_is_constructible(seed=seed, probe_context=probe, recovery_config=recovery):
                cases.append({**base, "probe_steps": probe_steps, "ineligibility_reason": "bounded_compensation_not_constructible", "evaluator_collection_steps": initial.steps + probe_steps}); _write_csv(run_dir / "case_results.csv", cases)
                print(f"episode={episode_id} seed={seed} candidate=ineligible", flush=True); continue
            eligible += 1
            probe_evidence = {**state.to_dict(), "evidence_id": f"feedback_episode{episode_id:03d}_attempt1", "attempt_id": 1, "source": EvidenceSource.DIAGNOSTIC_PROBE.value, "parent_evidence_ids": [state.evidence_id], "registered_probe_evidence": probe}
            validate_no_oracle_evidence(probe_evidence)
            signature = InterventionApplicabilitySignature.from_agent_evidence(probe_evidence)
            evidence_time = time.perf_counter_ns()
            _append_jsonl(run_dir / "evidence_signatures.jsonl", {"episode_id": episode_id, "seed": seed, "evidence_timestamp_ns": evidence_time, "evidence_signature": signature.to_dict(), "candidate_outcomes_available": False})
            evaluator_steps = initial.steps + probe_steps
            for realization, (first_seed, paired_seed) in enumerate(zip(unit["first_verification_seeds"], unit["paired_second_verification_seeds"]), start=1):
                first, first_exec = _run_verification(seed=seed, fault=fault, skill=RETRY, probe_context=probe, recovery_config=recovery, perturbation_seed=int(first_seed), max_steps=int(budget["verification_max_steps"]), initial_distance=initial.final_object_goal_distance)
                first_time = time.perf_counter_ns()
                if first_time <= evidence_time:
                    integrity["chronology_violations"] += 1; raise RuntimeError("first outcome preceded evidence")
                status = str(first_exec["verification_status"])
                observed_progress = initial.final_object_goal_distance - first.final_object_goal_distance
                branch = {**base, "probe_steps": probe_steps, "eligible_state": True, "ineligibility_reason": "", "eligible_state_index": eligible, "realization_index": realization, "first_verification_seed": int(first_seed), "first_verification_status": status, "first_verification_steps": first.steps, "first_final_object_goal_distance": first.final_object_goal_distance, "first_observed_progress": observed_progress, "paired_second_executed": status != "ACCEPTED", "paired_second_verification_seed": int(paired_seed)}
                branches.append(branch); evaluator_steps += first.steps
                if status != "ACCEPTED":
                    for skill in (COMPENSATION, RETRY):
                        result, execution = _run_verification(seed=seed, fault=fault, skill=skill, probe_context=probe, recovery_config=recovery, perturbation_seed=int(paired_seed), max_steps=int(budget["verification_max_steps"]), initial_distance=initial.final_object_goal_distance)
                        outcome_time = time.perf_counter_ns()
                        if outcome_time <= first_time:
                            integrity["chronology_violations"] += 1; raise RuntimeError("second outcome preceded first")
                        evaluator_steps += result.steps
                        candidates.append({**branch, "candidate_id": skill.value, "verification_status": execution["verification_status"], "verification_steps": result.steps, "final_object_goal_distance": result.final_object_goal_distance, "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance, "outcome_timestamp_ns": outcome_time})
                _write_csv(run_dir / "branch_results.csv", branches)
                _write_csv(run_dir / "second_candidate_results.csv", candidates)
            if evaluator_steps > int(budget["evaluator_collection_max_steps_per_state"]):
                integrity["budget_violations"] += 1; raise RuntimeError("evaluator budget exceeded")
            cases.append({**base, "probe_steps": probe_steps, "eligible_state": True, "ineligibility_reason": "", "eligible_state_index": eligible, "realizations": len(unit["first_verification_seeds"]), "evaluator_collection_steps": evaluator_steps})
            _write_csv(run_dir / "case_results.csv", cases)
            print(f"episode={episode_id} seed={seed} eligible={eligible}/{target}", flush=True)
        nonaccepted = sum(row["first_verification_status"] != "ACCEPTED" for row in branches)
        summary = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "initial_units_scanned": len(cases), "eligible_initial_states": eligible, "first_realization_branches": len(branches), "nonaccepted_first_branches": nonaccepted, "second_candidate_rollouts": len(candidates), **integrity, "api_calls": 0, "heldout_seeds_executed": 0}
        complete = eligible >= target
        _write_json(run_dir / "collection_summary.json", summary)
        _write_json(status_path, {"status": "COMPLETED" if complete else "INCOMPLETE_POPULATION", **summary})
        print(f"run: {run_dir}", flush=True)
        return 0 if complete else 2
    except Exception as exc:
        if status_path is not None and manifest is not None:
            _write_json(status_path, {"status": "FAILED", "manifest_id": manifest["manifest_id"], "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
