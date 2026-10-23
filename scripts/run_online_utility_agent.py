"""Run online candidate-utility selection on six frozen push-v3 tuning cases."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import (  # noqa: E402
    FaultCondition,
    rollout,
    save_csv,
    save_jsonl,
)
from src.autoresearch import RecoveryPolicyConfig, choose_runtime_skill  # noqa: E402
from src.diagnostic_probes import (  # noqa: E402
    build_agent_probe_context,
    estimate_planar_bias,
    run_symmetric_probes,
)
from src.recovery_skills import build_planar_recovery_skills, select_skill  # noqa: E402
from src.rollout import create_push_environment  # noqa: E402
from src.stochastic_recovery import derive_retry_seed  # noqa: E402
from src.utility_agent import AnthropicUtilityAgent  # noqa: E402
from src.online_planar_agent import validate_agent_payload  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="glm-5.2")
    parser.add_argument("--base-url")
    parser.add_argument("--api-timeout", type=float, default=300)
    parser.add_argument("--api-max-retries", type=int, default=2)
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=ROOT / "outputs/autoresearch/benchmark_tuning",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=(
            ROOT
            / "outputs/autoresearch/search_tuning/research_agent/"
            "research_r1_c1/candidate.json"
        ),
    )
    parser.add_argument("--case-ids", nargs="+")
    parser.add_argument("--candidate-probe-steps", type=int, default=80)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--max-api-calls", type=int, default=6)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="run and checkpoint candidate probes without making API calls",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def load_jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    return {
        record["case_id"]: record
        for record in (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def save_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def portable_path(path: Path) -> str:
    """Prefer repository-relative paths in committed experiment configs."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def probe_view(
    candidate_id: str, result: Any, probe_budget_steps: int
) -> dict[str, Any]:
    """Expose action-conditioned outcomes, never injected-fault metadata."""

    return {
        "candidate_id": candidate_id,
        "success_within_probe_budget": result.success,
        "steps": result.steps,
        "probe_budget_steps": probe_budget_steps,
        "final_object_goal_distance": result.final_object_goal_distance,
        "progress_to_goal": result.progress_to_goal,
        "minimum_gripper_object_distance": result.min_gripper_object_distance,
        "object_displacement": result.object_displacement,
    }


