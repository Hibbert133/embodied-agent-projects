"""Collect leakage-safe passive temporal evidence on a fresh development split."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import (  # noqa: E402
    get_conditions,
    save_csv,
    save_jsonl,
)
from src.diagnosis.passive_planar import (  # noqa: E402
    PassivePlanarEstimate,
    estimate_passive_planar_drift,
)
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def temporal_feature_row(
    *,
    condition_id: str,
    seed: int,
    case_id: str,
    estimate: PassivePlanarEstimate,
) -> dict[str, Any]:
    """Convert an Agent-visible estimate to a flat evaluator feature row."""
    return {
        "case_id": case_id,
        "condition_id": condition_id,
        "seed": seed,
        "temporal_uncertainty": estimate.uncertainty,
        "overall_confidence": estimate.overall_confidence,
        "normalized_residual_x": estimate.normalized_residual[0],
        "normalized_residual_y": estimate.normalized_residual[1],
        "normalized_residual_norm": float(np.linalg.norm(estimate.normalized_residual)),
        "response_gain_x": estimate.axis_response_gain[0],
        "response_gain_y": estimate.axis_response_gain[1],
        "estimated_drift_x": estimate.estimated_drift_per_step[0],
        "estimated_drift_y": estimate.estimated_drift_per_step[1],
        "action_excitation_x": estimate.action_excitation[0],
        "action_excitation_y": estimate.action_excitation[1],
        "sample_count": estimate.sample_count,
    }


def _load_agent_rows(path: Path) -> list[Mapping[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-start", type=int, default=320)
    parser.add_argument("--num-seeds", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=500)
    parser.add_argument(
        "--noise-selection",
        type=Path,
        default=ROOT / "outputs/autoresearch/noise_calibration/selected.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/temporal_development_rollouts",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if min(args.num_seeds, args.max_steps) <= 0:
            raise ValueError("num-seeds and max-steps must be positive")
        noise_std = float(
            json.loads(args.noise_selection.read_text(encoding="utf-8"))["noise_std"]
        )
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        oracle_rows: list[dict[str, Any]] = []
        baseline_rows: list[dict[str, Any]] = []
        temporal_rows: list[dict[str, Any]] = []
        number = 0
        with tempfile.TemporaryDirectory(prefix="agent_view_", dir=output_dir) as temporary:
            temporary_dir = Path(temporary)
            for fault in get_conditions(noise_std):
                for seed in range(args.seed_start, args.seed_start + args.num_seeds):
                    number += 1
                    case_id = f"development_case_{number:04d}"
                    trajectory_path = temporary_dir / f"{case_id}.jsonl"
                    env = create_push_environment(seed)
                    try:
                        result = run_episode(
                            env,
                            create_push_policy(),
                            seed=seed,
                            max_steps=args.max_steps,
                            episode_id=number,
                            perturbation=fault.build(),
                            agent_trajectory_path=trajectory_path,
                        )
                    finally:
                        env.close()
                    agent_rows = _load_agent_rows(trajectory_path)
                    estimate = estimate_passive_planar_drift(agent_rows)
                    baseline = {
                        "success": result.success,
                        "steps": result.steps,
                        "episode_return": result.episode_return,
                        "final_object_goal_distance": result.final_object_goal_distance,
                        "progress_to_goal": result.progress_to_goal,
                    }
                    oracle_rows.append(
                        {
                            "case_id": case_id,
                            "seed": seed,
                            "condition_id": fault.condition_id,
                            "perturbation_type": fault.kind,
                            "perturbation_parameters": fault.parameters,
                            "baseline": baseline,
                        }
                    )
                    baseline_rows.append(
                        {"condition_id": fault.condition_id, "seed": seed, **baseline}
                    )
                    temporal_rows.append(
                        temporal_feature_row(
                            condition_id=fault.condition_id,
                            seed=seed,
                            case_id=case_id,
                            estimate=estimate,
                        )
                    )
                    print(
                        f"condition={fault.condition_id} seed={seed} "
                        f"success={result.success} temporal_uncertainty={estimate.uncertainty:.6f}"
                    )
        save_jsonl(output_dir / "oracle_audit.jsonl", oracle_rows)
        save_csv(output_dir / "baselines.csv", baseline_rows)
        save_csv(output_dir / "temporal_features.csv", temporal_rows)
        metadata = {
            "split": "development",
            "seed_start": args.seed_start,
            "num_seeds": args.num_seeds,
            "max_steps": args.max_steps,
            "noise_std": noise_std,
            "trajectory_view": "schema-v2 Agent View",
            "raw_trajectories_retained": False,
            "rendering": False,
            "api_calls": 0,
            "feature_model": (
                "per-axis gripper_delta = response_gain * commanded_action + execution_drift"
            ),
            "metaworld_action_scale": 0.01,
            "action_semantics_source": (
                "MetaWorld 3.1.1 metaworld/sawyer_xyz_env.py set_xyz_action"
            ),
        }
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
        )
        print(f"temporal features: {output_dir / 'temporal_features.csv'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
