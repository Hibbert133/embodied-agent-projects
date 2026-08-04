"""Run the shared paired ProbeMem history-aware verifier Demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mixed_regime_tuning import MixedRegime  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible, _sha256, _write_csv, _write_json  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.probemem.compact_evidence import build_compact_causal_evidence  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory  # noqa: E402
from src.probemem_verifier.online_policy import BudgetedVerifierPolicy, PolicyDecision  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


FROZEN = "FROZEN_DETERMINISTIC"
ALWAYS = "ALWAYS_ON_VERIFIER"
BUDGETED = "BUDGETED_VERIFIER"
ORACLE = "EVALUATOR_ONLY_ORACLE"
OPERATIONAL_METHODS = (FROZEN, ALWAYS, BUDGETED)
MODE_BY_METHOD = {
    FROZEN: "frozen_deterministic",
    ALWAYS: "always_on_verifier",
    BUDGETED: "budgeted_verifier",
}
COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/probemem_verifier/demo_v1.json")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--method", choices=("all",), default="all")
    parser.add_argument("--verifier", choices=("deterministic", "glm"), default="deterministic")
    args = parser.parse_args()
    manifest: dict[str, Any] | None = None
    status_path: Path | None = None
    try:
        if args.smoke:
            return _synthetic_smoke(args.config.resolve(), args.verifier)
        if args.manifest is None:
            raise ValueError("--manifest is required unless --smoke is used")
        if args.verifier != "deterministic":
            raise RuntimeError("registered Demo manifest permits deterministic verifier only")
        manifest, config = _validate(args.manifest.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("verifier Demo run cannot overwrite or restart a manifest")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        bootstrap = _load_bootstrap(ROOT / config["memory"]["bootstrap_records"])
        memories = {method: RegimeActionMemory(bootstrap) for method in OPERATIONAL_METHODS}
        policies = {
            method: BudgetedVerifierPolicy(
                mode=MODE_BY_METHOD[method],
                ambiguity_margin=float(config["admission"]["ambiguity_margin"]),
                probability_margin_minimum=float(config["override_guard"]["probability_margin_minimum"]),
                coverage_minimum=int(config["override_guard"]["alternative_coverage_minimum"]),
                contradiction_rate_maximum=float(config["override_guard"]["alternative_contradiction_rate_maximum"]),
                confidence_minimum=float(config["override_guard"]["verifier_confidence_minimum"]),
            )
            for method in OPERATIONAL_METHODS
        }
        regimes = {
            row["regime_id"]: MixedRegime(row["regime_id"], tuple(row["bias"]), float(row["noise_std"]))
            for row in config["regimes"]
        }
        recovery = RecoveryPolicyConfig.from_mapping(
            json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
        )
        population: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        memory_records: list[dict[str, Any]] = []
        resonance: list[dict[str, Any]] = []
        timeline: list[dict[str, Any]] = []
        sequence = 0
        integrity = {name: 0 for name in (
            "chronology_violations", "oracle_leakage_events", "budget_violations",
            "random_namespace_violations", "future_memory_access", "counterfactual_memory_writes",
            "invalid_memory_ids", "invalid_skill_executions",
        )}
        operational = 0
        initial_units = 0
        for unit in manifest["population_units"]:
            if operational >= int(config["target_operational_cases"]):
                break
            initial_units += 1
            seed = int(unit["environment_seed"])
            regime = regimes[str(unit["regime_id_oracle"])]
            namespaces = {
                int(unit["initial_perturbation_seed"]), int(unit["diagnostic_probe_seed"]),
                int(unit["paired_verification_seed"]),
            }
            if len(namespaces) != 3:
                integrity["random_namespace_violations"] += 1
                raise RuntimeError("verifier Demo random namespaces overlap")
            trajectory = run_dir / "initial_trajectories" / f"unit{unit['unit_id']:03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, episode_id=int(unit["unit_id"]),
                    max_steps=int(config["budget"]["initial_max_steps"]), perturbation=regime.build(),
                    perturbation_seed=int(unit["initial_perturbation_seed"]), agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory), evidence_id=f"verifier_unit{unit['unit_id']:03d}_attempt0",
                source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            )
            population_row = {
                "unit_id": unit["unit_id"], "seed": seed,
                "regime_id_oracle": unit["regime_id_oracle"],
                "initial_success": not state.decision_required,
                "decision_required": state.decision_required,
                "eligible": False, "ineligibility_reason": "",
            }
            if not state.decision_required:
                population.append(population_row)
                _flush(run_dir, population, decisions, outcomes, memory_records, resonance, timeline)
                continue
            probe = _probe_context(regime, seed, config, int(unit["diagnostic_probe_seed"]))
            if not _compensation_is_constructible(seed=seed, probe_context=probe, recovery_config=recovery):
                population_row["ineligibility_reason"] = "BOUNDED_COMPENSATION_NOT_CONSTRUCTIBLE"
                population.append(population_row)
                _flush(run_dir, population, decisions, outcomes, memory_records, resonance, timeline)
                continue
            population_row["eligible"] = True
            population.append(population_row)
            operational += 1
            episode_id = int(config["first_online_episode_id"]) + operational - 1
            agent_evidence = {
                "evidence_id": f"verifier_episode{episode_id:03d}_attempt1", "episode_id": episode_id,
                "initial_evidence": {
                    **state.to_dict(), "episode_id": episode_id,
                    "evidence_id": f"verifier_episode{episode_id:03d}_attempt0",
                },
                "registered_probe_evidence": probe,
                "remaining_verification_budget": int(config["budget"]["verification_max_steps"]),
            }
            validate_no_oracle_evidence(agent_evidence)
            compact = build_compact_causal_evidence(agent_evidence)
            signature = ProbeRegimeSignature.from_agent_evidence(agent_evidence)
            score = float(probe["consistency"]["estimated_bias_std_norm"])
            sequence += 1
            timeline.append(_event(sequence, episode_id, "EVIDENCE_BUILT"))
            method_decisions: dict[str, PolicyDecision] = {}
            for method in OPERATIONAL_METHODS:
                method_decisions[method] = policies[method].decide(
                    score=score, signature=signature, memory=memories[method], episode_id=episode_id,
                )
                sequence += 1
                timeline.append(_event(
                    sequence, episode_id, "FINAL_SELECTION_WRITTEN", method=method,
                    selected_skill=method_decisions[method].override.final_skill,
                ))
            sequence += 1
            timeline.append(_event(sequence, episode_id, "CANDIDATE_EXECUTION_STARTED", evaluator_only=True))
            candidate_results: dict[str, tuple[Any, dict[str, Any]]] = {}
            for skill in (COMP, RETRY):
                result, execution = _run_verification(
                    seed=seed, fault=regime, skill=skill, probe_context=probe,
                    recovery_config=recovery, perturbation_seed=int(unit["paired_verification_seed"]),
                    max_steps=int(config["budget"]["verification_max_steps"]),
                    initial_distance=initial.final_object_goal_distance,
                )
                candidate_results[skill.value] = (result, execution)
                outcomes.append({
                    "experiment_run_id": manifest["experiment_run_id"],
                    "manifest_id": manifest["manifest_id"],
                    "source_git_commit": manifest["source_git_commit"],
                    "episode_id": episode_id, "seed": seed, "candidate_skill": skill.value,
                    "verification_status": execution["verification_status"], "steps": result.steps,
                    "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance,
                    "final_object_goal_distance": result.final_object_goal_distance,
                    "evaluator_only": True,
                })
            sequence += 1
            timeline.append(_event(sequence, episode_id, "FRESH_VERIFICATION_COMPLETED", evaluator_only=True))
            oracle_skill = _oracle(candidate_results, initial.final_object_goal_distance)
            for method in OPERATIONAL_METHODS:
                policy_decision = method_decisions[method]
                selected = policy_decision.override.final_skill
                if selected not in {COMP.value, RETRY.value}:
                    integrity["invalid_skill_executions"] += 1
                    raise RuntimeError("invalid registered skill execution")
                result, execution = candidate_results[selected]
                selected_prediction = policy_decision.candidate_verifications.get(selected)
                case_steps = initial.steps + int(probe["probe_environment_steps"]) + result.steps
                if case_steps > int(config["budget"]["total_case_max_steps"]):
                    integrity["budget_violations"] += 1
                    raise RuntimeError("verifier Demo exceeded total case budget")
                decisions.append(_decision_row(
                    manifest, episode_id, seed, method, policy_decision,
                    str(execution["verification_status"]), result, initial, case_steps,
                ))
                record = RegimeActionExperience(
                    schema_version=1,
                    record_id=f"{method.lower()}_episode{episode_id}",
                    episode_id=episode_id,
                    available_from_episode_id=episode_id + 1,
                    probe_signature=signature,
                    selected_skill=InterventionSkill(selected),
                    predicted_status=None if selected_prediction is None else selected_prediction.predicted_status,
                    predicted_accept_probability=None if selected_prediction is None else selected_prediction.predicted_accept_probability,
                    observed_status=str(execution["verification_status"]),
                    observed_progress=initial.final_object_goal_distance - result.final_object_goal_distance,
                    observed_final_distance=result.final_object_goal_distance,
                    interaction_cost=result.steps,
                    source_run_id=manifest["experiment_run_id"],
                    source_manifest_id=manifest["manifest_id"],
                    record_origin=f"{method}_SELECTED_ACTION_ONLY",
                )
                memories[method].append_after_verification(record)
                memory_records.append({"method": method, **record.to_dict()})
                resonance.append({
                    "method": method, "episode_id": episode_id, "selected_skill": selected,
                    "prediction_available": selected_prediction is not None,
                    "predicted_status": None if selected_prediction is None else selected_prediction.predicted_status,
                    "predicted_accept_probability": None if selected_prediction is None else selected_prediction.predicted_accept_probability,
                    "observed_status": execution["verification_status"],
                    "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance,
                    "matched": None if selected_prediction is None else selected_prediction.predicted_status == execution["verification_status"],
                })
                sequence += 1
                timeline.append(_event(
                    sequence, episode_id, "MEMORY_APPEND", method=method,
                    selected_skill=selected, record_id=record.record_id,
                ))
            oracle_result, oracle_execution = candidate_results[oracle_skill]
            decisions.append({
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
                "episode_id": episode_id, "seed": seed, "method": ORACLE,
                "default_skill": method_decisions[FROZEN].proposal.selected_skill,
                "final_skill": oracle_skill, "verifier_called": False,
                "override_applied": oracle_skill != method_decisions[FROZEN].proposal.selected_skill,
                "override_reason": "EVALUATOR_ONLY_UPPER_BOUND",
                "verification_status": oracle_execution["verification_status"],
                "final_object_goal_distance": oracle_result.final_object_goal_distance,
                "environment_steps": initial.steps + int(probe["probe_environment_steps"]) + oracle_result.steps,
                "evaluator_only": True,
            })
            _flush(run_dir, population, decisions, outcomes, memory_records, resonance, timeline)
            _write_json(status_path, {
                "status": "RUNNING", "manifest_id": manifest["manifest_id"],
                "initial_units": initial_units, "operational_cases": operational, **integrity,
            })
            print(f"episode={episode_id} seed={seed} operational={operational}", flush=True)
        summary = {
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"], "initial_units": initial_units,
            "operational_cases": operational,
            "minimum_operational_cases": int(config["minimum_operational_cases"]),
            "target_operational_cases": int(config["target_operational_cases"]),
            **integrity,
        }
        final_status = "COMPLETED" if operational >= int(config["minimum_operational_cases"]) else "INCOMPLETE_POPULATION"
        _write_json(run_dir / "summary.json", summary)
        _write_json(status_path, {"status": final_status, **summary})
        print(f"run: {run_dir}")
        return 0 if final_status == "COMPLETED" else 2
    except Exception as exc:
        if manifest is not None and status_path is not None:
            _write_json(status_path, {
                "status": "FAILED", "manifest_id": manifest["manifest_id"],
                "error_type": type(exc).__name__, "error": str(exc),
            })
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _decision_row(
    manifest: dict[str, Any], episode_id: int, seed: int, method: str,
    decision: PolicyDecision, status: str, result: Any, initial: Any, case_steps: int,
) -> dict[str, Any]:
    return {
        "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"], "episode_id": episode_id, "seed": seed,
        "method": method, "score": decision.proposal.score, "threshold": decision.proposal.threshold,
        "confidence_margin": decision.proposal.confidence_margin,
        "admission_reasons": "|".join(decision.admission.reasons),
        "memory_conflict": decision.memory_signals.memory_conflict,
        "memory_coverage": decision.memory_signals.memory_coverage,
        "recent_contradiction": decision.memory_signals.recent_contradiction,
        "default_skill": decision.override.default_skill, "final_skill": decision.override.final_skill,
        "verifier_called": decision.override.verifier_called, "override_applied": decision.override.override_applied,
        "override_reason": decision.override.override_reason,
        "default_probability": decision.override.default_probability,
        "alternative_probability": decision.override.alternative_probability,
        "verifier_latency_ms": decision.verifier_latency_ms,
        "candidate_summaries_json": json.dumps({key: value.to_dict() for key, value in decision.candidate_summaries.items()}, sort_keys=True),
        "candidate_verifications_json": json.dumps({key: value.to_dict() for key, value in decision.candidate_verifications.items()}, sort_keys=True),
        "verification_status": status, "final_object_goal_distance": result.final_object_goal_distance,
        "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance,
        "environment_steps": case_steps, "evaluator_only": False,
    }


def _event(sequence: int, episode_id: int, event: str, **extra: Any) -> dict[str, Any]:
    return {"sequence": sequence, "episode_id": episode_id, "event": event, **extra}


def _flush(
    run_dir: Path, population: list[dict[str, Any]], decisions: list[dict[str, Any]],
    outcomes: list[dict[str, Any]], memory_records: list[dict[str, Any]],
    resonance: list[dict[str, Any]], timeline: list[dict[str, Any]],
) -> None:
    _write_csv(run_dir / "population.csv", population)
    _write_csv(run_dir / "decisions.csv", decisions)
    _write_csv(run_dir / "candidate_outcomes.csv", outcomes)
    _write_json(run_dir / "operational_memory_records.json", memory_records)
    _write_json(run_dir / "resonance.json", resonance)
    _write_json(run_dir / "timeline.json", timeline)


def _oracle(results: dict[str, tuple[Any, dict[str, Any]]], initial_distance: float) -> str:
    order = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0}
    return max(results, key=lambda skill: (
        order[str(results[skill][1]["verification_status"])],
        initial_distance - results[skill][0].final_object_goal_distance,
        -results[skill][0].steps, skill,
    ))


def _load_bootstrap(path: Path) -> tuple[RegimeActionExperience, ...]:
    return tuple(RegimeActionExperience.from_dict(row) for row in json.loads(path.read_text(encoding="utf-8")))


def _synthetic_smoke(config_path: Path, verifier_mode: str) -> int:
    if verifier_mode != "deterministic":
        raise RuntimeError("synthetic registered smoke uses deterministic verifier")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    bootstrap = _load_bootstrap(ROOT / config["memory"]["bootstrap_records"])
    memories = {method: RegimeActionMemory(bootstrap) for method in OPERATIONAL_METHODS}
    policies = {
        method: BudgetedVerifierPolicy(
            mode=MODE_BY_METHOD[method],
            ambiguity_margin=float(config["admission"]["ambiguity_margin"]),
            probability_margin_minimum=float(config["override_guard"]["probability_margin_minimum"]),
            coverage_minimum=int(config["override_guard"]["alternative_coverage_minimum"]),
            contradiction_rate_maximum=float(config["override_guard"]["alternative_contradiction_rate_maximum"]),
            confidence_minimum=float(config["override_guard"]["verifier_confidence_minimum"]),
        )
        for method in OPERATIONAL_METHODS
    }
    scores = (0.01, 0.10, 0.11560838098372882, 0.14, 0.30)
    audit = []
    for offset, score in enumerate(scores):
        episode_id = int(config["first_online_episode_id"]) + offset
        signature = ProbeRegimeSignature(
            1, f"synthetic-smoke-{episode_id}", episode_id,
            (0.01 * offset, 0.0, 0.01 * offset, score, 0.8, 0.1, 0.2, 0.3),
        )
        decisions = {
            method: policies[method].decide(
                score=score, signature=signature, memory=memories[method], episode_id=episode_id,
            )
            for method in OPERATIONAL_METHODS
        }
        for method, decision in decisions.items():
            selected = decision.override.final_skill
            observed = "ACCEPTED" if (offset + (selected == RETRY.value)) % 2 == 0 else "REJECTED"
            prediction = decision.candidate_verifications.get(selected)
            record = RegimeActionExperience(
                1, f"smoke-{method.lower()}-{episode_id}", episode_id, episode_id + 1,
                signature, InterventionSkill(selected),
                None if prediction is None else prediction.predicted_status,
                None if prediction is None else prediction.predicted_accept_probability,
                observed, 0.1, 0.2, 10, "synthetic-smoke", "synthetic-smoke", f"{method}_SELECTED_ACTION_ONLY",
            )
            if record.record_id in {item.record_id for item in memories[method].prior(episode_id)}:
                raise RuntimeError("synthetic smoke exposed current record before decision")
            memories[method].append_after_verification(record)
            audit.append({
                "episode_id": episode_id, "method": method,
                "default_skill": decision.proposal.selected_skill,
                "verifier_called": decision.override.verifier_called,
                "final_skill": selected, "observed_status": observed,
                "memory_size": len(memories[method].records),
            })
    print(json.dumps({"status": "SYNTHETIC_SMOKE_PASSED", "cases": len(scores), "audit": audit}, indent=2))
    return 0


def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"] or _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("verifier Demo manifest identity mismatch")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("verifier Demo run requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("verifier Demo config changed")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"verifier Demo source changed: {relative}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if _sha256(ROOT / config["memory"]["bootstrap_records"]) != config["memory"]["bootstrap_records_sha256"]:
        raise RuntimeError("bootstrap memory hash mismatch")
    return manifest, config


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
