"""Re-render exact accepted and rejected ProbeMem verification cases."""

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

from scripts.build_autoresearch_benchmark import get_conditions  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs="+", default=[700, 703])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/probemem_v2/representative_videos",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        with (run_dir / "results.csv").open("r", encoding="utf-8", newline="") as handle:
            results = {int(row["seed"]): row for row in csv.DictReader(handle)}
        audits = {int(row["seed"]): row for row in _jsonl(run_dir / "interaction_audit.jsonl")}
        noise_std = float(json.loads((ROOT / "outputs/autoresearch/noise_calibration/selected.json").read_text(encoding="utf-8"))["noise_std"])
        conditions = {item.condition_id: item for item in get_conditions(noise_std)}
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        manifest_rows: list[dict[str, Any]] = []
        for seed in args.seeds:
            row = results[seed]
            audit = audits[seed]
            expected_status = row["verification_status"]
            if expected_status not in {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}:
                raise ValueError(f"seed {seed} does not contain a fresh verification")
            execution = audit["host_execution"]
            correction = tuple(float(item) for item in execution["correction"])
            schedule = str(execution["schedule"])
            skill = str(row["selected_skill"])
            random_key = "retry" if skill == "INDEPENDENT_STOCHASTIC_RETRY" else "verification"
            perturbation_seed = int(audit["random_seed_provenance"][random_key])
            fault = conditions[str(row["condition_id_oracle"])]
            status_slug = expected_status.lower()
            video = output / f"probemem_seed{seed}_{skill.lower()}_{status_slug}.mp4"
            trajectory = output / f"probemem_seed{seed}_{skill.lower()}_{status_slug}.jsonl"
            env = create_push_environment(seed, render_mode="rgb_array")
            policy = PhaseGatedCompensatedPolicy(create_push_policy(), correction, schedule=schedule)
            try:
                result = run_episode(
                    env,
                    policy,
                    seed=seed,
                    max_steps=500,
                    perturbation=fault.build(),
                    perturbation_seed=perturbation_seed,
                    video_path=video,
                    agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            observed_status = (
                "ACCEPTED" if result.success
                else "INCONCLUSIVE" if result.final_object_goal_distance < float(row["initial_final_object_goal_distance"])
                else "REJECTED"
            )
            if observed_status != expected_status or result.steps != int(row["verification_steps"]):
                raise RuntimeError(
                    f"rendered verification differs for seed {seed}: "
                    f"expected {expected_status}/{row['verification_steps']}, "
                    f"observed {observed_status}/{result.steps}"
                )
            manifest_rows.append({
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "seed": seed,
                "condition_id_oracle": fault.condition_id,
                "selected_skill": skill,
                "verification_status": observed_status,
                "success": result.success,
                "steps": result.steps,
                "final_object_goal_distance": result.final_object_goal_distance,
                "video_path": video.relative_to(ROOT).as_posix(),
                "trajectory_path": trajectory.relative_to(ROOT).as_posix(),
            })
            print(f"seed={seed} status={observed_status} video={video}")
        manifest_path = output / "manifest.csv"
        with manifest_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
            writer.writeheader()
            writer.writerows(manifest_rows)
        print(f"manifest: {manifest_path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
