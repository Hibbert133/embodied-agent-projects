"""Shared leakage-safe collector for Calibrated Verifier v2 stages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mixed_regime_tuning import MixedRegime  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible, _write_csv, _write_json  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.probemem.compact_evidence import build_compact_causal_evidence  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory  # noqa: E402
from src.probemem_verifier.applicability import ApplicabilityThresholds  # noqa: E402
from src.probemem_verifier.calibrated_override_guard import CalibratedGuardThresholds  # noqa: E402
from src.probemem_verifier.calibrated_policy import WeightedPolicyDecision, WeightedVerifierPolicy  # noqa: E402
from src.probemem_verifier.online_policy import BudgetedVerifierPolicy, PolicyDecision  # noqa: E402
from src.probemem_verifier.weighted_posterior import QueryConditionedCalibratedVerifier  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402

FROZEN = "FROZEN_DETERMINISTIC"
UNWEIGHTED = "UNWEIGHTED_VERIFIER_V1"
WEIGHTED = "WEIGHTED_POSTERIOR_V1_GUARD"
CALIBRATED = "CALIBRATED_SELECTIVE_VERIFIER_V2"
ORACLE = "EVALUATOR_ONLY_ORACLE"
COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def run_stage(manifest_path: Path, *, expected_stage: str) -> int:
    manifest, config = _validate(manifest_path.resolve(), expected_stage)
    run_dir = manifest_path.resolve().parent
    status_path = run_dir / "run_status.json"
    if status_path.exists():
        raise FileExistsError("calibrated verifier run cannot overwrite or restart a manifest")
    _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
    bootstrap = _load_bootstrap(ROOT / config["memory"]["bootstrap_records"])
    methods = [FROZEN, UNWEIGHTED, WEIGHTED]
    if expected_stage == "prospective_development":
        methods.append(CALIBRATED)
    memories = {method: RegimeActionMemory(bootstrap) for method in methods}
    policies = _policies(config, expected_stage)
    regimes = {row["regime_id"]: MixedRegime(row["regime_id"], tuple(row["bias"]), float(row["noise_std"])) for row in config["regimes"]}
    recovery = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8")))
    population: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    memory_records: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    integrity = {name: 0 for name in ("chronology_violations", "oracle_leakage_events", "budget_violations", "random_namespace_violations", "future_memory_access", "counterfactual_memory_writes", "invalid_memory_ids", "invalid_skill_executions")}
    operational = 0
    initial_units = 0
    sequence = 0
    for unit in manifest["population_units"]:
        if operational >= int(config["target_operational_cases"]):
            break
        initial_units += 1
        seed = int(unit["environment_seed"])
        regime = regimes[str(unit["regime_id_oracle"])]
        if len({int(unit["initial_perturbation_seed"]), int(unit["diagnostic_probe_seed"]), int(unit["paired_verification_seed"])}) != 3:
            integrity["random_namespace_violations"] += 1
            raise RuntimeError("random namespaces overlap")
        trajectory = run_dir / "initial_trajectories" / f"unit{unit['unit_id']:03d}_seed{seed}.jsonl"
        trajectory.parent.mkdir(parents=True, exist_ok=True)
        env = create_push_environment(seed)
        try:
            initial = run_episode(env, create_push_policy(), seed=seed, episode_id=int(unit["unit_id"]), max_steps=int(config["budget"]["initial_max_steps"]), perturbation=regime.build(), perturbation_seed=int(unit["initial_perturbation_seed"]), agent_trajectory_path=trajectory)
        finally:
            env.close()
        state = build_structured_evidence_state(_read_jsonl(trajectory), evidence_id=f"calibrated_unit{unit['unit_id']:03d}_attempt0", source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0)
        population_row = {"unit_id": unit["unit_id"], "seed": seed, "regime_id_oracle": unit["regime_id_oracle"], "initial_success": not state.decision_required, "decision_required": state.decision_required, "eligible": False, "ineligibility_reason": ""}
        if not state.decision_required:
            population.append(population_row)
            _flush(run_dir, population, decisions, outcomes, memory_records, episodes, timeline)
            continue
        probe = _probe_context(regime, seed, config, int(unit["diagnostic_probe_seed"]))
        if not _compensation_is_constructible(seed=seed, probe_context=probe, recovery_config=recovery):
            population_row["ineligibility_reason"] = "BOUNDED_COMPENSATION_NOT_CONSTRUCTIBLE"
            population.append(population_row)
            _flush(run_dir, population, decisions, outcomes, memory_records, episodes, timeline)
            continue
        population_row["eligible"] = True
        population.append(population_row)
        operational += 1
        episode_id = int(config["first_online_episode_id"]) + operational - 1
        agent_evidence = {
            "evidence_id": f"calibrated_episode{episode_id:03d}_attempt1", "episode_id": episode_id,
            "initial_evidence": {**state.to_dict(), "episode_id": episode_id, "evidence_id": f"calibrated_episode{episode_id:03d}_attempt0"},
            "registered_probe_evidence": probe,
            "remaining_verification_budget": int(config["budget"]["verification_max_steps"]),
        }
        validate_no_oracle_evidence(agent_evidence)
        build_compact_causal_evidence(agent_evidence)
        signature = ProbeRegimeSignature.from_agent_evidence(agent_evidence)
        score = float(probe["consistency"]["estimated_bias_std_norm"])
        method_decisions: dict[str, PolicyDecision | WeightedPolicyDecision] = {}
        for method in methods:
            method_decisions[method] = policies[method].decide(score=score, signature=signature, memory=memories[method], episode_id=episode_id)
            sequence += 1
            timeline.append({"sequence": sequence, "episode_id": episode_id, "event": "FINAL_SELECTION_WRITTEN", "method": method, "selected_skill": method_decisions[method].override.final_skill})
        sequence += 1
        timeline.append({"sequence": sequence, "episode_id": episode_id, "event": "CANDIDATE_EXECUTION_STARTED", "evaluator_only": True})
        candidate_results: dict[str, tuple[Any, dict[str, Any]]] = {}
        episode_outcomes: dict[str, dict[str, Any]] = {}
        for skill in (COMP, RETRY):
            result, execution = _run_verification(seed=seed, fault=regime, skill=skill, probe_context=probe, recovery_config=recovery, perturbation_seed=int(unit["paired_verification_seed"]), max_steps=int(config["budget"]["verification_max_steps"]), initial_distance=initial.final_object_goal_distance)
            candidate_results[skill.value] = (result, execution)
            row = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "episode_id": episode_id, "seed": seed, "candidate_skill": skill.value, "verification_status": execution["verification_status"], "steps": result.steps, "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance, "final_object_goal_distance": result.final_object_goal_distance, "evaluator_only": True}
            outcomes.append(row)
            episode_outcomes[skill.value] = row
        sequence += 1
        timeline.append({"sequence": sequence, "episode_id": episode_id, "event": "FRESH_VERIFICATION_COMPLETED", "evaluator_only": True})
        for method in methods:
            decision = method_decisions[method]
            selected = decision.override.final_skill
            if selected not in {COMP.value, RETRY.value}:
                integrity["invalid_skill_executions"] += 1
                raise RuntimeError("invalid skill execution")
            result, execution = candidate_results[selected]
            case_steps = initial.steps + int(probe["probe_environment_steps"]) + result.steps
            if case_steps > int(config["budget"]["total_case_max_steps"]):
                integrity["budget_violations"] += 1
                raise RuntimeError("case budget exceeded")
            prediction = _selected_prediction(decision, selected)
            decisions.append(_decision_row(manifest, episode_id, seed, method, decision, execution["verification_status"], result.final_object_goal_distance, initial.final_object_goal_distance - result.final_object_goal_distance, case_steps))
            record = RegimeActionExperience(1, f"{method.lower()}_episode{episode_id}", episode_id, episode_id + 1, signature, InterventionSkill(selected), prediction[0], prediction[1], str(execution["verification_status"]), initial.final_object_goal_distance - result.final_object_goal_distance, result.final_object_goal_distance, result.steps, manifest["experiment_run_id"], manifest["manifest_id"], f"{method}_SELECTED_ACTION_ONLY")
            memories[method].append_after_verification(record)
            memory_records.append({"method": method, **record.to_dict()})
            sequence += 1
            timeline.append({"sequence": sequence, "episode_id": episode_id, "event": "MEMORY_APPEND", "method": method, "selected_skill": selected, "record_id": record.record_id})
        oracle_skill = _oracle(candidate_results, initial.final_object_goal_distance)
        oracle_result, oracle_execution = candidate_results[oracle_skill]
        default = method_decisions[FROZEN].proposal.selected_skill
        decisions.append({"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "episode_id": episode_id, "seed": seed, "method": ORACLE, "default_skill": default, "final_skill": oracle_skill, "verifier_called": False, "override_applied": oracle_skill != default, "override_reason": "EVALUATOR_ONLY_UPPER_BOUND", "verification_status": oracle_execution["verification_status"], "final_object_goal_distance": oracle_result.final_object_goal_distance, "environment_steps": initial.steps + int(probe["probe_environment_steps"]) + oracle_result.steps, "evaluator_only": True})
        episodes.append({"episode_id": episode_id, "seed": seed, "score": score, "signature": signature.to_dict(), "initial_distance": initial.final_object_goal_distance, "initial_steps": initial.steps, "probe_steps": int(probe["probe_environment_steps"]), "candidate_outcomes": episode_outcomes})
        _flush(run_dir, population, decisions, outcomes, memory_records, episodes, timeline)
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"], "initial_units": initial_units, "operational_cases": operational, **integrity})
        print(f"stage={expected_stage} episode={episode_id} seed={seed} operational={operational}", flush=True)
    exclusive = _exclusive_count(outcomes)
    complete = operational >= int(config["minimum_operational_cases"]) and exclusive >= int(config["minimum_exclusive_recovery_cases"])
    summary = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "stage": expected_stage, "initial_units": initial_units, "operational_cases": operational, "exclusive_recovery_cases": exclusive, **integrity}
    _write_json(run_dir / "summary.json", summary)
    _write_json(status_path, {"status": "COMPLETED" if complete else "INCOMPLETE_POPULATION", **summary})
    return 0 if complete else 2


def _policies(config: dict[str, Any], stage: str) -> dict[str, Any]:
    posterior = config["posterior"]
    verifier = QueryConditionedCalibratedVerifier(top_k=int(posterior["top_k"]), recent_count=int(posterior["recent_count"]), prior_alpha=float(posterior["prior_alpha"]), prior_beta=float(posterior["prior_beta"]), credible_level=float(posterior["credible_level"]))
    policies: dict[str, Any] = {
        FROZEN: BudgetedVerifierPolicy(mode="frozen_deterministic"),
        UNWEIGHTED: BudgetedVerifierPolicy(mode="budgeted_verifier"),
        WEIGHTED: WeightedVerifierPolicy(mode="weighted_v1_guard", stage=stage, comparison_seed=int(posterior["comparison_seed"]), verifier=verifier),
    }
    if stage == "prospective_development":
        thresholds = config["frozen_thresholds"]
        policies[CALIBRATED] = WeightedVerifierPolicy(
            mode="calibrated_v2", stage=stage, comparison_seed=int(posterior["comparison_seed"]), verifier=verifier,
            applicability_thresholds=ApplicabilityThresholds(float(thresholds["minimum_effective_sample_size"]), float(thresholds["maximum_nearest_distance"]), float(thresholds["minimum_weighted_coverage"]), float(thresholds["maximum_weighted_contradiction_rate"])),
            guard_thresholds=CalibratedGuardThresholds(float(thresholds["minimum_superiority_probability"]), float(thresholds["minimum_expected_utility_gain"]), float(thresholds["minimum_effective_sample_size"])),
        )
    return policies


def _selected_prediction(decision: PolicyDecision | WeightedPolicyDecision, selected: str) -> tuple[str | None, float | None]:
    if isinstance(decision, PolicyDecision):
        value = decision.candidate_verifications.get(selected)
        return (None, None) if value is None else (value.predicted_status, value.predicted_accept_probability)
    if selected in decision.v1_candidate_verifications:
        value = decision.v1_candidate_verifications[selected]
        return value.predicted_status, value.predicted_accept_probability
    return None, None


def _decision_row(manifest: dict[str, Any], episode: int, seed: int, method: str, decision: Any, status: str, distance: float, progress: float, steps: int) -> dict[str, Any]:
    return {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "source_git_commit": manifest["source_git_commit"], "episode_id": episode, "seed": seed, "method": method, "score": decision.proposal.score, "threshold": decision.proposal.threshold, "confidence_margin": decision.proposal.confidence_margin, "admission_reasons": "|".join(decision.admission.reasons), "memory_conflict": decision.memory_signals.memory_conflict, "memory_coverage": decision.memory_signals.memory_coverage, "recent_contradiction": decision.memory_signals.recent_contradiction, "default_skill": decision.override.default_skill, "final_skill": decision.override.final_skill, "verifier_called": decision.override.verifier_called, "override_applied": decision.override.override_applied, "override_reason": decision.override.override_reason, "default_probability": decision.override.default_probability, "alternative_probability": decision.override.alternative_probability, "verifier_latency_ms": decision.verifier_latency_ms, "decision_audit_json": json.dumps(decision.to_dict(), sort_keys=True), "verification_status": status, "final_object_goal_distance": distance, "observed_progress": progress, "environment_steps": steps, "evaluator_only": False}


def _flush(run_dir: Path, population: list, decisions: list, outcomes: list, memory: list, episodes: list, timeline: list) -> None:
    _write_csv(run_dir / "population.csv", population)
    _write_csv(run_dir / "decisions.csv", decisions)
    _write_csv(run_dir / "candidate_outcomes.csv", outcomes)
    _write_json(run_dir / "operational_memory_records.json", memory)
    _write_json(run_dir / "episodes.json", episodes)
    _write_json(run_dir / "timeline.json", timeline)


def _oracle(results: dict[str, tuple[Any, dict[str, Any]]], initial_distance: float) -> str:
    order = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0}
    return max(results, key=lambda skill: (order[str(results[skill][1]["verification_status"])], initial_distance - results[skill][0].final_object_goal_distance, -results[skill][0].steps, skill))


def _exclusive_count(rows: list[dict[str, Any]]) -> int:
    by_episode: dict[int, list[str]] = {}
    for row in rows:
        by_episode.setdefault(int(row["episode_id"]), []).append(str(row["verification_status"]))
    return sum(values.count("ACCEPTED") == 1 for values in by_episode.values())


def _load_bootstrap(path: Path) -> tuple[RegimeActionExperience, ...]:
    return tuple(RegimeActionExperience.from_dict(row) for row in json.loads(path.read_text(encoding="utf-8")))


def _validate(path: Path, expected_stage: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"] or manifest["stage"] != expected_stage or _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("manifest identity mismatch")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("run requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha(config_path) != manifest["config_sha256"]:
        raise RuntimeError("config changed after manifest")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha(ROOT / relative) != expected:
                raise RuntimeError(f"manifest-bound source changed: {relative}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if expected_stage == "prospective_development":
        base = json.loads((ROOT / "configs/probemem_verifier/calibrated_v2_calibration.json").read_text(encoding="utf-8"))
        config = {**base, **config}
    if _sha(ROOT / config["memory"]["bootstrap_records"]) != config["memory"]["bootstrap_records_sha256"]:
        raise RuntimeError("bootstrap memory hash mismatch")
    return manifest, config


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
