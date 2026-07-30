"""Run bounded push-v3 recovery with random, rule, OpenAI, or Oracle planning."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.openai_recovery_planner import OpenAIRecoveryPlanner  # noqa: E402
from src.anthropic_recovery_planner import AnthropicRecoveryPlanner  # noqa: E402
from src.perturbations import ActionBiasPerturbation  # noqa: E402
from src.recovery_agent import (  # noqa: E402
    CompensatedPolicy,
    NoRecoveryPlanner,
    OracleRecoveryPlanner,
    RandomRecoveryPlanner,
    RecoveryPlanner,
    ProbeGuidedRecoveryPlanner,
    PhaseGatedCompensatedPolicy,
    RuleBasedRecoveryPlanner,
    TrialOutcome,
    run_budgeted_recovery,
)
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402
from src.trajectory_views import build_agent_view  # noqa: E402
from src.diagnostic_probes import (  # noqa: E402
    build_agent_probe_context,
    estimate_planar_bias,
    run_symmetric_probes,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--planner", choices=("none", "random", "rule", "probe_rule", "openai", "anthropic", "oracle"), default="rule")
    parser.add_argument("--num-episodes", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--seeds", type=int, nargs="+", help="Explicit seed list; overrides --num-episodes and --seed-start")
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument("--max-trials", type=int, default=5)
    parser.add_argument("--bias-axis", choices=("x", "y"), default="x")
    parser.add_argument("--bias-sign", choices=("positive", "negative"), default="positive")
    parser.add_argument("--bias-magnitude", type=float, default=0.145)
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL") or os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OPENAI_MODEL"))
    parser.add_argument("--base-url", default=os.environ.get("ANTHROPIC_BASE_URL"))
    parser.add_argument("--reasoning-effort", choices=("none", "low", "medium", "high", "xhigh", "max"), default="medium")
    parser.add_argument("--api-timeout", type=float, default=180.0)
    parser.add_argument("--api-max-retries", type=int, default=2)
    parser.add_argument("--output-csv", type=Path, default=PROJECT_ROOT / "outputs" / "recovery" / "trials.csv")
    parser.add_argument("--audit-jsonl", type=Path, default=PROJECT_ROOT / "outputs" / "recovery" / "planner_audit.jsonl")
    parser.add_argument("--trajectory-dir", type=Path, default=PROJECT_ROOT / "outputs" / "recovery" / "trajectories")
    parser.add_argument("--video-dir", type=Path, help="Record every trial to this directory")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--active-probes", action="store_true", help="Run four leakage-safe diagnostic probes before recovery planning")
    parser.add_argument("--probe-magnitude", type=float, default=0.2)
    parser.add_argument("--probe-steps", type=int, default=8)
    parser.add_argument("--correction-schedule", choices=("whole", "push_only", "phase_aware"), default="whole")
    parser.add_argument("--contact-distance", type=float, default=0.08)
    parser.add_argument("--near-goal-distance", type=float, default=0.08)
    return parser.parse_args()


def hidden_bias(args: argparse.Namespace) -> tuple[float, float, float, float]:
    if args.bias_magnitude <= 0:
        raise ValueError("--bias-magnitude must be positive")
    vector = [0.0, 0.0, 0.0, 0.0]
    vector[0 if args.bias_axis == "x" else 1] = args.bias_magnitude * (
        1.0 if args.bias_sign == "positive" else -1.0
    )
    return tuple(vector)


def make_planner(
    args: argparse.Namespace,
    seed: int,
    bias: tuple[float, ...],
    diagnostic_context: dict[str, Any] | None = None,
) -> RecoveryPlanner:
    if args.planner == "none":
        return NoRecoveryPlanner()
    if args.planner == "random":
        return RandomRecoveryPlanner(seed)
    if args.planner == "rule":
        return RuleBasedRecoveryPlanner()
    if args.planner == "probe_rule":
        if diagnostic_context is None:
            raise ValueError("--planner probe_rule requires --active-probes")
        return ProbeGuidedRecoveryPlanner(diagnostic_context)
    if args.planner == "oracle":
        return OracleRecoveryPlanner(bias)
    if args.planner == "anthropic":
        return AnthropicRecoveryPlanner(
            model=args.model or "glm-5.2", base_url=args.base_url,
            timeout_seconds=args.api_timeout, max_retries=args.api_max_retries,
            diagnostic_context=diagnostic_context,
        )
    return OpenAIRecoveryPlanner(
        model=args.model or "gpt-5.6-luna", reasoning_effort=args.reasoning_effort,
        diagnostic_context=diagnostic_context,
    )


def load_agent_records(path: Path) -> tuple[dict[str, Any], ...]:
    rows = tuple(
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    return tuple(build_agent_view(row) for row in rows)


def save_rows(rows: list[dict[str, Any]], path: Path) -> Path:
    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def save_audit(rows: list[dict[str, Any]], path: Path) -> Path:
    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            for row in rows:
                file.write(json.dumps(row, ensure_ascii=False) + "\n")
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def main() -> int:
    args = parse_args()
    if (
        args.num_episodes <= 0
        or args.max_steps <= 0
        or args.max_trials <= 0
        or args.api_timeout <= 0
        or args.api_max_retries < 0
    ):
        print(
            "[FAIL] episode/step/trial counts and timeout must be positive; retries cannot be negative",
            file=sys.stderr,
        )
        return 1
    try:
        bias = hidden_bias(args)
        output_rows: list[dict[str, Any]] = []
        audit_rows: list[dict[str, Any]] = []
        episode_seeds = args.seeds or [
            args.seed_start + index for index in range(args.num_episodes)
        ]
        for episode_index, seed in enumerate(episode_seeds):
            diagnostic_context = None

            def initialize_active_planner() -> RecoveryPlanner:
                nonlocal diagnostic_context
                probe_results = run_symmetric_probes(
                    lambda: create_push_environment(seed),
                    seed=seed,
                    perturbation_factory=lambda: ActionBiasPerturbation(bias),
                    magnitude=args.probe_magnitude,
                    steps=args.probe_steps,
                )
                diagnostic_context = build_agent_probe_context(
                    probe_results, estimate_planar_bias(probe_results)
                )
                return make_planner(args, seed, bias, diagnostic_context)

            planner = (
                RuleBasedRecoveryPlanner()
                if args.active_probes else make_planner(args, seed, bias)
            )
            base_policy = create_push_policy()
            phase_counts_by_trial: dict[int, dict[str, int]] = {}

            def run_trial(trial: int, correction: Any) -> TrialOutcome:
                trajectory_path = args.trajectory_dir / (
                    f"{args.planner}_seed{seed}_trial{trial:02d}.jsonl"
                )
                video_path = None
                if args.video_dir is not None:
                    video_path = args.video_dir / (
                        f"{args.planner}_seed{seed}_trial{trial:02d}.mp4"
                    )
                env = create_push_environment(
                    seed, render_mode="rgb_array" if video_path is not None else None
                )
                try:
                    compensated_policy = PhaseGatedCompensatedPolicy(
                        base_policy,
                        correction,
                        schedule=args.correction_schedule,
                        contact_distance=args.contact_distance,
                        near_goal_distance=args.near_goal_distance,
                    )
                    result = run_episode(
                        env,
                        compensated_policy,
                        seed=seed,
                        max_steps=args.max_steps,
                        episode_id=trial,
                        trajectory_path=trajectory_path,
                        video_path=video_path,
                        fps=args.fps,
                        perturbation=ActionBiasPerturbation(bias),
                    )
                    phase_counts_by_trial[trial] = dict(compensated_policy.phase_counts)
                finally:
                    env.close()
                return TrialOutcome(
                    result=result,
                    agent_records=load_agent_records(trajectory_path),
                    trajectory_path=str(trajectory_path.resolve()),
                    video_path=str(video_path.resolve()) if video_path is not None else "",
                )

            def checkpoint(trial: Any) -> None:
                proposal = trial.proposal
                evidence = trial.evidence
                output_rows.append(
                    {
                        "schema_version": 1,
                        "planner": args.planner,
                        "injected_bias_axis": args.bias_axis,
                        "injected_bias_sign": args.bias_sign,
                        "injected_bias_magnitude": args.bias_magnitude,
                        "episode_id": episode_index + 1,
                        "seed": seed,
                        "trial": trial.trial,
                        "correction_axis": proposal.correction_axis,
                        "correction_direction": proposal.correction_direction,
                        "correction_magnitude": proposal.correction_magnitude,
                        "success": evidence.success,
                        "steps": evidence.steps,
                        "episode_return": evidence.episode_return,
                        "elapsed_time_ms": trial.episode_result.elapsed_time_ms,
                        "final_object_goal_distance": evidence.final_object_goal_distance,
                        "minimum_gripper_object_distance": evidence.minimum_gripper_object_distance,
                        "object_displacement": evidence.object_displacement,
                        "progress_to_goal": evidence.progress_to_goal,
                        "clipped_step_count": trial.episode_result.clipped_step_count,
                        "clipped_step_fraction": trial.episode_result.clipped_step_fraction,
                        "clipped_element_count": trial.episode_result.clipped_element_count,
                        "clipped_element_fraction": trial.episode_result.clipped_element_fraction,
                        "trajectory_path": trial.trajectory_path,
                        "video_path": trial.video_path,
                        "probe_environment_steps": (
                            int(diagnostic_context["probe_environment_steps"])
                            if diagnostic_context is not None else 0
                        ),
                        "correction_schedule": args.correction_schedule,
                        "approach_steps": phase_counts_by_trial[trial.trial]["approach"],
                        "push_steps": phase_counts_by_trial[trial.trial]["push"],
                        "near_goal_steps": phase_counts_by_trial[trial.trial]["near_goal"],
                    }
                )
                audit_rows.append(
                    {
                        "planner": args.planner,
                        "episode_id": episode_index + 1,
                        "seed": seed,
                        "trial": trial.trial,
                        "proposal": proposal.to_dict(),
                        "planner_audit": trial.planner_audit,
                    }
                )
                save_rows(output_rows, args.output_csv)
                save_audit(audit_rows, args.audit_jsonl)

            recovery = run_budgeted_recovery(
                planner, run_trial, max_trials=args.max_trials,
                trial_observer=checkpoint,
                planner_after_initial_failure=(
                    initialize_active_planner if args.active_probes else None
                ),
            )
            print(
                f"episode={episode_index + 1} seed={seed} success={recovery.success} "
                f"trials={recovery.trials_used} environment_steps={recovery.environment_steps}"
            )
        print(f"csv: {args.output_csv.expanduser().resolve()}")
        print(f"audit: {args.audit_jsonl.expanduser().resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
