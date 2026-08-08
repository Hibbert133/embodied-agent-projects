"""Run frozen ProbeMem-SciAgent Micro-Probe Utility v1.7 once."""

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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mixed_regime_tuning import MixedRegime  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.planner.evidence_grounded import first_registered_probe_context, select_grounded_intervention  # noqa: E402
from src.probemem.compact_evidence import build_compact_causal_evidence  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget  # noqa: E402
from src.probemem_sciagent.agent_payload import build_decision_payload  # noqa: E402
from src.probemem_sciagent.api_reliability import build_health_check_payload, certify_payload  # noqa: E402
from src.probemem_sciagent.capability_contract import attach_capability_contract  # noqa: E402
from src.probemem_sciagent.compensation_probe import summarize_compensation_response  # noqa: E402
from src.probemem_sciagent.hard_deadline_transport import HardDeadlineEnvelopeClient  # noqa: E402
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot  # noqa: E402
from src.probemem_sciagent.probe_registry import ProbeBudget, allow_probe, run_prefix_records  # noqa: E402
from src.probemem_sciagent.probe_utility import classify_probe_utility, total_online_steps  # noqa: E402
from src.probemem_sciagent.retry_probe import summarize_retry_repeatability  # noqa: E402
from src.probemem_sciagent.robust_probe_value import attach_robust_probe_value_contract  # noqa: E402
from src.probemem_sciagent.schemas import MicroProbeRecord  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = None
    status_path = None
    try:
        manifest, config = _validate(args.manifest.resolve())
        run = args.manifest.resolve().parent
        status_path = run / "run_status.json"
        if status_path.exists():
            raise FileExistsError("probe-utility run cannot overwrite or resume")
        if not os.environ.get("ANTHROPIC_API_KEY") or not os.environ.get("ANTHROPIC_BASE_URL"):
            _write(status_path, {"status": "BLOCKED_MISSING_GLM_CREDENTIALS", "fresh_seed_consumed": False, "initial_units": 0, "api_calls": 0})
            return 3
        api = config["api"]
        budget = SciAgentCallBudget(
            int(api["health_check_primary_calls"]) + int(api["pre_probe_primary_calls"]) + int(api["maximum_post_probe_primary_calls"]),
            int(api["maximum_schema_repairs"]), int(api["maximum_total_calls"]),
        )
        client = HardDeadlineEnvelopeClient(
            model=str(api["model"]), timeout_seconds=float(api["timeout_seconds"]),
            hard_deadline_seconds=float(api["hard_deadline_seconds"]), max_tokens=int(api["max_tokens"]),
            call_budget=budget, maximum_consecutive_failures=int(api["maximum_consecutive_logical_failures"]),
        )
        empty = ScientificMemorySnapshot(1, (), (), (), ())
        health_payload = attach_capability_contract(
            build_health_check_payload(), snapshot=empty, current_evidence_id="api_health_check_evidence",
        )
        health = client.certified_decide(health_payload, snapshot=empty, current_evidence_id="api_health_check_evidence")
        health_valid = bool(
            health.valid and health.certified_decision is not None
            and health.certified_decision.decision.decision_mode == "ABSTAIN"
        )
        _write(run / "health_check.json", _result(health))
        if not health_valid:
            _write(status_path, {"status": "BLOCKED_API_HEALTH_CHECK", "fresh_seed_consumed": False, "initial_units": 0, "api_calls": budget.total_calls})
            return 4
        regimes = {
            row["regime_id"]: MixedRegime(row["regime_id"], tuple(row["bias"]), float(row["noise_std"]))
            for row in config["regimes"]
        }
        recovery = RecoveryPolicyConfig.from_mapping(
            json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
        )
        population: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        probes: list[dict[str, Any]] = []
        outcomes: list[dict[str, Any]] = []
        utilities: list[dict[str, Any]] = []
        initial_units = operational = 0
        for unit in manifest["population_units"]:
            if operational >= int(config["target_operational_cases"]):
                break
            initial_units += 1
            seed = int(unit["environment_seed"])
            regime = regimes[str(unit["regime_id_oracle"])]
            trajectory = run / "initial_trajectories" / f"unit{int(unit['unit_id']):03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, max_steps=int(config["budget"]["initial_max_steps"]),
                    perturbation=regime.build(), perturbation_seed=int(unit["initial_seed"]),
                    agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory), evidence_id=f"probe_utility_unit{unit['unit_id']}_initial",
                source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            )
            population_row = {
                "unit_id": unit["unit_id"], "seed": seed,
                "regime_id_oracle": unit["regime_id_oracle"],
                "decision_required": state.decision_required, "eligible": False,
                "ineligibility_reason": "",
            }
            if not state.decision_required:
                population.append(population_row)
                _flush(run, population, decisions, probes, outcomes, utilities, client)
                continue
            mandatory = _probe_context(
                regime, seed, {"registered_probe": config["mandatory_probe"]},
                int(unit["mandatory_probe_seed"]),
            )
            if int(mandatory["probe_environment_steps"]) > int(config["budget"]["mandatory_probe_max_steps"]):
                raise RuntimeError("mandatory probe exceeded budget")
            if not _compensation_is_constructible(seed=seed, probe_context=mandatory, recovery_config=recovery):
                population_row["ineligibility_reason"] = "BOUNDED_COMPENSATION_NOT_CONSTRUCTIBLE"
                population.append(population_row)
                _flush(run, population, decisions, probes, outcomes, utilities, client)
                continue
            population_row["eligible"] = True
            population.append(population_row)
            operational += 1
            episode_id = f"probe_utility_episode_{operational:03d}"
            evidence = {
                "evidence_id": f"{episode_id}_evidence", "episode_id": operational,
                "initial_evidence": {**state.to_dict(), "episode_id": operational, "evidence_id": f"{episode_id}_initial"},
                "registered_probe_evidence": mandatory, "remaining_verification_budget": 500,
            }
            compact = build_compact_causal_evidence(evidence)
            pre_payload = build_decision_payload(
                evidence=compact.to_dict(), memory=empty,
                remaining_budget={"micro_probe_steps": 192, "verification_steps": 500}, stage="PRE_PROBE",
            )
            pre_payload = attach_capability_contract(
                certify_payload(pre_payload), snapshot=empty, current_evidence_id=compact.evidence_id,
            )
            pre_payload = attach_robust_probe_value_contract(pre_payload)
            audit_start = len(client.audit)
            pre = client.certified_decide(
                pre_payload, snapshot=empty, current_evidence_id=compact.evidence_id, stage="PRE_PROBE",
            )
            assessment = _latest_probe_assessment(client.audit, audit_start)
            pre_decision = None if pre.certified_decision is None else pre.certified_decision.decision
            pre_row = {
                "episode_id": episode_id, "seed": seed, "stage": "PRE_PROBE", **_result(pre),
                "probe_value_assessment": assessment, "persisted_before_probe": True,
                "audit_slice_start": audit_start, "audit_slice_end": len(client.audit),
            }
            decisions.append(pre_row)
            _flush(run, population, decisions, probes, outcomes, utilities, client)
            admitted = bool(
                pre.valid and pre_decision is not None and assessment is not None
                and assessment.get("admitted") is True
                and allow_probe(pre_decision, ProbeBudget(int(config["budget"]["micro_probe_max_steps"])))
            )
            if not admitted:
                continue
            if len(probes) >= int(api["maximum_post_probe_primary_calls"]):
                raise RuntimeError("post-probe call/probe budget exceeded")
            probe = _run_micro_probe(
                config=config, unit=unit, seed=seed, episode_id=episode_id,
                decision_id=f"{episode_id}_pre", decision=pre_decision, regime=regime,
                mandatory=mandatory, recovery=recovery, created_at_step=operational * 3,
            )
            online_steps = total_online_steps(
                initial_steps=int(initial.steps), mandatory_probe_steps=int(mandatory["probe_environment_steps"]),
                micro_probe_steps=probe.environment_steps,
            )
            if online_steps + int(config["budget"]["verification_max_steps"]) > int(config["budget"]["total_online_case_max_steps"]):
                raise RuntimeError("online case budget exceeded")
            probe_row = asdict(probe)
            probe_row.update({"online_steps_before_reserved_recovery": online_steps, "outcome_unavailable_at_write": True})
            probes.append(probe_row)
            _flush(run, population, decisions, probes, outcomes, utilities, client)
            post_payload = build_decision_payload(
                evidence=compact.to_dict(), memory=empty,
                remaining_budget={"micro_probe_steps": 0, "verification_steps": 500}, stage="POST_PROBE",
                first_decision=pre_decision.to_dict(), probe_evidence=probe_row,
            )
            post_payload = attach_capability_contract(
                certify_payload(post_payload), snapshot=empty, current_evidence_id=compact.evidence_id,
                allowed_probe_record_ids=(probe.probe_record_id,),
            )
            post_audit_start = len(client.audit)
            post = client.certified_decide(
                post_payload, snapshot=empty, current_evidence_id=compact.evidence_id, stage="POST_PROBE",
                allowed_probe_record_ids=(probe.probe_record_id,),
            )
            post_decision = None if post.certified_decision is None else post.certified_decision.decision
            decisions.append({
                "episode_id": episode_id, "seed": seed, "stage": "POST_PROBE", **_result(post),
                "audit_slice_start": post_audit_start, "audit_slice_end": len(client.audit),
                "persisted_before_candidate_outcomes": True,
            })
            _flush(run, population, decisions, probes, outcomes, utilities, client)
            pre_skill = pre_decision.selected_skill
            post_skill = None if post_decision is None or post_decision.decision_mode == "ABSTAIN" else post_decision.selected_skill
            if not post.valid or post_skill is None:
                utilities.append(asdict(classify_probe_utility(
                    pre_probe_skill=pre_skill, post_probe_skill=None, candidate_statuses={},
                )) | {"episode_id": episode_id})
                _flush(run, population, decisions, probes, outcomes, utilities, client)
                continue
            statuses: dict[str, str] = {}
            evaluator_steps = 0
            for skill in (COMP, RETRY):
                result, execution = _run_verification(
                    seed=seed, fault=regime, skill=skill, probe_context=mandatory,
                    recovery_config=recovery, perturbation_seed=int(unit["paired_verification_seed"]),
                    max_steps=int(config["budget"]["verification_max_steps"]),
                    initial_distance=initial.final_object_goal_distance,
                )
                status = str(execution["verification_status"])
                statuses[skill.value] = status
                evaluator_steps += int(result.steps)
                outcomes.append({
                    "episode_id": episode_id, "seed": seed, "candidate_skill": skill.value,
                    "verification_status": status, "final_distance": float(result.final_object_goal_distance),
                    "environment_steps": int(result.steps), "evaluator_only": True,
                    "unavailable_to_agent": True,
                })
            if evaluator_steps > int(config["budget"]["maximum_evaluator_collection_steps"]):
                raise RuntimeError("evaluator collection budget exceeded")
            utility = asdict(classify_probe_utility(
                pre_probe_skill=pre_skill, post_probe_skill=post_skill, candidate_statuses=statuses,
            ))
            utility.update({"episode_id": episode_id, "evaluator_collection_steps": evaluator_steps})
            utilities.append(utility)
            _flush(run, population, decisions, probes, outcomes, utilities, client)
        summary = _summarize(
            manifest=manifest, config=config, budget=budget, client=client,
            initial_units=initial_units, operational=operational, decisions=decisions,
            probes=probes, utilities=utilities, health_valid=health_valid,
        )
        _write(run / "summary.json", summary)
        _write(status_path, summary)
        return 0 if summary["status"] == "COMPLETED_GATE_PASSED" else 2
    except Exception as exc:
        if status_path is not None:
            _write(status_path, {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_micro_probe(
    *, config: Mapping[str, Any], unit: Mapping[str, Any], seed: int, episode_id: str,
    decision_id: str, decision: Any, regime: Any, mandatory: Mapping[str, Any],
    recovery: RecoveryPolicyConfig, created_at_step: int,
) -> MicroProbeRecord:
    if decision.selected_probe_type == "COMPENSATION_RESPONSE_PROBE":
        plan = select_grounded_intervention(
            plan_id=f"{episode_id}_probe_plan", evidence_id=f"{episode_id}_mandatory_probe",
            mechanism_belief="stable_bias", correction_context=first_registered_probe_context(mandatory),
            recovery_config=recovery, evidence_source="registered_probe",
        )
        if not plan.requires_fresh_verification:
            raise ValueError("compensation probe plan is not constructible")
        records = run_prefix_records(
            env_factory=lambda: create_push_environment(seed),
            policy=PhaseGatedCompensatedPolicy(create_push_policy(), plan.correction, schedule=plan.schedule),
            seed=seed, max_steps=64, perturbation=regime.build(),
            perturbation_seed=int(unit["compensation_probe_seed"]),
        )
        evidence = asdict(summarize_compensation_response(
            records, contact_distance=float(config["probe_measurement"]["contact_distance"]),
        ))
        random_ids = (int(unit["compensation_probe_seed"]),)
    elif decision.selected_probe_type == "RETRY_REPEATABILITY_PROBE":
        trials = [
            run_prefix_records(
                env_factory=lambda: create_push_environment(seed), policy=create_push_policy(),
                seed=seed, max_steps=64, perturbation=regime.build(), perturbation_seed=int(random_seed),
            )
            for random_seed in unit["retry_probe_seeds"]
        ]
        evidence = asdict(summarize_retry_repeatability(
            trials,
            positive_progress_threshold=float(config["probe_measurement"]["positive_progress_threshold"]),
            severe_failure_threshold=float(config["probe_measurement"]["severe_failure_threshold"]),
        ))
        records = tuple(row for trial in trials for row in trial)
        random_ids = tuple(int(value) for value in unit["retry_probe_seeds"])
    else:
        raise ValueError("unregistered probe type")
    steps = len(records)
    if steps > int(config["registered_probes"][decision.selected_probe_type]["maximum_steps"]):
        raise RuntimeError("micro-probe exceeded registered budget")
    return MicroProbeRecord(
        probe_record_id=f"{episode_id}_micro_probe", episode_id=episode_id, seed=seed,
        probe_type=str(decision.selected_probe_type), requested_by_decision_id=decision_id,
        evidence=evidence, environment_steps=steps, random_seed_ids=random_ids,
        created_at_step=created_at_step, reset_before_formal_recovery=True,
    )


def _summarize(
    *, manifest: Mapping[str, Any], config: Mapping[str, Any], budget: Any, client: Any,
    initial_units: int, operational: int, decisions: list[dict[str, Any]], probes: list[dict[str, Any]],
    utilities: list[dict[str, Any]], health_valid: bool,
) -> dict[str, Any]:
    pre_valid = sum(row["stage"] == "PRE_PROBE" and bool(row["valid"]) for row in decisions)
    post_valid = sum(_is_valid_post_action(row) for row in decisions)
    helpful = sum(row["label"] == "HELPFUL_PROBE" for row in utilities)
    harmful = sum(row["label"] == "HARMFUL_PROBE" for row in utilities)
    no_benefit = sum(row["label"] == "NO_DECISION_BENEFIT" for row in utilities)
    not_evaluable = sum(row["label"] == "NOT_EVALUABLE" for row in utilities)
    fail_closed = sum(not bool(row["valid"]) for row in decisions)
    integrity_reasons = _integrity_violations(
        decisions=decisions, probes=probes, utilities=utilities, audit=client.audit,
    )
    integrity = len(integrity_reasons)
    gate = config["success_gate"]
    complete = operational >= int(config["minimum_operational_cases"])
    method_passed = (
        complete and pre_valid >= int(gate["minimum_valid_pre_probe_outputs"])
        and len(probes) >= int(gate["minimum_executed_probes"])
        and post_valid >= int(gate["minimum_valid_post_probe_outputs"])
        and fail_closed <= int(gate["maximum_fail_closed_outputs"])
        and budget.repair_calls <= int(gate["maximum_repairs"])
        and helpful >= int(gate["minimum_helpful_probes"])
        and (not gate["require_helpful_strictly_above_harmful"] or helpful > harmful)
        and integrity <= int(gate["maximum_integrity_violations"])
    )
    status = "COMPLETED_GATE_PASSED" if method_passed else ("COMPLETED_GATE_FAILED" if complete else "INCOMPLETE_POPULATION")
    return {
        "status": status, "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"], "initial_units": initial_units,
        "operational_cases": operational, "health_check_valid": health_valid,
        "valid_pre_probe_outputs": pre_valid, "executed_probes": len(probes),
        "valid_post_probe_action_outputs": post_valid, "helpful_probes": helpful,
        "harmful_probes": harmful, "no_decision_benefit_probes": no_benefit,
        "not_evaluable_probes": not_evaluable, "fail_closed_outputs": fail_closed,
        "api_calls": budget.total_calls, "repairs": budget.repair_calls,
        "hard_deadline_timeouts": sum(row.get("error_type") == "TimeoutExpired" for row in client.audit),
        "integrity_violations": integrity, "integrity_violation_reasons": integrity_reasons,
        "memory_write_count": 0,
        "principle_update_count": 0, "online_recovery_execution_count": 0,
        "claim_boundary": config["claim_boundary"],
    }


def _is_valid_post_action(row: Mapping[str, Any]) -> bool:
    certified = row.get("certified_decision")
    return bool(
        row.get("stage") == "POST_PROBE" and row.get("valid") is True
        and isinstance(certified, Mapping)
        and isinstance(certified.get("decision"), Mapping)
        and certified["decision"].get("decision_mode") == "ACT_DIRECTLY"
    )


def _integrity_violations(
    *, decisions: list[dict[str, Any]], probes: list[dict[str, Any]],
    utilities: list[dict[str, Any]], audit: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    pre_by_episode = {row["episode_id"]: row for row in decisions if row.get("stage") == "PRE_PROBE"}
    post_by_episode = {row["episode_id"]: row for row in decisions if row.get("stage") == "POST_PROBE"}
    if len(pre_by_episode) != sum(row.get("stage") == "PRE_PROBE" for row in decisions):
        reasons.append("DUPLICATE_PRE_PROBE_DECISION")
    if len(post_by_episode) != sum(row.get("stage") == "POST_PROBE" for row in decisions):
        reasons.append("DUPLICATE_POST_PROBE_DECISION")
    for probe in probes:
        episode = probe["episode_id"]
        pre = pre_by_episode.get(episode)
        if pre is None or pre.get("persisted_before_probe") is not True:
            reasons.append(f"PROBE_BEFORE_PRE_DECISION:{episode}")
        if probe.get("outcome_unavailable_at_write") is not True:
            reasons.append(f"PROBE_ROW_CAN_SEE_OUTCOME:{episode}")
        if episode not in post_by_episode:
            reasons.append(f"MISSING_POST_PROBE_DECISION:{episode}")
    for utility in utilities:
        episode = utility["episode_id"]
        post = post_by_episode.get(episode)
        if post is None or post.get("persisted_before_candidate_outcomes") is not True:
            reasons.append(f"OUTCOME_BEFORE_POST_DECISION:{episode}")
    request_hashes: set[str] = set()
    for row in decisions:
        request_hash = row.get("request_hash")
        if request_hash in request_hashes:
            reasons.append(f"DUPLICATE_CROSS_CASE_REQUEST_HASH:{row['episode_id']}:{row['stage']}")
        if isinstance(request_hash, str):
            request_hashes.add(request_hash)
        start, end = row.get("audit_slice_start"), row.get("audit_slice_end")
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start <= end <= len(audit):
            reasons.append(f"INVALID_AUDIT_SLICE:{row['episode_id']}:{row['stage']}")
            continue
        call_rows = audit[start:end]
        if row.get("valid") is True and not any(item.get("request_hash") == request_hash for item in call_rows):
            reasons.append(f"REQUEST_AUDIT_MISMATCH:{row['episode_id']}:{row['stage']}")
        if row.get("probe_value_assessment") is not None and not any(
            item.get("request_hash") == request_hash and item.get("valid_probe_value_certificate") is True
            for item in call_rows
        ):
            reasons.append(f"PROBE_ASSESSMENT_AUDIT_MISMATCH:{row['episode_id']}")
    return reasons


def _result(result: Any) -> dict[str, Any]:
    return {
        "valid": result.valid, "repaired": result.repaired, "cache_hit": result.cache_hit,
        "request_hash": result.request_hash, "error": result.error,
        "certified_decision": None if result.certified_decision is None else result.certified_decision.to_dict(),
        "fail_closed_decision": result.fail_closed_decision.to_dict(),
    }


def _latest_probe_assessment(audit: list[dict[str, Any]], start: int) -> dict[str, Any] | None:
    if start < 0 or start > len(audit):
        raise ValueError("audit start is outside current audit")
    for row in reversed(audit[start:]):
        assessment = row.get("probe_value_assessment")
        if row.get("valid_probe_value_certificate") is True and isinstance(assessment, dict):
            return assessment
    return None


def _flush(
    run: Path, population: list[Any], decisions: list[Any], probes: list[Any],
    outcomes: list[Any], utilities: list[Any], client: Any,
) -> None:
    _write(run / "population.json", population)
    _write(run / "decisions.json", decisions)
    _write(run / "micro_probes.json", probes)
    _write(run / "candidate_outcomes_evaluator_only.json", outcomes)
    _write(run / "probe_utility.json", utilities)
    _write(run / "api_audit.json", client.audit)
    _write(run / "memory_writes.json", [])
    _write(run / "principle_updates.json", [])


def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if _git("status", "--porcelain"):
        raise RuntimeError("probe-utility execution requires a clean worktree")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    config_path = ROOT / manifest["config_path"]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    head = _git("rev-parse", "HEAD")
    source = manifest["source_git_commit"]
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != manifest["config_sha256"]:
        raise RuntimeError("config hash mismatch")
    canonical = dict(manifest)
    recorded_id = canonical.pop("manifest_id")
    if hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != recorded_id:
        raise RuntimeError("manifest ID mismatch")
    ancestry = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "merge-base", "--is-ancestor", source, head],
        cwd=ROOT,
    )
    if ancestry.returncode != 0:
        raise RuntimeError("manifest source is not an ancestor of HEAD")
    if source != head:
        changed = set(_git("diff", "--name-only", source, head).splitlines())
        allowed = {path.relative_to(ROOT).as_posix()}
        if changed - allowed:
            raise RuntimeError(f"tracked changes after source commit: {sorted(changed - allowed)}")
    for relative, expected in {**manifest["implementation_sha256"], **manifest["input_sha256"]}.items():
        file = ROOT / relative
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"manifest-bound file changed: {relative}")
    return manifest, config


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
