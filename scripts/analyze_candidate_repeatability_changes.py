"""Audit all decisions changed by additional repeated candidate evidence."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import save_csv  # noqa: E402
from src.reasoning.evidence import validate_no_oracle_evidence  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs/autoresearch/candidate_repeatability_decision_change_audit_v1.json"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _bool(value: object) -> bool:
    return str(value).lower() == "true"


def _by_candidate(packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item["candidate_id"]): item
        for item in packet["candidate_repeatability_evidence"]
    }


def classify_changed_case(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    before_result: Mapping[str, str],
    after_result: Mapping[str, str],
) -> dict[str, Any]:
    """Join Agent evidence with evaluator outcomes after selection."""

    validate_no_oracle_evidence(before)
    validate_no_oracle_evidence(after)
    if before["case_id"] != after["case_id"] or before["selected_candidate"] == after["selected_candidate"]:
        raise ValueError("audit requires one changed decision from the same case")
    before_success = _bool(before_result["selected_recovery_success"])
    after_success = _bool(after_result["selected_recovery_success"])
    if after_success and not before_success:
        outcome_class = "HELPFUL"
    elif before_success and not after_success:
        outcome_class = "HARMFUL"
    else:
        outcome_class = "NEUTRAL"
    after_evidence = _by_candidate(after)
    selected_after = after_evidence[str(after["selected_candidate"])]
    rejected_after = next(
        value for key, value in after_evidence.items() if key != after["selected_candidate"]
    )
    if int(selected_after["prefix_success_count"]) > int(rejected_after["prefix_success_count"]):
        driver = "PREFIX_SUCCESS_PRIORITY"
    else:
        driver = "ROBUST_DISTANCE_RANK_FLIP"
    compensation = after_evidence["probe_grounded_compensation"]
    retry = after_evidence["stochastic_retry"]
    return {
        "case_id": before["case_id"],
        "seed": int(before["seed"]),
        "before_candidate": before["selected_candidate"],
        "after_candidate": after["selected_candidate"],
        "outcome_class": outcome_class,
        "evidence_driver": driver,
        "before_recovery_success": before_success,
        "after_recovery_success": after_success,
        "compensation_prefix_success_count_k3": int(compensation["prefix_success_count"]),
        "retry_prefix_success_count_k3": int(retry["prefix_success_count"]),
        "compensation_robust_distance_k3": float(compensation["robust_distance_score"]),
        "retry_robust_distance_k3": float(retry["robust_distance_score"]),
        "retry_minus_compensation_robust_margin_k3": float(retry["robust_distance_score"])
        - float(compensation["robust_distance_score"]),
    }


def select_representatives(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    representatives = []
    for outcome_class in ("HELPFUL", "HARMFUL", "NEUTRAL"):
        candidates = [row for row in rows if row["outcome_class"] == outcome_class]
        if candidates:
            representatives.append(
                dict(
                    min(
                        candidates,
                        key=lambda row: (
                            -abs(float(row["retry_minus_compensation_robust_margin_k3"])),
                            int(row["seed"]),
                        ),
                    )
                )
            )
    return representatives


def _plot(summary: Mapping[str, Any], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1500, 850), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    small = ImageFont.load_default(size=17)
    title = ImageFont.load_default(size=29)
    draw.text((360, 30), "What did additional repeated evidence change?", fill="black", font=title)
    stages = [
        ("Decision changed", summary["changed_cases"], "#4c78a8"),
        ("Helpful", summary["outcome_counts"].get("HELPFUL", 0), "#54a24b"),
        ("Neutral", summary["outcome_counts"].get("NEUTRAL", 0), "#bab0ac"),
        ("Harmful", summary["outcome_counts"].get("HARMFUL", 0), "#e45756"),
    ]
    for index, (label, count, color) in enumerate(stages):
        x = 110 + index * 340
        height = 45 * count
        draw.rectangle((x, 680 - height, x + 230, 680), fill=color)
        draw.text((x + 100, 640 - height), str(count), fill=color, font=font)
        draw.text((x + 55, 710), label, fill="black", font=small)
    draw.text((110, 785), "k=1 -> k=3; all changed cases; independent full verification determines helpful/harmful", fill="#666666", font=small)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", dpi=(180, 180), optimize=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-figure", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    run = args.run_dir.resolve()
    packets = _jsonl(run / "agent_repeatability_evidence.jsonl")
    results = _csv(run / "results.csv")
    by_packet = {(row["case_id"], int(row["repetition_count"])): row for row in packets}
    by_result = {(row["case_id"], int(row["repetition_count"])): row for row in results}
    before_k = int(config["comparison"]["before_repetitions"])
    after_k = int(config["comparison"]["after_repetitions"])
    rows = []
    for case_id in sorted({row["case_id"] for row in packets}):
        before, after = by_packet[(case_id, before_k)], by_packet[(case_id, after_k)]
        if before["selected_candidate"] != after["selected_candidate"]:
            rows.append(
                classify_changed_case(
                    before,
                    after,
                    by_result[(case_id, before_k)],
                    by_result[(case_id, after_k)],
                )
            )
    outcome_counts = Counter(row["outcome_class"] for row in rows)
    driver_counts = Counter(row["evidence_driver"] for row in rows)
    summary = {
        "protocol_id": config["protocol_id"],
        "repeatability_run_id": config["repeatability_run_id"],
        "changed_cases": len(rows),
        "outcome_counts": dict(outcome_counts),
        "driver_counts": dict(driver_counts),
        "representatives": select_representatives(rows),
        "claim_boundary": config["claim_boundary"],
    }
    save_csv(run / "decision_change_audit.csv", rows)
    (run / "decision_change_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    _plot(summary, args.output_figure.resolve())
    print(f"audit: {run / 'decision_change_audit.csv'}")
    print(f"summary: {run / 'decision_change_summary.json'}")
    print(f"figure: {args.output_figure.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
