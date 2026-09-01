"""Run the frozen ProbeMem additional-experiments paired development stream."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import get_conditions  # noqa: E402
from scripts.build_bias_noise_ambiguity_benchmark import classify_probe  # noqa: E402
from scripts.run_frozen_heldout_allocation import _build_probe_context, _load_passive_model  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _write_csv, _write_json  # noqa: E402
from scripts.run_probemem_v2_smoke import _read_jsonl, _seed  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.planner.evidence_grounded import (  # noqa: E402
    GroundedInterventionPlan,
    InterventionFamily,
    first_registered_probe_context,
    passive_correction_context,
    select_grounded_intervention,
)
from src.probemem.additional_experiments import (  # noqa: E402
    ExperimentMemoryRecord,
    MethodChronologicalMemory,
    REGISTERED_SKILLS,
    deterministic_verifier,
    select_from_retrieval,
)
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


BASELINE = "BASELINE"
MEMORY = "MEMORY_ONLY"
EVIDENCE = "EVIDENCE_ACQUISITION_ENABLED"
BRIDGE = "PROBE_MEMORY"
FULL = "FULL_PROBEMEM"
METHODS = (BASELINE, MEMORY, EVIDENCE, BRIDGE, FULL)
COMP, RETRY = REGISTERED_SKILLS


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _manifest_hash(value: Mapping[str, Any]) -> str:
    content = {key: item for key, item in value.items() if key != "manifest_id"}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if _manifest_hash(manifest) != manifest["manifest_id"]:
        raise ValueError("manifest content hash is invalid")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("current HEAD differs from manifest source commit")
    if _git("status", "--porcelain"):
        raise RuntimeError("registered execution requires a clean worktree")
    config_path = ROOT / manifest["config_path"]
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != manifest["config_sha256"]:
        raise RuntimeError("config hash differs from manifest")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _pre_signature(state: Mapping[str, Any]) -> tuple[float, ...]:
    validate_no_oracle_evidence(state)
    task = state["task_state"]
    temporal = state["temporal_response"]
    phase = state["phase_response"]
    drift = tuple(float(value) for value in temporal["estimated_drift_xy"])
    residual = tuple(float(value) for value in temporal["normalized_residual_xy"])
    if len(drift) != 2 or len(residual) != 2:
        raise ValueError("pre-acquisition signature requires planar drift and residual")
    return (
        float(task["progress_to_goal"]), float(task["final_object_goal_distance"]),
        float(temporal["uncertainty"]), float(phase["phase_inconsistency"]),
        drift[0], drift[1], (residual[0] ** 2 + residual[1] ** 2) ** 0.5,
    )


def _skill(plan: GroundedInterventionPlan) -> str | None:
    if plan.family is InterventionFamily.BIAS_COMPENSATION:
        return COMP
    if plan.family is InterventionFamily.STOCHASTIC_RETRY:
        return RETRY
    return None


def _plan(
    *, plan_id: str, evidence_id: str, skill: str,
    passive_context: Mapping[str, Any], probe_context: Mapping[str, Any] | None,
    probe_requested: bool, recovery: RecoveryPolicyConfig,
) -> GroundedInterventionPlan:
    if skill == RETRY:
        belief, context, source = "stochastic_noise", None, "initial_rollout"
    elif skill == COMP:
        belief = "stable_bias"
        context = first_registered_probe_context(probe_context) if probe_requested and probe_context else passive_context
        source = "registered_probe" if probe_requested and probe_context else "initial_rollout"
    else:
        raise ValueError("unregistered recovery skill")
    return select_grounded_intervention(
        plan_id=plan_id, evidence_id=evidence_id, mechanism_belief=belief,
        correction_context=context, recovery_config=recovery, evidence_source=source,
    )


def _first_observation_hash(path: Path) -> str:
    rows = _read_jsonl(path)
    if not rows:
        raise RuntimeError("trajectory has no state rows")
    payload = json.dumps(rows[0]["observation"], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _execute(
    *, seed: int, fault: Any, plan: GroundedInterventionPlan,
    perturbation_seed: int, max_steps: int, initial_distance: float,
    expected_initial_hash: str,
) -> dict[str, Any]:
    if not plan.requires_fresh_verification:
        return {
            "verification_status": "REJECTED", "success": False, "steps": 0,
            "final_object_goal_distance": initial_distance, "progress_to_goal": 0.0,
            "initial_state_hash": expected_initial_hash,
        }
    with tempfile.TemporaryDirectory(prefix="probemem_additional_branch_") as directory:
        trace = Path(directory) / "trace.jsonl"
        env = create_push_environment(seed)
        policy = PhaseGatedCompensatedPolicy(create_push_policy(), plan.correction, schedule=plan.schedule)
        try:
            result = run_episode(
                env, policy, seed=seed, max_steps=max_steps, perturbation=fault.build(),
                perturbation_seed=perturbation_seed, agent_trajectory_path=trace,
            )
        finally:
            env.close()
        state_hash = _first_observation_hash(trace)
    if state_hash != expected_initial_hash:
        raise RuntimeError("reset-matched environment state hash mismatch")
    status = "ACCEPTED" if result.success else (
        "INCONCLUSIVE" if result.final_object_goal_distance < initial_distance else "REJECTED"
    )
    return {
        "verification_status": status, "success": bool(result.success), "steps": int(result.steps),
        "final_object_goal_distance": float(result.final_object_goal_distance),
        "progress_to_goal": float(result.progress_to_goal), "initial_state_hash": state_hash,
    }


def _plan_key(plan: GroundedInterventionPlan) -> str:
    return hashlib.sha256(json.dumps(plan.execution_signature(), sort_keys=True).encode()).hexdigest()[:16]


def _flush(run_dir: Path, *, population: list[dict[str, Any]], decisions: list[dict[str, Any]],
           outcomes: list[dict[str, Any]], retrievals: list[dict[str, Any]],
           records: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> None:
    _write_csv(run_dir / "population.csv", population)
    _write_csv(run_dir / "decisions.csv", decisions)
    _write_csv(run_dir / "candidate_outcomes.csv", outcomes)
    _write_csv(run_dir / "memory_retrieval_audit.csv", retrievals)
    _write_json(run_dir / "method_memory_records.json", records)
    _write_json(run_dir / "timeline.json", timeline)


def run(manifest_path: Path) -> int:
    manifest, config = _validate(manifest_path)
    run_dir = manifest_path.parent
    status_path = run_dir / "run_status.json"
    if status_path.exists():
        raise FileExistsError("run cannot restart or overwrite an existing status")
    _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
    passive_model = _load_passive_model()
    recovery = RecoveryPolicyConfig.from_mapping(json.loads(
        (ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8")
    ))
    noise_std = float(json.loads((ROOT / config["noise_selection"]).read_text(encoding="utf-8"))["noise_std"])
    faults = {fault.condition_id: fault for fault in get_conditions(noise_std)}
    scales = tuple(config["memory"]["fixed_scales"])
    memories = {method: MethodChronologicalMemory(method, scales=scales) for method in (MEMORY, BRIDGE, FULL)}
    full_statistical_records: list[ExperimentMemoryRecord] = []
    record_mechanisms: dict[str, str] = {}
    population: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    retrievals: list[dict[str, Any]] = []
    memory_records: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    sequence = 0
    operational = 0
    initial_units = 0
    integrity = {name: 0 for name in (
        "state_hash_violations", "rng_namespace_violations", "chronology_violations",
        "future_memory_access", "cross_method_memory_access", "oracle_leakage_events",
        "counterfactual_memory_writes", "budget_violations", "invalid_skill_executions",
    )}
    for unit in manifest["population_units"]:
        if operational >= int(config["target_operational_cases"]):
            break
        initial_units += 1
        seed = int(unit["environment_seed"])
        fault = faults[str(unit["condition_id_oracle"])]
        mechanism = str(config["mechanism_by_condition"][fault.condition_id])
        if len({int(unit["initial_perturbation_seed"]), int(unit["probe_seed"]), *map(int, unit["verification_seeds"])}) != 6:
            integrity["rng_namespace_violations"] += 1
            raise RuntimeError("random namespaces overlap")
        trace = run_dir / "initial_trajectories" / f"unit{unit['unit_id']:03d}_seed{seed}.jsonl"
        trace.parent.mkdir(parents=True, exist_ok=True)
        env = create_push_environment(seed)
        try:
            initial = run_episode(
                env, create_push_policy(), seed=seed, episode_id=int(unit["unit_id"]),
                max_steps=int(config["budget"]["initial_max_steps"]), perturbation=fault.build(),
                perturbation_seed=int(unit["initial_perturbation_seed"]), agent_trajectory_path=trace,
            )
        finally:
            env.close()
        initial_hash = _first_observation_hash(trace)
        state = build_structured_evidence_state(
            _read_jsonl(trace), evidence_id=f"additional_unit{unit['unit_id']:03d}_attempt0",
            source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            minimum_phase_samples=int(config["allocation"]["minimum_phase_samples"]),
        )
        population_row = {
            "unit_id": unit["unit_id"], "seed": seed, "condition_id_oracle": fault.condition_id,
            "mechanism_oracle": mechanism, "initial_success": not state.decision_required,
            "decision_required": state.decision_required, "operational": False,
            "initial_steps": initial.steps, "initial_state_hash": initial_hash,
        }
        if not state.decision_required:
            population.append(population_row)
            _flush(run_dir, population=population, decisions=decisions, outcomes=outcomes,
                   retrievals=retrievals, records=memory_records, timeline=timeline)
            continue
        population_row["operational"] = True
        population.append(population_row)
        operational += 1
        episode_id = int(config["first_online_episode_id"]) + operational - 1
        state_dict = state.to_dict()
        signature = _pre_signature(state_dict)
        passive = passive_model.predict({
            "episode_return": initial.episode_return,
            "final_object_goal_distance": initial.final_object_goal_distance,
            "progress_to_goal": initial.progress_to_goal,
        })
        probe_requested = (
            float(state.phase_response.phase_inconsistency) >= float(config["allocation"]["phase_inconsistency_threshold"])
            and int(config["budget"]["total_online_case_max_steps"]) - int(initial.steps)
            >= int(config["budget"]["probe_max_steps"]) + int(config["budget"]["verification_max_steps"])
        )
        probe = _build_probe_context(
            fault=fault, seed=seed, perturbation_seed_base=int(unit["probe_seed"])
        ) if probe_requested else None
        probe_steps = 0 if probe is None else int(probe["probe_environment_steps"])
        if probe_steps > int(config["budget"]["probe_max_steps"]):
            integrity["budget_violations"] += 1
            raise RuntimeError("registered evidence exceeded its budget")
        active_belief = str(passive.mechanism) if probe is None else classify_probe(
            float(probe["consistency"]["estimated_bias_std_norm"]),
            float(config["registered_probe"]["outcome_classifier_threshold"]),
        )
        passive_context = passive_correction_context(state_dict)
        baseline_skill = COMP if passive.mechanism == "stable_bias" else RETRY
        evidence_skill = COMP if active_belief == "stable_bias" else RETRY
        sequence += 1
        decision_sequence = sequence
        method_skills = {BASELINE: baseline_skill, EVIDENCE: evidence_skill}
        episode_retrievals: dict[str, tuple[Any, ...]] = {}
        for method, fallback in ((MEMORY, baseline_skill), (BRIDGE, evidence_skill)):
            items = memories[method].retrieve(
                signature, current_episode_id=episode_id,
                decision_sequence=decision_sequence, limit=int(config["memory"]["top_k"]),
            )
            episode_retrievals[method] = items
            method_skills[method] = select_from_retrieval(items, fallback_skill=fallback)[0]
        full_items = memories[FULL].retrieve(
            signature, current_episode_id=episode_id,
            decision_sequence=decision_sequence, limit=int(config["memory"]["top_k"]),
        )
        episode_retrievals[FULL] = full_items
        full_proposal = select_from_retrieval(full_items, fallback_skill=evidence_skill)[0]
        verifier = deterministic_verifier(
            proposal_skill=full_proposal, prior_records=full_statistical_records,
            current_episode_id=episode_id, invoked=bool(full_statistical_records),
            probability_margin_minimum=float(config["verifier"]["probability_margin_minimum"]),
            coverage_minimum=int(config["verifier"]["alternative_coverage_minimum"]),
            confidence_minimum=float(config["verifier"]["accepted_threshold"]),
        )
        method_skills[FULL] = verifier.selected_skill
        plans: dict[str, GroundedInterventionPlan] = {}
        for method in METHODS:
            plans[method] = _plan(
                plan_id=f"{method.lower()}_episode{episode_id}", evidence_id=state.evidence_id,
                skill=method_skills[method], passive_context=passive_context,
                probe_context=probe, probe_requested=probe_requested and method in {EVIDENCE, BRIDGE, FULL},
                recovery=recovery,
            )
        # The Full alternative is collected for intervention-outcome accounting.
        alternative_skill = next(skill for skill in REGISTERED_SKILLS if skill != full_proposal)
        plans["FULL_ALTERNATIVE_EVALUATOR_ONLY"] = _plan(
            plan_id=f"full_alternative_episode{episode_id}", evidence_id=state.evidence_id,
            skill=alternative_skill, passive_context=passive_context, probe_context=probe,
            probe_requested=probe_requested, recovery=recovery,
        )
        full_proposal_plan = (
            plans[FULL] if method_skills[FULL] == full_proposal
            else plans["FULL_ALTERNATIVE_EVALUATOR_ONLY"]
        )
        for method in METHODS:
            sequence += 1
            timeline.append({
                "sequence": sequence, "episode_id": episode_id, "event": "FINAL_SELECTION_WRITTEN",
                "method": method, "selected_skill": method_skills[method],
            })
        cache: dict[tuple[str, int], dict[str, Any]] = {}
        for plan in plans.values():
            key = _plan_key(plan)
            for realization, verification_seed in enumerate(unit["verification_seeds"]):
                cache_key = (key, realization)
                if cache_key not in cache:
                    cache[cache_key] = _execute(
                        seed=seed, fault=fault, plan=plan, perturbation_seed=int(verification_seed),
                        max_steps=int(config["budget"]["verification_max_steps"]),
                        initial_distance=float(initial.final_object_goal_distance),
                        expected_initial_hash=initial_hash,
                    )
                    outcomes.append({
                        "experiment_run_id": manifest["experiment_run_id"],
                        "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"],
                        "episode_id": episode_id, "seed": seed, "action_signature_id": key,
                        "skill": _skill(plan), "realization": realization,
                        "verification_seed_oracle": verification_seed, **cache[cache_key],
                        "evaluator_only": True,
                    })
        first_by_method = {method: cache[(_plan_key(plans[method]), 0)] for method in METHODS}
        for method in METHODS:
            selected = method_skills[method]
            first = first_by_method[method]
            cost = int(initial.steps) + (probe_steps if method in {EVIDENCE, BRIDGE, FULL} and probe_requested else 0) + int(first["steps"])
            if cost > int(config["budget"]["total_online_case_max_steps"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("method exceeded total online case budget")
            items = episode_retrievals.get(method, ())
            decisions.append({
                "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"], "episode_id": episode_id,
                "seed": seed, "method": method, "condition_id_oracle": fault.condition_id,
                "mechanism_oracle": mechanism, "mechanism_prediction": (
                    str(passive.mechanism) if method in {BASELINE, MEMORY} else active_belief
                ),
                "probe_requested": probe_requested if method in {EVIDENCE, BRIDGE, FULL} else False,
                "evidence_steps": probe_steps if method in {EVIDENCE, BRIDGE, FULL} and probe_requested else 0,
                "retrieval_count": len(items), "proposal_skill": full_proposal if method == FULL else selected,
                "selected_skill": selected, "verifier_eligible": method == FULL,
                "valid_proposal": method == FULL and full_proposal in REGISTERED_SKILLS,
                "proposal_action_signature_id": _plan_key(full_proposal_plan) if method == FULL else _plan_key(plans[method]),
                "selected_action_signature_id": _plan_key(plans[method]),
                "verifier_invoked": method == FULL and verifier.invoked,
                "proposal_probability": verifier.proposal_probability if method == FULL else None,
                "alternative_probability": verifier.alternative_probability if method == FULL else None,
                "verifier_reason": verifier.reason if method == FULL else "NOT_APPLICABLE",
                "verification_status": first["verification_status"],
                "verification_steps": first["steps"], "total_online_steps": cost,
                "final_object_goal_distance": first["final_object_goal_distance"],
            })
            for item in items:
                retrievals.append({
                    "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
                    "episode_id": episode_id, "method": method, "record_id": item.record_id,
                    "owner_method": item.owner_method, "source_episode_id": item.source_episode_id,
                    "available_from_episode_id": item.available_from_episode_id,
                    "distance": item.distance, "similarity": item.similarity,
                    "historical_status": item.observed_status,
                    "source_mechanism_oracle": record_mechanisms[item.record_id],
                    "current_mechanism_oracle": mechanism,
                    "mechanism_consistent_evaluator_only": record_mechanisms[item.record_id] == mechanism,
                    "evaluator_only": True,
                })
        sequence += 1
        outcome_sequence = sequence
        for method in (MEMORY, BRIDGE, FULL):
            first = first_by_method[method]
            record = ExperimentMemoryRecord(
                record_id=f"{method.lower()}_episode{episode_id}", owner_method=method,
                source_episode_id=episode_id, available_from_episode_id=episode_id + 1,
                signature=signature, selected_skill=method_skills[method],
                observed_status=str(first["verification_status"]),
                outcome_completed_sequence=outcome_sequence,
            )
            record_mechanisms[record.record_id] = mechanism
            if record.observed_status == "ACCEPTED":
                memories[method].append(record)
            if method == FULL:
                full_statistical_records.append(record)
            memory_records.append({
                "record_id": record.record_id, "owner_method": record.owner_method,
                "source_episode_id": record.source_episode_id,
                "available_from_episode_id": record.available_from_episode_id,
                "selected_skill": record.selected_skill, "observed_status": record.observed_status,
                "actionable_memory_write": record.observed_status == "ACCEPTED",
                "statistical_verifier_record": method == FULL,
                "outcome_completed_sequence": outcome_sequence,
            })
        _flush(run_dir, population=population, decisions=decisions, outcomes=outcomes,
               retrievals=retrievals, records=memory_records, timeline=timeline)
        _write_json(status_path, {
            "status": "RUNNING", "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"],
            "initial_units": initial_units, "operational_cases": operational, **integrity,
        })
        print(f"episode={episode_id} seed={seed} condition={fault.condition_id} operational={operational}", flush=True)
    final_status = "COMPLETED" if operational >= int(config["target_operational_cases"]) else "INCOMPLETE_POPULATION"
    by_condition = {
        condition: sum(row["operational"] and row["condition_id_oracle"] == condition for row in population)
        for condition in config["condition_cycle"]
    }
    by_mechanism = {
        mechanism: sum(row["operational"] and row["mechanism_oracle"] == mechanism for row in population)
        for mechanism in sorted(set(config["mechanism_by_condition"].values()))
    }
    targets = config["population_descriptive_targets"]
    imbalance = (
        any(value < int(targets["minimum_per_condition"]) for value in by_condition.values())
        or any(value < int(targets["minimum_per_major_mechanism"]) for value in by_mechanism.values())
    )
    if final_status == "COMPLETED" and imbalance:
        final_status = "COMPLETED_WITH_POPULATION_IMBALANCE"
    summary = {
        "status": final_status, "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"],
        "initial_units": initial_units, "operational_cases": operational,
        "population_by_condition": by_condition, "population_by_mechanism": by_mechanism,
        "descriptive_population_imbalance": imbalance, **integrity,
    }
    _write_json(run_dir / "summary.json", summary)
    _write_json(status_path, summary)
    return 0 if final_status.startswith("COMPLETED") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        return run(args.manifest.resolve())
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
