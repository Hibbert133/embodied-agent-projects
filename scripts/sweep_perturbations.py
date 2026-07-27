"""Run paired-seed action perturbation sweeps on MetaWorld push-v3."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.perturbations import (  # noqa: E402
    ActionBiasPerturbation,
    ActionPerturbation,
    ActionScalePerturbation,
    GaussianNoisePerturbation,
)
from src.rollout import (  # noqa: E402
    create_push_environment,
    create_push_policy,
    run_episode,
)


DEFAULT_DETAILED_CSV = PROJECT_ROOT / "outputs" / "perturbation_sweep.csv"
DEFAULT_SUMMARY_CSV = PROJECT_ROOT / "outputs" / "perturbation_summary.csv"
DEFAULT_LEVELS = {
    "action_scale": [1.0, 0.8, 0.6, 0.4, 0.2],
    "gaussian_noise": [0.0, 0.02, 0.05, 0.10, 0.20],
    "action_bias": [0.0, 0.02, 0.05, 0.10, 0.15],
}


@dataclass(frozen=True)
class SweepRow:
    perturbation_type: str
    perturbation_level: float
    episode_id: int
    seed: int
    success: bool
    steps: int
    episode_return: float
    elapsed_time_ms: float
    clip_count: int
    clip_fraction: float


@dataclass(frozen=True)
class SummaryRow:
    perturbation_type: str
    perturbation_level: float
    num_episodes: int
    success_count: int
    success_rate: float
    average_steps: float
    average_return: float
    average_elapsed_time_ms: float
    total_clip_count: int
    clip_fraction: float


def configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-episodes", type=int, default=20)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument(
        "--perturbation-type",
        choices=("all", "action_scale", "gaussian_noise", "action_bias"),
        default="all",
    )
    parser.add_argument(
        "--levels",
        type=float,
        nargs="+",
        help="Custom levels; requires one non-'all' perturbation type.",
    )
    parser.add_argument(
        "--output-csv", type=Path, default=DEFAULT_DETAILED_CSV
    )
    parser.add_argument(
        "--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Merge this run into existing detailed and summary CSV files.",
    )
    return parser.parse_args()


def build_configurations(
    perturbation_type: str, custom_levels: list[float] | None
) -> list[tuple[str, float, Callable[[], ActionPerturbation]]]:
    if custom_levels is not None and perturbation_type == "all":
        raise ValueError("--levels requires selecting one --perturbation-type")
    selected_types = (
        list(DEFAULT_LEVELS) if perturbation_type == "all" else [perturbation_type]
    )
    configurations: list[tuple[str, float, Callable[[], ActionPerturbation]]] = []
    for name in selected_types:
        levels = custom_levels if custom_levels is not None else DEFAULT_LEVELS[name]
        for value in levels:
            level = float(value)
            if name == "action_scale":
                factory = lambda level=level: ActionScalePerturbation(level)
            elif name == "gaussian_noise":
                factory = lambda level=level: GaussianNoisePerturbation(level)
            else:
                factory = lambda level=level: ActionBiasPerturbation(level)
            # Construct once now so invalid levels fail before expensive episodes.
            factory()
            configurations.append((name, level, factory))
    return configurations


def save_rows(rows: list[Any], path: Path, fieldnames: list[str]) -> Path:
    output = path.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
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


def load_sweep_rows(path: Path) -> list[SweepRow]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return [
            SweepRow(
                perturbation_type=row["perturbation_type"],
                perturbation_level=float(row["perturbation_level"]),
                episode_id=int(row["episode_id"]),
                seed=int(row["seed"]),
                success=row["success"].lower() == "true",
                steps=int(row["steps"]),
                episode_return=float(row["episode_return"]),
                elapsed_time_ms=float(row["elapsed_time_ms"]),
                clip_count=int(row["clip_count"]),
                clip_fraction=float(row["clip_fraction"]),
            )
            for row in csv.DictReader(file)
        ]


def summarize(rows: list[SweepRow]) -> list[SummaryRow]:
    summary: list[SummaryRow] = []
    configuration_keys = list(
        dict.fromkeys(
            (row.perturbation_type, row.perturbation_level) for row in rows
        )
    )
    for name, level in configuration_keys:
        group = [
            row
            for row in rows
            if row.perturbation_type == name
            and row.perturbation_level == level
        ]
        count = len(group)
        total_steps = sum(row.steps for row in group)
        total_clips = sum(row.clip_count for row in group)
        summary.append(
            SummaryRow(
                perturbation_type=name,
                perturbation_level=level,
                num_episodes=count,
                success_count=sum(row.success for row in group),
                success_rate=sum(row.success for row in group) / count,
                average_steps=total_steps / count,
                average_return=sum(row.episode_return for row in group) / count,
                average_elapsed_time_ms=(
                    sum(row.elapsed_time_ms for row in group) / count
                ),
                total_clip_count=total_clips,
                clip_fraction=total_clips / total_steps if total_steps else 0.0,
            )
        )
    return summary


def sweep(
    *,
    num_episodes: int,
    seed_start: int,
    max_steps: int,
    perturbation_type: str,
    custom_levels: list[float] | None,
    output_csv: Path,
    summary_csv: Path,
    append: bool,
) -> tuple[list[SweepRow], list[SummaryRow]]:
    if num_episodes <= 0 or max_steps <= 0:
        raise ValueError("--num-episodes and --max-steps must be positive integers")
    configurations = build_configurations(perturbation_type, custom_levels)
    policy = create_push_policy()
    output_csv = output_csv.expanduser().resolve()
    rows: list[SweepRow] = load_sweep_rows(output_csv) if append else []
    replacement_keys = {(name, level) for name, level, _ in configurations}
    if append:
        rows = [
            row
            for row in rows
            if (row.perturbation_type, row.perturbation_level)
            not in replacement_keys
        ]

    for index in range(num_episodes):
        episode_id = index + 1
        seed = seed_start + index
        for name, level, factory in configurations:
            env: Any | None = None
            try:
                # A fresh environment is required for paired MetaWorld tasks.
                # Repeated reset(seed) does not reset the task-select wrapper.
                env = create_push_environment(seed, render_mode=None)
                result = run_episode(
                    env,
                    policy,
                    episode_id=episode_id,
                    seed=seed,
                    max_steps=max_steps,
                    perturbation=factory(),
                )
                rows.append(
                    SweepRow(
                        perturbation_type=name,
                        perturbation_level=level,
                        episode_id=episode_id,
                        seed=seed,
                        success=result.success,
                        steps=result.steps,
                        episode_return=result.episode_return,
                        elapsed_time_ms=result.elapsed_time_ms,
                        clip_count=result.clip_count,
                        clip_fraction=result.clip_fraction,
                    )
                )
                print(
                    f"seed={seed} {name}={level:g}: success={result.success}, "
                    f"steps={result.steps}, clips={result.clip_count}"
                )
            finally:
                if env is not None:
                    env.close()

    summary = summarize(rows)
    detailed_path = save_rows(
        rows, output_csv, list(SweepRow.__dataclass_fields__)
    )
    summary_path = save_rows(
        summary, summary_csv, list(SummaryRow.__dataclass_fields__)
    )
    for row in summary:
        print(
            f"{row.perturbation_type}={row.perturbation_level:g}: "
            f"success_rate={row.success_rate:.2%}, "
            f"clip_fraction={row.clip_fraction:.2%}"
        )
    print(f"detailed csv: {detailed_path}")
    print(f"summary csv: {summary_path}")
    return rows, summary


def main() -> int:
    configure_console()
    args = parse_args()
    try:
        sweep(
            num_episodes=args.num_episodes,
            seed_start=args.seed_start,
            max_steps=args.max_steps,
            perturbation_type=args.perturbation_type,
            custom_levels=args.levels,
            output_csv=args.output_csv,
            summary_csv=args.summary_csv,
            append=args.append,
        )
    except Exception as exc:
        print(f"[FAIL] sweep failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
