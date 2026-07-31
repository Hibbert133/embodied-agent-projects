"""Run the bounded ProbeMem v2 Phase-B online development smoke."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Mapping

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import FaultCondition, get_conditions  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.planner.evidence_grounded import first_registered_probe_context, select_grounded_intervention  # noqa: E402
from src.probe import build_repeated_agent_probe_context, estimate_planar_bias, run_repeated_symmetric_probes  # noqa: E402
from src.probemem import CaseBudget, InterventionSkill, MemorySnapshot, ProbeMemTool, build_default_tool_registry  # noqa: E402
from src.probemem.models import ProbeMemDecision  # noqa: E402
from src.probemem.online_policy import AnthropicProbeMemPolicy, ApiCallBudget  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed(seed: int, namespace: int) -> int:
    return int(np.random.SeedSequence([seed, namespace]).generate_state(1)[0])


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _validate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"]:
        raise ValueError("manifest directory does not match experiment_run_id")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("current HEAD differs from immutable manifest commit")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("ProbeMem execution requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("configuration differs from immutable manifest")
    for relative, expected in manifest["implementation_sha256"].items():
        if _sha256(ROOT / relative) != expected:
            raise RuntimeError(f"implementation differs from manifest: {relative}")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _probe_context(fault: FaultCondition, seed: int, config: Mapping[str, Any], random_seed: int) -> dict[str, Any]:
    probe = config["registered_probe"]
    repetitions = run_repeated_symmetric_probes(
        lambda: create_push_environment(seed),
        seed=seed,
        perturbation_factory=fault.build,
        repeats=int(probe["repeats"]),
        magnitude=float(probe["magnitude"]),
        steps=int(probe["steps_per_direction"]),
        perturbation_seed_base=random_seed,
    )
    estimates = [estimate_planar_bias(group) for group in repetitions]
    return build_repeated_agent_probe_context(repetitions, estimates)


def _verification_status(success: bool, final_distance: float, initial_distance: float) -> str:
    if success:
        return "ACCEPTED"
    if final_distance < initial_distance:
        return "INCONCLUSIVE"
    return "REJECTED"


def _run_verification(
    *,
    seed: int,
    fault: FaultCondition,
    skill: InterventionSkill,
    probe_context: Mapping[str, Any] | None,
    recovery_config: RecoveryPolicyConfig,
    perturbation_seed: int,
    max_steps: int,
    initial_distance: float,
) -> tuple[Any, dict[str, Any]]:
    if skill is InterventionSkill.BOUNDED_PLANAR_COMPENSATION:
        if probe_context is None:
            raise ValueError("bounded compensation requires registered probe evidence")
        plan = select_grounded_intervention(
            plan_id=f"probemem_plan_seed{seed}",
            evidence_id=f"probe_evidence_seed{seed}",
            mechanism_belief="stable_bias",
            correction_context=first_registered_probe_context(probe_context),
            recovery_config=recovery_config,
            evidence_source="registered_probe",
        )
        if not plan.requires_fresh_verification:
            raise ValueError("host compensation planner abstained")
        correction, schedule = plan.correction, plan.schedule
        execution = plan.to_dict()
    else:
        correction, schedule = (0.0, 0.0, 0.0, 0.0), "whole"
        execution = {
            "family": skill.value,
            "correction": correction,
            "schedule": schedule,
            "requires_fresh_verification": True,
        }
    env = create_push_environment(seed)
    policy = PhaseGatedCompensatedPolicy(create_push_policy(), correction, schedule=schedule)
    try:
        result = run_episode(
            env,
            policy,
            seed=seed,
            max_steps=max_steps,
            perturbation=fault.build(),
            perturbation_seed=perturbation_seed,
        )
    finally:
        env.close()
    return result, {
        **execution,
        "verification_status": _verification_status(
            result.success, result.final_object_goal_distance, initial_distance
        ),
    }


def _decision(
    *,
    policy: AnthropicProbeMemPolicy,
    evidence: Mapping[str, Any],
    snapshot: MemorySnapshot,
    registry: Any,
    probe_available: bool,
    probe_collected: bool,
    remaining_steps: int,
    call_budget: ApiCallBudget,
    decision_id: str,
) -> tuple[ProbeMemDecision, dict[str, Any]]:
    if call_budget.calls_used >= call_budget.maximum_calls:
        decision = ProbeMemDecision.fail_closed(
            decision_id=decision_id,
            evidence_id=str(evidence["evidence_id"]),
            memory_snapshot_id=snapshot.snapshot_id,
            reason="fail-closed because the registered API call budget is exhausted",
        )
        return decision, {"status": "fail_closed", "failure_reason": "api_budget_exhausted", "attempts": []}
    return policy.decide(
        decision_id=decision_id,
        evidence=evidence,
        memory_snapshot=snapshot,
        allowed_tools=registry.decision_tools(probe_available=probe_available),
        allowed_skills=registry.available_skills(probe_collected=probe_collected),
        remaining_environment_steps=remaining_steps,
        call_budget=call_budget,
        allow_schema_repair=(call_budget.maximum_calls - call_budget.calls_used >= 2),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--api-timeout", type=float, default=300.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest, config = _validate_manifest(args.manifest.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("run directory has already been executed")
        status_path.write_text(json.dumps({"status": "RUNNING", "manifest_id": manifest["manifest_id"]}, indent=2) + "\n", encoding="utf-8")
        noise_std = float(json.loads((ROOT / "outputs/autoresearch/noise_calibration/selected.json").read_text(encoding="utf-8"))["noise_std"])
        conditions = {item.condition_id: item for item in get_conditions(noise_std)}
        cycle = config["smoke"]["condition_cycle"]
        budget_config = config["budget"]
        namespaces = config["random_seed_namespaces"]
        registry = build_default_tool_registry()
        recovery_config = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / "configs/autoresearch/default_recovery_config.json").read_text(encoding="utf-8")))
        policy = AnthropicProbeMemPolicy(model=config["model"], timeout_seconds=args.api_timeout)
        global_call_limit = int(config["smoke"]["maximum_api_calls"])
        global_calls_used = 0
        target = int(config["smoke"]["target_operational_failures"])
        rows: list[dict[str, Any]] = []
        operational = 0
        seed_start, seed_stop = config["seed_partitions"]["smoke"]
        for index, seed in enumerate(range(int(seed_start), int(seed_stop) + 1)):
            fault = conditions[cycle[index % len(cycle)]]
            episode_id = index + 1
            trajectory = run_dir / "agent_trajectories" / f"seed{seed}_{fault.condition_id}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env,
                    create_push_policy(),
                    seed=seed,
                    max_steps=int(budget_config["initial_rollout_max_steps"]),
                    episode_id=episode_id,
                    perturbation=fault.build(),
                    perturbation_seed=_seed(seed, int(namespaces["initial_rollout"])),
                    agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            budget = CaseBudget().with_initial(initial.steps)
            base = {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
                "episode_id": episode_id,
                "seed": seed,
                "condition_id_oracle": fault.condition_id,
                "initial_success": initial.success,
                "initial_steps": initial.steps,
                "initial_return": initial.episode_return,
                "initial_final_object_goal_distance": initial.final_object_goal_distance,
            }
            if initial.success:
                rows.append({
                    **base,
                    "decision_required": False,
                    "api_calls": 0,
                    "probe_steps": 0,
                    "selected_skill": "NONE",
                    "verification_status": "NOT_REQUIRED",
                    "verification_success": True,
                    "verification_steps": 0,
                    "final_object_goal_distance": initial.final_object_goal_distance,
                    "total_environment_steps": initial.steps,
                    "agent_decision_ms": 0.0,
                })
                _write_csv(run_dir / "results.csv", rows)
                continue
            operational += 1
            transitions = _read_jsonl(trajectory)
            build_start = perf_counter_ns()
            state = build_structured_evidence_state(
                transitions,
                evidence_id=f"seed{seed}_attempt0",
                source=EvidenceSource.FAILED_ROLLOUT,
                attempt_id=0,
            )
            evidence_build_ms = (perf_counter_ns() - build_start) / 1_000_000.0
            snapshot = MemorySnapshot.empty_for_episode(episode_id)
            per_case_calls = min(
                int(config["smoke"]["maximum_api_calls_per_case"]),
                global_call_limit - global_calls_used,
            )
            call_budget = ApiCallBudget(maximum_calls=max(per_case_calls, 0))
            decision_start = perf_counter_ns()
            decision, api_audit = _decision(
                policy=policy,
                evidence=state.to_dict(),
                snapshot=snapshot,
                registry=registry,
                probe_available=budget.can_request_probe(),
                probe_collected=False,
                remaining_steps=budget.remaining_steps,
                call_budget=call_budget,
                decision_id=f"seed{seed}_decision0",
            )
            probe_context: dict[str, Any] | None = None
            decision_audits = [{"decision": decision.to_dict(), "api": api_audit}]
            if decision.requested_tool is ProbeMemTool.REQUEST_DIAGNOSTIC_PROBE:
                probe_context = _probe_context(
                    fault,
                    seed,
                    config,
                    _seed(seed, int(namespaces["diagnostic_probe"])),
                )
                budget = budget.with_probe(int(probe_context["probe_environment_steps"]))
                probe_evidence = {
                    **state.to_dict(),
                    "evidence_id": f"seed{seed}_attempt1_probe",
                    "attempt_id": 1,
                    "source": EvidenceSource.DIAGNOSTIC_PROBE.value,
                    "parent_evidence_ids": [state.evidence_id],
                    "registered_probe_evidence": probe_context,
                }
                decision, second_audit = _decision(
                    policy=policy,
                    evidence=probe_evidence,
                    snapshot=snapshot,
                    registry=registry,
                    probe_available=False,
                    probe_collected=True,
                    remaining_steps=budget.remaining_steps,
                    call_budget=call_budget,
                    decision_id=f"seed{seed}_decision1",
                )
                decision_audits.append({"decision": decision.to_dict(), "api": second_audit})
            decision_ms = (perf_counter_ns() - decision_start) / 1_000_000.0
            global_calls_used += call_budget.calls_used
            selected_skill = decision.selected_skill
            verification = None
            execution: dict[str, Any] = {"verification_status": "NOT_RUN"}
            if decision.requested_tool is ProbeMemTool.SELECT_INTERVENTION_SKILL and selected_skill is not None:
                verification_seed_namespace = (
                    namespaces["stochastic_retry"]
                    if selected_skill is InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY
                    else namespaces["fresh_verification"]
                )
                try:
                    verification, execution = _run_verification(
                        seed=seed,
                        fault=fault,
                        skill=selected_skill,
                        probe_context=probe_context,
                        recovery_config=recovery_config,
                        perturbation_seed=_seed(seed, int(verification_seed_namespace)),
                        max_steps=int(budget_config["fresh_verification_max_steps"]),
                        initial_distance=initial.final_object_goal_distance,
                    )
                    budget = budget.with_verification(verification.steps)
                except ValueError as exc:
                    execution = {"verification_status": "NOT_RUN", "host_rejection": str(exc)}
                    selected_skill = InterventionSkill.ABSTAIN
            audit_record = {
                **base,
                "agent_visible_initial_evidence": state.to_dict(),
                "memory_snapshot": snapshot.to_dict(),
                "decision_trace": decision_audits,
                "probe_context": probe_context,
                "selected_skill": selected_skill.value if selected_skill else None,
                "host_execution": execution,
                "random_seed_provenance": {
                    "initial": _seed(seed, int(namespaces["initial_rollout"])),
                    "probe": _seed(seed, int(namespaces["diagnostic_probe"])),
                    "verification": _seed(seed, int(namespaces["fresh_verification"])),
                    "retry": _seed(seed, int(namespaces["stochastic_retry"])),
                },
                "budget": {
                    "consumed_initial_steps": budget.consumed_initial_steps,
                    "consumed_probe_steps": budget.consumed_probe_steps,
                    "consumed_verification_steps": budget.consumed_verification_steps,
                    "total_consumed_steps": budget.consumed_steps,
                    "remaining_steps": budget.remaining_steps,
                },
            }
            _append_jsonl(run_dir / "interaction_audit.jsonl", audit_record)
            rows.append({
                **base,
                "decision_required": True,
                "api_calls": call_budget.calls_used,
                "probe_steps": budget.consumed_probe_steps,
                "selected_skill": selected_skill.value if selected_skill else "NONE",
                "verification_status": execution["verification_status"],
                "verification_success": bool(verification.success) if verification else False,
                "verification_steps": int(verification.steps) if verification else 0,
                "final_object_goal_distance": (
                    float(verification.final_object_goal_distance)
                    if verification else initial.final_object_goal_distance
                ),
                "total_environment_steps": budget.consumed_steps,
                "agent_decision_ms": decision_ms,
            })
            _write_csv(run_dir / "results.csv", rows)
            print(
                f"seed={seed} condition={fault.condition_id} decision={decision.requested_tool.value} "
                f"skill={selected_skill.value if selected_skill else 'NONE'} "
                f"verification={execution['verification_status']}"
            )
            if operational >= target:
                break
        status = "COMPLETED" if operational == target else "INCOMPLETE_OPERATIONAL_CASES"
        summary = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "status": status,
            "collection_units": len(rows),
            "operational_cases": operational,
            "api_calls": global_calls_used,
            "first_pass_valid_decisions": sum(
                1
                for record in _read_jsonl(run_dir / "interaction_audit.jsonl")
                if record["decision_trace"][0]["api"]["status"] == "valid"
                and not record["decision_trace"][0]["api"]["schema_repair_used"]
            ) if (run_dir / "interaction_audit.jsonl").exists() else 0,
            "fresh_verifications": sum(row["verification_status"] in {"ACCEPTED", "INCONCLUSIVE", "REJECTED"} for row in rows),
            "total_environment_steps": sum(int(row["total_environment_steps"]) for row in rows),
            "note": "Phase B uses an empty memory snapshot and cannot support a memory-benefit claim.",
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        status_path.write_text(json.dumps({"status": status, "manifest_id": manifest["manifest_id"]}, indent=2) + "\n", encoding="utf-8")
        print(f"status: {status}")
        print(f"results: {run_dir / 'results.csv'}")
        print(f"audit: {run_dir / 'interaction_audit.jsonl'}")
        return 0 if status == "COMPLETED" else 2
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
