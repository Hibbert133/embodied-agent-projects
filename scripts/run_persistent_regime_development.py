"""Collect paired candidate outcomes under persistent latent execution regimes."""

from __future__ import annotations

import argparse
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
from scripts.run_probemem_acr_utility_stability import (  # noqa: E402
    _compensation_is_constructible, _load_inputs, _sha256, _write_csv, _write_json,
)
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem.persistent_regime import FROZEN_CONSISTENCY_THRESHOLD, select_from_persistent_probe  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"] or _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("manifest identity or source commit mismatch")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("execution requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("config differs from immutable manifest")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"immutable source changed: {relative}")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest: dict[str, Any] | None = None
    status_path: Path | None = None
    try:
        manifest, config = _validate(args.manifest.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("run cannot be restarted or overwritten")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        fault_template, recovery = _load_inputs({
            "registered_condition": "fault_05", "noise_selection": config["noise_selection"],
            "recovery_policy_config": config["recovery_policy_config"],
        })
        noise_std = float(fault_template.parameters["std"])
        conditions = {item.condition_id: item for item in get_conditions(noise_std)}
        rows: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        integrity = {"chronology_violations": 0, "oracle_leakage_events": 0, "budget_violations": 0, "random_namespace_violations": 0}
        for unit in manifest["population_units"]:
            episode_id, seed = int(unit["episode_id"]), int(unit["environment_seed"])
            condition_id = str(unit["condition_id_oracle"])
            fault = conditions[condition_id]
            streams = {int(unit["initial_perturbation_seed"]), int(unit["diagnostic_probe_seed"]), int(unit["paired_verification_seed"])}
            if len(streams) != 3:
                integrity["random_namespace_violations"] += 1
                raise RuntimeError("random namespaces overlap")
            trajectory = run_dir / "initial_trajectories" / f"episode{episode_id:03d}_seed{seed}_{condition_id}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(env, create_push_policy(), seed=seed, episode_id=episode_id,
                                      max_steps=int(config["budget"]["initial_max_steps"]), perturbation=fault.build(),
                                      perturbation_seed=int(unit["initial_perturbation_seed"]), agent_trajectory_path=trajectory)
            finally:
                env.close()
            state = build_structured_evidence_state(_read_jsonl(trajectory), evidence_id=f"persistent_episode{episode_id:03d}_attempt0", source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0)
            base = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "episode_id": episode_id, "seed": seed, "condition_id_oracle": condition_id, "initial_success": initial.success, "initial_steps": initial.steps, "initial_final_object_goal_distance": initial.final_object_goal_distance, "decision_required": state.decision_required}
            if not state.decision_required:
                rows.append({**base, "paired_comparable": False, "ineligibility_reason": "initial_success", "probe_steps": 0, "selected_skill": None, "probe_consistency_score": None})
                _write_csv(run_dir / "case_results.csv", rows)
                continue
            probe = _probe_context(fault, seed, config, int(unit["diagnostic_probe_seed"]))
            probe_steps = int(probe["probe_environment_steps"])
            if probe_steps > int(config["budget"]["probe_max_steps"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("probe budget exceeded")
            if not _compensation_is_constructible(seed=seed, probe_context=probe, recovery_config=recovery):
                rows.append({**base, "paired_comparable": False, "ineligibility_reason": "compensation_not_constructible", "probe_steps": probe_steps, "selected_skill": None, "probe_consistency_score": None})
                _write_csv(run_dir / "case_results.csv", rows)
                continue
            agent_evidence = {"evidence_id": f"persistent_episode{episode_id:03d}_attempt1", "episode_id": episode_id, "initial_evidence": state.to_dict(), "registered_probe_evidence": probe, "remaining_verification_budget": int(config["budget"]["verification_max_steps_per_candidate"])}
            validate_no_oracle_evidence(agent_evidence)
            selected, score = select_from_persistent_probe(probe)
            decision_time = time.perf_counter_ns()
            decisions.append({"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "episode_id": episode_id, "seed": seed, "decision_timestamp_ns": decision_time, "agent_visible_evidence": agent_evidence, "selected_skill": selected.value, "probe_consistency_score": score, "frozen_threshold_hash": manifest["rule_hash"], "candidate_outcomes_available": False})
            _write_json(run_dir / "agent_decisions.json", decisions)
            evaluator_steps = initial.steps + probe_steps
            for skill in (COMPENSATION, RETRY):
                result, execution = _run_verification(seed=seed, fault=fault, skill=skill, probe_context=probe, recovery_config=recovery, perturbation_seed=int(unit["paired_verification_seed"]), max_steps=int(config["budget"]["verification_max_steps_per_candidate"]), initial_distance=initial.final_object_goal_distance)
                outcome_time = time.perf_counter_ns()
                if outcome_time <= decision_time:
                    integrity["chronology_violations"] += 1
                    raise RuntimeError("candidate outcome preceded decision")
                evaluator_steps += result.steps
                candidates.append({**base, "candidate_id": skill.value, "verification_status": execution["verification_status"], "verification_success": result.success, "verification_steps": result.steps, "final_object_goal_distance": result.final_object_goal_distance, "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance, "paired_verification_seed": int(unit["paired_verification_seed"]), "outcome_timestamp_ns": outcome_time})
            if evaluator_steps > int(config["budget"]["evaluator_max_steps_per_case"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("evaluator budget exceeded")
            rows.append({**base, "paired_comparable": True, "ineligibility_reason": "", "probe_steps": probe_steps, "selected_skill": selected.value, "probe_consistency_score": score, "evaluator_collection_steps": evaluator_steps})
            _write_csv(run_dir / "case_results.csv", rows)
            _write_csv(run_dir / "candidate_results.csv", candidates)
            print(f"episode={episode_id} seed={seed} condition={condition_id} selected={selected.value}", flush=True)
        summary = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "initial_units": len(rows), "paired_comparable_cases": sum(bool(row["paired_comparable"]) for row in rows), **integrity, "api_calls": 0, "heldout_seeds_executed": 0}
        _write_json(run_dir / "collection_summary.json", summary)
        _write_json(status_path, {"status": "COMPLETED", **summary})
        print(f"run: {run_dir}")
        return 0
    except Exception as exc:
        if manifest is not None and status_path is not None:
            _write_json(status_path, {"status": "FAILED", "manifest_id": manifest["manifest_id"], "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
