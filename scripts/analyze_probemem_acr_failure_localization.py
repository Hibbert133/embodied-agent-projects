"""Localize frozen ProbeMem-ACR errors without fitting another selector."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.probemem import InterventionSkill  # noqa: E402
from src.probemem.intervention_utility import INTERVENTION_APPLICABILITY_FEATURES  # noqa: E402


COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION.value
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY.value
CLAIM_SCOPE = "post-hoc evaluator-only failure localization; no fitted selector"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("localization output cannot be empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def outcome_partition(status_by_action: dict[str, str]) -> str:
    if set(status_by_action) != {COMPENSATION, RETRY}:
        raise ValueError("each localization case requires both registered candidates")
    accepted = {action for action, status in status_by_action.items() if status == "ACCEPTED"}
    if accepted == {COMPENSATION}:
        return "COMPENSATION_ONLY_RECOVERY"
    if accepted == {RETRY}:
        return "RETRY_ONLY_RECOVERY"
    if accepted == {COMPENSATION, RETRY}:
        return "BOTH_RECOVER"
    return "NEITHER_RECOVERS"


def rank_probability(positive: Iterable[float], negative: Iterable[float]) -> float:
    """Return P(positive > negative), assigning half credit to ties."""

    left, right = tuple(positive), tuple(negative)
    if not left or not right:
        raise ValueError("rank contrast requires both outcome groups")
    score = sum(1.0 if item > other else 0.5 if item == other else 0.0 for item in left for other in right)
    return score / (len(left) * len(right))


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _render_feature_contrasts(rows: list[dict[str, Any]], output: Path) -> None:
    ranked = sorted(rows, key=lambda row: float(row["rank_separation"]), reverse=True)[:10]
    image = Image.new("RGB", (1500, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), "Post-hoc feature contrast: retry-only vs compensation-only", fill="#172554", font=_font(31))
    draw.text((55, 82), "Descriptive only (n=4 vs n=47); no threshold or selector was fitted", fill="#991b1b", font=_font(18))
    draw.text((55, 112), "All retry-only cases are fault_05: the contrast is condition-confounded", fill="#991b1b", font=_font(18))
    left, top, width, row_height = 570, 170, 750, 63
    for index, row in enumerate(ranked):
        y = top + index * row_height
        separation = float(row["rank_separation"])
        draw.text((55, y + 10), str(row["feature"]), fill="#334155", font=_font(18))
        draw.rounded_rectangle((left, y + 8, left + separation * width, y + 43), radius=8, fill="#2a9d8f")
        draw.text((left + separation * width + 12, y + 12), f"{separation:.2f}", fill="#111827", font=_font(17))
        direction = str(row["retry_only_direction"])
        draw.text((left + 15, y + 12), direction, fill="white", font=_font(15))
    draw.text((55, 835), "Rank separation = max(P(retry feature > compensation feature), reverse); label-selected and non-confirmatory", fill="#475569", font=_font(16))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", dpi=(180, 180))


def analyze(run_dir: Path, output_root: Path) -> dict[str, Any]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
    if status.get("status") != "COMPLETED":
        raise RuntimeError("failure localization requires a completed immutable run")

    candidates = _read_csv(run_dir / "candidate_results.csv")
    decisions = {int(row["episode_id"]): row for row in _read_jsonl(run_dir / "pre_execution_decisions.jsonl")}
    outcomes = _read_jsonl(run_dir / "action_outcomes.jsonl")
    records_by_episode: dict[int, list[dict[str, Any]]] = {}
    for row in outcomes:
        records_by_episode.setdefault(int(row["source_episode_id"]), []).append(row)
    candidates_by_episode: dict[int, list[dict[str, str]]] = {}
    for row in candidates:
        candidates_by_episode.setdefault(int(row["episode_id"]), []).append(row)

    exclusive: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    for episode_id, candidate_group in sorted(candidates_by_episode.items()):
        status_by_action = {row["candidate_id"]: row["verification_status"] for row in candidate_group}
        partition = outcome_partition(status_by_action)
        if partition not in {"COMPENSATION_ONLY_RECOVERY", "RETRY_ONLY_RECOVERY"}:
            continue
        records = records_by_episode.get(episode_id, [])
        if len(records) != 2:
            raise ValueError(f"episode {episode_id} lacks exactly two action-outcome records")
        signature = records[0]["evidence_signature"]
        if any(item["evidence_signature"] != signature for item in records[1:]):
            raise ValueError("paired action records do not share an evidence signature")
        decision = decisions[episode_id]["action_conditional_decision"]
        predictions = decision["predictions"]
        row: dict[str, Any] = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "episode_id": episode_id,
            "seed": candidate_group[0]["seed"],
            "condition_id_oracle_evaluator_only": next(
                item["condition_id_oracle"]
                for item in _read_csv(output_root / "development_method_episode_results.csv")
                if int(item["episode_id"]) == episode_id
            ),
            "outcome_partition_evaluator_only": partition,
            "acr_selected_skill": decision["selected_skill"],
            "acr_decision_reason": decision["decision_reason"],
            "acr_compensation_accept_probability": predictions[COMPENSATION]["probabilities"]["ACCEPTED"],
            "acr_retry_accept_probability": predictions[RETRY]["probabilities"]["ACCEPTED"],
            "acr_compensation_utility": predictions[COMPENSATION]["utility"],
            "acr_retry_utility": predictions[RETRY]["utility"],
            "acr_selected_exclusive_winner": (
                decision["selected_skill"] == COMPENSATION
                if partition == "COMPENSATION_ONLY_RECOVERY"
                else decision["selected_skill"] == RETRY
            ),
        }
        row.update(signature["features"])
        case_rows.append(row)
        exclusive.append({"partition": partition, "features": signature["features"]})

    compensation = [item for item in exclusive if item["partition"] == "COMPENSATION_ONLY_RECOVERY"]
    retry = [item for item in exclusive if item["partition"] == "RETRY_ONLY_RECOVERY"]
    if len(compensation) != 47 or len(retry) != 4:
        raise RuntimeError("immutable ACR exclusive-recovery counts differ from the frozen result")

    retry_conditions = Counter(str(row["condition_id_oracle_evaluator_only"]) for row in case_rows if row["outcome_partition_evaluator_only"] == "RETRY_ONLY_RECOVERY")
    dominant_retry_condition = retry_conditions.most_common(1)[0][0]
    same_condition_compensation = [
        item for item, row in zip(exclusive, case_rows)
        if row["condition_id_oracle_evaluator_only"] == dominant_retry_condition
        and row["outcome_partition_evaluator_only"] == "COMPENSATION_ONLY_RECOVERY"
    ]

    feature_rows: list[dict[str, Any]] = []
    for feature in INTERVENTION_APPLICABILITY_FEATURES:
        retry_values = [float(item["features"][feature]) for item in retry]
        compensation_values = [float(item["features"][feature]) for item in compensation]
        all_values = retry_values + compensation_values
        scale = statistics.pstdev(all_values)
        probability = rank_probability(retry_values, compensation_values)
        feature_rows.append({
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "analysis_scope": CLAIM_SCOPE,
            "feature": feature,
            "retry_only_count": len(retry_values),
            "compensation_only_count": len(compensation_values),
            "retry_only_mean": statistics.fmean(retry_values),
            "compensation_only_mean": statistics.fmean(compensation_values),
            "retry_only_median": statistics.median(retry_values),
            "compensation_only_median": statistics.median(compensation_values),
            "standardized_mean_difference": (
                (statistics.fmean(retry_values) - statistics.fmean(compensation_values)) / scale
                if scale > 1e-12 else 0.0
            ),
            "rank_probability_retry_greater": probability,
            "rank_separation": max(probability, 1.0 - probability),
            "retry_only_direction": "HIGHER" if probability >= 0.5 else "LOWER",
            "range_overlap": max(min(retry_values), min(compensation_values)) <= min(max(retry_values), max(compensation_values)),
            "dominant_retry_condition_evaluator_only": dominant_retry_condition,
            "same_condition_compensation_count": len(same_condition_compensation),
            "same_condition_rank_probability_retry_greater": (
                rank_probability(
                    retry_values,
                    [float(item["features"][feature]) for item in same_condition_compensation],
                )
                if same_condition_compensation else None
            ),
        })

    feature_rows.sort(key=lambda row: float(row["rank_separation"]), reverse=True)
    _write_csv(output_root / "failure_localization_cases.csv", case_rows)
    _write_csv(output_root / "failure_localization_feature_contrasts.csv", feature_rows)
    _render_feature_contrasts(feature_rows, output_root / "figures/acr_retry_only_feature_contrasts.png")
    retry_case_rows = [row for row in case_rows if row["outcome_partition_evaluator_only"] == "RETRY_ONLY_RECOVERY"]
    summary = {
        "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"],
        "claim_scope": CLAIM_SCOPE,
        "new_rollouts": 0,
        "api_calls": 0,
        "exclusive_recovery_cases": len(case_rows),
        "compensation_only_cases": len(compensation),
        "retry_only_cases": len(retry),
        "acr_correct_on_retry_only": sum(bool(row["acr_selected_exclusive_winner"]) for row in retry_case_rows),
        "retry_only_condition_counts_evaluator_only": dict(sorted(retry_conditions.items())),
        "all_retry_only_share_one_condition": len(retry_conditions) == 1,
        "dominant_retry_condition_evaluator_only": dominant_retry_condition,
        "same_condition_compensation_only_cases": len(same_condition_compensation),
        "condition_confounding_detected": len(retry_conditions) == 1,
        "top_posthoc_feature_contrasts": [
            {
                "feature": row["feature"],
                "rank_separation": row["rank_separation"],
                "retry_only_direction": row["retry_only_direction"],
                "range_overlap": row["range_overlap"],
            }
            for row in feature_rows[:5]
        ],
        "threshold_fitted": False,
        "selector_created": False,
        "validation_authorized": False,
    }
    _write_json(output_root / "failure_localization_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs/probemem_acr")
    args = parser.parse_args()
    try:
        summary = analyze(args.run_dir.resolve(), args.output_root.resolve())
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
