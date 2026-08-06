"""Run the immutable live ProbeMem-SciAgent v1 Demo."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from scripts.run_mixed_regime_tuning import MixedRegime  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.planner.evidence_grounded import first_registered_probe_context, select_grounded_intervention  # noqa: E402
from src.probemem.compact_evidence import build_compact_causal_evidence  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem.regime_memory import ProbeRegimeSignature  # noqa: E402
from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget, SciAgentGlmClient  # noqa: E402
from src.probemem_sciagent.agent_payload import build_decision_payload, build_knowledge_update_payload  # noqa: E402
from src.probemem_sciagent.compensation_probe import summarize_compensation_response  # noqa: E402
from src.probemem_sciagent.online_policy import SciAgentOnlinePolicy  # noqa: E402
from src.probemem_sciagent.probe_registry import ProbeBudget, allow_probe, run_prefix_records  # noqa: E402
from src.probemem_sciagent.retry_probe import summarize_retry_repeatability  # noqa: E402
from src.probemem_sciagent.schemas import ExperienceRecord, MicroProbeRecord  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/probemem_sciagent/demo_v1.json")
    args = parser.parse_args()
    manifest: dict[str, Any] | None = None
    status_path: Path | None = None
    try:
        manifest, config = _validate(args.manifest.resolve(), args.config.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("SciAgent run cannot overwrite or resume a manifest")
        if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("ANTHROPIC_BASE_URL"):
            _write_json(status_path, {
                "status": "BLOCKED_MISSING_GLM_CREDENTIALS", "manifest_id": manifest["manifest_id"],
                "initial_units": 0, "operational_cases": 0, "fresh_seed_consumed": False,
            })
            print("[BLOCKED] ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required", file=sys.stderr)
            return 3
        _write_json(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        regimes = {
            row["regime_id"]: MixedRegime(row["regime_id"], tuple(row["bias"]), float(row["noise_std"]))
            for row in config["regimes"]
        }
        recovery = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8")))
        api_budget = SciAgentCallBudget(
            int(config["glm"]["maximum_primary_calls"]), int(config["glm"]["maximum_schema_repairs"]),
            int(config["glm"]["maximum_total_calls"]),
        )
        agent = SciAgentGlmClient(
            model=str(config["glm"]["model"]), timeout_seconds=float(config["glm"]["timeout_seconds"]),
            max_tokens=int(config["glm"]["max_tokens"]), call_budget=api_budget,
        )
        online = SciAgentOnlinePolicy()
        population: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        probes: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        knowledge: list[dict[str, Any]] = []
        operational = 0
        initial_units = 0
        for unit in manifest["population_units"]:
            if operational >= int(config["target_operational_cases"]): break
            initial_units += 1
            seed = int(unit["environment_seed"])
            regime = regimes[str(unit["regime_id_oracle"])]
            trajectory = run_dir / "initial_trajectories" / f"unit{int(unit['unit_id']):03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, episode_id=int(unit["unit_id"]),
                    max_steps=int(config["budget"]["initial_max_steps"]), perturbation=regime.build(),
                    perturbation_seed=int(unit["initial_seed"]), agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory), evidence_id=f"sciagent_unit{unit['unit_id']}_initial",
                source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            )
            row = {
                "unit_id": unit["unit_id"], "seed": seed, "regime_id_oracle": unit["regime_id_oracle"],
                "initial_success": not state.decision_required, "decision_required": state.decision_required,
                "eligible": False, "ineligibility_reason": "",
            }
            if not state.decision_required:
                population.append(row); _flush(run_dir, population, decisions, probes, outcomes, knowledge, online, agent); continue
            probe_config = {"registered_probe": config["mandatory_probe"]}
            mandatory = _probe_context(regime, seed, probe_config, int(unit["mandatory_probe_seed"]))
            if not _compensation_is_constructible(seed=seed, probe_context=mandatory, recovery_config=recovery):
                row["ineligibility_reason"] = "BOUNDED_COMPENSATION_NOT_CONSTRUCTIBLE"
                population.append(row); _flush(run_dir, population, decisions, probes, outcomes, knowledge, online, agent); continue
            row["eligible"] = True; population.append(row); operational += 1
            episode_num = operational
            episode_id = f"sciagent_episode_{episode_num:03d}"
            agent_evidence = {
                "evidence_id": f"{episode_id}_evidence", "episode_id": episode_num,
                "initial_evidence": {**state.to_dict(), "episode_id": episode_num, "evidence_id": f"{episode_id}_initial"},
                "registered_probe_evidence": mandatory,
                "remaining_verification_budget": int(config["budget"]["verification_max_steps"]),
            }
            compact = build_compact_causal_evidence(agent_evidence)
            signature = ProbeRegimeSignature.from_agent_evidence(agent_evidence)
            condition_codes = _condition_codes(mandatory)
            snapshot = online.retrieve(query_signature=signature.to_dict()["features"], condition_codes=condition_codes)
            if not snapshot.principles:
                condition_codes = (*condition_codes, "NO_ACTIVE_PRINCIPLE_APPLIES")
                snapshot = online.retrieve(query_signature=signature.to_dict()["features"], condition_codes=condition_codes)
            first_payload = build_decision_payload(
                evidence=compact.to_dict(), memory=snapshot,
                remaining_budget={"micro_probe_steps": 192, "verification_steps": 500}, stage="PRE_PROBE",
            )
            online.audit.validate_payload(first_payload, episode_id)
            first = agent.decide(first_payload, snapshot=snapshot, stage="PRE_PROBE")
            first_id = f"{episode_id}_decision_pre"
            online.persist_decision(decision_id=first_id, episode_id=episode_id, decision=first)
            decisions.append(_decision_row(manifest, episode_id, seed, "PRE_PROBE", first_id, first))
            final = first; final_id = first_id; probe_record: MicroProbeRecord | None = None
            if allow_probe(first, ProbeBudget(192)):
                probe_record = _run_micro_probe(
                    config=config, unit=unit, seed=seed, episode_id=episode_id,
                    decision_id=first_id, decision=first, regime=regime,
                    mandatory=mandatory, recovery=recovery, online=online,
                )
                online.persist_probe(probe_record)
                probes.append(_probe_row(manifest, probe_record))
                post_payload = build_decision_payload(
                    evidence=compact.to_dict(), memory=snapshot,
                    remaining_budget={"micro_probe_steps": 0, "verification_steps": 500}, stage="POST_PROBE",
                    first_decision=first.to_dict(), probe_evidence=dict(probe_record.evidence),
                )
                online.audit.validate_payload(post_payload, episode_id)
                final = agent.decide(post_payload, snapshot=snapshot, stage="POST_PROBE")
                final_id = f"{episode_id}_decision_post"
                online.persist_decision(decision_id=final_id, episode_id=episode_id, decision=final)
                decisions.append(_decision_row(manifest, episode_id, seed, "POST_PROBE", final_id, final))
            online.audit.event(episode_id, "FINAL_SELECTION_WRITTEN", decision_id=final_id, selected_skill=final.selected_skill)
            candidate_results: dict[str, tuple[Any, dict[str, Any]]] = {}
            for skill in (COMP, RETRY):
                result, execution = _run_verification(
                    seed=seed, fault=regime, skill=skill, probe_context=mandatory,
                    recovery_config=recovery, perturbation_seed=int(unit["paired_verification_seed"]),
                    max_steps=int(config["budget"]["verification_max_steps"]),
                    initial_distance=initial.final_object_goal_distance,
                )
                candidate_results[skill.value] = (result, execution)
                outcomes.append({
                    "episode_id": episode_id, "seed": seed, "candidate_skill": skill.value,
                    "verification_status": execution["verification_status"], "steps": result.steps,
                    "final_distance": result.final_object_goal_distance, "evaluator_only": True,
                })
            if final.decision_mode != "ABSTAIN":
                selected = str(final.selected_skill)
                result, execution = candidate_results[selected]
                online_steps = (
                    int(initial.steps) + int(mandatory["probe_environment_steps"])
                    + (0 if probe_record is None else int(probe_record.environment_steps))
                    + int(result.steps)
                )
                if online_steps > int(config["budget"]["total_case_max_steps"]):
                    online.audit.violation("probe_budget_violations", episode_id, f"case used {online_steps} steps")
                    raise RuntimeError("SciAgent case exceeded total interaction budget")
                experience_step = online.next_step()
                prediction = "ACCEPTED" if final.predicted_success_probability >= 0.7 else ("REJECTED" if final.predicted_success_probability <= 0.3 else "INCONCLUSIVE")
                supporting = tuple(
                    principle_id for principle_id in final.retrieved_principle_ids
                    if online.principles.get(principle_id).recommended_skill == selected
                )
                experience = ExperienceRecord(
                    experience_id=f"{episode_id}_selected", episode_id=episode_id, seed=seed,
                    evidence_signature=signature.to_dict()["features"], selected_skill=selected,
                    agent_prediction=prediction, predicted_success_probability=final.predicted_success_probability,
                    agent_reasoning_summary=f"{final.evidence_summary} {final.expected_effect}",
                    verification_status=str(execution["verification_status"]),
                    final_distance=float(result.final_object_goal_distance), environment_steps=int(result.steps),
                    supporting_principle_ids=supporting,
                    probe_record_ids=() if probe_record is None else (probe_record.probe_record_id,),
                    created_at_step=experience_step,
                )
                update_payload = build_knowledge_update_payload(
                    decision=final.to_dict(), selected_experience=experience.to_dict(),
                    known_hypotheses=[row.to_dict() for row in online.hypotheses.records],
                    known_principles=[row.to_dict() for row in online.principles.records],
                )
                proposals = agent.propose_updates(update_payload)
                update = online.persist_selected_outcome(
                    decision_id=final_id, experience=experience, selected_skill=selected, proposals=proposals,
                )
                knowledge.append({
                    "episode_id": episode_id, "accepted_operations": list(update.accepted_operations),
                    "rejected_operations": list(update.rejected_operations),
                    "promoted_principle_ids": list(update.promoted_principle_ids),
                })
            _flush(run_dir, population, decisions, probes, outcomes, knowledge, online, agent)
            _write_json(status_path, {
                "status": "RUNNING", "manifest_id": manifest["manifest_id"],
                "initial_units": initial_units, "operational_cases": operational,
                "api_primary_calls": api_budget.primary_calls, "api_repair_calls": api_budget.repair_calls,
            })
            print(f"episode={episode_id} seed={seed} operational={operational}", flush=True)
        status = "COMPLETED" if operational >= int(config["minimum_operational_cases"]) else "INCOMPLETE_POPULATION"
        summary = {
            "status": status, "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"], "initial_units": initial_units,
            "operational_cases": operational, "api_primary_calls": api_budget.primary_calls,
            "api_repair_calls": api_budget.repair_calls, **online.audit.counts,
        }
        _write_json(run_dir / "summary.json", summary); _write_json(status_path, summary)
        return 0 if status == "COMPLETED" else 2
    except Exception as exc:
        if manifest is not None and status_path is not None and not status_path.exists():
            _write_json(status_path, {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        elif status_path is not None:
            _write_json(status_path, {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_micro_probe(
    *, config: Mapping[str, Any], unit: Mapping[str, Any], seed: int, episode_id: str,
    decision_id: str, decision: Any, regime: Any, mandatory: Mapping[str, Any],
    recovery: RecoveryPolicyConfig, online: SciAgentOnlinePolicy,
) -> MicroProbeRecord:
    if decision.selected_probe_type == "COMPENSATION_RESPONSE_PROBE":
        plan = select_grounded_intervention(
            plan_id=f"{episode_id}_probe_plan", evidence_id=f"{episode_id}_mandatory_probe",
            mechanism_belief="stable_bias", correction_context=first_registered_probe_context(mandatory),
            recovery_config=recovery, evidence_source="registered_probe",
        )
        if not plan.requires_fresh_verification: raise ValueError("compensation probe plan is not constructible")
        records = run_prefix_records(
            env_factory=lambda: create_push_environment(seed),
            policy=PhaseGatedCompensatedPolicy(create_push_policy(), plan.correction, schedule=plan.schedule),
            seed=seed, max_steps=64, perturbation=regime.build(),
            perturbation_seed=int(unit["compensation_probe_seed"]),
        )
        evidence = asdict(summarize_compensation_response(records, contact_distance=float(config["probe_measurement"]["contact_distance"])))
        random_ids = (int(unit["compensation_probe_seed"]),)
    else:
        trials = []
        for random_seed in unit["retry_probe_seeds"]:
            trials.append(run_prefix_records(
                env_factory=lambda: create_push_environment(seed), policy=create_push_policy(),
                seed=seed, max_steps=64, perturbation=regime.build(), perturbation_seed=int(random_seed),
            ))
        evidence = asdict(summarize_retry_repeatability(
            trials, positive_progress_threshold=float(config["probe_measurement"]["positive_progress_threshold"]),
            severe_failure_threshold=float(config["probe_measurement"]["severe_failure_threshold"]),
        ))
        records = tuple(row for trial in trials for row in trial)
        random_ids = tuple(int(value) for value in unit["retry_probe_seeds"])
    steps = len(records)
    if steps > int(config["registered_probes"][decision.selected_probe_type]["maximum_steps"]):
        raise RuntimeError("micro-probe exceeded registered budget")
    return MicroProbeRecord(
        probe_record_id=f"{episode_id}_micro_probe", episode_id=episode_id, seed=seed,
        probe_type=str(decision.selected_probe_type), requested_by_decision_id=decision_id,
        evidence=evidence, environment_steps=steps, random_seed_ids=random_ids,
        created_at_step=online.next_step(), reset_before_formal_recovery=True,
    )


def _condition_codes(probe: Mapping[str, Any]) -> tuple[str, ...]:
    consistency = probe["consistency"]
    stable = float(consistency["relative_bias_std"]) <= 1.0 and float(consistency["dominant_axis_sign_agreement"]) >= 0.75
    return ("CURRENT_FAILURE", "STABLE_DIRECTIONAL_RESPONSE" if stable else "VARIABLE_DIRECTIONAL_RESPONSE")


def _decision_row(manifest: Mapping[str, Any], episode_id: str, seed: int, stage: str, decision_id: str, decision: Any) -> dict[str, Any]:
    return {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"], "episode_id": episode_id, "seed": seed, "stage": stage, "decision_id": decision_id, **decision.to_dict()}


def _probe_row(manifest: Mapping[str, Any], record: MicroProbeRecord) -> dict[str, Any]:
    value = asdict(record); value["experiment_run_id"] = manifest["experiment_run_id"]; value["manifest_id"] = manifest["manifest_id"]; return value


def _flush(run_dir: Path, population: list, decisions: list, probes: list, outcomes: list, knowledge: list, online: SciAgentOnlinePolicy, agent: SciAgentGlmClient) -> None:
    _write_json(run_dir / "population.json", population)
    _write_json(run_dir / "decisions.json", decisions)
    _write_json(run_dir / "micro_probes.json", probes)
    _write_json(run_dir / "candidate_outcomes_evaluator_only.json", outcomes)
    _write_json(run_dir / "experience_memory.json", [row.to_dict() for row in online.experiences.records])
    _write_json(run_dir / "hypothesis_memory.json", [row.to_dict() for row in online.hypotheses.records])
    _write_json(run_dir / "principle_memory.json", [row.to_dict() for row in online.principles.records])
    _write_json(run_dir / "knowledge_updates.json", knowledge)
    _write_json(run_dir / "timeline.json", online.audit.events)
    _write_json(run_dir / "api_audit.json", agent.audit)


def _validate(manifest_path: Path, config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if _git("status", "--porcelain"): raise RuntimeError("SciAgent execution requires a clean worktree")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); config = json.loads(config_path.read_text(encoding="utf-8"))
    source_commit = str(manifest["source_git_commit"])
    head = _git("rev-parse", "HEAD")
    ancestry = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "merge-base", "--is-ancestor", source_commit, head],
        cwd=ROOT, capture_output=True, text=True,
    )
    if ancestry.returncode != 0:
        raise RuntimeError("manifest source commit is not an ancestor of HEAD")
    if source_commit != head:
        changed = set(_git("diff", "--name-only", source_commit, head).splitlines())
        allowed = {manifest_path.relative_to(ROOT).as_posix()}
        if changed - allowed:
            raise RuntimeError(f"tracked files changed after manifest source commit: {sorted(changed - allowed)}")
    if manifest["config_sha256"] != hashlib.sha256(config_path.read_bytes()).hexdigest(): raise RuntimeError("config hash mismatch")
    if manifest["config_path"] != config_path.relative_to(ROOT).as_posix(): raise RuntimeError("config path mismatch")
    canonical = dict(manifest); recorded_id = canonical.pop("manifest_id")
    if recorded_id != hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest():
        raise RuntimeError("manifest ID mismatch")
    for relative, expected in {**manifest["implementation_sha256"], **manifest["input_sha256"]}.items():
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"manifest-bound file changed: {relative}")
    return manifest, config


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__": raise SystemExit(main())