def main() -> int:
    args = parse_args()
    try:
        if args.candidate_probe_steps <= 0 or args.max_steps <= 0:
            raise ValueError("step budgets must be positive")
        output = args.output_dir.resolve()
        config_mapping = json.loads(args.config.read_text(encoding="utf-8"))
        config = RecoveryPolicyConfig.from_mapping(config_mapping)
        agent_cases = load_jsonl_by_id(args.benchmark_dir / "agent_cases.jsonl")
        oracle_cases = load_jsonl_by_id(args.benchmark_dir / "oracle_audit.jsonl")
        case_ids = args.case_ids or json.loads(
            (
                ROOT / "outputs/autoresearch/search_tuning/selected_case_ids.json"
            ).read_text(encoding="utf-8")
        )
        if not case_ids or len(case_ids) > args.max_api_calls:
            raise ValueError("case count must be positive and within the API-call budget")
        missing = set(case_ids) - (set(agent_cases) & set(oracle_cases))
        if missing:
            raise ValueError(f"benchmark is missing cases: {sorted(missing)}")

        run_config = {
            "protocol": "online-candidate-utility-v1",
            "model": args.model,
            "base_url": args.base_url or "environment",
            "benchmark_dir": portable_path(args.benchmark_dir),
            "recovery_config": config_mapping,
            "case_ids": case_ids,
            "candidate_probe_steps": args.candidate_probe_steps,
            "max_steps": args.max_steps,
            "max_api_calls": args.max_api_calls,
        }
        config_path = output / "run_config.json"
        if config_path.exists():
            recorded = json.loads(config_path.read_text(encoding="utf-8"))
            if recorded != run_config:
                raise RuntimeError(
                    "existing run configuration differs; choose a new output directory"
                )
        else:
            save_json(config_path, run_config)

        results = load_csv(output / "results.csv")
        audits = load_jsonl(output / "planner_audit.jsonl")
        prepared_rows = load_jsonl(output / "prepared_cases.jsonl")
        prepared_by_id = {str(row["case_id"]): row for row in prepared_rows}
        completed = {str(row["case_id"]) for row in results}
        if completed != {str(row["case_id"]) for row in audits}:
            raise RuntimeError("results and planner audit checkpoints are inconsistent")

        online = None
        if not args.prepare_only:
            online = AnthropicUtilityAgent(
                model=args.model,
                base_url=args.base_url,
                timeout_seconds=args.api_timeout,
                max_retries=args.api_max_retries,
            )
        for case_id in case_ids:
            if case_id in completed:
                print(f"case={case_id} status=already_complete")
                continue
            visible = agent_cases[case_id]
            hidden = oracle_cases[case_id]
            seed = int(visible["seed"])
            # Oracle fields instantiate the simulator only. They are never passed
            # to AnthropicUtilityAgent and appear only in the post-hoc result CSV.
            fault = FaultCondition(
                hidden["condition_id"],
                hidden["perturbation_type"],
                hidden["perturbation_parameters"],
            )
            compensation_id = "bias_compensation"
            retry_id = "stochastic_retry"
            if case_id in prepared_by_id:
                prepared = prepared_by_id[case_id]
                diagnosis = prepared["structured_diagnosis"]
                candidates = prepared["candidates"]
                candidate_evidence = prepared["candidate_probe_evidence"]
                active_steps = int(prepared["active_probe_steps"])
                candidate_steps = int(prepared["candidate_probe_steps"])
                print(f"case={case_id} evidence=already_prepared")
            else:
                probes = run_symmetric_probes(
                    lambda: create_push_environment(seed),
                    seed=seed,
                    perturbation_factory=fault.build,
                    magnitude=config.probe_magnitude,
                    steps=config.probe_steps_per_direction,
                )
                context = build_agent_probe_context(
                    probes, estimate_planar_bias(probes)
                )
                diagnosis, skills = build_planar_recovery_skills(context)
                runtime = choose_runtime_skill(config, diagnosis)
                if runtime.skill_id == "abstain_and_escalate":
                    raise RuntimeError(
                        f"{case_id}: diagnosis produced no executable compensation candidate"
                    )
                compensation = select_skill(skills, runtime.skill_id)
                candidates = [
                    {
                        "candidate_id": compensation_id,
                        "strategy": "apply inferred bounded compensation",
                        "correction": compensation.correction,
                        "schedule": runtime.schedule,
                        "max_full_rollout_steps": args.max_steps,
                    },
                    {
                        "candidate_id": retry_id,
                        "strategy": (
                            "retry without correction on a fresh execution realization"
                        ),
                        "correction": [0.0, 0.0, 0.0, 0.0],
                        "schedule": "whole",
                        "max_full_rollout_steps": args.max_steps,
                    },
                ]

                # Candidate probes and final execution use distinct reproducible
                # streams. Probe outcomes cannot replay the final future.
                compensation_probe = rollout(
                    seed,
                    fault,
                    compensation.correction,
                    runtime.schedule,
                    args.candidate_probe_steps,
                    perturbation_seed=derive_retry_seed(seed, 101),
                )
                retry_probe = rollout(
                    seed,
                    fault,
                    (0.0, 0.0, 0.0, 0.0),
                    "whole",
                    args.candidate_probe_steps,
                    perturbation_seed=derive_retry_seed(seed, 102),
                )
                candidate_evidence = [
                    probe_view(
                        compensation_id,
                        compensation_probe,
                        args.candidate_probe_steps,
                    ),
                    probe_view(retry_id, retry_probe, args.candidate_probe_steps),
                ]
                active_steps = int(context["probe_environment_steps"])
                candidate_steps = compensation_probe.steps + retry_probe.steps
                prepared = {
                    "case_id": case_id,
                    "seed": seed,
                    "structured_diagnosis": diagnosis,
                    "candidates": candidates,
                    "candidate_probe_evidence": candidate_evidence,
                    "active_probe_steps": active_steps,
                    "candidate_probe_steps": candidate_steps,
                }
                validate_agent_payload(prepared)
                prepared_rows.append(prepared)
                prepared_by_id[case_id] = prepared
                save_jsonl(output / "prepared_cases.jsonl", prepared_rows)
                print(f"case={case_id} evidence=prepared")

            if args.prepare_only:
                continue

            compensation_candidate = next(
                candidate
                for candidate in candidates
                if candidate["candidate_id"] == compensation_id
            )
            compensation_correction = tuple(compensation_candidate["correction"])
            compensation_schedule = str(compensation_candidate["schedule"])
            assert online is not None
            decision, request_audit = online.decide(
                episode_evidence={
                    "case_id": case_id,
                    "seed": seed,
                    "initial_rollout": visible["initial_rollout"],
                },
                structured_diagnosis=diagnosis,
                candidates=candidates,
                candidate_probe_evidence=candidate_evidence,
            )
            execution_seed = derive_retry_seed(seed, 201)
            if decision.candidate_id == compensation_id:
                final = rollout(
                    seed,
                    fault,
                    compensation_correction,
                    compensation_schedule,
                    args.max_steps,
                    perturbation_seed=execution_seed,
                )
            else:
                final = rollout(
                    seed,
                    fault,
                    (0.0, 0.0, 0.0, 0.0),
                    "whole",
                    args.max_steps,
                    perturbation_seed=execution_seed,
                )
            total_steps = active_steps + candidate_steps + final.steps
            results.append(
                {
                    "case_id": case_id,
                    "seed": seed,
                    "condition_id": hidden["condition_id"],
                    "model": args.model,
                    "candidate_id": decision.candidate_id,
                    "recovery_success": final.success,
                    "active_probe_steps": active_steps,
                    "candidate_probe_steps": candidate_steps,
                    "final_rollout_steps": final.steps,
                    "total_recovery_environment_steps": total_steps,
                    "final_object_goal_distance": final.final_object_goal_distance,
                    "api_calls": 1,
                    "api_latency_ms": request_audit["latency_ms"],
                }
            )
            audits.append(
                {
                    "case_id": case_id,
                    "decision": decision.to_dict(),
                    "request_audit": request_audit,
                    "structured_diagnosis": diagnosis,
                    "candidates": candidates,
                    "candidate_probe_evidence": candidate_evidence,
                }
            )
            save_csv(output / "results.csv", results)
            save_jsonl(output / "planner_audit.jsonl", audits)
            print(
                f"case={case_id} selected={decision.candidate_id} "
                f"success={final.success}"
            )

        if args.prepare_only:
            print(f"prepared: {(output / 'prepared_cases.jsonl').resolve()}")
            return 0

        recovered = sum(as_bool(row["recovery_success"]) for row in results)
        summary = [
            {
                "method": "online_candidate_utility_agent",
                "model": args.model,
                "cases": len(results),
                "recovered": recovered,
                "conditional_recovery_rate": recovered / len(results),
                "mean_total_recovery_environment_steps": mean(
                    float(row["total_recovery_environment_steps"])
                    for row in results
                ),
                "mean_final_object_goal_distance": mean(
                    float(row["final_object_goal_distance"]) for row in results
                ),
                "api_calls": len(results),
                "mean_api_latency_ms": mean(
                    float(row["api_latency_ms"]) for row in results
                ),
            }
        ]
        save_csv(output / "summary.csv", summary)
        print(f"summary: {(output / 'summary.csv').resolve()}")
        print(f"audit: {(output / 'planner_audit.jsonl').resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
