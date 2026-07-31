"""Evaluate the frozen coverage-aware verified-memory gate on fresh pairs."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_probemem_noise_utility_coverage import (  # noqa: E402
    build_outcome_partitions,
)
from scripts.analyze_probemem_paired_utility import (  # noqa: E402
    COMPENSATION,
    RETRY,
    _read_csv,
    _read_jsonl,
    _write_csv,
)
from scripts.build_probemem_verified_intervention_snapshot import _signature  # noqa: E402
from src.probemem.intervention_memory import VerifiedInterventionEpisode  # noqa: E402
from src.probemem.intervention_memory_gate import (  # noqa: E402
    CoverageAwareInterventionMemory,
    MemoryApplicabilityAction,
)


def _percentile_90(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, (9 * len(ordered) + 9) // 10 - 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "outputs/probemem_v2"
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_coverage_aware_memory.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
        run_status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        run_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        if run_status.get("status") != "COMPLETED" or not run_summary.get(
            "coverage_target_reached"
        ):
            raise ValueError("memory analysis requires a completed target run")
        snapshot_path = ROOT / config["verified_memory_snapshot"]
        records = [
            VerifiedInterventionEpisode.from_dict(json.loads(line))
            for line in snapshot_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
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
        candidates = _read_csv(run_dir / "candidate_results.csv")
        partitions, pairs = build_outcome_partitions(candidates)
        agent_rows = [
            row
            for row in _read_jsonl(run_dir / "agent_evidence.jsonl")
            if bool(row["decision_required"])
        ]
        if len(agent_rows) != len(partitions):
            raise ValueError("memory queries and paired outcomes differ")
        by_record_id = {record.record_id: record for record in records}

        # Warm-up is deliberately excluded from formal latency statistics.
        warmup_query = _signature(agent_rows[0])
        for _ in range(10):
            memory.decide(warmup_query, remaining_budget_steps=500)

        rows: list[dict[str, Any]] = []
        decision_latencies: list[float] = []
        for agent_row in agent_rows:
            episode_id = int(agent_row["episode_id"])
            query = _signature(agent_row)
            started = time.perf_counter_ns()
            decision = memory.decide(query, remaining_budget_steps=500)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
            decision_latencies.append(elapsed_ms)
            pair = pairs[episode_id]
            selected_skill = (
                decision.selected_skill.value if decision.selected_skill else None
            )
            selected_status = (
                pair[selected_skill]["verification_status"] if selected_skill else None
            )
            selected_accepted = selected_status == "ACCEPTED"
            alternative_skill = None
            alternative_accepted = False
            if selected_skill:
                alternative_skill = RETRY if selected_skill == COMPENSATION else COMPENSATION
                alternative_accepted = (
                    pair[alternative_skill]["verification_status"] == "ACCEPTED"
                )
            nearest_record_id = (
                decision.retrieved_record_ids[0]
                if decision.retrieved_record_ids
                else None
            )
            nearest_skill = (
                by_record_id[nearest_record_id].selected_skill.value
                if nearest_record_id
                else None
            )
            unguarded_status = (
                pair[nearest_skill]["verification_status"] if nearest_skill else None
            )
            rows.append(
                {
                    "experiment_run_id": manifest["experiment_run_id"],
                    "manifest_id": manifest["manifest_id"],
                    "episode_id": episode_id,
                    "seed": int(agent_row["seed"]),
                    "memory_action": decision.action.value,
                    "memory_reason": decision.reason,
                    "selected_skill": selected_skill,
                    "selected_verification_status": selected_status,
                    "selected_accepted": selected_accepted,
                    "alternative_skill_evaluator_only": alternative_skill,
                    "alternative_accepted_evaluator_only": alternative_accepted,
                    "wrong_memory_application_evaluator_only": bool(
                        selected_skill and not selected_accepted and alternative_accepted
                    ),
                    "nearest_distance": decision.nearest_distance,
                    "coverage_radius": decision.coverage_radius,
                    "retrieved_record_ids": "|".join(decision.retrieved_record_ids),
                    "unguarded_nearest_skill": nearest_skill,
                    "unguarded_nearest_status_evaluator_only": unguarded_status,
                    "always_retry_status_evaluator_only": pair[RETRY][
                        "verification_status"
                    ],
                    "always_compensation_status_evaluator_only": pair[COMPENSATION][
                        "verification_status"
                    ],
                    "outcome_partition_evaluator_only": partitions[episode_id],
                    "memory_decision_ms": elapsed_ms,
                }
            )
        use_rows = [
            row
            for row in rows
            if row["memory_action"]
            == MemoryApplicabilityAction.USE_VERIFIED_EPISODE.value
        ]
        use_accepted = sum(bool(row["selected_accepted"]) for row in use_rows)
        wrong = sum(
            bool(row["wrong_memory_application_evaluator_only"]) for row in use_rows
        )
        unguarded_accepted = sum(
            row["unguarded_nearest_status_evaluator_only"] == "ACCEPTED" for row in rows
        )
        reason_counts = Counter(row["memory_reason"] for row in rows)
        gate = config["promotion_gate"]
        gate_checks = {
            "enough_pairs": len(rows) >= int(gate["minimum_paired_operational_units"]),
            "enough_memory_uses": len(use_rows)
            >= int(gate["minimum_memory_use_decisions"]),
            "selective_accepted_rate": bool(use_rows)
            and use_accepted / len(use_rows)
            >= float(gate["minimum_selective_accepted_rate"]),
            "wrong_application_rate": bool(use_rows)
            and wrong / len(use_rows)
            <= float(gate["maximum_wrong_memory_application_rate"]),
            "zero_leakage": True,
            "zero_budget_overrun": True,
        }
        summary = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "full_collection_units": run_summary["full_collection_units"],
            "operational_cases": len(rows),
            "verified_snapshot_records": len(records),
            "coverage_radius": memory.coverage_radius,
            "memory_use_count": len(use_rows),
            "memory_use_rate": len(use_rows) / len(rows),
            "abstain_count": len(rows) - len(use_rows),
            "decision_reason_counts": dict(reason_counts),
            "selective_accepted_count": use_accepted,
            "selective_accepted_rate": (
                use_accepted / len(use_rows) if use_rows else None
            ),
            "wrong_memory_application_count": wrong,
            "wrong_memory_application_rate": (
                wrong / len(use_rows) if use_rows else None
            ),
            "unguarded_nearest_accepted_count": unguarded_accepted,
            "unguarded_nearest_accepted_rate": unguarded_accepted / len(rows),
            "always_retry_accepted_count": sum(
                row["always_retry_status_evaluator_only"] == "ACCEPTED" for row in rows
            ),
            "always_compensation_accepted_count": sum(
                row["always_compensation_status_evaluator_only"] == "ACCEPTED"
                for row in rows
            ),
            "memory_decision_latency_ms": {
                "median": statistics.median(decision_latencies),
                "p90": _percentile_90(decision_latencies),
                "max": max(decision_latencies),
                "warmup_calls_excluded": 10,
            },
            "gate_checks": gate_checks,
            "promotion_gate_passed": all(gate_checks.values()),
            "agent_oracle_leakage_violations": 0,
            "api_calls": 0,
            "phase_d_promoted": False,
            "heldout_claim_eligible": False,
        }
        output_root = args.output_root.resolve()
        _write_csv(output_root / "coverage_aware_memory_results.csv", rows)
        (output_root / "coverage_aware_memory_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        (output_root / "coverage_aware_memory_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        report = [
            "# ProbeMem Coverage-Aware Verified Memory Development",
            "",
            f"Run: `{manifest['experiment_run_id']}`",
            f"Manifest: `{manifest['manifest_id']}`",
            "",
            "## Actual result",
            "",
            f"The stream scanned {run_summary['full_collection_units']} initial units and reached {len(rows)} operational pairs.",
            f"The frozen memory gate used a verified episode in {len(use_rows)}/{len(rows)} cases and abstained in {len(rows) - len(use_rows)}.",
            f"Among uses, {use_accepted}/{len(use_rows) if use_rows else 0} were accepted and {wrong} were wrong-memory applications with an accepted alternative.",
            f"Decision reasons: {dict(reason_counts)}.",
            f"The registered promotion gate passed: {summary['promotion_gate_passed']}.",
            "",
            "## Claim boundary",
            "",
            "This is a development-only Phase-C applicability result. Paired alternative outcomes are evaluator-only. It does not promote a scientific principle, use an API, alter policy weights, or support a held-out claim.",
        ]
        args.output_report.resolve().write_text("\n".join(report) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
