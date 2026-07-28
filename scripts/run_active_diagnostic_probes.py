"""Run leakage-safe symmetric probes on fixed MetaWorld push-v3 seeds."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.diagnostic_probes import estimate_planar_bias, run_symmetric_probes  # noqa: E402
from src.perturbations import ActionBiasPerturbation  # noqa: E402
from src.rollout import create_push_environment  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="+", default=[103, 107, 108, 144, 148])
    parser.add_argument("--bias-axis", choices=("x", "y"), default="x")
    parser.add_argument("--bias-sign", choices=("positive", "negative"), default="positive")
    parser.add_argument("--bias-magnitude", type=float, default=0.145)
    parser.add_argument("--probe-magnitude", type=float, default=0.2)
    parser.add_argument("--probe-steps", type=int, default=8)
    parser.add_argument(
        "--output-dir", type=Path,
        default=PROJECT_ROOT / "outputs" / "active_probes",
    )
    return parser.parse_args()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    if args.bias_magnitude <= 0 or args.probe_steps <= 0:
        print("[FAIL] magnitudes and probe steps must be positive", file=sys.stderr)
        return 1
    bias = [0.0, 0.0, 0.0, 0.0]
    axis_index = 0 if args.bias_axis == "x" else 1
    bias[axis_index] = args.bias_magnitude * (1.0 if args.bias_sign == "positive" else -1.0)
    agent_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    try:
        for seed in args.seeds:
            probes = run_symmetric_probes(
                lambda: create_push_environment(seed),
                seed=seed,
                perturbation_factory=lambda: ActionBiasPerturbation(tuple(bias)),
                magnitude=args.probe_magnitude,
                steps=args.probe_steps,
            )
            estimate = estimate_planar_bias(probes)
            for probe in probes:
                agent_rows.append(
                    {
                        "schema_version": 1,
                        **probe.to_dict(),
                        "commanded_action": json.dumps(probe.commanded_action),
                        "start_gripper_position": json.dumps(probe.start_gripper_position),
                        "end_gripper_position": json.dumps(probe.end_gripper_position),
                        "gripper_displacement": json.dumps(probe.gripper_displacement),
                    }
                )
            audit_rows.append(
                {
                    "seed": seed,
                    "injected_bias_axis": args.bias_axis,
                    "injected_bias_sign": args.bias_sign,
                    "injected_bias_magnitude": args.bias_magnitude,
                    **estimate.to_dict(),
                    "estimated_drift_per_step": json.dumps(estimate.estimated_drift_per_step),
                    "axis_response_gain": json.dumps(estimate.axis_response_gain),
                    "axis_correct": estimate.dominant_axis == args.bias_axis,
                    "direction_correct": estimate.estimated_direction == args.bias_sign,
                    "probe_environment_steps": sum(item.steps for item in probes),
                }
            )
            print(
                f"seed={seed} estimate={estimate.dominant_axis}_{estimate.estimated_direction} "
                f"confidence={estimate.confidence:.3f} residual={estimate.residual:.6f}"
            )
        write_csv(args.output_dir / "probe_transitions_agent_view.csv", agent_rows)
        write_csv(args.output_dir / "probe_estimates_oracle_audit.csv", audit_rows)
        print(f"agent evidence: {(args.output_dir / 'probe_transitions_agent_view.csv').resolve()}")
        print(f"oracle audit: {(args.output_dir / 'probe_estimates_oracle_audit.csv').resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
