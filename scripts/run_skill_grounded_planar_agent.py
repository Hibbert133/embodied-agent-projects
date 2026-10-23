"""Run one-call skill-grounded online recovery on fixed push-v3 seeds."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_online_planar_agent import load_evidence, run_rollout, save_csv  # noqa: E402
from src.diagnostic_probes import build_agent_probe_context, estimate_planar_bias, run_symmetric_probes  # noqa: E402
from src.perturbations import ActionBiasPerturbation  # noqa: E402
from src.recovery_skills import build_planar_recovery_skills, select_skill  # noqa: E402
from src.rollout import create_push_environment  # noqa: E402
from src.skill_grounded_agent import AnthropicSkillGroundedAgent  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[250, 251, 252, 253, 254])
    parser.add_argument("--bias-x", type=float, default=0.14)
    parser.add_argument("--bias-y", type=float, default=-0.14)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--probe-magnitude", type=float, default=0.2)
    parser.add_argument("--probe-steps", type=int, default=8)
    parser.add_argument("--model", default="glm-5.2")
    parser.add_argument("--base-url")
    parser.add_argument("--api-timeout", type=float, default=300.0)
    parser.add_argument("--api-max-retries", type=int, default=2)
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "outputs" / "online_planar_agent" / "glm52_skills_dev",
    )
    return parser.parse_args()


def save_summary(path: Path, rows: list[dict[str, Any]], audits: list[dict[str, Any]]) -> None:
    if not rows:
        return
    failures = [row for row in rows if not row["initial_success"]]
    recovered = sum(bool(row["recovery_success"]) for row in failures)
    summary = [{
        "method": "online_skill_grounded",
        "episodes": len(rows),
        "initial_failures": len(failures),
        "recovered": recovered,
        "conditional_recovery_rate": recovered / len(failures) if failures else 0.0,
        "mean_total_recovery_environment_steps": mean(
            float(row["total_recovery_environment_steps"]) for row in failures
        ) if failures else 0.0,
        "mean_final_object_goal_distance": mean(
            float(row["final_object_goal_distance"]) for row in failures
        ) if failures else 0.0,
        "mean_api_latency_ms": mean(
            float(row["request_audit"]["latency_ms"]) for row in audits
        ) if audits else 0.0,
        "total_input_tokens": sum(
            int(row["request_audit"]["usage"].get("input_tokens", 0)) for row in audits
        ),
        "total_output_tokens": sum(
            int(row["request_audit"]["usage"].get("output_tokens", 0)) for row in audits
        ),
    }]
    save_csv(path, summary)


def main() -> int:
    args = parse_args()
    if not args.seeds or args.max_steps <= 0 or args.probe_steps <= 0:
        print("[FAIL] seeds and positive step budgets are required", file=sys.stderr)
        return 1
    bias = (float(args.bias_x), float(args.bias_y), 0.0, 0.0)
    output = args.output_dir.expanduser().resolve()
    trajectory_dir = output / "trajectories"
    agent = AnthropicSkillGroundedAgent(
        model=args.model, base_url=args.base_url,
        timeout_seconds=args.api_timeout, max_retries=args.api_max_retries,
    )
    rows: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    try:
        for seed in args.seeds:
            baseline_path = trajectory_dir / f"seed{seed}_baseline.jsonl"
            baseline = run_rollout(
                seed=seed, bias=bias, correction=(0.0, 0.0, 0.0, 0.0),
                schedule="whole", max_steps=args.max_steps,
                trajectory_path=baseline_path,
            )
            if baseline.success:
                rows.append({
                    "seed": seed, "initial_success": True, "api_calls": 0,
                    "skill_id": "not_needed", "correction_x": 0.0,
                    "correction_y": 0.0, "correction_schedule": "whole",
                    "recovery_success": True, "recovery_steps": 0,
                    "probe_environment_steps": 0,
                    "total_recovery_environment_steps": 0,
                    "final_object_goal_distance": baseline.final_object_goal_distance,
                })
                save_csv(output / "results.csv", rows)
                continue
            evidence = load_evidence(baseline_path)
            probes = run_symmetric_probes(
                lambda: create_push_environment(seed), seed=seed,
                perturbation_factory=lambda: ActionBiasPerturbation(bias),
                magnitude=args.probe_magnitude, steps=args.probe_steps,
            )
            raw_context = build_agent_probe_context(probes, estimate_planar_bias(probes))
            diagnosis, skills = build_planar_recovery_skills(raw_context)
            decision, request_audit = agent.decide(
                episode_evidence=evidence.to_dict(), structured_diagnosis=diagnosis,
                skills=skills, remaining_rollouts=1,
            )
            if decision.stop:
                recovery = baseline
                correction = (0.0, 0.0, 0.0, 0.0)
                recovery_steps = 0
            else:
                selected = select_skill(skills, decision.skill_id)
                correction = selected.correction
                recovery = run_rollout(
                    seed=seed, bias=bias, correction=correction,
                    schedule=decision.correction_schedule, max_steps=args.max_steps,
                    trajectory_path=trajectory_dir / f"seed{seed}_repair.jsonl",
                )
                recovery_steps = recovery.steps
            probe_steps = int(diagnosis["probe_environment_steps"])
            rows.append({
                "seed": seed, "initial_success": False, "api_calls": 1,
                "skill_id": decision.skill_id,
                "correction_x": correction[0], "correction_y": correction[1],
                "correction_schedule": decision.correction_schedule,
                "recovery_success": recovery.success,
                "recovery_steps": recovery_steps,
                "probe_environment_steps": probe_steps,
                "total_recovery_environment_steps": probe_steps + recovery_steps,
                "final_object_goal_distance": recovery.final_object_goal_distance,
            })
            audits.append({
                "seed": seed, "decision": decision.to_dict(),
                "request_audit": request_audit,
                "structured_diagnosis": diagnosis,
                "available_skills": [skill.to_dict() for skill in skills],
            })
            save_csv(output / "results.csv", rows)
            (output / "planner_audit.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audits),
                encoding="utf-8",
            )
            save_summary(output / "summary.csv", rows, audits)
            print(
                f"seed={seed} skill={decision.skill_id} schedule="
                f"{decision.correction_schedule} success={recovery.success}"
            )
        save_summary(output / "summary.csv", rows, audits)
        print(f"results: {(output / 'results.csv').resolve()}")
        print(f"summary: {(output / 'summary.csv').resolve()}")
        print(f"audit: {(output / 'planner_audit.jsonl').resolve()}")
        return 0
    except Exception as exc:
        save_csv(output / "results.csv", rows)
        save_summary(output / "summary.csv", rows, audits)
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
