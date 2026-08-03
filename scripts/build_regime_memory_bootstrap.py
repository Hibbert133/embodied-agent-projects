"""Collect the frozen outcome-blind ProbeMem-Online Gate-B bootstrap."""

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
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible, _load_inputs, _sha256, _write_csv, _write_json  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"] or _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("bootstrap manifest identity or commit mismatch")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("bootstrap requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("bootstrap config changed")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"bootstrap frozen input changed: {relative}")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _snapshot(records: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": 1,
        "snapshot_id": f"bootstrap_{hashlib.sha256(canonical).hexdigest()[:16]}",
        "source_manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"],
        "record_count": len(records),
        "record_ids": [row["record_id"] for row in records],
        "verified_example_ids": [row["record_id"] for row in records if row["observed_status"] == "ACCEPTED"],
        "records_sha256": hashlib.sha256(canonical).hexdigest(),
        "chronological_max_episode_id": max(row["episode_id"] for row in records),
        "counterfactual_records": 0,
    }


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
            raise FileExistsError("bootstrap cannot restart or overwrite")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        fault_template, recovery = _load_inputs(config)
        conditions = {item.condition_id: item for item in get_conditions(float(fault_template.parameters["std"]))}
        target = int(config["target_per_condition_skill_cell"])
        cells: Counter[tuple[str, str]] = Counter()
        cases: list[dict[str, Any]] = []
        evidence_rows: list[dict[str, Any]] = []
        memory = RegimeActionMemory()
        integrity = {"chronology_violations": 0, "oracle_leakage_events": 0, "budget_violations": 0, "random_namespace_violations": 0, "counterfactual_records": 0}
        for unit in manifest["candidate_units"]:
            condition_id = str(unit["condition_id_oracle"])
            skill = InterventionSkill(str(unit["selected_skill"]))
            cell = (condition_id, skill.value)
            if cells[cell] >= target:
                continue
            seed, unit_id = int(unit["environment_seed"]), int(unit["unit_id"])
            streams = {int(unit["initial_perturbation_seed"]), int(unit["diagnostic_probe_seed"]), int(unit["selected_verification_seed"])}
            if len(streams) != 3:
                integrity["random_namespace_violations"] += 1
                raise RuntimeError("bootstrap random namespaces overlap")
            fault = conditions[condition_id]
            trajectory = run_dir / "initial_trajectories" / f"unit{unit_id:03d}_seed{seed}_{condition_id}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, episode_id=unit_id,
                    max_steps=int(config["budget"]["initial_max_steps"]), perturbation=fault.build(),
                    perturbation_seed=int(unit["initial_perturbation_seed"]), agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory), evidence_id=f"online_bootstrap_unit{unit_id:03d}_attempt0",
                source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            )
            base = {
                "unit_id": unit_id, "seed": seed, "condition_id_oracle": condition_id,
                "assigned_skill": skill.value, "initial_success": initial.success,
                "initial_steps": initial.steps, "initial_final_object_goal_distance": initial.final_object_goal_distance,
            }
            if not state.decision_required:
                cases.append({**base, "operational": False, "ineligibility_reason": "initial_success"})
                _write_csv(run_dir / "case_results.csv", cases)
                continue
            probe = _probe_context(fault, seed, config, int(unit["diagnostic_probe_seed"]))
            probe_steps = int(probe["probe_environment_steps"])
            if probe_steps > int(config["budget"]["probe_max_steps"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("bootstrap probe budget exceeded")
            if skill is InterventionSkill.BOUNDED_PLANAR_COMPENSATION and not _compensation_is_constructible(seed=seed, probe_context=probe, recovery_config=recovery):
                cases.append({**base, "operational": False, "ineligibility_reason": "assigned_compensation_not_constructible"})
                _write_csv(run_dir / "case_results.csv", cases)
                continue
            episode_id = sum(cells.values()) + 1
            agent_evidence = {
                "evidence_id": f"online_bootstrap_episode{episode_id:03d}_attempt1", "episode_id": episode_id,
                "initial_evidence": {**state.to_dict(), "episode_id": episode_id, "evidence_id": f"online_bootstrap_episode{episode_id:03d}_attempt0"},
                "registered_probe_evidence": probe,
                "remaining_verification_budget": int(config["budget"]["verification_max_steps"]),
            }
            validate_no_oracle_evidence(agent_evidence)
            signature = ProbeRegimeSignature.from_agent_evidence(agent_evidence)
            decision_timestamp = time.perf_counter_ns()
            evidence_rows.append({
                "episode_id": episode_id, "unit_id": unit_id, "agent_visible_evidence": agent_evidence,
                "assigned_action_manifest_only": skill.value, "decision_timestamp_ns": decision_timestamp,
                "outcome_available": False,
            })
            _write_json(run_dir / "agent_evidence.json", evidence_rows)
            result, execution = _run_verification(
                seed=seed, fault=fault, skill=skill, probe_context=probe, recovery_config=recovery,
                perturbation_seed=int(unit["selected_verification_seed"]),
                max_steps=int(config["budget"]["verification_max_steps"]),
                initial_distance=initial.final_object_goal_distance,
            )
            if time.perf_counter_ns() <= decision_timestamp:
                integrity["chronology_violations"] += 1
                raise RuntimeError("bootstrap outcome preceded persisted decision evidence")
            additional_cost = probe_steps + result.steps
            if initial.steps + additional_cost > int(config["budget"]["online_max_steps"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("bootstrap online budget exceeded")
            experience = RegimeActionExperience(
                schema_version=1, record_id=f"bootstrap_episode{episode_id:03d}_{skill.value.lower()}",
                episode_id=episode_id, available_from_episode_id=episode_id + 1,
                probe_signature=signature, selected_skill=skill,
                predicted_status=None, predicted_accept_probability=None,
                observed_status=str(execution["verification_status"]),
                observed_progress=initial.final_object_goal_distance - result.final_object_goal_distance,
                observed_final_distance=result.final_object_goal_distance,
                interaction_cost=additional_cost, source_run_id=manifest["experiment_run_id"],
                source_manifest_id=manifest["manifest_id"],
                record_origin="OUTCOME_BLIND_BOOTSTRAP_SELECTED_ACTION",
            )
            memory.append_after_verification(experience)
            cells[cell] += 1
            cases.append({
                **base, "episode_id": episode_id, "operational": True, "ineligibility_reason": "",
                "verification_status": experience.observed_status, "verification_success": result.success,
                "verification_steps": result.steps, "probe_steps": probe_steps,
                "final_object_goal_distance": result.final_object_goal_distance,
            })
            rows = [record.to_dict() for record in memory.records]
            _write_json(run_dir / "action_outcome_records.json", rows)
            _write_json(run_dir / "verified_examples.json", [record.to_dict() for record in memory.verified_examples])
            _write_json(run_dir / "bootstrap_snapshot.json", _snapshot(rows, manifest))
            _write_csv(run_dir / "case_results.csv", cases)
            print(f"episode={episode_id} seed={seed} cell={cell} status={experience.observed_status}", flush=True)
            if all(cells[(condition, skill_name)] == target for condition in config["conditions"] for skill_name in config["selected_skills"]):
                break
        complete = len(memory.records) == 4 * target
        summary = {
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"], "operational_records": len(memory.records),
            "records_by_cell": {f"{condition}|{skill}": cells[(condition, skill)] for condition in config["conditions"] for skill in config["selected_skills"]},
            "records_by_status": dict(Counter(record.observed_status for record in memory.records)),
            "verified_example_count": len(memory.verified_examples), "selected_actions_executed": len(memory.records),
            "unselected_actions_executed": 0, **integrity, "api_calls": 0,
        }
        _write_json(run_dir / "summary.json", summary)
        _write_json(status_path, {"status": "COMPLETED" if complete else "INCOMPLETE_POPULATION", **summary})
        print(f"run: {run_dir}")
        return 0 if complete else 2
    except Exception as exc:
        if manifest is not None and status_path is not None:
            _write_json(status_path, {"status": "FAILED", "manifest_id": manifest["manifest_id"], "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
