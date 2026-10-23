"""Run the frozen ambiguity-gated ProbeMem-Online development protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mixed_regime_tuning import MixedRegime  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible, _sha256, _write_csv, _write_json  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.probemem.compact_evidence import build_compact_causal_evidence  # noqa: E402
from src.probemem.memory_resonance import ActionResonanceRecord  # noqa: E402
from src.probemem.memory_tools import retrieve_action_memory_payload  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem.online_glm_contract import EvidenceInterpretation, SkillPrediction  # noqa: E402
from src.probemem.online_memory_policy import OnlineMemoryDecision, OnlineMemoryGlmPolicy, build_online_memory_payload  # noqa: E402
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory  # noqa: E402
from src.probemem.selective_override import (  # noqa: E402
    ProbeAmbiguityAssessment,
    agreed_memory_preference,
    assess_probe_ambiguity,
    estimates_from_probe_context,
    guard_memory_override,
)
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY
FROZEN = "FROZEN_VARIANCE_RULE"
STATELESS = "AMBIGUITY_GATED_STATELESS_GLM"
FALLBACK = "AMBIGUITY_GATED_MEMORY_FALLBACK"
ABSTAIN = "AMBIGUITY_GATED_MEMORY_ABSTAIN"
ORACLE = "EVALUATOR_ONLY_ORACLE"
GLM_METHODS = (STATELESS, FALLBACK, ABSTAIN)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base-url", default=None)
    args = parser.parse_args()
    manifest: dict[str, Any] | None = None
    status_path: Path | None = None
    try:
        manifest, config = _validate(args.manifest.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("selective-override run cannot overwrite or restart a manifest")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        bootstrap = _load_bootstrap(ROOT / config["memory"]["bootstrap_records"])
        memories = {method: RegimeActionMemory(bootstrap) for method in (FALLBACK, ABSTAIN)}
        empty_memory = RegimeActionMemory()
        policy = OnlineMemoryGlmPolicy(
            model=config["glm"]["model"], base_url=args.base_url,
            timeout_seconds=float(config["glm"]["timeout_seconds"]),
            max_tokens=int(config["glm"]["max_tokens"]),
        )
        regimes = {
            row["regime_id"]: MixedRegime(row["regime_id"], tuple(row["bias"]), float(row["noise_std"]))
            for row in config["regimes"]
        }
        recovery = RecoveryPolicyConfig.from_mapping(
            json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
        )
        decisions: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        ambiguity_rows: list[dict[str, Any]] = []
        api_audit: list[dict[str, Any]] = []
        memory_records: list[dict[str, Any]] = []
        resonance_rows: list[dict[str, Any]] = []
        integrity = {name: 0 for name in (
            "chronology_violations", "oracle_leakage_events", "budget_violations",
            "random_namespace_violations", "future_memory_access", "counterfactual_memory_writes",
            "invalid_memory_ids", "invalid_skill_executions", "high_confidence_api_calls",
        )}
        operational = 0
        ambiguous_count = 0
        for unit in manifest["population_units"]:
            if operational >= int(config["target_operational_cases"]):
                break
            seed = int(unit["environment_seed"])
            regime = regimes[str(unit["regime_id_oracle"])]
            namespaces = {
                int(unit["initial_perturbation_seed"]), int(unit["diagnostic_probe_seed"]),
                int(unit["paired_verification_seed"]),
            }
            if len(namespaces) != 3:
                integrity["random_namespace_violations"] += 1
                raise RuntimeError("selective-override random namespaces overlap")
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
                _read_jsonl(trajectory), evidence_id=f"selective_unit{unit['unit_id']:03d}_attempt0",
                source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            )
            if not state.decision_required:
                continue
            probe = _probe_context(regime, seed, config, int(unit["diagnostic_probe_seed"]))
            if not _compensation_is_constructible(seed=seed, probe_context=probe, recovery_config=recovery):
                continue
            operational += 1
            episode_id = int(config["first_online_episode_id"]) + operational - 1
            agent_evidence = {
                "evidence_id": f"selective_episode{episode_id:03d}_attempt1", "episode_id": episode_id,
                "initial_evidence": {**state.to_dict(), "episode_id": episode_id, "evidence_id": f"selective_episode{episode_id:03d}_attempt0"},
                "registered_probe_evidence": probe,
                "remaining_verification_budget": int(config["budget"]["verification_max_steps"]),
            }
            validate_no_oracle_evidence(agent_evidence)
            compact = build_compact_causal_evidence(agent_evidence)
            signature = ProbeRegimeSignature.from_agent_evidence(agent_evidence)
            assessment = assess_probe_ambiguity(estimates_from_probe_context(probe))
            ambiguous_count += int(assessment.ambiguous)
            ambiguity_rows.append({
                "episode_id": episode_id, "seed": seed,
                "segment_id_oracle": unit["segment_id_oracle"], "regime_id_oracle": unit["regime_id_oracle"],
                **assessment.to_dict(),
            })
            decision_timestamp = time.perf_counter_ns()
            episode_decisions, host_audit = _decide(
                assessment=assessment, compact=compact.to_dict(), signature=signature,
                memories=memories, empty_memory=empty_memory, episode_id=episode_id,
                policy=policy, api_audit=api_audit,
            )
            if not assessment.ambiguous and any(row["api_called"] for row in host_audit.values()):
                integrity["high_confidence_api_calls"] += 1
                raise RuntimeError("high-confidence decision attempted an API call")
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
                    "episode_id": episode_id, "seed": seed, "candidate_skill": skill.value,
                    "verification_status": execution["verification_status"], "steps": result.steps,
                    "observed_progress": initial.final_object_goal_distance - result.final_object_goal_distance,
                    "final_object_goal_distance": result.final_object_goal_distance, "evaluator_only": True,
                })
            if time.perf_counter_ns() <= decision_timestamp:
                integrity["chronology_violations"] += 1
                raise RuntimeError("candidate outcomes preceded decisions")
            oracle_skill = _oracle(candidate_results, initial.final_object_goal_distance)
            selected_by_method = {method: decision.selected_skill for method, decision in episode_decisions.items()}
            selected_by_method[ORACLE] = oracle_skill
            for method in (FROZEN, STATELESS, FALLBACK, ABSTAIN, ORACLE):
                selected = selected_by_method[method]
                selected_result = None if selected is None else candidate_results[selected]
                status = "ABSTAIN" if selected_result is None else str(selected_result[1]["verification_status"])
                audit = host_audit.get(method, {})
                decisions.append({
                    "episode_id": episode_id, "seed": seed,
                    "segment_id_oracle": unit["segment_id_oracle"], "regime_id_oracle": unit["regime_id_oracle"],
                    "method": method, "ambiguous": assessment.ambiguous,
                    "deterministic_skill": assessment.full_action.value,
                    "glm_proposed_skill": audit.get("glm_proposed_skill"),
                    "memory_preference": audit.get("memory_preference"),
                    "override_authorized": audit.get("override_authorized", False),
                    "fallback_used": audit.get("fallback_used", False),
                    "api_called": audit.get("api_called", False),
                    "selected_skill": selected, "verification_status": status, "abstain": selected is None,
                })
                if method in (FALLBACK, ABSTAIN) and selected_result is not None:
                    model_decision = episode_decisions[method]
                    prediction = model_decision.action_predictions[selected]
                    result, execution = selected_result
                    record = RegimeActionExperience(
                        1, f"{method.lower()}_episode{episode_id}", episode_id, episode_id + 1,
                        signature, InterventionSkill(selected), prediction.predicted_status,
                        prediction.accept_probability, str(execution["verification_status"]),
                        initial.final_object_goal_distance - result.final_object_goal_distance,
                        result.final_object_goal_distance, result.steps, manifest["experiment_run_id"],
                        manifest["manifest_id"], "ONLINE_SELECTED_ACTION",
                    )
                    memories[method].append_after_verification(record)
                    memory_records.append({"method": method, **record.to_dict()})
                    probabilities = _status_probabilities(prediction)
                    resonance_rows.append({
                        "method": method,
                        **ActionResonanceRecord.create(
                            episode_id=episode_id, selected_skill=InterventionSkill(selected),
                            predicted_status=prediction.predicted_status, probabilities=probabilities,
                            observed_status=str(execution["verification_status"]),
                            observed_progress=initial.final_object_goal_distance - result.final_object_goal_distance,
                            supporting_memory_ids=model_decision.supporting_memory_ids,
                            contradicting_memory_ids=model_decision.contradicting_memory_ids,
                        ).to_dict(),
                    })
            _write_csv(run_dir / "decisions.csv", decisions)
            _write_csv(run_dir / "candidate_outcomes.csv", outcomes)
            _write_json(run_dir / "ambiguity_audit.json", ambiguity_rows)
            _write_json(run_dir / "api_audit.json", api_audit)
            _write_json(run_dir / "operational_memory_records.json", memory_records)
            _write_json(run_dir / "resonance.json", resonance_rows)
            _write_json(status_path, {
                "status": "RUNNING", "manifest_id": manifest["manifest_id"],
                "operational_cases": operational, "ambiguous_cases": ambiguous_count,
                "api_calls": len(api_audit), **integrity,
            })
            print(f"episode={episode_id} seed={seed} ambiguous={assessment.ambiguous} api_calls={len(api_audit)}", flush=True)
        summary = {
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"], "operational_cases": operational,
            "target_operational_cases": int(config["target_operational_cases"]),
            "ambiguous_cases": ambiguous_count, "minimum_ambiguous_cases": int(config["minimum_ambiguous_cases"]),
            "api_calls": len(api_audit), **integrity,
        }
        population_complete = operational == int(config["target_operational_cases"])
        ambiguity_complete = ambiguous_count >= int(config["minimum_ambiguous_cases"])
        final_status = "COMPLETED" if population_complete and ambiguity_complete else "INCOMPLETE_POPULATION"
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


def _decide(
    *, assessment: ProbeAmbiguityAssessment, compact: dict[str, Any], signature: ProbeRegimeSignature,
    memories: dict[str, RegimeActionMemory], empty_memory: RegimeActionMemory, episode_id: int,
    policy: OnlineMemoryGlmPolicy, api_audit: list[dict[str, Any]],
) -> tuple[dict[str, OnlineMemoryDecision], dict[str, dict[str, Any]]]:
    deterministic = assessment.full_action.value
    decisions = {FROZEN: _host_decision(deterministic)}
    host_audit: dict[str, dict[str, Any]] = {FROZEN: {"api_called": False}}
    if not assessment.ambiguous:
        for method in GLM_METHODS:
            decisions[method] = _host_decision(deterministic)
            host_audit[method] = {"api_called": False, "fallback_used": False, "override_authorized": False}
        return decisions, host_audit
    for method in GLM_METHODS:
        memory = empty_memory if method == STATELESS else memories[method]
        memory_payload = retrieve_action_memory_payload(memory, signature, created_before_episode_id=episode_id)
        payload = build_online_memory_payload(
            compact_evidence=compact, memory_payload=memory_payload, memory=memory, episode_id=episode_id,
        )
        payload["agent_variant"] = method
        allowed = {record.record_id for record in memory.prior(episode_id)}
        model_decision = _request(policy, payload, allowed, episode_id, method, api_audit)
        proposed = None if model_decision.abstain else InterventionSkill(model_decision.selected_skill)
        if method == STATELESS:
            selected = assessment.full_action if proposed is None else proposed
            decisions[method] = _replace_selected(model_decision, selected)
            host_audit[method] = {
                "api_called": True, "glm_proposed_skill": None if proposed is None else proposed.value,
                "fallback_used": proposed is None, "override_authorized": proposed is not None and proposed is not assessment.full_action,
            }
            continue
        guarded = guard_memory_override(
            assessment=assessment, proposed_skill=proposed, memory_payload=memory_payload,
        )
        preference = agreed_memory_preference(memory_payload)
        selected: InterventionSkill | None = guarded.selected_skill
        if method == ABSTAIN and guarded.fallback_used:
            selected = None
        decisions[method] = _replace_selected(model_decision, selected)
        host_audit[method] = {
            "api_called": True, "glm_proposed_skill": None if proposed is None else proposed.value,
            "memory_preference": None if preference is None else preference.value,
            "override_authorized": guarded.override_authorized,
            "fallback_used": guarded.fallback_used,
        }
    return decisions, host_audit


def _request(
    policy: OnlineMemoryGlmPolicy, payload: dict[str, Any], allowed: set[str], episode_id: int,
    method: str, api_audit: list[dict[str, Any]],
) -> OnlineMemoryDecision:
    decision, audit = policy.request_once(payload, allowed_memory_ids=allowed)
    audit.update({"episode_id": episode_id, "method": method, "repair": False})
    api_audit.append(audit)
    if decision is None:
        decision, repaired = policy.request_once(
            payload, allowed_memory_ids=allowed, previous_error=audit.get("error", "invalid output"),
        )
        repaired.update({"episode_id": episode_id, "method": method, "repair": True})
        api_audit.append(repaired)
    return decision or OnlineMemoryDecision.fail_closed("invalid_or_unavailable_model_output")


def _replace_selected(decision: OnlineMemoryDecision, selected: InterventionSkill | None) -> OnlineMemoryDecision:
    if selected is None:
        return OnlineMemoryDecision(
            EvidenceInterpretation(
                decision.evidence_interpretation.persistent_directional_drift,
                decision.evidence_interpretation.high_response_variance, False,
            ),
            decision.action_predictions, decision.memory_used, decision.supporting_memory_ids,
            decision.contradicting_memory_ids, decision.memory_applicable,
            decision.memory_conflict_detected, None, True, decision.reason,
        )
    return OnlineMemoryDecision(
        EvidenceInterpretation(
            decision.evidence_interpretation.persistent_directional_drift,
            decision.evidence_interpretation.high_response_variance, True,
        ),
        decision.action_predictions, decision.memory_used, decision.supporting_memory_ids,
        decision.contradicting_memory_ids, decision.memory_applicable,
        decision.memory_conflict_detected, selected.value, False, decision.reason,
    )


def _host_decision(skill: str) -> OnlineMemoryDecision:
    neutral = SkillPrediction("INCONCLUSIVE", 0.5, 0.0)
    return OnlineMemoryDecision(
        EvidenceInterpretation(False, False, True),
        {COMP.value: neutral, RETRY.value: neutral}, False, (), (), False, False,
        skill, False, "Frozen host decision; API bypassed.",
    )


def _oracle(results: dict[str, tuple[Any, dict[str, Any]]], initial_distance: float) -> str:
    order = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0}
    return max(results, key=lambda skill: (
        order[str(results[skill][1]["verification_status"])],
        initial_distance - results[skill][0].final_object_goal_distance,
        -results[skill][0].steps, skill,
    ))


def _status_probabilities(prediction: SkillPrediction) -> dict[str, float]:
    accepted = float(prediction.accept_probability)
    remainder = 1.0 - accepted
    if prediction.predicted_status == "REJECTED":
        return {"ACCEPTED": accepted, "INCONCLUSIVE": remainder * 0.25, "REJECTED": remainder * 0.75}
    return {"ACCEPTED": accepted, "INCONCLUSIVE": remainder * 0.75, "REJECTED": remainder * 0.25}


def _load_bootstrap(path: Path) -> tuple[RegimeActionExperience, ...]:
    return tuple(RegimeActionExperience.from_dict(row) for row in json.loads(path.read_text(encoding="utf-8")))


def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"] or _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("selective-override manifest identity mismatch")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("selective-override run requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("selective-override config changed")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"selective-override source changed: {relative}")
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
