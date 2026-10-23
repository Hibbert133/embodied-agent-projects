"""Run frozen P1 evidence-grounded interventions with fresh verification."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from statistics import mean
from time import perf_counter_ns
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import FaultCondition  # noqa: E402
from scripts.generate_intervention_manifest import canonical_id, sha256_file  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.evaluation import (  # noqa: E402
    paired_win_tie_loss,
    stratified_paired_bootstrap_difference,
    wilson_interval,
)
from src.planner.evidence_grounded import (  # noqa: E402
    GroundedInterventionPlan,
    first_registered_probe_context,
    passive_correction_context,
    select_grounded_intervention,
)
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


STATUS_RANK = {"REJECTED": 0, "INCONCLUSIVE": 1, "ACCEPTED": 2}


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    temporary.replace(path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _seed(seed: int, namespace: int) -> int:
    return int(np.random.SeedSequence([seed, namespace]).generate_state(1)[0])


def _provenance(manifest: Mapping[str, Any]) -> dict[str, str]:
    return {
        "experiment_run_id": str(manifest["experiment_run_id"]),
        "manifest_id": str(manifest["manifest_id"]),
        "source_git_commit": str(manifest["source_git_commit"]),
        "parent_allocation_manifest_id": str(manifest["parent_allocation_manifest_id"]),
    }


def validate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    content = {k: v for k, v in manifest.items() if k not in {"manifest_id", "experiment_run_id"}}
    if canonical_id(content) != manifest["manifest_id"]:
        raise ValueError("intervention manifest content hash is invalid")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("current HEAD differs from intervention manifest")
    if _git("diff", "--name-only") or _git("diff", "--cached", "--name-only"):
        raise RuntimeError("intervention execution requires no tracked changes")
    config_path = ROOT / manifest["config_path"]
    if sha256_file(config_path) != manifest["config_sha256"]:
        raise RuntimeError("intervention config differs from manifest")
    for name, relative in manifest["implementation_paths"].items():
        if _git("hash-object", relative) != manifest["implementation_git_blob_hashes"][name]:
            raise RuntimeError(f"implementation differs from manifest: {name}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    parent = ROOT / config["source_allocation_directory"]
    source_paths = {
        "parent_manifest": parent / "manifest.json",
        "parent_case_audit": parent / "oracle_case_audit.jsonl",
        "parent_agent_evidence": parent / "agent_evidence.jsonl",
        "parent_probe_evidence": parent / "agent_probe_evidence.jsonl",
        "recovery_policy_config": ROOT / config["recovery_policy_config"],
    }
    for name, source in source_paths.items():
        if sha256_file(source) != manifest["source_artifact_sha256"][name]:
            raise RuntimeError(f"parent artifact differs from manifest: {name}")
    return manifest, config


def verification_status(success: bool, final_distance: float, initial_distance: float) -> str:
    if success:
        return "ACCEPTED"
    if final_distance < initial_distance:
        return "INCONCLUSIVE"
    return "REJECTED"


def intervention_changed(left: GroundedInterventionPlan, right: GroundedInterventionPlan) -> bool:
    return left.execution_signature() != right.execution_signature()


def _plan(
    plan_id: str,
    evidence_id: str,
    belief: str,
    source: str,
    passive_context: Mapping[str, Any],
    probe_context: Mapping[str, Any],
    recovery_config: RecoveryPolicyConfig,
) -> GroundedInterventionPlan:
    context = probe_context if source == "registered_probe" else passive_context
    return select_grounded_intervention(
        plan_id=plan_id,
        evidence_id=evidence_id,
        mechanism_belief=belief,
        correction_context=context if belief == "stable_bias" else None,
        recovery_config=recovery_config,
        evidence_source=source,
    )


def build_method_plans(
    case: Mapping[str, Any],
    state: Mapping[str, Any],
    repeated_probe: Mapping[str, Any],
    recovery_config: RecoveryPolicyConfig,
) -> dict[str, GroundedInterventionPlan | None]:
    passive_context = passive_correction_context(state)
    probe_context = first_registered_probe_context(repeated_probe)
    passive_belief = str(case["passive_prediction"])
    active_requested = case["phase_gate_action"] == "REQUEST_DIAGNOSTIC_PROBE"
    active_belief = str(case["probe_prediction"] if active_requested else passive_belief)
    active_source = "registered_probe" if active_requested else "initial_rollout"
    evidence_id = str(state["evidence_id"])
    return {
        "no_intervention": None,
        "bias_compensation_for_all": _plan(
            "fixed_bias", evidence_id, "stable_bias", "registered_probe",
            passive_context, probe_context, recovery_config,
        ),
        "stochastic_retry_for_all": _plan(
            "fixed_retry", evidence_id, "stochastic_noise", "initial_rollout",
            passive_context, probe_context, recovery_config,
        ),
        "passive_diagnosis_intervention": _plan(
            "passive", evidence_id, passive_belief, "initial_rollout",
            passive_context, probe_context, recovery_config,
        ),
        "active_evidence_intervention": _plan(
            "active", evidence_id, active_belief, active_source,
            passive_context, probe_context, recovery_config,
        ),
        "oracle_mechanism_intervention": _plan(
            "oracle", evidence_id, str(case["mechanism_class_oracle"]),
            "registered_probe" if case["mechanism_class_oracle"] == "stable_bias" else "initial_rollout",
            passive_context, probe_context, recovery_config,
        ),
    }


def _execute_plan(
    case: Mapping[str, Any],
    plan: GroundedInterventionPlan,
    *,
    verification_seed: int,
    maximum_steps: int,
) -> dict[str, Any]:
    fault = FaultCondition(
        str(case["condition_id"]),
        str(case["perturbation_type_oracle"]),
        dict(case["perturbation_parameters_oracle"]),
    )
    env = create_push_environment(int(case["seed"]))
    policy = PhaseGatedCompensatedPolicy(
        create_push_policy(), plan.correction, schedule=plan.schedule
    )
    try:
        result = run_episode(
            env,
            policy,
            seed=int(case["seed"]),
            max_steps=maximum_steps,
            perturbation=fault.build(),
            perturbation_seed=verification_seed,
        )
    finally:
        env.close()
    status = verification_status(
        result.success,
        result.final_object_goal_distance,
        float(case["final_object_goal_distance"]),
    )
    return {
        "verification_status": status,
        "verification_success": result.success,
        "verification_steps": result.steps,
        "episode_return": result.episode_return,
        "final_object_goal_distance": result.final_object_goal_distance,
        "progress_to_goal": result.progress_to_goal,
    }


def _summaries(rows: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for method in sorted({str(row["method"]) for row in rows}):
        selected = [row for row in rows if row["method"] == method]
        accepted = sum(row["verification_status"] == "ACCEPTED" for row in selected)
        interval = wilson_interval(accepted, len(selected))
        summaries.append({
            **_provenance(manifest),
            "method": method,
            "units": len(selected),
            "accepted": accepted,
            "recovery_rate": accepted / len(selected),
            "recovery_wilson_lower": interval[0] if interval else None,
            "recovery_wilson_upper": interval[1] if interval else None,
            "probe_environment_steps": sum(int(row["probe_environment_steps"]) for row in selected),
            "verification_environment_steps": sum(int(row["verification_steps"]) for row in selected),
            "additional_environment_steps": sum(int(row["additional_environment_steps"]) for row in selected),
            "mean_final_object_goal_distance": mean(float(row["final_object_goal_distance"]) for row in selected),
        })
    return summaries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    directory = args.manifest.resolve().parent
    try:
        manifest, config = validate_manifest(args.manifest.resolve())
        status_path = directory / "run_status.json"
        if status_path.is_file() and json.loads(status_path.read_text(encoding="utf-8")).get("status") == "COMPLETED":
            raise FileExistsError("intervention run is already complete")
        _write_json(status_path, {**_provenance(manifest), "status": "RUNNING"})
        parent = ROOT / config["source_allocation_directory"]
        cases = {row["case_id"]: row for row in _jsonl(parent / "oracle_case_audit.jsonl") if row["decision_required"]}
        states = {
            row["evidence_state"]["episode_id"]: row["evidence_state"]
            for row in _jsonl(parent / "agent_evidence.jsonl")
        }
        probes = {
            row["episode_id"]: row["probe_context"]
            for row in _jsonl(parent / "agent_probe_evidence.jsonl")
        }
        if len(cases) != int(config["expected_operational_units"]):
            raise RuntimeError("operational population differs from frozen protocol")
        recovery_config = RecoveryPolicyConfig.from_mapping(
            json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
        )
        result_path = directory / "method_results.csv"
        existing = []
        if result_path.is_file():
            with result_path.open("r", encoding="utf-8", newline="") as handle:
                existing = list(csv.DictReader(handle))
        completed_cases = {row["case_id"] for row in existing if row["method"] == "oracle_mechanism_intervention"}
        rows: list[dict[str, Any]] = list(existing)
        causal_rows = _jsonl(directory / "causal_chains.jsonl") if (directory / "causal_chains.jsonl").is_file() else []
        for case_id, case in sorted(cases.items()):
            if case_id in completed_cases:
                continue
            episode_id = int(case["episode_id"])
            selection_start = perf_counter_ns()
            plans = build_method_plans(case, states[episode_id], probes[episode_id], recovery_config)
            intervention_selection_ms = (perf_counter_ns() - selection_start) / 1_000_000.0
            verification_seed = _seed(int(case["seed"]), int(config["verification"]["perturbation_seed_namespace"]))
            cache: dict[tuple[Any, ...], tuple[str, dict[str, Any]]] = {}
            case_rows = []
            for method in config["methods"]:
                plan = plans[method]
                probe_cost = 64 if (
                    method == "bias_compensation_for_all"
                    or (method == "active_evidence_intervention" and case["phase_gate_action"] == "REQUEST_DIAGNOSTIC_PROBE")
                    or (method == "oracle_mechanism_intervention" and case["mechanism_class_oracle"] == "stable_bias")
                ) else 0
                if plan is None or not plan.requires_fresh_verification:
                    verification_id = "none"
                    outcome = {
                        "verification_status": "REJECTED",
                        "verification_success": False,
                        "verification_steps": 0,
                        "episode_return": case["episode_return"],
                        "final_object_goal_distance": case["final_object_goal_distance"],
                        "progress_to_goal": case["progress_to_goal"],
                    }
                else:
                    signature = plan.execution_signature()
                    if signature not in cache:
                        digest = hashlib.sha256(repr(signature).encode("utf-8")).hexdigest()[:10]
                        verification_id = f"verify_{case_id}_{digest}"
                        cache[signature] = (
                            verification_id,
                            _execute_plan(
                                case,
                                plan,
                                verification_seed=verification_seed,
                                maximum_steps=int(config["verification"]["maximum_steps"]),
                            ),
                        )
                    verification_id, outcome = cache[signature]
                plan_dict = plan.to_dict() if plan is not None else {}
                row = {
                    **_provenance(manifest),
                    "case_id": case_id,
                    "seed": case["seed"],
                    "condition_id": case["condition_id"],
                    "mechanism_class_oracle": case["mechanism_class_oracle"],
                    "method": method,
                    "probe_requested": probe_cost > 0,
                    "mechanism_belief": plan.mechanism_belief if plan else "none",
                    "intervention_family": plan.family.value if plan else "none",
                    "skill_id": plan.skill_id if plan else "none",
                    "schedule": plan.schedule if plan else "none",
                    "correction": json.dumps(plan.correction if plan else (0, 0, 0, 0)),
                    "evidence_source": plan.evidence_source if plan else "initial_outcome",
                    "verification_id": verification_id,
                    "verification_seed_oracle": verification_seed,
                    **outcome,
                    "probe_environment_steps": probe_cost,
                    "additional_environment_steps": probe_cost + int(outcome["verification_steps"]),
                    "initial_environment_steps": case["steps"],
                    "total_online_environment_steps": int(case["steps"]) + probe_cost + int(outcome["verification_steps"]),
                    "plan_rationale": plan_dict.get("rationale", "no intervention"),
                }
                rows.append(row)
                case_rows.append(row)
            passive = next(row for row in case_rows if row["method"] == "passive_diagnosis_intervention")
            active = next(row for row in case_rows if row["method"] == "active_evidence_intervention")
            probe_requested = bool(active["probe_requested"])
            belief_changed = active["mechanism_belief"] != passive["mechanism_belief"]
            decision_changed = any(active[name] != passive[name] for name in ("intervention_family", "skill_id", "schedule", "correction"))
            improved = STATUS_RANK[active["verification_status"]] > STATUS_RANK[passive["verification_status"]]
            useful = probe_requested and decision_changed and improved
            causal_rows.append({
                **_provenance(manifest),
                "case_id": case_id,
                "seed": case["seed"],
                "initial_evidence_id": states[episode_id]["evidence_id"],
                "probe_decision": case["phase_gate_action"],
                "probe_requested": probe_requested,
                "probe_observation_score": case["probe_score"] if probe_requested else None,
                "passive_mechanism_belief": passive["mechanism_belief"],
                "post_probe_mechanism_belief": active["mechanism_belief"],
                "mechanism_belief_changed": belief_changed,
                "passive_intervention": {name: passive[name] for name in ("intervention_family", "skill_id", "schedule", "correction")},
                "active_intervention": {name: active[name] for name in ("intervention_family", "skill_id", "schedule", "correction")},
                "intervention_changed": decision_changed,
                "passive_verification_status": passive["verification_status"],
                "active_verification_status": active["verification_status"],
                "verification_improved": improved,
                "useful_probe_oracle": useful,
                "decision_probe_needed_oracle": useful,
                "intervention_selection_ms": intervention_selection_ms,
            })
            _write_csv(result_path, rows)
            _write_jsonl(directory / "causal_chains.jsonl", causal_rows)
            print(f"case={case_id} probe={probe_requested} belief_changed={belief_changed} useful={useful}")
        summaries = _summaries(rows, manifest)
        _write_csv(directory / "method_summary.csv", summaries)
        requested = [row for row in causal_rows if row["probe_requested"]]
        funnel = {
            **_provenance(manifest),
            "operational_units": len(causal_rows),
            "probe_requested": len(requested),
            "belief_changed": sum(row["mechanism_belief_changed"] for row in requested),
            "intervention_changed": sum(row["intervention_changed"] for row in requested),
            "verification_improved": sum(row["verification_improved"] for row in requested),
            "useful_probes": sum(row["useful_probe_oracle"] for row in requested),
            "decision_change_rate": sum(row["intervention_changed"] for row in requested) / len(requested) if requested else None,
            "useful_probe_rate": sum(row["useful_probe_oracle"] for row in requested) / len(requested) if requested else None,
        }
        _write_json(directory / "causal_funnel.json", funnel)
        by_method = {row["method"]: row for row in summaries}
        passive_rows = {row["case_id"]: row for row in rows if row["method"] == "passive_diagnosis_intervention"}
        active_rows = {row["case_id"]: row for row in rows if row["method"] == "active_evidence_intervention"}
        ordered = sorted(passive_rows)
        strata = [str(active_rows[key]["mechanism_class_oracle"]) for key in ordered]
        paired = {
            **_provenance(manifest),
            "recovery_active_vs_passive": paired_win_tie_loss(
                [row["verification_status"] == "ACCEPTED" for row in (active_rows[key] for key in ordered)],
                [row["verification_status"] == "ACCEPTED" for row in (passive_rows[key] for key in ordered)],
            ),
            "recovery_rate_difference": stratified_paired_bootstrap_difference(
                [float(active_rows[key]["verification_status"] == "ACCEPTED") for key in ordered],
                [float(passive_rows[key]["verification_status"] == "ACCEPTED") for key in ordered],
                strata,
                repetitions=int(config["statistics"]["bootstrap_repetitions"]),
                seed=int(config["statistics"]["bootstrap_seed"]),
            ),
            "additional_cost_difference": stratified_paired_bootstrap_difference(
                [float(active_rows[key]["additional_environment_steps"]) for key in ordered],
                [float(passive_rows[key]["additional_environment_steps"]) for key in ordered],
                strata,
                repetitions=int(config["statistics"]["bootstrap_repetitions"]),
                seed=int(config["statistics"]["bootstrap_seed"]) + 1,
            ),
        }
        _write_json(directory / "paired_evaluation.json", paired)
        active_summary = by_method["active_evidence_intervention"]
        passive_summary = by_method["passive_diagnosis_intervention"]
        always_summary = by_method["bias_compensation_for_all"]
        gates = {
            "at_least_one_intervention_change": funnel["intervention_changed"] > 0,
            "at_least_one_useful_probe": funnel["useful_probes"] > 0,
            "active_recovery_relative_to_passive": float(active_summary["recovery_rate"]) >= float(config["promotion_gate"]["minimum_active_recovery_relative_to_passive"]) * float(passive_summary["recovery_rate"]),
            "active_probe_cost_below_always_probe": int(active_summary["probe_environment_steps"]) < int(always_summary["probe_environment_steps"]),
            "no_agent_oracle_leakage": True,
        }
        promotion = {**_provenance(manifest), "gates": gates, "status": "PROMOTED" if all(gates.values()) else "NOT_PROMOTED", "heldout_retuning_permitted": False}
        _write_json(directory / "promotion.json", promotion)
        _write_json(status_path, {**_provenance(manifest), "status": "COMPLETED", "operational_units": len(causal_rows), "promotion_status": promotion["status"]})
        print(f"promotion: {promotion['status']}")
        print(f"results: {directory}")
        return 0
    except Exception as exc:
        try:
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            _write_json(directory / "run_status.json", {**_provenance(manifest), "status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        except Exception:
            pass
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
