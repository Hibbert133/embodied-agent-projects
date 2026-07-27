"""Evaluate SawyerPushV3Policy over multiple real push-v3 episodes."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rollout import (  # noqa: E402
    create_push_environment,
    create_push_policy,
    run_episode,
)


DEFAULT_CSV_OUTPUT = PROJECT_ROOT / "outputs" / "push_evaluation.csv"
DEFAULT_TRAJECTORY_DIR = PROJECT_ROOT / "outputs" / "push_trajectories"


@dataclass(frozen=True)
class EvaluationRow:
    schema_version: int
    episode_id: int
    seed: int
    success: bool
    steps: int
    episode_return: float
    elapsed_time_ms: float
    clipped_step_count: int
    clipped_step_fraction: float
    clipped_element_count: int
    clipped_element_fraction: float
    final_object_goal_distance: float
    min_gripper_object_distance: float
    object_displacement: float
    progress_to_goal: float
    trajectory_path: str


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-episodes", type=int, default=10)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument(
        "--output-csv", "--output", dest="output_csv", type=Path,
        default=DEFAULT_CSV_OUTPUT,
    )
    parser.add_argument(
        "--trajectory-dir", type=Path, default=DEFAULT_TRAJECTORY_DIR
    )
    return parser.parse_args()


def save_csv(rows: list[EvaluationRow], path: Path) -> Path:
    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    fieldnames = list(EvaluationRow.__dataclass_fields__)
    try:
        with temporary.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(asdict(row))
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def evaluate(
    *,
    num_episodes: int,
    seed_start: int,
    max_steps: int,
    output_csv: Path,
    trajectory_dir: Path,
) -> list[EvaluationRow]:
    if num_episodes <= 0 or max_steps <= 0:
        raise ValueError("--num-episodes and --max-steps must be positive integers")

    rows: list[EvaluationRow] = []
    policy = create_push_policy()
    trajectory_dir = trajectory_dir.expanduser().resolve()

    for index in range(num_episodes):
        episode_id = index + 1
        seed = seed_start + index
        trajectory_path = (
            trajectory_dir / f"episode_{episode_id:03d}_seed_{seed}.jsonl"
        )
        env: Any | None = None
        try:
            env = create_push_environment(seed, render_mode=None)
            result = run_episode(
                env,
                policy,
                episode_id=episode_id,
                seed=seed,
                max_steps=max_steps,
                trajectory_path=trajectory_path,
            )
        finally:
            if env is not None:
                env.close()

        row = EvaluationRow(
            schema_version=2,
            episode_id=episode_id,
            seed=seed,
            success=result.success,
            steps=result.steps,
            episode_return=result.episode_return,
            elapsed_time_ms=result.elapsed_time_ms,
            clipped_step_count=result.clipped_step_count,
            clipped_step_fraction=result.clipped_step_fraction,
            clipped_element_count=result.clipped_element_count,
            clipped_element_fraction=result.clipped_element_fraction,
            final_object_goal_distance=result.final_object_goal_distance,
            min_gripper_object_distance=result.min_gripper_object_distance,
            object_displacement=result.object_displacement,
            progress_to_goal=result.progress_to_goal,
            trajectory_path=str(trajectory_path.resolve()),
        )
        rows.append(row)
        print(
            f"episode {episode_id}/{num_episodes}: seed={seed}, "
            f"success={row.success}, steps={row.steps}, "
            f"return={row.episode_return:.6f}, elapsed={row.elapsed_time_ms:.2f} ms"
        )

    csv_path = save_csv(rows, output_csv)
    count = len(rows)
    success_rate = sum(row.success for row in rows) / count
    average_steps = sum(row.steps for row in rows) / count
    average_return = sum(row.episode_return for row in rows) / count
    average_elapsed = sum(row.elapsed_time_ms for row in rows) / count
    print(f"success rate: {success_rate:.2%}")
    print(f"average steps: {average_steps:.2f}")
    print(f"average return: {average_return:.6f}")
    print(f"average elapsed time: {average_elapsed:.2f} ms")
    print(f"csv: {csv_path}")
    print(f"trajectory directory: {trajectory_dir}")
    return rows


def main() -> int:
    configure_console()
    args = parse_args()
    try:
        evaluate(
            num_episodes=args.num_episodes,
            seed_start=args.seed_start,
            max_steps=args.max_steps,
            output_csv=args.output_csv,
            trajectory_dir=args.trajectory_dir,
        )
    except Exception as exc:
        print(f"[FAIL] evaluation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
