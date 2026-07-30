"""Run a one-call online planar recovery pilot on fixed push-v3 seeds."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.diagnostic_probes import build_agent_probe_context, estimate_planar_bias, run_symmetric_probes  # noqa: E402
from src.online_planar_agent import AnthropicPlanarRecoveryAgent  # noqa: E402
from src.perturbations import ActionBiasPerturbation  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy, build_episode_evidence  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402
from src.trajectory_views import build_agent_view  # noqa: E402


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
    parser.add_argument("--api-timeout", type=float, default=180.0)
    parser.add_argument("--api-max-retries", type=int, default=2)
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "outputs" / "online_planar_agent" / "glm52_dev",
    )
    return parser.parse_args()


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def load_evidence(path: Path) -> Any:
    records = [
        build_agent_view(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    return build_episode_evidence(records)


def run_rollout(
    *, seed: int, bias: tuple[float, float, float, float], correction: Any,
    schedule: str, max_steps: int, trajectory_path: Path,
) -> Any:
    env = create_push_environment(seed)
    policy = PhaseGatedCompensatedPolicy(create_push_policy(), correction, schedule=schedule)
    try:
        return run_episode(
            env, policy, seed=seed, max_steps=max_steps,
            trajectory_path=trajectory_path,
            perturbation=ActionBiasPerturbation(bias),
        )
    finally:
        env.close()


def main() -> int:
    args = parse_args()
    if not args.seeds or args.max_steps <= 0 or args.probe_steps <= 0:
        print("[FAIL] seeds and positive step budgets are required", file=sys.stderr)
        return 1
    bias = (float(args.bias_x), float(args.bias_y), 0.0, 0.0)
    output = args.output_dir.expanduser().resolve()
    trajectory_dir = output / "trajectories"
    agent = AnthropicPlanarRecoveryAgent(
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
                    "repair_mode": "not_needed", "correction_x": 0.0,
                    "correction_y": 0.0, "correction_schedule": "whole",
                    "recovery_success": True, "recovery_steps": 0,
                    "probe_environment_steps": 0, "total_recovery_environment_steps": 0,
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
            context = build_agent_probe_context(probes, estimate_planar_bias(probes))
            decision, audit = agent.decide(
                episode_evidence=evidence.to_dict(), diagnostic_context=context,
                remaining_rollouts=1,
            )
            if decision.stop:
                recovery = baseline
                recovery_steps = 0
            else:
                repair_path = trajectory_dir / f"seed{seed}_repair.jsonl"
                recovery = run_rollout(
                    seed=seed, bias=bias, correction=decision.correction(),
                    schedule=decision.correction_schedule, max_steps=args.max_steps,
                    trajectory_path=repair_path,
                )
                recovery_steps = recovery.steps
            probe_steps = int(context["probe_environment_steps"])
            rows.append({
                "seed": seed, "initial_success": False, "api_calls": 1,
                "repair_mode": decision.repair_mode,
                "correction_x": decision.correction_x,
                "correction_y": decision.correction_y,
                "correction_schedule": decision.correction_schedule,
                "recovery_success": recovery.success,
                "recovery_steps": recovery_steps,
                "probe_environment_steps": probe_steps,
                "total_recovery_environment_steps": probe_steps + recovery_steps,
                "final_object_goal_distance": recovery.final_object_goal_distance,
            })
            audits.append({
                "seed": seed, "decision": decision.to_dict(), "request_audit": audit,
                "agent_probe_inference": context["inference"],
            })
            save_csv(output / "results.csv", rows)
            (output / "planner_audit.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in audits),
                encoding="utf-8",
            )
            print(
                f"seed={seed} mode={decision.repair_mode} correction="
                f"({decision.correction_x:+.3f},{decision.correction_y:+.3f}) "
                f"success={recovery.success}"
            )
        print(f"results: {(output / 'results.csv').resolve()}")
        print(f"audit: {(output / 'planner_audit.jsonl').resolve()}")
        return 0
    except Exception as exc:
        save_csv(output / "results.csv", rows)
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
