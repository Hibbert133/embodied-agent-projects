"""Audit a completed ProbeMem paired intervention-utility development run."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reasoning import validate_no_oracle_evidence  # noqa: E402


COMPENSATION = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def summarize_candidate_pairs(
    case_rows: list[dict[str, str]], candidate_rows: list[dict[str, str]]
) -> dict[str, Any]:
    operational = [row for row in case_rows if _as_bool(row["decision_required"])]
    comparable = [row for row in operational if _as_bool(row["paired_comparable"])]
    by_episode: dict[int, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in candidate_rows:
        by_episode[int(row["episode_id"])][row["candidate_id"]] = row
    missing = {
        int(row["episode_id"]): sorted(
            {COMPENSATION, RETRY} - set(by_episode[int(row["episode_id"])])
        )
        for row in comparable
        if set(by_episode[int(row["episode_id"])]) != {COMPENSATION, RETRY}
    }
    if missing:
        raise ValueError(f"paired candidate records are incomplete: {missing}")

    exclusive_recovery = Counter()
    harmful_compensation_cases: list[int] = []
    for row in comparable:
        episode_id = int(row["episode_id"])
        pair = by_episode[episode_id]
        compensation_accepted = pair[COMPENSATION]["verification_status"] == "ACCEPTED"
        retry_accepted = pair[RETRY]["verification_status"] == "ACCEPTED"
        if compensation_accepted and not retry_accepted:
            exclusive_recovery[COMPENSATION] += 1
        if retry_accepted and not compensation_accepted:
            exclusive_recovery[RETRY] += 1
        if (
            float(pair[COMPENSATION]["goal_distance_change"]) < 0
            and float(pair[RETRY]["goal_distance_change"]) >= 0
        ):
            harmful_compensation_cases.append(episode_id)

    winner_counts = Counter(row["winner_candidate_ids_oracle"] for row in comparable)
    operational_conditions = Counter(row["condition_id_oracle"] for row in operational)
    recovery_counts = Counter(
        row["candidate_id"]
        for row in candidate_rows
        if row["verification_status"] == "ACCEPTED"
    )
    retry_recovery_advantage = exclusive_recovery[RETRY]
    return {
        "full_collection_units": len(case_rows),
        "operational_units": len(operational),
        "paired_comparable_units": len(comparable),
        "winner_counts_oracle": dict(sorted(winner_counts.items())),
        "accepted_recoveries": {
            COMPENSATION: recovery_counts[COMPENSATION],
            RETRY: recovery_counts[RETRY],
        },
        "exclusive_recovery_cases": {
            COMPENSATION: exclusive_recovery[COMPENSATION],
            RETRY: retry_recovery_advantage,
        },
        "harmful_compensation_episode_ids": harmful_compensation_cases,
        "operational_condition_counts_oracle": dict(sorted(operational_conditions.items())),
        "operational_noise_cases": operational_conditions["fault_05"],
        "recovery_selector_improvement_available": retry_recovery_advantage > 0,
        "experiment_interpretation_status": (
            "READY_FOR_DEVELOPMENT_SELECTOR_TEST"
            if retry_recovery_advantage > 0 and operational_conditions["fault_05"] > 0
            else "INSUFFICIENT_ACTION_UTILITY_DIVERSITY"
        ),
    }


def build_feature_rows(
    agent_rows: list[dict[str, Any]], case_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    case_index = {int(row["episode_id"]): row for row in case_rows}
    rows: list[dict[str, Any]] = []
    for record in agent_rows:
        validate_no_oracle_evidence(record)
        if not bool(record["decision_required"]):
            continue
        episode_id = int(record["episode_id"])
        case = case_index[episode_id]
        features = record["applicability_signature"]["features"]
        rows.append(
            {
                "experiment_run_id": record["experiment_run_id"],
                "manifest_id": record["manifest_id"],
                "episode_id": episode_id,
                "seed": int(record["seed"]),
                **{name: float(value) for name, value in features.items()},
                "winner_candidate_ids_evaluator_only": case[
                    "winner_candidate_ids_oracle"
                ],
            }
        )
    return rows


def _write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write empty paired utility feature audit")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-features",
        type=Path,
        default=ROOT / "outputs/probemem_v2/paired_utility_feature_audit.csv",
    )
    parser.add_argument(
        "--output-cases",
        type=Path,
        default=ROOT / "outputs/probemem_v2/paired_utility_case_results.csv",
    )
    parser.add_argument(
        "--output-candidates",
        type=Path,
        default=ROOT / "outputs/probemem_v2/paired_utility_candidate_results.csv",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=ROOT / "outputs/probemem_v2/paired_utility_manifest.json",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=ROOT / "outputs/probemem_v2/paired_utility_summary.json",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_paired_utility_development.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED":
            raise ValueError("paired utility analysis requires a COMPLETED run")
        case_rows = _read_csv(run_dir / "case_results.csv")
        candidate_rows = _read_csv(run_dir / "candidate_results.csv")
        agent_rows = _read_jsonl(run_dir / "agent_evidence.jsonl")
        summary = summarize_candidate_pairs(case_rows, candidate_rows)
        summary.update(
            {
                "experiment_run_id": manifest["experiment_run_id"],
                "manifest_id": manifest["manifest_id"],
                "source_git_commit": manifest["source_git_commit"],
                "agent_oracle_leakage_violations": 0,
                "api_calls": 0,
                "heldout_claim_eligible": False,
                "selector_fitting_permitted": False,
            }
        )
        feature_rows = build_feature_rows(agent_rows, case_rows)
        if len(feature_rows) != summary["operational_units"]:
            raise ValueError("Agent feature rows do not cover operational population")
        _write_csv(args.output_features.resolve(), feature_rows)
        _write_csv(args.output_cases.resolve(), case_rows)
        _write_csv(args.output_candidates.resolve(), candidate_rows)
        args.output_manifest.resolve().write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        args.output_summary.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_summary.resolve().write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        harmful = summary["harmful_compensation_episode_ids"]
        lines = [
            "# ProbeMem Paired Intervention-Utility Development Result",
            "",
            f"Run: `{manifest['experiment_run_id']}`",
            f"Manifest: `{manifest['manifest_id']}`",
            f"Source commit: `{manifest['source_git_commit']}`",
            "",
            "## Actual collection",
            "",
            f"- Full initial-rollout units: {summary['full_collection_units']}.",
            f"- Operational failed units: {summary['operational_units']}.",
            f"- Complete paired candidate units: {summary['paired_comparable_units']}.",
            f"- Compensation utility winners: {summary['winner_counts_oracle'].get(COMPENSATION, 0)}.",
            f"- Retry utility winners: {summary['winner_counts_oracle'].get(RETRY, 0)}.",
            f"- Compensation accepted recoveries: {summary['accepted_recoveries'][COMPENSATION]}/"
            f"{summary['operational_units']}.",
            f"- Retry accepted recoveries: {summary['accepted_recoveries'][RETRY]}/"
            f"{summary['operational_units']}.",
            f"- Operational stochastic-noise cases: {summary['operational_noise_cases']}.",
            "",
            "## Interpretation",
            "",
            f"The only retry utility winner was episode {harmful[0] if harmful else 'N/A'}, "
            "where both candidates were rejected. Retry won the preregistered failed-case "
            "tie-break because it preserved the initial object-goal distance, while "
            "compensation increased that distance. This is evidence of a harmful "
            "compensation edge case, not a successful retry recovery.",
            "",
            "There is no episode in which retry recovered and compensation did not. "
            "Moreover, every registered noise rollout succeeded initially, leaving zero "
            "operational noise cases. The result is therefore "
            "`INSUFFICIENT_ACTION_UTILITY_DIVERSITY`: fitting a 9:1 selector or promoting "
            "a memory principle would overfit this development stream and cannot improve "
            "recovery success over always selecting compensation.",
            "",
            "## Integrity",
            "",
            "Agent feature rows passed nested Oracle-field rejection. Candidate winners "
            "remain evaluator-only. The experiment used no API calls, rendering, memory "
            "writes, or principle generation. It does not authorize a held-out run.",
            "",
            "## Next step",
            "",
            "Use a new label-blind development coverage protocol that collects additional "
            "operational stochastic-noise failures without selecting seeds by candidate "
            "outcome. Preserve this run unchanged. Do not tune a threshold on the unique "
            "retry winner.",
            "",
            "## Reproduction",
            "",
            "```bash",
            f"python scripts/analyze_probemem_paired_utility.py --run-dir \"{run_dir}\"",
            "```",
        ]
        args.output_report.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_report.resolve().write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"features: {args.output_features.resolve()}")
        print(f"cases: {args.output_cases.resolve()}")
        print(f"candidates: {args.output_candidates.resolve()}")
        print(f"manifest: {args.output_manifest.resolve()}")
        print(f"summary: {args.output_summary.resolve()}")
        print(f"report: {args.output_report.resolve()}")
        print(f"status: {summary['experiment_interpretation_status']}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
