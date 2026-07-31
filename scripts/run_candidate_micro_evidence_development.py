"""Evaluate action-conditioned candidate prefixes on a fixed development set."""

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
from src.horizon_utility import build_prefix_evidence  # noqa: E402
from src.reasoning.evidence import validate_no_oracle_evidence  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402
from src.utility_controls import choose_probe_greedy  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs/autoresearch/candidate_micro_evidence_development_v1.json"


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def validate_config(config: Mapping[str, Any]) -> None:
    horizons = [int(value) for value in config["prefix_horizons"]]
    if config.get("split") != "development" or horizons != [16, 32, 64, 128]:
        raise ValueError("v1 requires the frozen development horizons")
    if max(horizons) != int(config["maximum_prefix_steps"]):
        raise ValueError("maximum prefix must equal the largest horizon")
    if bool(config["analysis"]["fit_threshold"]):
        raise ValueError("micro-evidence development cannot fit a threshold")
    if config.get("rendering") is not False or int(config.get("api_calls", -1)) != 0:
        raise ValueError("timing study cannot render or call an API")
    if list(config.get("candidates", ())) != [
        "probe_grounded_compensation",
        "stochastic_retry",
    ]:
        raise ValueError("v1 requires the two registered intervention candidates")
    if int(config.get("expected_cases", 0)) <= 0:
        raise ValueError("expected_cases must be positive")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/candidate_micro_evidence/runs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        validate_config(config)
        if _git("diff", "--name-only") or _git("diff", "--cached", "--name-only"):
            raise RuntimeError("commit implementation before execution")
        source = (ROOT / config["source_run"]).resolve()
        source_status = json.loads((source / "run_status.json").read_text(encoding="utf-8"))
        if source_status.get("status") != "COMPLETED" or not source_status.get("coverage_target_reached"):
            raise ValueError("source coverage run is not complete")
        if source_status.get("source_git_commit") != config.get("source_run_commit"):
            raise ValueError("source run commit differs from the frozen protocol")
        cases = [row for row in _csv(source / "case_results.csv") if row["paired_comparable"] == "True"]
        if len(cases) != int(config["expected_cases"]):
            raise ValueError("source comparable population differs from protocol")
        candidate_rows = _csv(source / "candidate_results.csv")
        candidates = {(row["case_id"], row["candidate_id"]): row for row in candidate_rows}
        oracle = {row["case_id"]: row for row in _jsonl(source / "oracle_audit.jsonl")}
        commit = _git("rev-parse", "HEAD")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"micro_{timestamp}_{commit[:12]}"
        output = args.output_root.resolve() / run_id
        output.mkdir(parents=True)
        manifest = {
            "experiment_run_id": run_id,
            "source_git_commit": commit,
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "source_run_id": source_status["experiment_run_id"],
            "execution_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(output / "manifest.json", manifest)
        evidence_rows: list[dict[str, Any]] = []
        result_rows: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="candidate_prefix_") as temporary:
            temp = Path(temporary)
            for case in cases:
                case_id, seed = case["case_id"], int(case["seed"])
                hidden = oracle[case_id]
                fault = FaultCondition(hidden["condition_id"], hidden["perturbation_type_oracle"], hidden["perturbation_parameters_oracle"])
                traces: dict[str, list[dict[str, Any]]] = {}
                for candidate_id in config["candidates"]:
                    registered = candidates[(case_id, candidate_id)]
                    correction = (float(registered["correction_x"]), float(registered["correction_y"]), 0.0, 0.0)
                    path = temp / f"{case_id}_{candidate_id}.jsonl"
                    env = create_push_environment(seed)
                    try:
                        run_episode(
                            env,
                            PhaseGatedCompensatedPolicy(create_push_policy(), correction, schedule=registered["schedule"]),
                            seed=seed,
                            max_steps=int(config["maximum_prefix_steps"]),
                            perturbation=fault.build(),
                            perturbation_seed=derive_random_seed(seed, int(config["prefix_perturbation_seed_namespace"])),
                            agent_trajectory_path=path,
                        )
                    finally:
                        env.close()
                    traces[candidate_id] = _jsonl(path)
                for horizon in config["prefix_horizons"]:
                    evidence = [build_prefix_evidence(traces[candidate_id], candidate_id=candidate_id, horizon=int(horizon)) for candidate_id in config["candidates"]]
                    packet = {"experiment_run_id": run_id, "case_id": case_id, "seed": seed, "horizon": horizon, "candidate_prefix_evidence": evidence}
                    validate_no_oracle_evidence(packet)
                    evidence_rows.append(packet)
                    selected = choose_probe_greedy(evidence)
                    outcome = candidates[(case_id, selected)]
                    result_rows.append({
                        **manifest,
                        "case_id": case_id,
                        "seed": seed,
                        "horizon": horizon,
                        "selected_candidate": selected,
                        "outcome_preferred_candidate": case["best_candidate_ids"],
                        "utility_agreement": selected == case["best_candidate_ids"],
                        "selected_recovery_success": outcome["verification_success"],
                        "selected_verification_steps": int(outcome["verification_steps"]),
                        "selected_final_object_goal_distance": float(outcome["final_object_goal_distance"]),
                        "prefix_environment_steps": sum(int(item["observed_steps"]) for item in evidence),
                    })
                print(f"case={case_id} seed={seed} prefixes=complete")
        _write_jsonl(output / "agent_prefix_evidence.jsonl", evidence_rows)
        save_csv(output / "results.csv", result_rows)
        summaries = []
        for horizon in config["prefix_horizons"]:
            rows = [row for row in result_rows if row["horizon"] == horizon]
            compensation_recovery = mean(
                candidates[(row["case_id"], "probe_grounded_compensation")]["verification_success"].lower()
                == "true"
                for row in rows
            )
            retry_recovery = mean(
                candidates[(row["case_id"], "stochastic_retry")]["verification_success"].lower()
                == "true"
                for row in rows
            )
            summaries.append({
                **manifest,
                "horizon": horizon,
                "cases": len(rows),
                "utility_agreement_rate": mean(bool(row["utility_agreement"]) for row in rows),
                "selected_recovery_rate": mean(str(row["selected_recovery_success"]).lower() == "true" for row in rows),
                "fixed_compensation_recovery_rate": compensation_recovery,
                "fixed_retry_recovery_rate": retry_recovery,
                "mean_prefix_environment_steps": mean(row["prefix_environment_steps"] for row in rows),
                "mean_total_additional_steps": mean(row["prefix_environment_steps"] + row["selected_verification_steps"] for row in rows),
            })
        save_csv(output / "summary.csv", summaries)
        _write_json(output / "run_status.json", {**manifest, "status": "COMPLETED", "cases": len(cases)})
        print(f"results: {output}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
