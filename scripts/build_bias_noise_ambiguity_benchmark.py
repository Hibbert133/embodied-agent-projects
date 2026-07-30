"""Build a frozen passive-symptom-matched bias-versus-noise benchmark.

Pair selection uses only outcomes of the initial failed rollout. Repeated-probe
scores are joined strictly after matching and are used only for post-selection
audit. This separation prevents diagnostic evidence from leaking into case
selection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PASSIVE_MATCH_FEATURES = (
    "episode_return",
    "final_object_goal_distance",
    "progress_to_goal",
)
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class PassiveFailureCase:
    case_id: str
    condition_id: str
    seed: int
    mechanism_class: str
    episode_return: float
    final_object_goal_distance: float
    progress_to_goal: float
    perturbation_parameters: dict[str, Any]

    def feature(self, name: str) -> float:
        if name not in PASSIVE_MATCH_FEATURES:
            raise ValueError(f"forbidden matching feature: {name}")
        return float(getattr(self, name))


@dataclass(frozen=True)
class MatchedPair:
    pair_id: str
    bias_case: PassiveFailureCase
    noise_case: PassiveFailureCase
    standardized_distance: float


def _validate_features(features: Sequence[str]) -> tuple[str, ...]:
    selected = tuple(features)
    if selected != PASSIVE_MATCH_FEATURES:
        raise ValueError(
            "matching features must be exactly the registered passive feature set: "
            f"{PASSIVE_MATCH_FEATURES}"
        )
    return selected


def match_passive_failures(
    bias_cases: Sequence[PassiveFailureCase],
    noise_cases: Sequence[PassiveFailureCase],
    *,
    features: Sequence[str] = PASSIVE_MATCH_FEATURES,
) -> list[MatchedPair]:
    """Return a deterministic globally minimum-cost one-to-one assignment."""
    selected_features = _validate_features(features)
    biases = sorted(bias_cases, key=lambda case: case.case_id)
    noises = sorted(noise_cases, key=lambda case: case.case_id)
    if not noises:
        raise ValueError("at least one noise failure is required")
    if len(biases) < len(noises):
        raise ValueError("one-to-one matching requires at least as many bias failures")
    if len({case.case_id for case in (*biases, *noises)}) != len(biases) + len(noises):
        raise ValueError("case_id values must be unique")

    pool = [*biases, *noises]
    centers = {name: mean(case.feature(name) for case in pool) for name in selected_features}
    scales = {
        name: pstdev(case.feature(name) for case in pool) or 1.0
        for name in selected_features
    }

    def vector(case: PassiveFailureCase) -> tuple[float, ...]:
        return tuple(
            (case.feature(name) - centers[name]) / scales[name]
            for name in selected_features
        )

    bias_vectors = [vector(case) for case in biases]
    noise_vectors = [vector(case) for case in noises]
    costs = [
        [math.dist(noise_vector, bias_vector) for bias_vector in bias_vectors]
        for noise_vector in noise_vectors
    ]

    @lru_cache(maxsize=None)
    def solve(noise_index: int, used_mask: int) -> tuple[float, tuple[int, ...]]:
        if noise_index == len(noises):
            return 0.0, ()
        best: tuple[float, tuple[int, ...]] | None = None
        for bias_index in range(len(biases)):
            if used_mask & (1 << bias_index):
                continue
            tail_cost, tail_indices = solve(
                noise_index + 1, used_mask | (1 << bias_index)
            )
            candidate = (costs[noise_index][bias_index] + tail_cost, (bias_index, *tail_indices))
            if best is None or candidate[0] < best[0] - 1e-12:
                best = candidate
            elif abs(candidate[0] - best[0]) <= 1e-12:
                candidate_ids = tuple(biases[index].case_id for index in candidate[1])
                best_ids = tuple(biases[index].case_id for index in best[1])
                if candidate_ids < best_ids:
                    best = candidate
        if best is None:
            raise RuntimeError("matching solver found no assignment")
        return best

    _, selected_bias_indices = solve(0, 0)
    return [
        MatchedPair(
            pair_id=f"pair_{index:02d}",
            bias_case=biases[bias_index],
            noise_case=noise_case,
            standardized_distance=costs[index - 1][bias_index],
        )
        for index, (noise_case, bias_index) in enumerate(
            zip(noises, selected_bias_indices), start=1
        )
    ]


def classify_probe(score: float, threshold: float) -> str:
    if threshold < 0:
        raise ValueError("probe threshold must be non-negative")
    return "stochastic_noise" if float(score) > threshold else "stable_bias"


def _load_oracle_failures(path: Path) -> list[PassiveFailureCase]:
    rows: list[PassiveFailureCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        baseline = record.get("baseline", {})
        if bool(baseline.get("success")):
            continue
        perturbation_type = record.get("perturbation_type")
        if perturbation_type == "action_bias":
            mechanism_class = "stable_bias"
        elif perturbation_type == "gaussian_noise":
            mechanism_class = "stochastic_noise"
        else:
            continue
        try:
            rows.append(
                PassiveFailureCase(
                    case_id=str(record["case_id"]),
                    condition_id=str(record["condition_id"]),
                    seed=int(record["seed"]),
                    mechanism_class=mechanism_class,
                    episode_return=float(baseline["episode_return"]),
                    final_object_goal_distance=float(
                        baseline["final_object_goal_distance"]
                    ),
                    progress_to_goal=float(baseline["progress_to_goal"]),
                    perturbation_parameters=dict(record["perturbation_parameters"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid oracle record at line {line_number}: {exc}") from exc
    return rows


def _load_probe_rows(path: Path) -> dict[tuple[str, int], dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result: dict[tuple[str, int], dict[str, str]] = {}
    for row in rows:
        key = (str(row["condition_id"]), int(row["seed"]))
        if key in result:
            raise ValueError(f"duplicate probe result for {key}")
        result[key] = row
    return result


def _write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_benchmark(
    oracle_path: Path,
    probe_path: Path,
    threshold_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    failures = _load_oracle_failures(oracle_path)
    bias_cases = [case for case in failures if case.mechanism_class == "stable_bias"]
    noise_cases = [case for case in failures if case.mechanism_class == "stochastic_noise"]
    pairs = match_passive_failures(bias_cases, noise_cases)

    threshold_record = json.loads(threshold_path.read_text(encoding="utf-8"))
    threshold = float(threshold_record["threshold"])
    probe_rows = _load_probe_rows(probe_path)
    selected_cases = [case for pair in pairs for case in (pair.bias_case, pair.noise_case)]

    pair_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for pair in pairs:
        pair_rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "pair_id": pair.pair_id,
                "bias_case_id": pair.bias_case.case_id,
                "noise_case_id": pair.noise_case.case_id,
                "standardized_passive_distance": pair.standardized_distance,
            }
        )
        for case in (pair.bias_case, pair.noise_case):
            probe_key = (case.condition_id, case.seed)
            if probe_key not in probe_rows:
                raise ValueError(f"missing repeated-probe result for {probe_key}")
            probe = probe_rows[probe_key]
            score = float(probe["estimated_bias_std_norm"])
            predicted = classify_probe(score, threshold)
            case_rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "pair_id": pair.pair_id,
                    "case_id": case.case_id,
                    "condition_id": case.condition_id,
                    "seed": case.seed,
                    "mechanism_class": case.mechanism_class,
                    "episode_return": case.episode_return,
                    "final_object_goal_distance": case.final_object_goal_distance,
                    "progress_to_goal": case.progress_to_goal,
                    "perturbation_parameters_oracle": json.dumps(
                        case.perturbation_parameters, separators=(",", ":")
                    ),
                }
            )
            audit_rows.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "pair_id": pair.pair_id,
                    "case_id": case.case_id,
                    "condition_id": case.condition_id,
                    "seed": case.seed,
                    "mechanism_class_oracle": case.mechanism_class,
                    "estimated_bias_std_norm": score,
                    "frozen_threshold": threshold,
                    "predicted_mechanism": predicted,
                    "correct": predicted == case.mechanism_class,
                    "probe_environment_steps": int(probe["probe_environment_steps"]),
                    "repeat_count": int(probe["repeat_count"]),
                }
            )

    correct = sum(bool(row["correct"]) for row in audit_rows)
    by_class = {
        label: [row for row in audit_rows if row["mechanism_class_oracle"] == label]
        for label in ("stable_bias", "stochastic_noise")
    }
    recalls = [
        sum(bool(row["correct"]) for row in rows) / len(rows)
        for rows in by_class.values()
    ]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": "bias_noise_tuning_v1",
        "split": "tuning",
        "source_oracle_audit": _relative(oracle_path),
        "source_oracle_audit_sha256": _sha256(oracle_path),
        "source_probe_results": _relative(probe_path),
        "source_probe_results_sha256": _sha256(probe_path),
        "source_threshold": _relative(threshold_path),
        "source_threshold_sha256": _sha256(threshold_path),
        "selection_rule": (
            "global one-to-one minimum standardized Euclidean distance; "
            "probe evidence excluded from matching"
        ),
        "selection_features": list(PASSIVE_MATCH_FEATURES),
        "candidate_bias_failures": len(bias_cases),
        "candidate_noise_failures": len(noise_cases),
        "matched_pairs": len(pairs),
        "matched_cases": len(selected_cases),
        "frozen_probe_threshold": threshold,
        "post_selection_probe_accuracy": correct / len(audit_rows),
        "post_selection_probe_balanced_accuracy": mean(recalls),
        "mean_standardized_passive_distance": mean(
            pair.standardized_distance for pair in pairs
        ),
        "claim_boundary": (
            "tuning pilot only; selected cases and threshold are not a held-out claim"
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "pairs.csv", pair_rows)
    _write_csv(output_dir / "cases.csv", case_rows)
    _write_csv(output_dir / "probe_audit.csv", audit_rows)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--oracle-audit",
        type=Path,
        default=ROOT / "outputs/autoresearch/benchmark_tuning/oracle_audit.jsonl",
    )
    parser.add_argument(
        "--probe-results",
        type=Path,
        default=ROOT / "outputs/autoresearch/probe_consistency_tuning/results.csv",
    )
    parser.add_argument(
        "--threshold-selection",
        type=Path,
        default=ROOT
        / "outputs/autoresearch/probe_consistency_tuning/threshold_selection.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/ambiguity_benchmark/bias_noise_tuning_v1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = build_benchmark(
            args.oracle_audit,
            args.probe_results,
            args.threshold_selection,
            args.output_dir.resolve(),
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
