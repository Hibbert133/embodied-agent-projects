"""Run the chronological stateless/raw/verified ProbeMem Phase-C comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import get_conditions  # noqa: E402
from scripts.run_probemem_v2_smoke import (  # noqa: E402
    _append_jsonl,
    _probe_context,
    _read_jsonl,
    _run_verification,
    _seed,
    _write_csv,
)
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.probemem import (  # noqa: E402
    CaseBudget,
    ChronologicalEpisodeMemory,
    EvidenceSignature,
    InterventionSkill,
    MemorySnapshot,
    ProbeMemTool,
    RecoveryExperience,
    build_default_tool_registry,
)
from src.probemem.models import ProbeMemDecision  # noqa: E402
from src.probemem.online_policy import AnthropicProbeMemPolicy, ApiCallBudget  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state  # noqa: E402
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


def _validate_manifest(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if path.parent.name != manifest["experiment_run_id"]:
        raise ValueError("manifest directory does not match experiment_run_id")
    if _git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise RuntimeError("current HEAD differs from the Phase-C manifest")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Phase-C execution requires a clean tracked worktree")
    config_path = ROOT / manifest["config_path"]
    if _sha256(config_path) != manifest["config_sha256"]:
        raise RuntimeError("Phase-C config differs from its manifest")
    for relative, expected in manifest["implementation_sha256"].items():
        if _sha256(ROOT / relative) != expected:
            raise RuntimeError(f"implementation differs from manifest: {relative}")
    return manifest, json.loads(config_path.read_text(encoding="utf-8"))


def _memory_context(
    method: str,
    memory: ChronologicalEpisodeMemory,
    signature: EvidenceSignature,
    episode_id: int,
    limit: int,
) -> tuple[MemorySnapshot, list[dict[str, Any]]]:
    if method == "stateless_online_llm":
        return MemorySnapshot.empty_for_episode(episode_id), []
    if method == "raw_episodic_retrieval_development_only":
        rows = memory.retrieve_raw_development_only(
            signature,
            current_episode_id=episode_id,
            limit=limit,
            development_only=True,
        )
        snapshot = memory.raw_snapshot_before(episode_id)
    elif method == "verified_episodic_retrieval":
        rows = memory.retrieve_verified(
            signature, current_episode_id=episode_id, limit=limit
        )
        snapshot = memory.snapshot_before(episode_id)
    else:
        raise ValueError(f"unsupported Phase-C method: {method}")
    selected_ids = tuple(item.record_id for item in rows)
    snapshot = MemorySnapshot(
        schema_version=2,
        snapshot_id=snapshot.snapshot_id,
        created_before_episode_id=episode_id,
        verified_episode_ids=(
            selected_ids if method == "verified_episodic_retrieval" else ()
        ),
        retrievable_episode_ids=selected_ids,
        memory_mode=snapshot.memory_mode,
    )
    return snapshot, [item.to_prompt_dict() for item in rows]


def _decide(
    *,
    policy: AnthropicProbeMemPolicy,
    decision_id: str,
    evidence: Mapping[str, Any],
    snapshot: MemorySnapshot,
    records: list[dict[str, Any]],
    registry: Any,
    probe_available: bool,
    probe_collected: bool,
    remaining_steps: int,
    call_budget: ApiCallBudget,
) -> tuple[ProbeMemDecision, dict[str, Any]]:
    if call_budget.calls_used >= call_budget.maximum_calls:
        decision = ProbeMemDecision.fail_closed(
            decision_id=decision_id,
            evidence_id=str(evidence["evidence_id"]),
            memory_snapshot_id=snapshot.snapshot_id,
            reason="fail-closed because the per-method API budget is exhausted",
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
        retrieved_episode_records=records,
        allow_schema_repair=False,
    )


def _api_metrics(trace: list[dict[str, Any]]) -> dict[str, float | int]:
    attempts = [
        attempt
        for item in trace
        for attempt in item["api"].get("attempts", [])
    ]
    return {
        "api_latency_ms": sum(float(item.get("latency_ms", 0.0)) for item in attempts),
        "api_input_tokens": sum(
            int(item.get("usage", {}).get("input_tokens", 0)) for item in attempts
        ),
        "api_output_tokens": sum(
            int(item.get("usage", {}).get("output_tokens", 0)) for item in attempts
        ),
        "invalid_structured_outputs": sum(not bool(item.get("valid")) for item in attempts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--api-timeout", type=float, default=300.0)
    args = parser.parse_args()
    status_path: Path | None = None
    try:
        manifest, config = _validate_manifest(args.manifest.resolve())
        run_dir = args.manifest.resolve().parent
        status_path = run_dir / "run_status.json"
        if status_path.exists():
            raise FileExistsError("Phase-C run directory has already been executed")
        status_path.write_text(json.dumps({"status": "RUNNING", "manifest_id": manifest["manifest_id"]}, indent=2) + "\n", encoding="utf-8")
        noise_std = float(json.loads((ROOT / "outputs/autoresearch/noise_calibration/selected.json").read_text(encoding="utf-8"))["noise_std"])
        conditions = {item.condition_id: item for item in get_conditions(noise_std)}
        methods = tuple(str(item) for item in config["methods"])
        cycle = tuple(str(item) for item in config["condition_cycle"])
        scales = tuple(float(item) for item in config["retrieval"]["fixed_scales"])
        memories = {method: ChronologicalEpisodeMemory(scales=scales) for method in methods}
        registry = build_default_tool_registry()
        recovery_config = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / "configs/autoresearch/default_recovery_config.json").read_text(encoding="utf-8")))
        policy = AnthropicProbeMemPolicy(model=config["model"], timeout_seconds=args.api_timeout)
        namespaces = config["random_seed_namespaces"]
        budget_config = config["budget"]
        global_limit = int(config["api_budget"]["maximum_calls"])
        global_calls = 0
        rows: list[dict[str, Any]] = []
        seed_start, seed_stop = (int(item) for item in config["seed_range"])
        for index, seed in enumerate(range(seed_start, seed_stop + 1)):
            episode_id = index + 1
            fault = conditions[cycle[index % len(cycle)]]
            trajectory = run_dir / "shared_initial_trajectories" / f"episode{episode_id:03d}_seed{seed}.jsonl"
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
            state = build_structured_evidence_state(
                _read_jsonl(trajectory),
                evidence_id=f"phase_c_episode{episode_id:03d}_attempt0",
                source=EvidenceSource.FAILED_ROLLOUT,
                attempt_id=0,
            )
            signature = EvidenceSignature.from_structured_evidence(state.to_dict())
            for method in methods:
                base = {
                    "experiment_run_id": manifest["experiment_run_id"],
                    "manifest_id": manifest["manifest_id"],
                    "source_git_commit": manifest["source_git_commit"],
                    "method": method,
                    "episode_id": episode_id,
                    "seed": seed,
                    "condition_id_oracle": fault.condition_id,
                    "initial_success": initial.success,
                    "initial_steps": initial.steps,
                    "initial_final_object_goal_distance": initial.final_object_goal_distance,
                }
                if initial.success:
                    rows.append({
                        **base,
                        "decision_required": False,
                        "retrieved_records": 0,
                        "memory_used": False,
                        "api_calls": 0,
                        "api_latency_ms": 0.0,
                        "api_input_tokens": 0,
                        "api_output_tokens": 0,
                        "invalid_structured_outputs": 0,
                        "probe_steps": 0,
                        "selected_skill": "NONE",
                        "verification_status": "NOT_REQUIRED",
                        "verification_success": True,
                        "verification_steps": 0,
                        "final_object_goal_distance": initial.final_object_goal_distance,
                        "total_environment_steps": initial.steps,
                    })
                    continue
                memory = memories[method]
                snapshot, retrieved = _memory_context(
                    method, memory, signature, episode_id,
                    int(config["retrieval"]["maximum_episodes"]),
                )
                remaining_global = global_limit - global_calls
                per_case = min(
                    int(config["api_budget"]["maximum_calls_per_method_case"]),
                    remaining_global,
                )
                calls = ApiCallBudget(maximum_calls=max(per_case, 0))
                budget = CaseBudget().with_initial(initial.steps)
                decision, api_audit = _decide(
                    policy=policy,
                    decision_id=f"{method}_episode{episode_id:03d}_decision0",
                    evidence=state.to_dict(),
                    snapshot=snapshot,
                    records=retrieved,
                    registry=registry,
                    probe_available=budget.can_request_probe(),
                    probe_collected=False,
                    remaining_steps=budget.remaining_steps,
                    call_budget=calls,
                )
                trace = [{"decision": decision.to_dict(), "api": api_audit}]
                probe_context = None
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
                        "evidence_id": f"phase_c_episode{episode_id:03d}_{method}_attempt1",
                        "attempt_id": 1,
                        "source": EvidenceSource.DIAGNOSTIC_PROBE.value,
                        "parent_evidence_ids": [state.evidence_id],
                        "registered_probe_evidence": probe_context,
                    }
                    decision, second_audit = _decide(
                        policy=policy,
                        decision_id=f"{method}_episode{episode_id:03d}_decision1",
                        evidence=probe_evidence,
                        snapshot=snapshot,
                        records=retrieved,
                        registry=registry,
                        probe_available=False,
                        probe_collected=True,
                        remaining_steps=budget.remaining_steps,
                        call_budget=calls,
                    )
                    trace.append({"decision": decision.to_dict(), "api": second_audit})
                global_calls += calls.calls_used
                api_metrics = _api_metrics(trace)
                selected = decision.selected_skill
                verification = None
                execution: dict[str, Any] = {"verification_status": "NOT_RUN"}
                if decision.requested_tool is ProbeMemTool.SELECT_INTERVENTION_SKILL and selected is not None:
                    namespace = (
                        namespaces["stochastic_retry"]
                        if selected is InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY
                        else namespaces["fresh_verification"]
                    )
                    try:
                        verification, execution = _run_verification(
                            seed=seed,
                            fault=fault,
                            skill=selected,
                            probe_context=probe_context,
                            recovery_config=recovery_config,
                            perturbation_seed=_seed(seed, int(namespace)),
                            max_steps=int(budget_config["fresh_verification_max_steps"]),
                            initial_distance=initial.final_object_goal_distance,
                        )
                        budget = budget.with_verification(verification.steps)
                    except ValueError as exc:
                        selected = InterventionSkill.ABSTAIN
                        execution = {"verification_status": "NOT_RUN", "host_rejection": str(exc)}
                if verification is not None and selected is not None:
                    prediction = decision.predicted_outcome
                    assert prediction is not None
                    memory.record(RecoveryExperience(
                        schema_version=1,
                        record_id=f"{method}_episode{episode_id:03d}",
                        source_episode_id=episode_id,
                        source_manifest_id=manifest["manifest_id"],
                        signature=signature,
                        selected_skill=selected,
                        predicted_verification_status=prediction.verification_status,
                        observed_verification_status=str(execution["verification_status"]),
                        verification_success=bool(verification.success),
                        interaction_cost=budget.consumed_steps,
                    ))
                _append_jsonl(run_dir / "interaction_audit.jsonl", {
                    **base,
                    "agent_visible_initial_evidence": state.to_dict(),
                    "memory_snapshot": snapshot.to_dict(),
                    "retrieved_episode_records": retrieved,
                    "decision_trace": trace,
                    "selected_skill": selected.value if selected else None,
                    "host_execution": execution,
                    "budget": {
                        "initial": budget.consumed_initial_steps,
                        "probe": budget.consumed_probe_steps,
                        "verification": budget.consumed_verification_steps,
                        "total": budget.consumed_steps,
                    },
                })
                rows.append({
                    **base,
                    "decision_required": True,
                    "retrieved_records": len(retrieved),
                    "memory_used": bool(decision.memory_used),
                    "api_calls": calls.calls_used,
                    **api_metrics,
                    "probe_steps": budget.consumed_probe_steps,
                    "selected_skill": selected.value if selected else "NONE",
                    "verification_status": execution["verification_status"],
                    "verification_success": bool(verification.success) if verification else False,
                    "verification_steps": int(verification.steps) if verification else 0,
                    "final_object_goal_distance": (
                        verification.final_object_goal_distance if verification
                        else initial.final_object_goal_distance
                    ),
                    "total_environment_steps": budget.consumed_steps,
                })
                print(
                    f"episode={episode_id} seed={seed} method={method} "
                    f"retrieved={len(retrieved)} skill={selected.value if selected else 'NONE'} "
                    f"verification={execution['verification_status']}"
                )
                _write_csv(run_dir / "results.csv", rows)
                memory.save(run_dir / "memory" / method)
            _write_csv(run_dir / "results.csv", rows)
        summary_rows = []
        for method in methods:
            selected_rows = [row for row in rows if row["method"] == method and row["decision_required"]]
            summary_rows.append({
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "method": method,
                "operational_cases": len(selected_rows),
                "accepted": sum(row["verification_status"] == "ACCEPTED" for row in selected_rows),
                "rejected": sum(row["verification_status"] == "REJECTED" for row in selected_rows),
                "inconclusive": sum(row["verification_status"] == "INCONCLUSIVE" for row in selected_rows),
                "not_run": sum(row["verification_status"] == "NOT_RUN" for row in selected_rows),
                "probe_environment_steps": sum(int(row["probe_steps"]) for row in selected_rows),
                "verification_environment_steps": sum(int(row["verification_steps"]) for row in selected_rows),
                "total_environment_steps": sum(int(row["total_environment_steps"]) for row in selected_rows),
                "api_calls": sum(int(row["api_calls"]) for row in selected_rows),
                "api_latency_ms": sum(float(row["api_latency_ms"]) for row in selected_rows),
                "api_input_tokens": sum(int(row["api_input_tokens"]) for row in selected_rows),
                "api_output_tokens": sum(int(row["api_output_tokens"]) for row in selected_rows),
                "invalid_structured_outputs": sum(
                    int(row["invalid_structured_outputs"]) for row in selected_rows
                ),
                "memory_use_cases": sum(bool(row["memory_used"]) for row in selected_rows),
            })
        _write_csv(run_dir / "summary.csv", summary_rows)
        status_path.write_text(json.dumps({"status": "COMPLETED", "manifest_id": manifest["manifest_id"], "api_calls": global_calls}, indent=2) + "\n", encoding="utf-8")
        print(f"results: {run_dir / 'results.csv'}")
        print(f"summary: {run_dir / 'summary.csv'}")
        return 0
    except Exception as exc:
        if status_path is not None:
            status_path.write_text(
                json.dumps(
                    {
                        "status": "FAILED",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
