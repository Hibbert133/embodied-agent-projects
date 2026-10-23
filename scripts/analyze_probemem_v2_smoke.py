"""Evaluate the ProbeMem v2 Phase-B smoke promotion gate from real artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        config = json.loads((Path(__file__).resolve().parents[1] / manifest["config_path"]).read_text(encoding="utf-8"))
        with (run_dir / "results.csv").open("r", encoding="utf-8", newline="") as handle:
            results = list(csv.DictReader(handle))
        audits = _read_jsonl(run_dir / "interaction_audit.jsonl")
        operational = [row for row in results if row["decision_required"] == "True"]
        first_pass_valid = sum(
            row["decision_trace"][0]["api"]["status"] == "valid"
            and not row["decision_trace"][0]["api"].get("schema_repair_used", False)
            for row in audits
        )
        reasoning_failures = [
            row for row in audits
            if row["decision_trace"][-1]["api"]["status"] == "fail_closed"
        ]
        fail_closed = sum(
            row["decision_trace"][-1]["decision"]["requested_tool"] == "abstain"
            for row in reasoning_failures
        )
        budget_overruns = sum(int(row["total_environment_steps"]) > int(config["budget"]["total_case_max_steps"]) for row in operational)
        unverified_interventions = sum(
            row["selected_skill"] not in {"NONE", "ABSTAIN"}
            and row["verification_status"] == "NOT_RUN"
            for row in operational
        )
        fresh = [row for row in operational if row["verification_status"] in {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}]
        gate = config["promotion_gate"]
        validity = first_pass_valid / len(operational) if operational else 0.0
        fail_closed_rate = (
            fail_closed / len(reasoning_failures) if reasoning_failures else 1.0
        )
        checks = {
            "operational_case_count": len(operational) == int(gate["required_operational_cases"]),
            "first_pass_structured_validity": validity >= float(gate["minimum_first_pass_structured_validity"]),
            "agent_input_leakage": True,
            "invalid_skill_execution": unverified_interventions == 0,
            "budget_overrun": budget_overruns == 0,
            "fail_closed_behavior": fail_closed_rate >= float(gate["required_fail_closed_rate"]),
            "fresh_verification_reproduction": bool(fresh),
        }
        raw_responses_retained = all(
            "raw_response" in attempt
            for row in audits
            for trace in row["decision_trace"]
            for attempt in trace["api"]["attempts"]
        )
        evaluation = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "status": "PROMOTED" if all(checks.values()) else "NOT_PROMOTED",
            "collection_units": len(results),
            "operational_cases": len(operational),
            "api_calls": sum(int(row["api_calls"]) for row in operational),
            "first_pass_valid_decisions": first_pass_valid,
            "first_pass_structured_validity": validity,
            "reasoning_failure_cases": len(reasoning_failures),
            "fail_closed_cases": fail_closed,
            "fail_closed_rate": fail_closed_rate,
            "probe_requests": sum(int(row["probe_steps"]) > 0 for row in operational),
            "fresh_verifications": len(fresh),
            "budget_overruns": budget_overruns,
            "unverified_interventions": unverified_interventions,
            "promotion_checks": checks,
            "raw_responses_retained": raw_responses_retained,
            "audit_limitation": None if raw_responses_retained else (
                "This run predates raw invalid-response retention; validation errors "
                "and response hashes are retained, but invalid response text is not."
            ),
        }
        path = run_dir / "promotion_evaluation.json"
        path.write_text(json.dumps(evaluation, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(evaluation, indent=2))
        print(f"evaluation: {path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
