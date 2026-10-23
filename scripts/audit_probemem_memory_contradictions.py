"""Post-hoc contradiction audit for the frozen coverage-aware memory run.

This script is evaluator-only. It does not change the frozen retrieval gate,
create actionable memory, or promote intervention principles. A memory use
implicitly predicts that its selected skill will repeat the ACCEPTED outcome
of the retrieved verified episodes; fresh verification tests that prediction.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_probemem_verified_intervention_snapshot import _signature  # noqa: E402
from src.probemem.intervention_memory import VerifiedInterventionEpisode  # noqa: E402
from src.probemem.intervention_memory_gate import CoverageAwareInterventionMemory  # noqa: E402
from src.probemem.intervention_utility import (  # noqa: E402
    INTERVENTION_APPLICABILITY_FEATURES,
    InterventionApplicabilitySignature,
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("contradiction audit requires at least one row")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def implicit_prediction_resonance(observed_status: str) -> str:
    """Compare a retrieved ACCEPTED precedent with a fresh observed status."""

    if observed_status == "ACCEPTED":
        return "SUPPORTED"
    if observed_status == "INCONCLUSIVE":
        return "UNRESOLVED"
    if observed_status == "REJECTED":
        return "CONTRADICTED"
    raise ValueError(f"unsupported verification status: {observed_status}")


def standardized_feature_contributions(
    query: InterventionApplicabilitySignature,
    reference: InterventionApplicabilitySignature,
    scales: Sequence[float],
) -> list[tuple[str, float]]:
    """Return normalized squared contributions to the registered RMS distance."""

    if len(scales) != len(INTERVENTION_APPLICABILITY_FEATURES):
        raise ValueError("feature scales do not match the registered schema")
    squared = []
    for name, left, right, scale in zip(
        INTERVENTION_APPLICABILITY_FEATURES,
        query.values,
        reference.values,
        scales,
    ):
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("feature scales must be finite and positive")
        squared.append((name, ((left - right) / scale) ** 2))
    total = sum(value for _, value in squared)
    if total <= 0:
        return [(name, 0.0) for name, _ in squared]
    return sorted(
        ((name, value / total) for name, value in squared),
        key=lambda item: (-item[1], item[0]),
    )


def _status_by_episode(
    candidate_rows: Iterable[Mapping[str, str]],
) -> dict[int, dict[str, str]]:
    output: dict[int, dict[str, str]] = {}
    for row in candidate_rows:
        output.setdefault(int(row["episode_id"]), {})[row["candidate_id"]] = row[
            "verification_status"
        ]
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT
        / "outputs/probemem_v2/runs"
        / "probemem_paired_utility_20260731T184353Z_cca94dad8cbe",
    )
    parser.add_argument(
        "--memory-results",
        type=Path,
        default=ROOT / "outputs/probemem_v2/coverage_aware_memory_results.csv",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=ROOT
        / "outputs/probemem_v2/verified_selected_intervention_episodes.jsonl",
    )
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "outputs/probemem_v2"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "reports/probemem_v2_memory_contradiction_audit.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
        records = [
            VerifiedInterventionEpisode.from_dict(row)
            for row in _read_jsonl(args.snapshot.resolve())
        ]
        memory_config = config["memory_applicability"]
        memory = CoverageAwareInterventionMemory(
            records,
            neighbor_count=int(memory_config["neighbor_count"]),
            coverage_quantile=float(memory_config["coverage_quantile"]),
            reserved_verification_steps=int(
                memory_config["reserved_verification_steps"]
            ),
            development_protocol_authorized=True,
        )
        by_record = {record.record_id: record for record in records}
        evidence = {
            int(row["episode_id"]): row
            for row in _read_jsonl(run_dir / "agent_evidence.jsonl")
            if bool(row["decision_required"])
        }
        statuses = _status_by_episode(_read_csv(run_dir / "candidate_results.csv"))
        memory_rows = _read_csv(args.memory_results.resolve())

        audit_rows: list[dict[str, Any]] = []
        for row in memory_rows:
            episode_id = int(row["episode_id"])
            query = _signature(evidence[episode_id])
            record_ids = [item for item in row["retrieved_record_ids"].split("|") if item]
            neighbors = [by_record[item] for item in record_ids]
            neighbor_distances = [
                memory._distance(query, item.applicability_signature)  # noqa: SLF001
                for item in neighbors
            ]
            skill_counts = Counter(item.selected_skill.value for item in neighbors)
            nearest = neighbors[0]
            contributions = standardized_feature_contributions(
                query, nearest.applicability_signature, memory.scales
            )
            used = row["memory_action"] == "USE_VERIFIED_EPISODE"
            selected_skill = row["selected_skill"] or None
            observed_status = row["selected_verification_status"] or None
            audit_rows.append(
                {
                    "experiment_run_id": manifest["experiment_run_id"],
                    "manifest_id": manifest["manifest_id"],
                    "episode_id": episode_id,
                    "seed": int(row["seed"]),
                    "memory_action": row["memory_action"],
                    "memory_reason": row["memory_reason"],
                    "nearest_distance": float(row["nearest_distance"]),
                    "coverage_radius": memory.coverage_radius,
                    "radius_ratio": float(row["nearest_distance"])
                    / memory.coverage_radius,
                    "neighbor_record_ids": "|".join(record_ids),
                    "neighbor_skills": "|".join(
                        item.selected_skill.value for item in neighbors
                    ),
                    "neighbor_distances": "|".join(
                        f"{item:.9f}" for item in neighbor_distances
                    ),
                    "retry_neighbor_count": skill_counts.get(
                        "INDEPENDENT_STOCHASTIC_RETRY", 0
                    ),
                    "compensation_neighbor_count": skill_counts.get(
                        "BOUNDED_PLANAR_COMPENSATION", 0
                    ),
                    "nearest_top_feature": contributions[0][0],
                    "nearest_top_feature_share": contributions[0][1],
                    "nearest_second_feature": contributions[1][0],
                    "nearest_second_feature_share": contributions[1][1],
                    "implicit_prediction": "ACCEPTED" if used else "",
                    "selected_skill": selected_skill or "",
                    "fresh_observed_status": observed_status or "",
                    "prediction_resonance": (
                        implicit_prediction_resonance(observed_status)
                        if used and observed_status
                        else "NOT_EVALUATED"
                    ),
                    "outcome_partition_evaluator_only": row[
                        "outcome_partition_evaluator_only"
                    ],
                    "unguarded_nearest_skill_evaluator_only": row[
                        "unguarded_nearest_skill"
                    ],
                    "unguarded_nearest_status_evaluator_only": row[
                        "unguarded_nearest_status_evaluator_only"
                    ],
                }
            )

        use_rows = [row for row in audit_rows if row["implicit_prediction"]]
        abstain_rows = [row for row in audit_rows if not row["implicit_prediction"]]
        conflict_rows = [
            row
            for row in abstain_rows
            if row["memory_reason"] == "CONFLICTING_VERIFIED_EPISODES"
        ]
        conflict_partitions = Counter(
            row["outcome_partition_evaluator_only"] for row in conflict_rows
        )
        summary = {
            "audit_role": "post_hoc_evaluator_only_contradiction_audit",
            "actionable_memory": False,
            "principle_promotion_eligible": False,
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "operational_cases": len(audit_rows),
            "memory_use_count": len(use_rows),
            "implicit_prediction_definition": "retrieved accepted precedent predicts selected skill ACCEPTED",
            "resonance_counts": dict(
                Counter(row["prediction_resonance"] for row in use_rows)
            ),
            "conflict_abstain_count": len(conflict_rows),
            "conflict_outcome_partitions_evaluator_only": dict(conflict_partitions),
            "abstain_unguarded_nearest_accepted_count_evaluator_only": sum(
                row["unguarded_nearest_status_evaluator_only"] == "ACCEPTED"
                for row in abstain_rows
            ),
            "abstain_unguarded_nearest_not_accepted_count_evaluator_only": sum(
                row["unguarded_nearest_status_evaluator_only"] != "ACCEPTED"
                for row in abstain_rows
            ),
            "harmful_transfer_seeds": [
                row["seed"]
                for row in use_rows
                if row["prediction_resonance"] != "SUPPORTED"
            ],
            "api_calls": 0,
            "heldout_claim_eligible": False,
            "gate_or_threshold_modified": False,
        }
        output_root = args.output_root.resolve()
        _write_csv(output_root / "memory_contradiction_audit.csv", audit_rows)
        (output_root / "memory_contradiction_audit_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )

        harmful_lines = []
        for row in use_rows:
            harmful_lines.append(
                f"* Seed {row['seed']}: selected `{row['selected_skill']}`, "
                f"fresh outcome `{row['fresh_observed_status']}` "
                f"({row['prediction_resonance']}); radius ratio "
                f"{row['radius_ratio']:.3f}; dominant distance features "
                f"`{row['nearest_top_feature']}` ({row['nearest_top_feature_share']:.1%}) "
                f"and `{row['nearest_second_feature']}` "
                f"({row['nearest_second_feature_share']:.1%})."
            )
        report = [
            "# ProbeMem Memory Contradiction and Resonance Audit",
            "",
            "This is a post-hoc evaluator-only audit of the frozen development run. It does not alter retrieval, create actionable memory, or promote a principle.",
            "",
            "## Question",
            "",
            "Does accepted-only local precedent provide a stable prediction that the same intervention will be accepted on a nearby Agent-visible query?",
            "",
            "## Result",
            "",
            f"The gate used memory in {len(use_rows)}/{len(audit_rows)} operational cases. The implicit ACCEPTED prediction was supported in {summary['resonance_counts'].get('SUPPORTED', 0)}, unresolved in {summary['resonance_counts'].get('UNRESOLVED', 0)}, and contradicted in {summary['resonance_counts'].get('CONTRADICTED', 0)}.",
            f"It abstained on {len(conflict_rows)} local skill conflicts. Among all {len(abstain_rows)} abstentions, unguarded nearest retrieval would have been accepted in {summary['abstain_unguarded_nearest_accepted_count_evaluator_only']} and not accepted in {summary['abstain_unguarded_nearest_not_accepted_count_evaluator_only']} cases.",
            f"Conflict outcome partitions were `{dict(conflict_partitions)}`.",
            "",
            "## Harmful transfers",
            "",
            *harmful_lines,
            "",
            "## Interpretation",
            "",
            "The failures are not explained solely by crossing the frozen coverage boundary: both memory uses were inside coverage with unanimous local skill support. Local geometric agreement therefore did not imply repeatable intervention utility. The high conflict rate also shows that nearby accepted episodes frequently support different skills.",
            "",
            "This evidence blocks principle promotion. A future protocol must predict action-conditional outcomes and test resonance explicitly, or acquire evidence that is more causally informative about intervention response. Threshold retuning on this run is prohibited.",
        ]
        args.report.resolve().write_text("\n".join(report) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, TypeError, ValueError, ZeroDivisionError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
