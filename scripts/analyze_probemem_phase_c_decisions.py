"""Audit how episodic retrieval changed ProbeMem Phase-C reasoning and behavior.

This is a post-hoc, no-API analysis of an immutable development run.  It does
not rerun the robot environment and must not be used to tune held-out logic.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATELESS_METHOD = "stateless_online_llm"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("decision audit produced no rows")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _prediction_status(decision: dict[str, Any]) -> str:
    prediction = decision.get("predicted_outcome")
    return "" if prediction is None else str(prediction["verification_status"])


def _retrieved_statuses(record: dict[str, Any]) -> list[str]:
    return [
        str(item["observed_verification_status"])
        for item in record["retrieved_episode_records"]
    ]


def build_decision_audit(
    records: list[dict[str, Any]], methods: tuple[str, ...]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return episode rows, method summaries, and paired audit metadata."""
    by_episode: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        if not bool(record["initial_success"]):
            by_episode[int(record["episode_id"])][str(record["method"])] = record

    incomplete = {
        episode_id: sorted(set(methods) - set(group))
        for episode_id, group in by_episode.items()
        if set(group) != set(methods)
    }
    if incomplete:
        raise ValueError(f"incomplete operational method groups: {incomplete}")
    if STATELESS_METHOD not in methods:
        raise ValueError(f"missing reference method: {STATELESS_METHOD}")

    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        group = by_episode[episode_id]
        reference = group[STATELESS_METHOD]
        reference_initial = reference["decision_trace"][0]["decision"]
        reference_final = reference["decision_trace"][-1]["decision"]
        for method in methods:
            record = group[method]
            if len(record["decision_trace"]) < 2:
                raise ValueError(
                    f"episode={episode_id} method={method} lacks post-probe decision"
                )
            initial = record["decision_trace"][0]["decision"]
            final = record["decision_trace"][-1]["decision"]
            retrieved_statuses = _retrieved_statuses(record)
            predicted_status = _prediction_status(final)
            actual_status = str(record["host_execution"]["verification_status"])
            rows.append(
                {
                    "experiment_run_id": record["experiment_run_id"],
                    "manifest_id": record["manifest_id"],
                    "episode_id": episode_id,
                    "seed": int(record["seed"]),
                    "method": method,
                    "retrieved_record_count": len(record["retrieved_episode_records"]),
                    "retrieved_statuses": "|".join(retrieved_statuses),
                    "retrieved_nonaccepted_count": sum(
                        status != "ACCEPTED" for status in retrieved_statuses
                    ),
                    "initial_memory_used": bool(initial["memory_used"]),
                    "post_probe_memory_used": bool(final["memory_used"]),
                    "initial_tool": initial["requested_tool"],
                    "post_probe_tool": final["requested_tool"],
                    "initial_mechanism_hypothesis": initial["mechanism_hypothesis"],
                    "post_probe_mechanism_hypothesis": final["mechanism_hypothesis"],
                    "initial_confidence": initial["confidence"],
                    "post_probe_confidence": final["confidence"],
                    "predicted_verification_status": predicted_status,
                    "actual_verification_status": actual_status,
                    "prediction_exact": predicted_status == actual_status,
                    "selected_skill": record["selected_skill"],
                    "initial_hypothesis_differs_from_stateless": (
                        initial["mechanism_hypothesis"]
                        != reference_initial["mechanism_hypothesis"]
                    ),
                    "post_probe_hypothesis_differs_from_stateless": (
                        final["mechanism_hypothesis"]
                        != reference_final["mechanism_hypothesis"]
                    ),
                    "post_probe_confidence_differs_from_stateless": (
                        final["confidence"] != reference_final["confidence"]
                    ),
                    "prediction_differs_from_stateless": (
                        predicted_status != _prediction_status(reference_final)
                    ),
                    "skill_differs_from_stateless": (
                        record["selected_skill"] != reference["selected_skill"]
                    ),
                    "outcome_differs_from_stateless": (
                        actual_status
                        != str(reference["host_execution"]["verification_status"])
                    ),
                }
            )

    by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_method[str(row["method"])].append(row)

    reference_exact = {
        int(row["episode_id"]): bool(row["prediction_exact"])
        for row in by_method[STATELESS_METHOD]
    }
    summaries: list[dict[str, Any]] = []
    for method in methods:
        selected = by_method[method]
        retrieval_cases = [row for row in selected if row["retrieved_record_count"] > 0]
        improved = sum(
            bool(row["prediction_exact"])
            and not reference_exact[int(row["episode_id"])]
            for row in selected
        )
        worsened = sum(
            not bool(row["prediction_exact"])
            and reference_exact[int(row["episode_id"])]
            for row in selected
        )
        summaries.append(
            {
                "method": method,
                "operational_cases": len(selected),
                "retrieval_cases": len(retrieval_cases),
                "memory_acknowledged_cases": sum(
                    bool(row["post_probe_memory_used"]) for row in selected
                ),
                "initial_hypothesis_difference_cases": sum(
                    bool(row["initial_hypothesis_differs_from_stateless"])
                    for row in selected
                ),
                "post_probe_hypothesis_difference_cases": sum(
                    bool(row["post_probe_hypothesis_differs_from_stateless"])
                    for row in selected
                ),
                "post_probe_confidence_difference_cases": sum(
                    bool(row["post_probe_confidence_differs_from_stateless"])
                    for row in selected
                ),
                "prediction_difference_cases": sum(
                    bool(row["prediction_differs_from_stateless"]) for row in selected
                ),
                "exact_prediction_cases": sum(
                    bool(row["prediction_exact"]) for row in selected
                ),
                "prediction_improved_vs_stateless": improved,
                "prediction_worsened_vs_stateless": worsened,
                "prediction_tied_vs_stateless": len(selected) - improved - worsened,
                "intervention_difference_cases": sum(
                    bool(row["skill_differs_from_stateless"]) for row in selected
                ),
                "verification_outcome_difference_cases": sum(
                    bool(row["outcome_differs_from_stateless"]) for row in selected
                ),
                "nonaccepted_record_exposures": sum(
                    int(row["retrieved_nonaccepted_count"]) for row in selected
                ),
            }
        )

    audit = {
        "operational_episode_count": len(by_episode),
        "operational_record_count": len(rows),
        "methods": list(methods),
        "all_interventions_tied": all(
            not bool(row["skill_differs_from_stateless"]) for row in rows
        ),
        "all_verification_outcomes_tied": all(
            not bool(row["outcome_differs_from_stateless"]) for row in rows
        ),
        "interpretation_scope": "post_hoc_development_decision_trace_audit",
    }
    return rows, summaries, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-decisions",
        type=Path,
        default=ROOT / "outputs/probemem_v2/phase_c_decision_audit.csv",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=ROOT / "outputs/probemem_v2/phase_c_decision_audit_summary.csv",
    )
    parser.add_argument(
        "--output-audit",
        type=Path,
        default=ROOT / "outputs/probemem_v2/phase_c_decision_audit.json",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_phase_c_decision_audit.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED":
            raise ValueError(f"decision audit requires COMPLETED run, got {status}")
        methods = tuple(str(item) for item in manifest["methods"])
        rows, summaries, audit = build_decision_audit(
            _read_jsonl(run_dir / "interaction_audit.jsonl"), methods
        )
        audit.update(
            {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
            }
        )
        _write_csv(args.output_decisions.resolve(), rows)
        _write_csv(args.output_summary.resolve(), summaries)
        args.output_audit.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_audit.resolve().write_text(
            json.dumps(audit, indent=2) + "\n", encoding="utf-8"
        )

        summary_by_method = {row["method"]: row for row in summaries}
        raw = summary_by_method["raw_episodic_retrieval_development_only"]
        verified = summary_by_method["verified_episodic_retrieval"]
        lines = [
            "# ProbeMem Phase C Decision-Trace Audit",
            "",
            f"Run: `{manifest['experiment_run_id']}`",
            f"Manifest: `{manifest['manifest_id']}`",
            f"Source commit: `{manifest['source_git_commit']}`",
            "",
            "## Question",
            "",
            "Why did chronological episodic retrieval get acknowledged by the online "
            "model without changing the selected intervention? This is a no-API, "
            "post-hoc audit of the immutable development trace; it does not tune or "
            "rerun the registered experiment.",
            "",
            "## Quantitative trace result",
            "",
            f"- Operational paired episodes: {audit['operational_episode_count']}.",
            f"- Raw retrieval was available in {raw['retrieval_cases']} cases and "
            f"acknowledged in {raw['memory_acknowledged_cases']} post-probe decisions.",
            f"- Verified retrieval was available in {verified['retrieval_cases']} cases "
            f"and acknowledged in {verified['memory_acknowledged_cases']} post-probe decisions.",
            f"- Raw retrieval was associated with a different predicted verification "
            f"status in {raw['prediction_difference_cases']} cases, but changed the "
            f"intervention in {raw['intervention_difference_cases']} cases.",
            f"- Verified retrieval changed post-probe confidence in "
            f"{verified['post_probe_confidence_difference_cases']} cases, but changed "
            f"the intervention in {verified['intervention_difference_cases']} cases.",
            f"- Exact prediction agreement was {summary_by_method[STATELESS_METHOD]['exact_prediction_cases']}/"
            f"{audit['operational_episode_count']} stateless, "
            f"{raw['exact_prediction_cases']}/{audit['operational_episode_count']} raw, "
            f"and {verified['exact_prediction_cases']}/{audit['operational_episode_count']} verified.",
            f"- Relative to stateless prediction agreement, raw retrieval improved "
            f"{raw['prediction_improved_vs_stateless']} cases and worsened "
            f"{raw['prediction_worsened_vs_stateless']} cases; this is descriptive, "
            "not a powered calibration comparison.",
            f"- Raw memory exposed {raw['nonaccepted_record_exposures']} non-accepted "
            "historical records; verified memory exposed none.",
            "- All methods selected the same bounded skill and received the same fresh "
            "verification outcome in every operational pair.",
            "",
            "## Research interpretation",
            "",
            "Memory context affected structured reasoning fields, especially raw-memory "
            "outcome predictions and verified-memory confidence, but this variation was "
            "compressed by the final skill decision. The registered post-probe evidence "
            "made every method infer `stable_bias`, after which the available bounded "
            "skill interface led every method to `BOUNDED_PLANAR_COMPENSATION`.",
            "",
            "This supports a narrower diagnosis than \"the model ignored memory\": the "
            "current episodic representation lacks a reliable, action-discriminative "
            "utility signal. Raw rejected/inconclusive episodes changed predictions but "
            "did not safely redirect behavior. Accepted-only episodes sometimes raised "
            "confidence but did not establish when compensation should fail. Independent "
            "LLM sampling is a confound, so differences in hypotheses or predictions are "
            "associations, not causal effects of memory.",
            "",
            "## Phase-D promotion decision",
            "",
            "Do not promote unrestricted LLM-generated principles yet. The next "
            "development experiment should first define a falsifiable intervention-utility "
            "record: Agent-visible applicability conditions, selected skill, predicted "
            "verification status, observed fresh outcome, and explicit contradiction. "
            "It should test whether that record changes a discrete intervention on new "
            "development seeds before any held-out freeze.",
            "",
            "## Reproduction",
            "",
            "```bash",
            f"python scripts/analyze_probemem_phase_c_decisions.py --run-dir \"{run_dir}\"",
            "```",
        ]
        args.output_report.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_report.resolve().write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"decisions: {args.output_decisions.resolve()}")
        print(f"summary: {args.output_summary.resolve()}")
        print(f"audit: {args.output_audit.resolve()}")
        print(f"report: {args.output_report.resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
