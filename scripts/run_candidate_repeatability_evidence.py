"""Evaluate a frozen repeated-prefix selector on a fresh source run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import FaultCondition, save_csv  # noqa: E402
from scripts.run_frozen_heldout_allocation import derive_random_seed  # noqa: E402
from src.candidate_repeatability import (  # noqa: E402
    aggregate_candidate_repetitions,
    select_repeatability_candidate,
)
from src.horizon_utility import build_prefix_evidence  # noqa: E402
from src.reasoning.evidence import validate_no_oracle_evidence  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs/autoresearch/candidate_repeatability_evidence_v1.json"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    temporary.replace(path)


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("split") != "development":
        raise ValueError("repeatability evidence must use development data")
    if list(config.get("candidates", ())) != [
        "probe_grounded_compensation",
        "stochastic_retry",
    ]:
        raise ValueError("v1 requires the two registered candidates")
    if int(config.get("prefix_horizon", 0)) != 64:
        raise ValueError("v1 prefix horizon must remain 64")
    if list(config.get("reported_repetition_counts", ())) != [1, 2, 3]:
        raise ValueError("v1 must report one, two, and three repetitions")
    namespaces = list(config.get("prefix_perturbation_seed_namespaces", ()))
    if len(namespaces) != 3 or len(set(namespaces)) != 3:
        raise ValueError("each repetition requires an independent seed namespace")
    if bool(config["selector"].get("fit_threshold", True)):
        raise ValueError("repeatability selector cannot fit a threshold")
    if config.get("rendering") is not False or int(config.get("api_calls", -1)) != 0:
        raise ValueError("repeatability timing run cannot render or call an API")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "outputs/candidate_repeatability/runs",
    )
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        validate_config(config)
        if _git("diff", "--name-only") or _git("diff", "--cached", "--name-only"):
            raise RuntimeError("commit selector and protocol before evaluation")

        source = args.source_run.resolve()
        source_status = json.loads((source / "run_status.json").read_text(encoding="utf-8"))
        source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        if (
            source_status.get("status") != "COMPLETED"
            or source_status.get("coverage_target_reached") is not True
        ):
            raise ValueError("source run did not reach its frozen coverage target")
        if source_manifest.get("protocol_id") != config["required_source_protocol_id"]:
            raise ValueError("source protocol ID differs from repeatability registration")
        if list(source_manifest.get("seed_range", ())) != list(config["required_source_seed_range"]):
            raise ValueError("source seed range differs from repeatability registration")

        cases = [
            row
            for row in _read_csv(source / "case_results.csv")
            if row["paired_comparable"] == "True"
        ]
        expected = int(config["expected_paired_comparable_cases"])
        if len(cases) != expected:
            raise ValueError("source comparable population differs from registration")
        candidate_rows = _read_csv(source / "candidate_results.csv")
        candidates = {(row["case_id"], row["candidate_id"]): row for row in candidate_rows}
        oracle = {row["case_id"]: row for row in _read_jsonl(source / "oracle_audit.jsonl")}

        commit = _git("rev-parse", "HEAD")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"repeatability_{timestamp}_{commit[:12]}"
        output = args.output_root.resolve() / run_id
        output.mkdir(parents=True)
        manifest = {
            "experiment_run_id": run_id,
            "source_git_commit": commit,
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "source_run_id": source_status["experiment_run_id"],
            "source_run_commit": source_manifest["source_git_commit"],
            "execution_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(output / "manifest.json", manifest)

        evidence_rows: list[dict[str, Any]] = []
        result_rows: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="candidate_repeatability_") as temporary:
            temporary_dir = Path(temporary)
            for case in cases:
                case_id = case["case_id"]
                seed = int(case["seed"])
                hidden = oracle[case_id]
                fault = FaultCondition(
                    hidden["condition_id"],
                    hidden["perturbation_type_oracle"],
                    hidden["perturbation_parameters_oracle"],
                )
                repeated: dict[str, list[dict[str, Any]]] = {
                    candidate_id: [] for candidate_id in config["candidates"]
                }
                for repetition_index, namespace in enumerate(
                    config["prefix_perturbation_seed_namespaces"], start=1
                ):
                    perturbation_seed = derive_random_seed(seed, int(namespace))
                    for candidate_id in config["candidates"]:
                        registered = candidates[(case_id, candidate_id)]
                        correction = (
                            float(registered["correction_x"]),
                            float(registered["correction_y"]),
                            0.0,
                            0.0,
                        )
                        trajectory_path = temporary_dir / f"{case_id}_{candidate_id}_{repetition_index}.jsonl"
                        environment = create_push_environment(seed)
                        try:
                            run_episode(
                                environment,
                                PhaseGatedCompensatedPolicy(
                                    create_push_policy(),
                                    correction,
                                    schedule=registered["schedule"],
                                ),
                                seed=seed,
                                max_steps=int(config["prefix_horizon"]),
                                perturbation=fault.build(),
                                perturbation_seed=perturbation_seed,
                                agent_trajectory_path=trajectory_path,
                            )
                        finally:
                            environment.close()
                        records = _read_jsonl(trajectory_path)
                        repeated[candidate_id].append(
                            build_prefix_evidence(
                                records,
                                candidate_id=candidate_id,
                                horizon=int(config["prefix_horizon"]),
                            )
                        )

                for repetition_count in config["reported_repetition_counts"]:
                    aggregates = [
                        aggregate_candidate_repetitions(
                            repeated[candidate_id][: int(repetition_count)],
                            candidate_id=candidate_id,
                        )
                        for candidate_id in config["candidates"]
                    ]
                    selected = select_repeatability_candidate(aggregates)
                    packet = {
                        "experiment_run_id": run_id,
                        "case_id": case_id,
                        "seed": seed,
                        "repetition_count": repetition_count,
                        "candidate_repeatability_evidence": aggregates,
                        "selected_candidate": selected,
                    }
                    validate_no_oracle_evidence(packet)
                    evidence_rows.append(packet)
                    outcome = candidates[(case_id, selected)]
                    result_rows.append(
                        {
                            **manifest,
                            "case_id": case_id,
                            "seed": seed,
                            "repetition_count": repetition_count,
                            "selected_candidate": selected,
                            "outcome_preferred_candidate": case["best_candidate_ids"],
                            "utility_agreement": selected in case["best_candidate_ids"].split(","),
                            "selected_recovery_success": outcome["verification_success"],
                            "selected_verification_steps": int(outcome["verification_steps"]),
                            "selected_final_object_goal_distance": float(
                                outcome["final_object_goal_distance"]
                            ),
                            "prefix_environment_steps": sum(
                                int(item["total_environment_steps"]) for item in aggregates
                            ),
                        }
                    )
                print(f"case={case_id} seed={seed} repeatability_evidence=complete")

        _write_jsonl(output / "agent_repeatability_evidence.jsonl", evidence_rows)
        save_csv(output / "results.csv", result_rows)
        summaries: list[dict[str, Any]] = []
        for repetition_count in config["reported_repetition_counts"]:
            selected_rows = [
                row for row in result_rows if row["repetition_count"] == repetition_count
            ]
            summaries.append(
                {
                    **manifest,
                    "repetition_count": repetition_count,
                    "cases": len(selected_rows),
                    "utility_agreement_rate": mean(
                        bool(row["utility_agreement"]) for row in selected_rows
                    ),
                    "selected_recovery_rate": mean(
                        str(row["selected_recovery_success"]).lower() == "true"
                        for row in selected_rows
                    ),
                    "mean_prefix_environment_steps": mean(
                        row["prefix_environment_steps"] for row in selected_rows
                    ),
                    "mean_total_additional_steps": mean(
                        row["prefix_environment_steps"]
                        + row["selected_verification_steps"]
                        for row in selected_rows
                    ),
                }
            )
        save_csv(output / "summary.csv", summaries)
        _write_json(
            output / "run_status.json",
            {**manifest, "status": "COMPLETED", "cases": len(cases)},
        )
        print(f"results: {output}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
