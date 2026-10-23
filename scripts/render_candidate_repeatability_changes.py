"""Render both candidates for preregistered representative decision changes."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import FaultCondition, save_csv  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _bool(value: object) -> bool:
    return str(value).lower() == "true"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeatability-run", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/videos/candidate_repeatability_changes_v1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repeatability = args.repeatability_run.resolve()
        source = args.source_run.resolve()
        summary = json.loads(
            (repeatability / "decision_change_summary.json").read_text(encoding="utf-8")
        )
        representatives = summary["representatives"]
        if {row["outcome_class"] for row in representatives} != {"HELPFUL", "HARMFUL", "NEUTRAL"}:
            raise ValueError("representatives must cover all registered outcome classes")
        candidate_rows = _csv(source / "candidate_results.csv")
        candidates = {(row["case_id"], row["candidate_id"]): row for row in candidate_rows}
        oracle = {row["case_id"]: row for row in _jsonl(source / "oracle_audit.jsonl")}
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        manifest: list[dict[str, Any]] = []
        for representative in representatives:
            case_id = representative["case_id"]
            seed = int(representative["seed"])
            role = str(representative["outcome_class"]).lower()
            hidden = oracle[case_id]
            fault = FaultCondition(
                hidden["condition_id"],
                hidden["perturbation_type_oracle"],
                hidden["perturbation_parameters_oracle"],
            )
            for candidate_id in ("probe_grounded_compensation", "stochastic_retry"):
                expected = candidates[(case_id, candidate_id)]
                correction = (
                    float(expected["correction_x"]),
                    float(expected["correction_y"]),
                    0.0,
                    0.0,
                )
                video = output / f"{role}_seed{seed}_{candidate_id}.mp4"
                environment = create_push_environment(seed, render_mode="rgb_array")
                try:
                    result = run_episode(
                        environment,
                        PhaseGatedCompensatedPolicy(
                            create_push_policy(),
                            correction,
                            schedule=expected["schedule"],
                        ),
                        seed=seed,
                        max_steps=500,
                        perturbation=fault.build(),
                        perturbation_seed=int(expected["verification_perturbation_seed"]),
                        video_path=video,
                    )
                finally:
                    environment.close()
                if (
                    result.success != _bool(expected["verification_success"])
                    or result.steps != int(expected["verification_steps"])
                    or abs(
                        result.final_object_goal_distance
                        - float(expected["final_object_goal_distance"])
                    )
                    > 1e-10
                ):
                    raise RuntimeError(f"rendered result differs from source: {case_id} {candidate_id}")
                manifest.append(
                    {
                        "repeatability_run_id": summary["repeatability_run_id"],
                        "selection_rule": "largest_absolute_k3_robust_margin_within_outcome_class",
                        "outcome_class": representative["outcome_class"],
                        "evidence_driver": representative["evidence_driver"],
                        "case_id": case_id,
                        "seed": seed,
                        "candidate_id": candidate_id,
                        "selected_at_k1": candidate_id == representative["before_candidate"],
                        "selected_at_k3": candidate_id == representative["after_candidate"],
                        "success": result.success,
                        "steps": result.steps,
                        "final_object_goal_distance": result.final_object_goal_distance,
                        "video_path": video.relative_to(ROOT).as_posix(),
                    }
                )
                print(f"class={role} seed={seed} candidate={candidate_id} success={result.success}")
        save_csv(output / "manifest.csv", manifest)
        print(f"manifest: {output / 'manifest.csv'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
