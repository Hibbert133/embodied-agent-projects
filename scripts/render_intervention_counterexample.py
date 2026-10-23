"""Render the registered passive-success/active-failure P1 counterexample."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import FaultCondition  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/videos/intervention_counterexample",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run = args.run_dir.resolve()
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
        parent = ROOT / config["source_allocation_directory"]
        oracle = {str(row["case_id"]): row for row in _jsonl(parent / "oracle_case_audit.jsonl")}
        causal = _jsonl(run / "causal_chains.jsonl")
        results = _csv(run / "method_results.csv")
        by_case_method = {(row["case_id"], row["method"]): row for row in results}
        candidates = []
        for row in causal:
            case_id = str(row["case_id"])
            passive = by_case_method[(case_id, "passive_diagnosis_intervention")]
            active = by_case_method[(case_id, "active_evidence_intervention")]
            if (
                bool(row["probe_requested"])
                and bool(row["mechanism_belief_changed"])
                and passive["verification_status"] == "ACCEPTED"
                and active["verification_status"] == "REJECTED"
            ):
                candidates.append(case_id)
        if not candidates:
            raise RuntimeError("no registered passive-success/active-failure counterexample")
        case_id = min(candidates)
        case = oracle[case_id]
        fault = FaultCondition(
            str(case["condition_id"]),
            str(case["perturbation_type_oracle"]),
            dict(case["perturbation_parameters_oracle"]),
        )
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        rows = []
        for method in ("passive_diagnosis_intervention", "active_evidence_intervention"):
            expected = by_case_method[(case_id, method)]
            correction = tuple(float(value) for value in json.loads(expected["correction"]))
            seed = int(expected["seed"])
            video = output / f"{case_id}_seed{seed}_{method}_{expected['verification_status'].lower()}.mp4"
            env = create_push_environment(seed, render_mode="rgb_array")
            policy = PhaseGatedCompensatedPolicy(
                create_push_policy(), correction, schedule=expected["schedule"]
            )
            try:
                result = run_episode(
                    env,
                    policy,
                    seed=seed,
                    max_steps=500,
                    perturbation=fault.build(),
                    perturbation_seed=int(expected["verification_seed_oracle"]),
                    video_path=video,
                )
            finally:
                env.close()
            if (
                result.success != (expected["verification_success"].lower() == "true")
                or result.steps != int(expected["verification_steps"])
                or abs(result.final_object_goal_distance - float(expected["final_object_goal_distance"])) > 1e-9
            ):
                raise RuntimeError(f"rendered outcome differs from frozen CSV for {method}")
            rows.append(
                {
                    "source_intervention_run_id": manifest["experiment_run_id"],
                    "source_manifest_id": manifest["manifest_id"],
                    "selection_rule": "lowest case_id with requested probe, belief change, passive ACCEPTED, active REJECTED",
                    "case_id": case_id,
                    "seed": seed,
                    "method": method,
                    "verification_status": expected["verification_status"],
                    "steps": result.steps,
                    "final_object_goal_distance": result.final_object_goal_distance,
                    "correction": json.dumps(correction),
                    "schedule": expected["schedule"],
                    "video_path": video.relative_to(ROOT).as_posix(),
                }
            )
            print(f"method={method} status={expected['verification_status']} video={video}")
        with (output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"manifest: {output / 'manifest.csv'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
