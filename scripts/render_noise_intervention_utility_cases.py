"""Render paired candidates for rule-selected helpful and harmful retry cases."""

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

from scripts.build_autoresearch_benchmark import FaultCondition  # noqa: E402
from scripts.build_autoresearch_benchmark import save_csv  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMPENSATION = "probe_grounded_compensation"
RETRY = "stochastic_retry"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _bool(value: str) -> bool:
    return value.lower() == "true"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/videos/noise_intervention_utility",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run = args.run_dir.resolve()
        cases = _csv(run / "case_results.csv")
        candidates = _csv(run / "candidate_results.csv")
        oracle = {row["case_id"]: row for row in _jsonl(run / "oracle_audit.jsonl")}
        helpful = sorted(
            (
                row for row in cases
                if row.get("probe_candidate") == RETRY
                and row.get("best_candidate_ids") == RETRY
            ),
            key=lambda row: row["case_id"],
        )[0]
        harmful = sorted(
            (
                row for row in cases
                if row.get("probe_candidate") == RETRY
                and row.get("best_candidate_ids") == COMPENSATION
            ),
            key=lambda row: row["case_id"],
        )[0]
        selections = (("helpful_retry", helpful), ("harmful_retry", harmful))
        by_pair = {(row["case_id"], row["candidate_id"]): row for row in candidates}
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        manifest_rows: list[dict[str, Any]] = []
        for role, case in selections:
            hidden = oracle[case["case_id"]]
            fault = FaultCondition(
                str(hidden["condition_id"]),
                str(hidden["perturbation_type_oracle"]),
                dict(hidden["perturbation_parameters_oracle"]),
            )
            for candidate_id in (COMPENSATION, RETRY):
                expected = by_pair[(case["case_id"], candidate_id)]
                correction = (
                    float(expected["correction_x"]),
                    float(expected["correction_y"]),
                    0.0,
                    0.0,
                )
                seed = int(case["seed"])
                video = output / f"{role}_seed{seed}_{candidate_id}.mp4"
                environment = create_push_environment(seed, render_mode="rgb_array")
                policy = PhaseGatedCompensatedPolicy(
                    create_push_policy(), correction, schedule=expected["schedule"]
                )
                try:
                    result = run_episode(
                        environment,
                        policy,
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
                    or abs(result.final_object_goal_distance - float(expected["final_object_goal_distance"])) > 1e-10
                ):
                    raise RuntimeError(f"rendered outcome differs from frozen CSV: {case['case_id']} {candidate_id}")
                manifest_rows.append(
                    {
                        "experiment_run_id": case["experiment_run_id"],
                        "selection_rule": role,
                        "case_id": case["case_id"],
                        "seed": seed,
                        "candidate_id": candidate_id,
                        "outcome_preferred": candidate_id == case["best_candidate_ids"],
                        "success": result.success,
                        "steps": result.steps,
                        "final_object_goal_distance": result.final_object_goal_distance,
                        "video_path": video.relative_to(ROOT).as_posix(),
                    }
                )
                print(f"role={role} seed={seed} candidate={candidate_id} success={result.success}")
        save_csv(output / "manifest.csv", manifest_rows)
        print(f"manifest: {output / 'manifest.csv'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
