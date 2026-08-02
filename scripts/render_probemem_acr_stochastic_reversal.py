"""Render a mechanically selected same-state stochastic winner reversal."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import (  # noqa: E402
    COMPENSATION,
    RETRY,
    _load_inputs,
)
from scripts.run_probemem_v2_smoke import _probe_context, _verification_status  # noqa: E402
from src.planner.evidence_grounded import first_registered_probe_context, select_grounded_intervention  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def select_reversal(rows: list[dict[str, str]]) -> tuple[int, int, int]:
    grouped: dict[tuple[int, int], dict[str, dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault((int(row["seed"]), int(row["realization_index"])), {})[
            row["candidate_id"]
        ] = row
    by_seed: dict[int, dict[str, list[int]]] = {}
    for (seed, realization), pair in grouped.items():
        compensation = pair[COMPENSATION.value]["verification_status"] == "ACCEPTED"
        retry = pair[RETRY.value]["verification_status"] == "ACCEPTED"
        label = "compensation_only" if compensation and not retry else "retry_only" if retry and not compensation else "other"
        by_seed.setdefault(seed, {}).setdefault(label, []).append(realization)
    eligible = [
        seed for seed, labels in by_seed.items()
        if labels.get("compensation_only") and labels.get("retry_only")
    ]
    if not eligible:
        raise ValueError("no same-state exclusive winner reversal exists")
    seed = min(eligible)
    return seed, min(by_seed[seed]["compensation_only"]), min(by_seed[seed]["retry_only"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/probemem_acr/videos/stochastic_reversal")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
    formal_rows = _rows(run_dir / "candidate_results.csv")
    seed, compensation_realization, retry_realization = select_reversal(formal_rows)
    unit = next(item for item in manifest["population_units"] if int(item["environment_seed"]) == seed)
    fault, recovery_config = _load_inputs(config)
    probe_context = _probe_context(fault, seed, config, int(unit["diagnostic_probe_seed"]))
    plan = select_grounded_intervention(
        plan_id=f"reversal_visual_seed{seed}", evidence_id=f"reversal_probe_seed{seed}",
        mechanism_belief="stable_bias",
        correction_context=first_registered_probe_context(probe_context),
        recovery_config=recovery_config, evidence_source="registered_probe",
    )
    if not plan.requires_fresh_verification:
        raise RuntimeError("selected reversal no longer supports compensation")
    lookup = {
        (int(row["realization_index"]), row["candidate_id"]): row
        for row in formal_rows if int(row["seed"]) == seed
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_rows: list[dict[str, Any]] = []
    for realization in (compensation_realization, retry_realization):
        paired_seed = int(unit["paired_verification_seeds"][realization - 1])
        for skill in (COMPENSATION, RETRY):
            if skill is COMPENSATION:
                correction, schedule = plan.correction, plan.schedule
            else:
                correction, schedule = (0.0, 0.0, 0.0, 0.0), "whole"
            expected = lookup[(realization, skill.value)]
            filename = f"seed{seed}_realization{realization}_{skill.value.lower()}_{expected['verification_status'].lower()}.mp4"
            video_path = args.output_dir / filename
            env = create_push_environment(seed, "rgb_array")
            try:
                result = run_episode(
                    env,
                    PhaseGatedCompensatedPolicy(create_push_policy(), correction, schedule=schedule),
                    seed=seed,
                    max_steps=int(config["budget"]["fresh_verification_max_steps_per_candidate"]),
                    perturbation=fault.build(),
                    perturbation_seed=paired_seed,
                    video_path=video_path,
                )
            finally:
                env.close()
            observed_status = _verification_status(
                result.success, result.final_object_goal_distance,
                float(expected["initial_final_object_goal_distance"]),
            )
            if (
                observed_status != expected["verification_status"]
                or result.steps != int(expected["verification_steps"])
                or not math.isclose(result.final_object_goal_distance, float(expected["final_object_goal_distance"]), abs_tol=1e-9)
            ):
                raise RuntimeError("rendered reversal does not reproduce frozen candidate outcome")
            output_rows.append({
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "seed": seed,
                "realization_index": realization,
                "paired_verification_seed": paired_seed,
                "candidate_id": skill.value,
                "verification_status": observed_status,
                "success": result.success,
                "steps": result.steps,
                "final_object_goal_distance": result.final_object_goal_distance,
                "video_path": video_path.relative_to(ROOT).as_posix(),
            })
            print(f"seed={seed} realization={realization} skill={skill.value} status={observed_status}")
    with (args.output_dir / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"videos: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
