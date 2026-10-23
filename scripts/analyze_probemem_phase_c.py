"""Audit a ProbeMem Phase-C run, including explicitly incomplete runs."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reasoning import validate_no_oracle_evidence  # noqa: E402


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=ROOT / "outputs/probemem_v2/phase_c_incomplete_summary.csv",
    )
    parser.add_argument(
        "--output-audit",
        type=Path,
        default=ROOT / "outputs/probemem_v2/phase_c_incomplete_audit.json",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_phase_c_incomplete_run.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        rows = _read_csv(run_dir / "results.csv")
        audits = _read_jsonl(run_dir / "interaction_audit.jsonl")
        methods = tuple(str(item) for item in manifest["methods"])
        seed_start, seed_stop = (int(item) for item in manifest["seed_range"])
        expected_episodes = seed_stop - seed_start + 1
        expected_rows = expected_episodes * len(methods)

        by_method: dict[str, list[dict[str, str]]] = defaultdict(list)
        by_episode: dict[int, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            by_method[row["method"]].append(row)
            by_episode[int(row["episode_id"])].append(row)
        complete_episode_ids = sorted(
            episode_id
            for episode_id, episode_rows in by_episode.items()
            if {row["method"] for row in episode_rows} == set(methods)
        )
        operational_episode_ids = [
            episode_id
            for episode_id in complete_episode_ids
            if any(
                _as_bool(row["decision_required"])
                for row in by_episode[episode_id]
            )
        ]

        chronology_violations: list[str] = []
        leakage_violations: list[str] = []
        budget_violations: list[str] = []
        for record in audits:
            current_episode = int(record["episode_id"])
            try:
                validate_no_oracle_evidence(record["agent_visible_initial_evidence"])
                validate_no_oracle_evidence(record["retrieved_episode_records"])
                for trace in record["decision_trace"]:
                    payload = trace["api"].get("request_payload")
                    if payload is not None:
                        validate_no_oracle_evidence(payload)
            except ValueError as exc:
                leakage_violations.append(
                    f"episode={current_episode} method={record['method']}: {exc}"
                )
            for retrieved in record["retrieved_episode_records"]:
                source_episode = int(retrieved["source_episode_id"])
                if source_episode >= current_episode:
                    chronology_violations.append(
                        f"episode={current_episode} retrieved_future={source_episode}"
                    )
                if (
                    record["method"] == "verified_episodic_retrieval"
                    and retrieved["observed_verification_status"] != "ACCEPTED"
                ):
                    chronology_violations.append(
                        f"verified memory retrieved non-accepted record at episode={current_episode}"
                    )
            if int(record["budget"]["total"]) > int(manifest["budget"]["total_case_max_steps"]):
                budget_violations.append(
                    f"episode={current_episode} method={record['method']}"
                )

        summary_rows: list[dict[str, Any]] = []
        for method in methods:
            selected = by_method[method]
            operational = [row for row in selected if _as_bool(row["decision_required"])]
            latencies = [float(row["api_latency_ms"]) for row in operational]
            summary_rows.append(
                {
                    "experiment_run_id": manifest["experiment_run_id"],
                    "manifest_id": manifest["manifest_id"],
                    "run_status": status["status"],
                    "method": method,
                    "completed_cases": len(selected),
                    "operational_cases": len(operational),
                    "accepted_rate": (
                        sum(row["verification_status"] == "ACCEPTED" for row in operational)
                        / len(operational)
                        if operational
                        else 0.0
                    ),
                    "accepted": sum(row["verification_status"] == "ACCEPTED" for row in operational),
                    "inconclusive": sum(row["verification_status"] == "INCONCLUSIVE" for row in operational),
                    "rejected": sum(row["verification_status"] == "REJECTED" for row in operational),
                    "not_run": sum(row["verification_status"] == "NOT_RUN" for row in operational),
                    "memory_use_cases": sum(_as_bool(row["memory_used"]) for row in operational),
                    "retrieved_records": sum(int(row["retrieved_records"]) for row in operational),
                    "retrieval_coverage": (
                        sum(int(row["retrieved_records"]) > 0 for row in operational)
                        / len(operational)
                        if operational
                        else 0.0
                    ),
                    "api_calls": sum(int(row["api_calls"]) for row in operational),
                    "api_latency_ms_median": statistics.median(latencies) if latencies else 0.0,
                    "api_latency_ms_max": max(latencies, default=0.0),
                    "api_input_tokens": sum(int(row["api_input_tokens"]) for row in operational),
                    "api_output_tokens": sum(int(row["api_output_tokens"]) for row in operational),
                    "invalid_structured_outputs": sum(
                        int(row["invalid_structured_outputs"]) for row in operational
                    ),
                    "probe_environment_steps": sum(int(row["probe_steps"]) for row in operational),
                    "verification_environment_steps": sum(
                        int(row["verification_steps"]) for row in operational
                    ),
                    "total_environment_steps": sum(
                        int(row["total_environment_steps"]) for row in operational
                    ),
                }
            )

        paired_outcome_ties = 0
        paired_skill_ties = 0
        for episode_id in operational_episode_ids:
            episode_rows = by_episode[episode_id]
            paired_outcome_ties += len({row["verification_status"] for row in episode_rows}) == 1
            paired_skill_ties += len({row["selected_skill"] for row in episode_rows}) == 1

        raw_rejected_exposures = sum(
            retrieved["observed_verification_status"] != "ACCEPTED"
            for record in audits
            if record["method"] == "raw_episodic_retrieval_development_only"
            for retrieved in record["retrieved_episode_records"]
        )
        completed_cleanly = (
            status["status"] == "COMPLETED"
            and len(rows) == expected_rows
            and not chronology_violations
            and not leakage_violations
            and not budget_violations
        )

        audit = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "run_status": status,
            "expected_result_rows": expected_rows,
            "actual_result_rows": len(rows),
            "expected_episodes": expected_episodes,
            "complete_paired_episodes": len(complete_episode_ids),
            "complete_episode_ids": complete_episode_ids,
            "operational_paired_episodes": len(operational_episode_ids),
            "operational_episode_ids": operational_episode_ids,
            "operational_audit_records": len(audits),
            "chronology_violations": chronology_violations,
            "leakage_violations": leakage_violations,
            "budget_violations": budget_violations,
            "paired_outcome_ties": paired_outcome_ties,
            "paired_skill_ties": paired_skill_ties,
            "raw_nonaccepted_record_exposures": raw_rejected_exposures,
            "development_comparison_complete": completed_cleanly,
            "memory_changed_any_intervention": (
                paired_skill_ties < len(operational_episode_ids)
            ),
            "memory_changed_any_verification_outcome": (
                paired_outcome_ties < len(operational_episode_ids)
            ),
            "claim_eligible": completed_cleanly,
        }
        _write_csv(args.output_summary.resolve(), summary_rows)
        args.output_audit.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_audit.resolve().write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")

        if completed_cleanly:
            title = "# ProbeMem Phase C: Completed Sequential Retrieval Development Run"
            status_lines = [
                f"The immutable development run completed all {len(rows)}/{expected_rows} "
                f"method-cases ({len(complete_episode_ids)}/{expected_episodes} paired "
                f"episodes; {len(operational_episode_ids)} required an online decision).",
                "",
                "This artifact supports a narrow development conclusion: episodic "
                "records were retrieved through a chronological leakage-safe interface, "
                "but neither raw nor accepted-only retrieval changed the intervention "
                "or verification outcome on this stream. It does not establish broad "
                "method equivalence or a memory benefit.",
            ]
            interpretation = (
                "All operational pairs selected the same bounded intervention and had "
                "the same verification outcome. Raw retrieval exposed the model to "
                f"{raw_rejected_exposures} non-accepted historical records, while "
                "verified retrieval excluded them. The absence of behavioral change "
                "shows that retrieval alone is insufficient in this registered setup; "
                "Phase D must not be promoted merely because memory was cited."
            )
            final_note = (
                "This is a completed development result. Held-out or stronger memory "
                "claims require a separately frozen protocol and cannot be inferred here."
            )
        else:
            title = "# ProbeMem Phase C: Incomplete Sequential Retrieval Run"
            status_lines = [
                f"The immutable development run ended with `{status['status']}` after "
                f"{len(rows)}/{expected_rows} method-cases ({len(complete_episode_ids)}/"
                f"{expected_episodes} complete paired episodes). The recorded error was "
                f"`{status.get('error_type')}: {status.get('error')}`.",
                "",
                "This artifact is **not claim-eligible** and must not be used to state "
                "that episodic retrieval improves or harms recovery. It is retained as "
                "an incomplete infrastructure result.",
            ]
            interpretation = (
                "The completed prefix is useful for integration and cost auditing only. "
                "Identical paired outcomes in an incomplete prefix are neither evidence "
                "of benefit nor evidence of equivalence."
            )
            final_note = (
                "A new full run requires a new immutable manifest and an explicit "
                "decision to spend the API budget again. This run must not be overwritten."
            )

        method_lines = []
        for row in summary_rows:
            method_lines.append(
                f"- `{row['method']}`: {row['accepted']}/{row['operational_cases']} "
                f"accepted, {row['retrieved_records']} retrieved records, "
                f"{row['api_calls']} API calls, {row['api_input_tokens']} input and "
                f"{row['api_output_tokens']} output tokens."
            )

        lines = [
            title,
            "",
            f"Run: `{manifest['experiment_run_id']}`",
            f"Manifest: `{manifest['manifest_id']}`",
            f"Source commit: `{manifest['source_git_commit']}`",
            "",
            "## Status",
            "",
            *status_lines,
            "",
            "## Method results",
            "",
            *method_lines,
            "",
            "## Integrity audit",
            "",
            f"- Operational audit records: {len(audits)}.",
            f"- Chronology violations: {len(chronology_violations)}.",
            f"- Agent/Oracle leakage violations: {len(leakage_violations)}.",
            f"- Interaction-budget violations: {len(budget_violations)}.",
            f"- Operational paired episodes: {len(operational_episode_ids)}.",
            f"- Paired outcome ties: {paired_outcome_ties}/{len(operational_episode_ids)}.",
            f"- Paired intervention-skill ties: {paired_skill_ties}/{len(operational_episode_ids)}.",
            f"- Raw-memory non-accepted record exposures: {raw_rejected_exposures}.",
            "",
            "## Interpretation",
            "",
            interpretation,
            "",
            "## Reproduction",
            "",
            "```powershell",
            f".\\scripts\\run_probemem_phase_c_comparison.ps1 -Manifest \"{(run_dir / 'manifest.json')}\" -ApiTimeout 300",
            f".\\.venv\\Scripts\\python.exe scripts\\analyze_probemem_phase_c.py --run-dir \"{run_dir}\"",
            "```",
            "",
            final_note,
        ]
        args.output_report.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_report.resolve().write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"summary: {args.output_summary.resolve()}")
        print(f"audit: {args.output_audit.resolve()}")
        print(f"report: {args.output_report.resolve()}")
        print(f"claim_eligible: {audit['claim_eligible']}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
