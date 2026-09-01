"""Analyze the frozen ProbeMem additional-experiments run."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import statistics
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_acr_utility_stability import _write_csv, _write_json  # noqa: E402
from src.evaluation import wilson_interval  # noqa: E402
from src.probemem.additional_experiments import (  # noqa: E402
    STATUS_RANK, transfer_label, verifier_intervention_outcome,
)


BASELINE = "BASELINE"
MEMORY = "MEMORY_ONLY"
EVIDENCE = "EVIDENCE_ACQUISITION_ENABLED"
BRIDGE = "PROBE_MEMORY"
FULL = "FULL_PROBEMEM"
METHODS = (BASELINE, MEMORY, EVIDENCE, BRIDGE, FULL)


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.stat().st_size:
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _paired_interval(left: list[int], right: list[int], *, samples: int, seed: int) -> dict[str, float]:
    if len(left) != len(right) or not left:
        raise ValueError("paired interval requires aligned non-empty values")
    generator = random.Random(seed)
    differences = []
    for _ in range(samples):
        indexes = [generator.randrange(len(left)) for _ in left]
        differences.append(sum(left[index] - right[index] for index in indexes) / len(indexes))
    differences.sort()
    return {
        "difference": statistics.fmean(left) - statistics.fmean(right),
        "lower": differences[int(0.025 * (len(differences) - 1))],
        "upper": differences[int(0.975 * (len(differences) - 1))],
    }


def _method_summary(rows: list[dict[str, str]], denominator: int) -> list[dict[str, Any]]:
    result = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        if len(selected) != denominator:
            raise ValueError(f"{method} does not use the common initial-failure denominator")
        recovered = sum(row["verification_status"] == "ACCEPTED" for row in selected)
        diagnosed = sum(row["mechanism_prediction"] == row["mechanism_oracle"] for row in selected)
        recovery_ci = wilson_interval(recovered, denominator)
        diagnosis_ci = wilson_interval(diagnosed, denominator)
        result.append({
            "method": method, "initial_failed_episodes": denominator,
            "successful_recoveries": recovered, "recovery_rate": recovered / denominator,
            "recovery_wilson_lower": recovery_ci[0], "recovery_wilson_upper": recovery_ci[1],
            "correct_diagnoses": diagnosed, "diagnosis_accuracy": diagnosed / denominator,
            "diagnosis_wilson_lower": diagnosis_ci[0], "diagnosis_wilson_upper": diagnosis_ci[1],
            "total_evidence_steps": sum(int(row["evidence_steps"]) for row in selected),
            "mean_evidence_steps": statistics.fmean(int(row["evidence_steps"]) for row in selected),
            "total_online_steps": sum(int(row["total_online_steps"]) for row in selected),
            "mean_online_steps": statistics.fmean(int(row["total_online_steps"]) for row in selected),
        })
    return result


def _memory_utility(rows_by_method: dict[str, dict[int, dict[str, str]]]) -> dict[str, Any]:
    comparisons = {
        "MEMORY_ONLY_VS_BASELINE": (MEMORY, BASELINE),
        "PROBE_MEMORY_VS_EVIDENCE_ACQUISITION": (BRIDGE, EVIDENCE),
    }
    output: dict[str, Any] = {}
    for name, (memory_method, reference_method) in comparisons.items():
        counts = {label: 0 for label in (
            "NO_RETRIEVAL", "USEFUL_TRANSFER", "HARMFUL_TRANSFER", "NEUTRAL_TRANSFER", "INDETERMINATE",
        )}
        changed = 0
        for episode, row in rows_by_method[memory_method].items():
            reference = rows_by_method[reference_method][episode]
            label = transfer_label(
                no_memory_skill=reference["selected_skill"], memory_skill=row["selected_skill"],
                no_memory_status=reference["verification_status"], memory_status=row["verification_status"],
                retrieval_count=int(row["retrieval_count"]),
            )
            counts[label] += 1
            changed += row["selected_skill"] != reference["selected_skill"]
        total = len(rows_by_method[memory_method])
        output[name] = {
            "eligible_cases": total, "action_changes": changed, "counts": counts,
            "rates_all_eligible": {key: value / total for key, value in counts.items()},
            "nonempty_retrieval_rate": 1.0 - counts["NO_RETRIEVAL"] / total,
        }
    return output


def _verifier(rows_by_method: dict[str, dict[int, dict[str, str]]],
              outcomes: list[dict[str, str]]) -> dict[str, Any]:
    outcome_map = {
        (int(row["episode_id"]), row["action_signature_id"]): row["verification_status"]
        for row in outcomes if int(row["realization"]) == 0
    }
    full_rows = rows_by_method[FULL]
    eligible = sum(_bool(row["verifier_eligible"]) for row in full_rows.values())
    proposals = sum(_bool(row["valid_proposal"]) for row in full_rows.values())
    invoked = sum(_bool(row["verifier_invoked"]) for row in full_rows.values())
    categories: dict[str, int] = {}
    calibration = {
        "HIGH_CONFIDENCE_SUCCESS": 0, "HIGH_CONFIDENCE_FAILURE": 0,
        "UNCERTAIN_PREDICTION": 0, "LOW_PREDICTED_SUCCESS": 0,
    }
    brier_terms = []
    for episode, row in full_rows.items():
        proposal_status = outcome_map.get((episode, row["proposal_action_signature_id"]))
        selected_status = outcome_map.get((episode, row["selected_action_signature_id"]))
        if not _bool(row["verifier_invoked"]):
            categories["NOT_INVOKED"] = categories.get("NOT_INVOKED", 0) + 1
            continue
        category = verifier_intervention_outcome(
            proposal_skill=row.get("proposal_skill"), selected_skill=row.get("selected_skill"),
            proposal_status=proposal_status, selected_status=selected_status,
        )
        categories[category] = categories.get(category, 0) + 1
        selected_probability = (
            row["proposal_probability"] if row["proposal_skill"] == row["selected_skill"]
            else row["alternative_probability"]
        )
        if selected_probability in (None, ""):
            continue
        probability = float(selected_probability)
        accepted = selected_status == "ACCEPTED"
        brier_terms.append((probability - float(accepted)) ** 2)
        if probability >= 0.70:
            calibration["HIGH_CONFIDENCE_SUCCESS" if accepted else "HIGH_CONFIDENCE_FAILURE"] += 1
        elif probability <= 0.30:
            calibration["LOW_PREDICTED_SUCCESS"] += 1
        else:
            calibration["UNCERTAIN_PREDICTION"] += 1
    proposal_ci = wilson_interval(proposals, eligible) if eligible else None
    invocation_ci = wilson_interval(invoked, eligible) if eligible else None
    return {
        "eligible_cases": eligible, "valid_proposals": proposals,
        "proposal_coverage": None if not eligible else proposals / eligible,
        "proposal_coverage_wilson": proposal_ci,
        "invocations": invoked, "invocation_coverage": None if not eligible else invoked / eligible,
        "invocation_coverage_wilson": invocation_ci,
        "intervention_outcomes": categories,
        "prevented_unsafe_actions": categories.get("CORRECT_REJECTION", 0),
        "unnecessary_rejections": categories.get("FALSE_REJECTION", 0),
        "calibration_counts": calibration,
        "brier_score": None if not brier_terms else statistics.fmean(brier_terms),
        "coverage_caveat": "Low invocation coverage must not be interpreted as high verifier reliability.",
    }


def _historical_acquisition(config: dict[str, Any], output: Path) -> list[dict[str, Any]]:
    source = ROOT / config["historical_allocation_run"] / "method_summary.csv"
    rows = _csv(source)
    mapping = {
        "passive": "NO_ACQUISITION",
        "always_probe": "ALWAYS_ACQUIRE_FIXED_64_STEP_EVIDENCE",
        "frozen_phase_conditioned_gate": "ADAPTIVE_ACQUISITION",
    }
    result = []
    for row in rows:
        if row["population"] != "operational_decision" or row["method"] not in mapping:
            continue
        units = int(row["units"])
        result.append({
            "policy": mapping[row["method"]], "cases": units,
            "correct_diagnoses": int(row["mechanism_correct"]),
            "diagnosis_accuracy": float(row["mechanism_accuracy"]),
            "total_evidence_steps": int(row["probe_environment_steps"]),
            "mean_evidence_steps": int(row["probe_environment_steps"]) / units,
            "entropy_reduction": "N/A",
        })
    _write_csv(output, result)
    return result


def _select_cases(rows_by_method: dict[str, dict[int, dict[str, str]]]) -> list[dict[str, Any]]:
    """Select the first sequential operational case per perturbation, without outcomes."""
    selected: list[dict[str, Any]] = []
    conditions = sorted({row["condition_id_oracle"] for row in rows_by_method[BASELINE].values()})
    for condition in conditions:
        for episode in sorted(rows_by_method[BASELINE]):
            full = rows_by_method[FULL][episode]
            if full["condition_id_oracle"] != condition:
                continue
            evidence = rows_by_method[EVIDENCE][episode]
            bridge = rows_by_method[BRIDGE][episode]
            tags: list[str] = []
            if evidence["mechanism_prediction"] != evidence["mechanism_oracle"]:
                tags.append("DIAGNOSIS_FAILURE")
            elif evidence["verification_status"] != "ACCEPTED":
                tags.append("DIAGNOSIS_CORRECT_RECOVERY_FAILED")
            if int(bridge["retrieval_count"]) > 0 and STATUS_RANK[bridge["verification_status"]] < STATUS_RANK[evidence["verification_status"]]:
                tags.append("MEMORY_HARMFUL_TRANSFER")
            if _bool(full["verifier_invoked"]) and full["verification_status"] != "ACCEPTED":
                tags.append("VERIFIER_FAILED_TO_PREVENT_UNRELIABLE_ACTION")
            if not tags:
                tags.append("SUCCESS_OR_NO_REGISTERED_FAILURE_TAG")
            selected.append({
                "selection_basis": f"FIRST_SEQUENTIAL_OPERATIONAL_{condition}",
                "observed_case_types": ";".join(tags),
                "episode_id": episode,
                "seed": int(full["seed"]),
            })
            break
    return selected


def analyze(run_dir: Path) -> dict[str, Any]:
    config = json.loads((ROOT / "configs/probemem_additional/ablation_development_v1.json").read_text())
    status = json.loads((run_dir / "run_status.json").read_text())
    population = _csv(run_dir / "population.csv")
    decisions = _csv(run_dir / "decisions.csv")
    outcomes = _csv(run_dir / "candidate_outcomes.csv")
    retrievals = _csv(run_dir / "memory_retrieval_audit.csv")
    denominator = sum(_bool(row["operational"]) for row in population)
    rows_by_method = {
        method: {int(row["episode_id"]): row for row in decisions if row["method"] == method}
        for method in METHODS
    }
    summaries = _method_summary(decisions, denominator)
    _write_csv(run_dir / "ablation_result_table.csv", summaries)
    historical = _historical_acquisition(config, run_dir / "evidence_acquisition_policy_table.csv")
    summary_by_method = {row["method"]: row for row in summaries}
    samples = int(config["statistics"]["bootstrap_repetitions"])
    seed = int(config["statistics"]["bootstrap_seed"])
    comparisons = {}
    for name, left, right in (
        ("MEMORY_ONLY_MINUS_BASELINE", MEMORY, BASELINE),
        ("PROBE_MEMORY_MINUS_EVIDENCE_ACQUISITION", BRIDGE, EVIDENCE),
        ("FULL_MINUS_PROBE_MEMORY", FULL, BRIDGE),
        ("EVIDENCE_ACQUISITION_MINUS_BASELINE", EVIDENCE, BASELINE),
    ):
        episodes = sorted(rows_by_method[left])
        comparisons[name] = _paired_interval(
            [int(rows_by_method[left][episode]["verification_status"] == "ACCEPTED") for episode in episodes],
            [int(rows_by_method[right][episode]["verification_status"] == "ACCEPTED") for episode in episodes],
            samples=samples, seed=seed + len(comparisons),
        )
    memory_utility = _memory_utility(rows_by_method)
    verifier = _verifier(rows_by_method, outcomes)
    cases = _select_cases(rows_by_method)
    _write_csv(run_dir / "selected_failure_cases.csv", cases)
    leakage = {
        "retrieval_items": len(retrievals),
        "owner_mismatches": sum(row["method"] != row["owner_method"] for row in retrievals),
        "non_accepted_items": sum(row["historical_status"] != "ACCEPTED" for row in retrievals),
        "not_strictly_prior": sum(int(row["source_episode_id"]) >= int(row["episode_id"]) for row in retrievals),
    }
    rq1_supported = (
        next(row for row in historical if row["policy"] == "ADAPTIVE_ACQUISITION")["diagnosis_accuracy"]
        >= next(row for row in historical if row["policy"].startswith("ALWAYS"))["diagnosis_accuracy"]
        and next(row for row in historical if row["policy"] == "ADAPTIVE_ACQUISITION")["total_evidence_steps"]
        < next(row for row in historical if row["policy"].startswith("ALWAYS"))["total_evidence_steps"]
    )
    memory_counts = memory_utility["PROBE_MEMORY_VS_EVIDENCE_ACQUISITION"]["counts"]
    rq2_delta = comparisons["PROBE_MEMORY_MINUS_EVIDENCE_ACQUISITION"]["difference"]
    rq2 = "Supported" if rq2_delta > 0 and memory_counts["USEFUL_TRANSFER"] > memory_counts["HARMFUL_TRANSFER"] else "Not supported" if rq2_delta < 0 or memory_counts["HARMFUL_TRANSFER"] > memory_counts["USEFUL_TRANSFER"] else "Inconclusive"
    rq3_delta = comparisons["FULL_MINUS_PROBE_MEMORY"]["difference"]
    rq3 = (
        "Supported"
        if rq3_delta > 0 and verifier["prevented_unsafe_actions"] > verifier["unnecessary_rejections"]
        else "Not supported"
        if (
            rq3_delta < 0
            or verifier["unnecessary_rejections"] > verifier["prevented_unsafe_actions"]
            or (
                rq3_delta == 0
                and verifier["prevented_unsafe_actions"] == 0
                and verifier["intervention_outcomes"].get("CORRECT_REJECTION", 0) == 0
            )
        )
        else "Inconclusive"
    )
    adaptive = next(row for row in historical if row["policy"] == "ADAPTIVE_ACQUISITION")
    fixed = next(row for row in historical if row["policy"].startswith("ALWAYS"))
    adaptive_reduction = 1.0 - adaptive["mean_evidence_steps"] / fixed["mean_evidence_steps"]
    bridge_utility = memory_utility["PROBE_MEMORY_VS_EVIDENCE_ACQUISITION"]
    failure_taxonomy = {
        "DIAGNOSIS_FAILURE": sum(
            row["mechanism_prediction"] != row["mechanism_oracle"]
            for row in rows_by_method[EVIDENCE].values()
        ),
        "DIAGNOSIS_CORRECT_RECOVERY_FAILED": sum(
            row["mechanism_prediction"] == row["mechanism_oracle"]
            and row["verification_status"] != "ACCEPTED"
            for row in rows_by_method[EVIDENCE].values()
        ),
        "MEMORY_HARMFUL_TRANSFER": bridge_utility["counts"]["HARMFUL_TRANSFER"],
        "VERIFIER_FAILED_TO_PREVENT_UNRELIABLE_ACTION": sum(
            _bool(row["verifier_invoked"])
            and row["mechanism_prediction"] == row["mechanism_oracle"]
            and row["verification_status"] != "ACCEPTED"
            for row in rows_by_method[FULL].values()
        ),
    }
    rq_observations = {
        "RQ1": (
            f"On {adaptive['cases']} comparable historical cases, adaptive acquisition and fixed 64-step "
            f"acquisition both diagnosed {adaptive['correct_diagnoses']}/{adaptive['cases']} cases "
            f"({adaptive['diagnosis_accuracy']:.1%}); adaptive acquisition used {adaptive['mean_evidence_steps']:.2f} "
            f"mean evidence steps versus {fixed['mean_evidence_steps']:.2f}, a {adaptive_reduction:.1%} reduction."
        ),
        "RQ2": (
            f"Adding method-isolated accepted-only memory on top of evidence acquisition changed recovery "
            f"from {summary_by_method[EVIDENCE]['successful_recoveries']}/{denominator} to "
            f"{summary_by_method[BRIDGE]['successful_recoveries']}/{denominator} "
            f"(paired difference {rq2_delta:+.1%}); transfer labels were "
            f"{bridge_utility['counts']['USEFUL_TRANSFER']} useful, "
            f"{bridge_utility['counts']['HARMFUL_TRANSFER']} harmful, "
            f"{bridge_utility['counts']['NEUTRAL_TRANSFER']} neutral, and "
            f"{bridge_utility['counts']['NO_RETRIEVAL']} no-retrieval."
        ),
        "RQ3": (
            f"Adding verifier on top of Probe+Memory changed recovery by {rq3_delta:+.1%} "
            f"({summary_by_method[BRIDGE]['successful_recoveries']}/{denominator} versus "
            f"{summary_by_method[FULL]['successful_recoveries']}/{denominator}). Proposal coverage was "
            f"{verifier['valid_proposals']}/{verifier['eligible_cases']}, invocation coverage was "
            f"{verifier['invocations']}/{verifier['eligible_cases']}, and no unsafe proposal was converted "
            f"from a non-ACCEPTED evaluator outcome to an ACCEPTED selected outcome."
        ),
    }
    result = {
        "run_status": status["status"], "experiment_run_id": status["experiment_run_id"],
        "manifest_id": status["manifest_id"], "source_git_commit": status["source_git_commit"],
        "common_initial_failure_denominator": denominator,
        "methods": summary_by_method, "paired_recovery_differences": comparisons,
        "memory_retrieval_utility": memory_utility, "memory_leakage_audit": leakage,
        "verifier": verifier, "population_by_condition": status["population_by_condition"],
        "population_by_mechanism": status["population_by_mechanism"],
        "descriptive_population_imbalance": status["descriptive_population_imbalance"],
        "failure_taxonomy_counts": failure_taxonomy,
        "research_findings": {
            "RQ1": {"question": "Does adaptive evidence acquisition reduce diagnosis cost?", "observed_evidence": rq_observations["RQ1"], "conclusion": "Supported" if rq1_supported else "Not supported"},
            "RQ2": {"question": "Does memory improve evidence utilization?", "observed_evidence": rq_observations["RQ2"], "conclusion": rq2},
            "RQ3": {"question": "Can verification bridge diagnosis and recovery?", "observed_evidence": rq_observations["RQ3"], "conclusion": rq3},
        },
        "selected_cases": cases,
        "claim_boundary": "configuration-level marginal effects, not fully independent component causal effects",
    }
    _write_json(run_dir / "analysis_summary.json", result)
    _write_report(run_dir / "additional_experiments_report.md", result, historical)
    return result


def _write_report(path: Path, result: dict[str, Any], historical: list[dict[str, Any]]) -> None:
    methods = result["methods"]
    lines = [
        "# ProbeMem Additional Experiments", "", f"Run: `{result['experiment_run_id']}`", "",
        "Recovery Rate = successful recoveries / initial failed episodes. All primary methods use "
        f"the same denominator (`{result['common_initial_failure_denominator']}`).", "",
        "## Ablation Result", "",
        "| Method | Diagnosis | Evidence steps | Recovery |", "|---|---:|---:|---:|",
    ]
    for method in METHODS:
        row = methods[method]
        lines.append(f"| {method} | {row['correct_diagnoses']}/{row['initial_failed_episodes']} ({row['diagnosis_accuracy']:.1%}) | {row['total_evidence_steps']} | {row['successful_recoveries']}/{row['initial_failed_episodes']} ({row['recovery_rate']:.1%}) |")
    lines += ["", "## Evidence Acquisition Policy Comparison", "", "| Policy | Diagnosis | Mean evidence steps |", "|---|---:|---:|"]
    for row in historical:
        lines.append(f"| {row['policy']} | {row['correct_diagnoses']}/{row['cases']} ({row['diagnosis_accuracy']:.1%}) | {row['mean_evidence_steps']:.2f} |")
    comparisons = result["paired_recovery_differences"]
    memory_utility = result["memory_retrieval_utility"]
    leakage = result["memory_leakage_audit"]
    lines += [
        "", "## Configuration-level Marginal Contributions", "",
        "These contrasts are marginal system contributions, not fully independent component causal effects.", "",
        f"- Memory contribution (`MEMORY_ONLY - BASELINE`): {comparisons['MEMORY_ONLY_MINUS_BASELINE']['difference']:+.1%} recovery rate.",
        f"- Evidence Acquisition contribution (`EVIDENCE_ACQUISITION_ENABLED - BASELINE`): {comparisons['EVIDENCE_ACQUISITION_MINUS_BASELINE']['difference']:+.1%} recovery rate. This is not an isolated probe-selector effect.",
        f"- Memory after acquisition (`PROBE_MEMORY - EVIDENCE_ACQUISITION_ENABLED`): {comparisons['PROBE_MEMORY_MINUS_EVIDENCE_ACQUISITION']['difference']:+.1%} recovery rate.",
        f"- Verifier addition (`FULL_PROBEMEM - PROBE_MEMORY`): {comparisons['FULL_MINUS_PROBE_MEMORY']['difference']:+.1%} recovery rate.",
        "", "## Memory Retrieval Utility and Leakage Audit", "",
    ]
    for label, utility in memory_utility.items():
        counts = utility["counts"]
        lines.append(
            f"- `{label}`: no retrieval {counts['NO_RETRIEVAL']}/{utility['eligible_cases']}; "
            f"useful {counts['USEFUL_TRANSFER']}/{utility['eligible_cases']}; harmful "
            f"{counts['HARMFUL_TRANSFER']}/{utility['eligible_cases']}; neutral "
            f"{counts['NEUTRAL_TRANSFER']}/{utility['eligible_cases']}."
        )
    lines += [
        f"- Retrieved items audited: {leakage['retrieval_items']}; owner mismatches: {leakage['owner_mismatches']}; non-ACCEPTED items: {leakage['non_accepted_items']}; non-prior items: {leakage['not_strictly_prior']}.",
        "- Retrieval similarity, source availability time, failure-mechanism consistency, and method ownership are recorded in `memory_retrieval_audit.csv`.",
    ]
    verifier = result["verifier"]
    lines += [
        "", "## Verifier Coverage and Calibration", "",
        f"- Proposal coverage: {verifier['valid_proposals']}/{verifier['eligible_cases']} ({verifier['proposal_coverage']:.1%})",
        f"- Invocation coverage: {verifier['invocations']}/{verifier['eligible_cases']} ({verifier['invocation_coverage']:.1%})",
        f"- Brier score: {verifier['brier_score']}",
        f"- Confidence/outcome consistency: `{verifier['calibration_counts']}`",
        f"- Intervention outcomes: `{verifier['intervention_outcomes']}`",
        f"- Prevented unsafe actions: {verifier['prevented_unsafe_actions']}; unnecessary rejections: {verifier['unnecessary_rejections']}.", "",
        verifier["coverage_caveat"], "",
        "## Population Coverage", "",
        f"- Perturbation categories: `{result['population_by_condition']}`",
        f"- Failure mechanisms: `{result['population_by_mechanism']}`",
        f"- Descriptive population imbalance: `{result['descriptive_population_imbalance']}`. Coverage targets did not alter stopping, resampling, or seed selection.", "",
        "## Full-population Failure Taxonomy", "",
        f"- Diagnosis failure: {result['failure_taxonomy_counts']['DIAGNOSIS_FAILURE']}/{result['common_initial_failure_denominator']}.",
        f"- Diagnosis correct but recovery failed: {result['failure_taxonomy_counts']['DIAGNOSIS_CORRECT_RECOVERY_FAILED']}/{result['common_initial_failure_denominator']}.",
        f"- Harmful Memory transfer: {result['failure_taxonomy_counts']['MEMORY_HARMFUL_TRANSFER']}/{result['common_initial_failure_denominator']}.",
        f"- Correct diagnosis but verifier failed to prevent an unreliable action: {result['failure_taxonomy_counts']['VERIFIER_FAILED_TO_PREVENT_UNRELIABLE_ACTION']}/{result['common_initial_failure_denominator']}.",
        "- These are full-population counts, not result-selected examples. The separate five-case report uses outcome-blind first-sequential-per-condition selection.", "",
        "The five-row ablation identifies configuration-level marginal effects, not fully independent component causal effects.", "",
        "## Research Findings", "",
    ]
    for rq in ("RQ1", "RQ2", "RQ3"):
        finding = result["research_findings"][rq]
        mechanism = {"RQ1": "adaptive evidence acquisition", "RQ2": "accepted-only chronological memory", "RQ3": "adding verifier on top of Probe+Memory"}[rq]
        metric = {"RQ1": "diagnostic interaction cost", "RQ2": "recovery and transfer utility", "RQ3": "recovery behavior"}[rq]
        verb = {"Supported": "support", "Not supported": "reject", "Inconclusive": "suggest"}[finding["conclusion"]]
        lines += [
            f"### {rq}", "", f"Question: {finding['question']}", "",
            f"Observed evidence: {finding['observed_evidence']}", "",
            f"Conclusion: {finding['conclusion']}. The results {verb} that {mechanism} affects {metric}{' beneficially' if rq == 'RQ2' else ''} under this development evaluation setting.", "",
            "Limitation: Fixed evidence action space, development-only population, and configuration-level marginal effects.", "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = analyze(args.run_dir.resolve())
        print(f"analysis: {args.run_dir.resolve() / 'analysis_summary.json'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
