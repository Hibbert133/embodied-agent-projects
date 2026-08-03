"""Run the frozen chronological ProbeMem-Online Gate-C development stream."""

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
from src.probemem.online_memory_policy import OnlineMemoryDecision, OnlineMemoryGlmPolicy, build_online_memory_payload  # noqa: E402
from src.probemem.persistent_regime import select_from_persistent_probe  # noqa: E402
from src.probemem.regime_memory import ProbeRegimeSignature, RegimeActionExperience, RegimeActionMemory  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state, validate_no_oracle_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY
GLM_METHODS = (
    "STATELESS_GLM", "GLM_FROZEN_BOOTSTRAP_MEMORY",
    "GLM_ONLINE_ACTION_MEMORY", "GLM_ONLINE_MEMORY_RESONANCE",
)


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
            raise FileExistsError("Gate C run cannot overwrite or restart a manifest")
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        bootstrap = _load_bootstrap(ROOT / config["memory"]["bootstrap_records"])
        memories = {
            "GLM_FROZEN_BOOTSTRAP_MEMORY": RegimeActionMemory(bootstrap),
            "GLM_ONLINE_ACTION_MEMORY": RegimeActionMemory(bootstrap),
            "GLM_ONLINE_MEMORY_RESONANCE": RegimeActionMemory(bootstrap),
        }
        empty_memory = RegimeActionMemory()
        policy = OnlineMemoryGlmPolicy(
            model=config["glm"]["model"], base_url=args.base_url,
            timeout_seconds=float(config["glm"]["timeout_seconds"]),
            max_tokens=int(config["glm"]["max_tokens"]),
        )
        regimes = {row["regime_id"]: MixedRegime(row["regime_id"], tuple(row["bias"]), float(row["noise_std"])) for row in config["regimes"]}
        recovery = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8")))
        decisions: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        api_audit: list[dict[str, Any]] = []
        memory_records: list[dict[str, Any]] = []
        resonance_rows: list[dict[str, Any]] = []
        integrity = {name: 0 for name in (
            "chronology_violations", "oracle_leakage_events", "budget_violations",
            "random_namespace_violations", "future_memory_access", "counterfactual_memory_writes",
            "invalid_memory_ids", "invalid_skill_executions",
        )}
        operational = 0
        for unit in manifest["population_units"]:
            if operational >= int(config["target_operational_cases"]):
                break
            seed = int(unit["environment_seed"])
            regime = regimes[str(unit["regime_id_oracle"])]
            if len({int(unit["initial_perturbation_seed"]), int(unit["diagnostic_probe_seed"]), int(unit["paired_verification_seed"])}) != 3:
                integrity["random_namespace_violations"] += 1
                raise RuntimeError("Gate C random namespaces overlap")
            trajectory = run_dir / "initial_trajectories" / f"unit{unit['unit_id']:03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, episode_id=int(unit["unit_id"]),
                    max_steps=int(config["budget"]["initial_max_steps"]),
                    perturbation=regime.build(), perturbation_seed=int(unit["initial_perturbation_seed"]),
                    agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory), evidence_id=f"gate_c_unit{unit['unit_id']:03d}_attempt0",
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
                "evidence_id": f"gate_c_episode{episode_id:03d}_attempt1", "episode_id": episode_id,
                "initial_evidence": {**state.to_dict(), "episode_id": episode_id, "evidence_id": f"gate_c_episode{episode_id:03d}_attempt0"},
                "registered_probe_evidence": probe,
                "remaining_verification_budget": int(config["budget"]["verification_max_steps"]),
            }
            validate_no_oracle_evidence(agent_evidence)
            compact = build_compact_causal_evidence(agent_evidence)
            signature = ProbeRegimeSignature.from_agent_evidence(agent_evidence)
            decision_timestamp = time.perf_counter_ns()
            episode_decisions = _decide_all(
                policy=policy, compact=compact.to_dict(), signature=signature,
                probe=probe, memories=memories, empty_memory=empty_memory,
                episode_id=episode_id, api_audit=api_audit,
            )
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
                    "final_object_goal_distance": result.final_object_goal_distance,
                    "evaluator_only": True,
                })
            if time.perf_counter_ns() <= decision_timestamp:
                integrity["chronology_violations"] += 1
                raise RuntimeError("candidate outcomes preceded decisions")
            oracle_skill = _oracle(candidate_results, initial.final_object_goal_distance)
            episode_decisions["EVALUATOR_ONLY_ORACLE"] = OnlineMemoryDecision.fail_closed("evaluator_only")
            for method, decision in episode_decisions.items():
                selected = oracle_skill if method == "EVALUATOR_ONLY_ORACLE" else decision.selected_skill
                selected_result = None if selected is None else candidate_results[selected]
                status = "ABSTAIN" if selected_result is None else str(selected_result[1]["verification_status"])
                decisions.append({
                    "episode_id": episode_id, "seed": seed, "segment_id_oracle": unit["segment_id_oracle"],
                    "regime_id_oracle": unit["regime_id_oracle"], "method": method,
                    "selected_skill": selected, "verification_status": status,
                    "abstain": selected is None,
                })
                if method in ("GLM_ONLINE_ACTION_MEMORY", "GLM_ONLINE_MEMORY_RESONANCE") and selected_result is not None:
                    prediction = decision.action_predictions[selected]
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
                    if method == "GLM_ONLINE_MEMORY_RESONANCE":
                        probabilities = _status_probabilities(prediction)
                        resonance_rows.append(ActionResonanceRecord.create(
                            episode_id=episode_id, selected_skill=InterventionSkill(selected),
                            predicted_status=prediction.predicted_status, probabilities=probabilities,
                            observed_status=str(execution["verification_status"]),
                            observed_progress=initial.final_object_goal_distance - result.final_object_goal_distance,
                            supporting_memory_ids=decision.supporting_memory_ids,
                            contradicting_memory_ids=decision.contradicting_memory_ids,
                        ).to_dict())
            _write_csv(run_dir / "decisions.csv", decisions)
            _write_csv(run_dir / "candidate_outcomes.csv", outcomes)
            _write_json(run_dir / "api_audit.json", api_audit)
            _write_json(run_dir / "operational_memory_records.json", memory_records)
            _write_json(run_dir / "resonance.json", resonance_rows)
            print(f"episode={episode_id} seed={seed} completed methods={len(episode_decisions)}", flush=True)
        summary = {
            "experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"], "operational_cases": operational,
            "target_operational_cases": int(config["target_operational_cases"]), "api_calls": len(api_audit),
            **integrity,
        }
        _write_json(run_dir / "summary.json", summary)
        _write_json(status_path, {"status": "COMPLETED" if operational == int(config["target_operational_cases"]) else "INCOMPLETE", **summary})
        print(f"run: {run_dir}")
        return 0 if operational == int(config["target_operational_cases"]) else 2
    except Exception as exc:
        if manifest is not None and status_path is not None:
            _write_json(status_path, {"status": "FAILED", "manifest_id": manifest["manifest_id"], "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _decide_all(*, policy: OnlineMemoryGlmPolicy, compact: dict[str, Any], signature: ProbeRegimeSignature,
                probe: dict[str, Any], memories: dict[str, RegimeActionMemory], empty_memory: RegimeActionMemory,
                episode_id: int, api_audit: list[dict[str, Any]]) -> dict[str, OnlineMemoryDecision]:
    decisions = {
        "ALWAYS_COMPENSATION": _host_decision(COMP.value),
        "ALWAYS_RETRY": _host_decision(RETRY.value),
        "FROZEN_VARIANCE_RULE": _host_decision(select_from_persistent_probe(probe)[0].value),
    }
    frozen_summary = retrieve_action_memory_payload(memories["GLM_FROZEN_BOOTSTRAP_MEMORY"], signature, created_before_episode_id=episode_id)
    candidates = frozen_summary["candidate_actions"]
    posterior_skill = max((COMP.value, RETRY.value), key=lambda skill: (candidates[skill]["global"]["accepted_probability"], skill))
    decisions["DETERMINISTIC_ACTION_POSTERIOR"] = _host_decision(posterior_skill)
    for method in GLM_METHODS:
        memory = empty_memory if method == "STATELESS_GLM" else memories[method]
        summary = retrieve_action_memory_payload(memory, signature, created_before_episode_id=episode_id)
        payload = build_online_memory_payload(compact_evidence=compact, memory_payload=summary, memory=memory, episode_id=episode_id)
        payload["agent_variant"] = method
        allowed = {record.record_id for record in memory.prior(episode_id)}
        decision, audit = policy.request_once(payload, allowed_memory_ids=allowed)
        audit.update({"episode_id": episode_id, "method": method, "repair": False})
        api_audit.append(audit)
        if decision is None:
            decision, repaired = policy.request_once(payload, allowed_memory_ids=allowed, previous_error=audit.get("error", "invalid output"))
            repaired.update({"episode_id": episode_id, "method": method, "repair": True})
            api_audit.append(repaired)
        decisions[method] = decision or OnlineMemoryDecision.fail_closed("invalid_or_unavailable_model_output")
    return decisions


def _host_decision(skill: str) -> OnlineMemoryDecision:
    prediction = {name: {"predicted_status": "INCONCLUSIVE", "accept_probability": 0.5, "confidence": 0.0} for name in (COMP.value, RETRY.value)}
    return OnlineMemoryDecision.from_mapping({
        "evidence_interpretation": {"persistent_directional_drift": False, "high_response_variance": False, "evidence_sufficient": True},
        "action_predictions": prediction, "memory_used": False, "supporting_memory_ids": [],
        "contradicting_memory_ids": [], "memory_applicable": False, "memory_conflict_detected": False,
        "selected_skill": skill, "abstain": False, "reason": "Frozen host baseline.",
    }, allowed_memory_ids=set())


def _oracle(results: dict[str, tuple[Any, dict[str, Any]]], initial_distance: float) -> str:
    order = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0}
    return max(results, key=lambda skill: (order[str(results[skill][1]["verification_status"])], initial_distance - results[skill][0].final_object_goal_distance, -results[skill][0].steps, skill))


def _status_probabilities(prediction: Any) -> dict[str, float]:
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
        raise RuntimeError("Gate C manifest identity mismatch")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Gate C requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("Gate C config changed")
    for group in ("implementation_sha256", "input_sha256"):
        for relative, expected in manifest[group].items():
            if _sha256(ROOT / relative) != expected:
                raise RuntimeError(f"Gate C source changed: {relative}")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
