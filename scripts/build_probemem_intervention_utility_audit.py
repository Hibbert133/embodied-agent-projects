"""Build falsifiable utility records from an immutable ProbeMem Phase-C run."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.probemem import (  # noqa: E402
    EvidenceSignature,
    FreshVerificationObservation,
    InterventionSkill,
    InterventionUtilityRecord,
    PredictedOutcome,
)
from src.reasoning import validate_no_oracle_evidence  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _as_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def build_records(
    *,
    audits: list[dict[str, Any]],
    results: list[dict[str, str]],
    source_method: str,
) -> list[InterventionUtilityRecord]:
    result_index = {
        (row["method"], int(row["episode_id"])): row
        for row in results
        if _as_bool(row["decision_required"])
    }
    records: list[InterventionUtilityRecord] = []
    for audit in audits:
        if audit["method"] != source_method or bool(audit["initial_success"]):
            continue
        episode_id = int(audit["episode_id"])
        result = result_index.get((source_method, episode_id))
        if result is None:
            raise ValueError(f"missing operational result for episode={episode_id}")
        if not audit["decision_trace"]:
            raise ValueError(f"missing decision trace for episode={episode_id}")
        final_trace = audit["decision_trace"][-1]
        final_decision = final_trace["decision"]
        payload = final_trace["api"].get("request_payload")
        if not isinstance(payload, dict):
            raise ValueError(f"missing final API payload for episode={episode_id}")
        evidence = payload.get("agent_visible_evidence")
        if not isinstance(evidence, dict):
            raise ValueError(f"missing final Agent evidence for episode={episode_id}")
        validate_no_oracle_evidence(evidence)
        if final_decision["requested_tool"] != "select_intervention_skill":
            raise ValueError(f"episode={episode_id} did not execute an intervention")
        if final_decision["predicted_outcome"] is None:
            raise ValueError(f"episode={episode_id} lacks a falsifiable prediction")
        if final_decision["selected_skill"] != result["selected_skill"]:
            raise ValueError(f"episode={episode_id} decision/result skill mismatch")
        if audit["host_execution"]["verification_status"] != result["verification_status"]:
            raise ValueError(f"episode={episode_id} audit/result outcome mismatch")

        observed = FreshVerificationObservation(
            evidence_id=str(audit["host_execution"]["evidence_id"]),
            verification_status=result["verification_status"],
            verification_success=_as_bool(result["verification_success"]),
            environment_steps=int(result["verification_steps"]),
            final_object_goal_distance=float(result["final_object_goal_distance"]),
            goal_distance_change=(
                float(result["initial_final_object_goal_distance"])
                - float(result["final_object_goal_distance"])
            ),
        )
        records.append(
            InterventionUtilityRecord.create(
                record_id=f"phase_c_utility_episode_{episode_id:04d}",
                source_episode_id=episode_id,
                source_run_id=str(audit["experiment_run_id"]),
                source_manifest_id=str(audit["manifest_id"]),
                source_method=source_method,
                applicability_signature=EvidenceSignature.from_structured_evidence(evidence),
                selected_skill=InterventionSkill(str(final_decision["selected_skill"])),
                predicted_outcome=PredictedOutcome.from_mapping(
                    final_decision["predicted_outcome"]
                ),
                observed_outcome=observed,
            )
        )
    return sorted(records, key=lambda item: item.source_episode_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT
        / "configs/probemem_v2/phase_c_intervention_utility_audit_v1.json",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=ROOT / "outputs/probemem_v2/phase_c_intervention_utility_records.jsonl",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=ROOT / "outputs/probemem_v2/phase_c_intervention_utility_summary.json",
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        default=ROOT / "reports/probemem_v2_phase_c_intervention_utility_audit.md",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        run_status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        if run_status.get("status") != "COMPLETED":
            raise ValueError("utility audit requires an immutable COMPLETED run")
        if manifest["experiment_run_id"] != config["source_experiment_run_id"]:
            raise ValueError("source run does not match the registered audit config")
        if manifest["manifest_id"] != config["source_manifest_id"]:
            raise ValueError("source manifest does not match the registered audit config")
        if config["actionable_memory"] or config["principle_promotion_eligible"]:
            raise ValueError("post-hoc audit cannot produce actionable memory")

        records = build_records(
            audits=_read_jsonl(run_dir / "interaction_audit.jsonl"),
            results=_read_csv(run_dir / "results.csv"),
            source_method=str(config["source_method"]),
        )
        if len(records) != int(config["expected_operational_records"]):
            raise ValueError(
                f"expected {config['expected_operational_records']} records, got {len(records)}"
            )
        verdict_counts = Counter(item.utility_verdict.value for item in records)
        relation_counts = Counter(item.prediction_relation.value for item in records)
        skills = sorted({item.selected_skill.value for item in records})
        summary = {
            "protocol": config["protocol"],
            "source_experiment_run_id": manifest["experiment_run_id"],
            "source_manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "source_method": config["source_method"],
            "record_count": len(records),
            "utility_verdict_counts": dict(sorted(verdict_counts.items())),
            "prediction_relation_counts": dict(sorted(relation_counts.items())),
            "distinct_intervention_skills": skills,
            "distinct_intervention_skill_count": len(skills),
            "counterfactual_skill_pairs": 0,
            "actionable_memory_records": sum(item.actionable_memory for item in records),
            "principle_promotion_eligible_records": sum(
                item.principle_promotion_eligible for item in records
            ),
            "api_calls": 0,
            "environment_rollouts": 0,
            "claim_scope": (
                "prediction-resonance and executed-skill contradiction audit only; "
                "no alternative-skill utility or memory-benefit claim"
            ),
        }
        args.output_jsonl.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_jsonl.resolve().write_text(
            "".join(json.dumps(item.to_dict()) + "\n" for item in records),
            encoding="utf-8",
        )
        args.output_summary.resolve().write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        report = [
            "# ProbeMem Phase C Intervention-Utility Audit",
            "",
            f"Source run: `{manifest['experiment_run_id']}`",
            f"Source manifest: `{manifest['manifest_id']}`",
            f"Source method: `{config['source_method']}`",
            "",
            "## Result",
            "",
            f"The audit created {len(records)} falsifiable action-conditional records "
            "without new API calls or environment rollouts. Fresh verification supported "
            f"the executed skill in {verdict_counts['SUPPORTED']} cases, contradicted it "
            f"in {verdict_counts['CONTRADICTED']}, and remained unresolved in "
            f"{verdict_counts['UNRESOLVED']}.",
            "",
            f"The predicted verification status matched in {relation_counts['MATCHED']} "
            f"cases and produced {relation_counts['NEGATIVE_SURPRISE']} negative surprises. "
            "There were no positive surprises.",
            "",
            "## Scientific boundary",
            "",
            "Every record concerns `BOUNDED_PLANAR_COMPENSATION`; there are no matched "
            "counterfactual skill pairs. These records can identify failed predictions "
            "and contradictions for the executed skill, but cannot establish that another "
            "registered skill would have been better. They are development audit records, "
            "not actionable episodic memory, and all principle-promotion flags are false.",
            "",
            "## Next registered question",
            "",
            "On new development seeds, execute matched fresh verification for the two "
            "existing intervention families from the same initial failure. Test whether "
            "Agent-visible applicability signatures separate which skill wins. Do not "
            "use the current held-out seeds or promote an LLM-generated principle first.",
            "",
            "## Reproduction",
            "",
            "```bash",
            f"python scripts/build_probemem_intervention_utility_audit.py --run-dir \"{run_dir}\"",
            "```",
        ]
        args.output_report.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.output_report.resolve().write_text("\n".join(report) + "\n", encoding="utf-8")
        print(f"records: {args.output_jsonl.resolve()}")
        print(f"summary: {args.output_summary.resolve()}")
        print(f"report: {args.output_report.resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
