"""Analyze the frozen deterministic ProbeMem-ACR development campaign."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.probemem import ActionOutcomeRecord, InterventionSkill, ResonanceRecord  # noqa: E402


METHODS = (
    "always_compensation",
    "always_retry",
    "state_only_nearest_accepted",
    "v2_fixed_coverage_aware",
    "frozen_single_feature_selector",
    "deterministic_action_conditional",
)
MEMORY_BASELINES = ("state_only_nearest_accepted", "v2_fixed_coverage_aware")
FIXED_BASELINES = ("always_compensation", "always_retry")
STATUS_UTILITY = {"ACCEPTED": 1.0, "INCONCLUSIVE": 0.5, "REJECTED": 0.0}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("ACR analysis cannot write an empty CSV")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def oracle_winners(pair: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    def key(item: Mapping[str, Any]) -> tuple[float, float, float]:
        return (
            STATUS_UTILITY[str(item["verification_status"])],
            float(item["observed_progress"]),
            -float(item["verification_steps"]),
        )

    scored = {skill: key(value) for skill, value in pair.items()}
    best = max(scored.values())
    return tuple(sorted(skill for skill, value in scored.items() if value == best))


def _paired_bootstrap(values: Sequence[float], *, seed: int, resamples: int) -> dict[str, float] | None:
    if not values:
        return None
    array = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    samples = np.empty(resamples, dtype=float)
    for index in range(resamples):
        samples[index] = float(np.mean(rng.choice(array, size=len(array), replace=True)))
    return {
        "estimate": float(np.mean(array)),
        "ci95_low": float(np.percentile(samples, 2.5)),
        "ci95_high": float(np.percentile(samples, 97.5)),
        "resamples": resamples,
        "unit_count": len(values),
    }


def _strongest(stats: Mapping[str, Mapping[str, Any]], names: Sequence[str]) -> str:
    return max(
        names,
        key=lambda name: (
            int(stats[name]["accepted_count"]),
            -int(stats[name]["harmful_transfer_count"]),
            int(stats[name]["selection_count"]),
            name,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "outputs/probemem_acr"
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "reports/probemem_acr_development_v1.md"
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED" or status.get("initial_units") != 100:
            raise ValueError("ACR analysis requires the complete 100-unit run")
        cases = _read_csv(run_dir / "case_results.csv")
        operational = [row for row in cases if row["decision_required"] == "True"]
        candidates = _read_csv(run_dir / "candidate_results.csv")
        pairs: dict[int, dict[str, dict[str, Any]]] = {}
        for row in candidates:
            episode_id = int(row["episode_id"])
            pairs.setdefault(episode_id, {})[row["candidate_id"]] = row
        if any(len(pair) != 2 for pair in pairs.values()) or len(pairs) != len(operational):
            raise ValueError("ACR paired candidate population is incomplete")
        predecisions = {int(row["episode_id"]): row for row in _read_jsonl(run_dir / "pre_execution_decisions.jsonl")}
        records = [ActionOutcomeRecord.from_dict(row) for row in _read_jsonl(run_dir / "action_outcomes.jsonl")]
        if len(records) != 2 * len(operational):
            raise ValueError("ACR action-outcome record count differs from paired population")

        chronology_violations = 0
        for episode_id, decision in predecisions.items():
            history = decision["action_conditional_evidence_pack"]["standardization_episode_ids"]
            if any(int(item) >= episode_id for item in history):
                chronology_violations += 1
            if int(decision["pre_execution_timestamp_ns"]) >= min(
                int(item["outcome_timestamp_ns"])
                for item in pairs[episode_id].values()
            ):
                chronology_violations += 1
        for raw in _read_jsonl(run_dir / "action_outcomes.jsonl"):
            if int(raw["memory_append_timestamp_ns"]) <= int(
                predecisions[int(raw["source_episode_id"])]["pre_execution_timestamp_ns"]
            ):
                chronology_violations += 1

        detail_rows: list[dict[str, Any]] = []
        method_stats: dict[str, dict[str, Any]] = {}
        decisive_episodes = []
        exclusive_episodes = []
        partitions = Counter()
        for row in operational:
            episode_id = int(row["episode_id"])
            pair = pairs[episode_id]
            accepted = [skill for skill, value in pair.items() if value["verification_status"] == "ACCEPTED"]
            if len(accepted) == 2:
                partition = "BOTH_RECOVER"
            elif len(accepted) == 1:
                partition = "COMPENSATION_ONLY_RECOVERY" if accepted[0] == COMPENSATION else "RETRY_ONLY_RECOVERY"
                exclusive_episodes.append(episode_id)
            else:
                partition = "NEITHER_RECOVERS"
            partitions[partition] += 1
            status_values = {skill: STATUS_UTILITY[value["verification_status"]] for skill, value in pair.items()}
            decisive = len(set(status_values.values())) == 2
            if decisive:
                decisive_episodes.append(episode_id)
            winners = oracle_winners(pair)
            decision = predecisions[episode_id]
            for method in METHODS:
                selected = decision["method_selections"][method]
                selected_row = pair.get(selected) if selected else None
                alternative = next((skill for skill in pair if skill != selected), None) if selected else None
                selected_status = selected_row["verification_status"] if selected_row else "ABSTAIN"
                selected_accepted = selected_status == "ACCEPTED"
                harmful = bool(
                    selected
                    and not selected_accepted
                    and alternative
                    and pair[alternative]["verification_status"] == "ACCEPTED"
                )
                decisive_correct = bool(
                    decisive and selected and status_values[selected] == max(status_values.values())
                )
                detail_rows.append({
                    "experiment_run_id": manifest["experiment_run_id"],
                    "manifest_id": manifest["manifest_id"],
                    "episode_id": episode_id,
                    "seed": int(row["seed"]),
                    "condition_id_oracle": row["condition_id_oracle"],
                    "method": method,
                    "selected_skill": selected or "",
                    "selected_status": selected_status,
                    "selected_accepted": selected_accepted,
                    "selected_progress": float(selected_row["observed_progress"]) if selected_row else "",
                    "selected_steps": int(selected_row["verification_steps"]) if selected_row else 0,
                    "harmful_transfer": harmful,
                    "exclusive_recovery": episode_id in exclusive_episodes,
                    "decisive_status": decisive,
                    "decisive_correct": decisive_correct,
                    "outcome_partition_evaluator_only": partition,
                    "oracle_winners_evaluator_only": "|".join(winners),
                })

        for method in METHODS:
            rows = [row for row in detail_rows if row["method"] == method]
            decisive_rows = [row for row in rows if row["decisive_status"]]
            selected_decisive = [row for row in decisive_rows if row["selected_skill"]]
            selected_rows = [row for row in rows if row["selected_skill"]]
            method_stats[method] = {
                "operational_cases": len(rows),
                "selection_count": len(selected_rows),
                "coverage": len(selected_rows) / len(rows),
                "accepted_count": sum(bool(row["selected_accepted"]) for row in rows),
                "accepted_rate": sum(bool(row["selected_accepted"]) for row in rows) / len(rows),
                "harmful_transfer_count": sum(bool(row["harmful_transfer"]) for row in rows),
                "decisive_cases": len(decisive_rows),
                "decisive_correct_count": sum(bool(row["decisive_correct"]) for row in decisive_rows),
                "full_decisive_accuracy": (
                    sum(bool(row["decisive_correct"]) for row in decisive_rows) / len(decisive_rows)
                    if decisive_rows else None
                ),
                "conditional_decisive_accuracy": (
                    sum(bool(row["decisive_correct"]) for row in selected_decisive) / len(selected_decisive)
                    if selected_decisive else None
                ),
                "decisive_selection_coverage": len(selected_decisive) / len(decisive_rows) if decisive_rows else None,
                "mean_selected_final_distance": (
                    statistics.mean(
                        float(pairs[int(row["episode_id"])][row["selected_skill"]]["final_object_goal_distance"])
                        for row in selected_rows
                    ) if selected_rows else None
                ),
            }

        strongest_memory = _strongest(method_stats, MEMORY_BASELINES)
        strongest_fixed = _strongest(method_stats, FIXED_BASELINES)
        acr_stats = method_stats["deterministic_action_conditional"]
        state_stats = method_stats["state_only_nearest_accepted"]
        memory_stats = method_stats[strongest_memory]
        fixed_stats = method_stats[strongest_fixed]
        accuracy_gain_pp = 100.0 * (
            (acr_stats["full_decisive_accuracy"] or 0.0)
            - (state_stats["full_decisive_accuracy"] or 0.0)
        )
        net_correct = acr_stats["decisive_correct_count"] - state_stats["decisive_correct_count"]
        harmful_absolute = memory_stats["harmful_transfer_count"] - acr_stats["harmful_transfer_count"]
        harmful_relative = (
            harmful_absolute / memory_stats["harmful_transfer_count"]
            if memory_stats["harmful_transfer_count"] else None
        )

        resonance_rows = []
        brier = []
        status_matches = []
        progress_errors = []
        for episode_id, pair in pairs.items():
            predictions = predecisions[episode_id]["action_conditional_decision"]["predictions"]
            for skill, observed in pair.items():
                prediction = predictions[skill]
                probabilities = prediction["probabilities"]
                item = ResonanceRecord.create(
                    prediction_id=f"acr_episode{episode_id:03d}_{skill.lower()}",
                    episode_id=episode_id,
                    selected_skill=InterventionSkill(skill),
                    predicted_status=prediction["predicted_status"],
                    probabilities=probabilities,
                    observed_status=observed["verification_status"],
                    predicted_progress=prediction["predicted_progress"],
                    observed_progress=float(observed["observed_progress"]),
                )
                resonance_rows.append({
                    **item.to_dict(),
                    "predicted_accept_probability": float(probabilities["ACCEPTED"]),
                    "observed_accepted": observed["verification_status"] == "ACCEPTED",
                })
                brier.append((float(probabilities["ACCEPTED"]) - (observed["verification_status"] == "ACCEPTED")) ** 2)
                status_matches.append(item.status_match)
                if item.progress_error is not None:
                    progress_errors.append(item.progress_error)

        gate = config["promotion_gate"]
        integrity = {
            "operational_cases": len(operational) >= int(gate["minimum_operational_cases"]),
            "exclusive_recovery_cases": len(exclusive_episodes) >= int(gate["minimum_exclusive_recovery_cases"]),
            "zero_chronology_violations": chronology_violations == 0,
            "zero_oracle_leakage": int(status["oracle_leakage_events"]) == 0,
            "zero_budget_violations": int(status["budget_violations"]) == 0,
        }
        accuracy_path = (
            accuracy_gain_pp >= float(gate["minimum_decisive_accuracy_percentage_point_gain"])
            and net_correct >= int(gate["minimum_net_decisive_correct_gain"])
        )
        harmful_path = (
            harmful_relative is not None
            and harmful_relative >= float(gate["minimum_harmful_transfer_relative_reduction"])
            and harmful_absolute >= int(gate["minimum_harmful_transfer_absolute_reduction"])
        )
        recovery_check = (
            acr_stats["accepted_count"]
            >= fixed_stats["accepted_count"] - int(gate["maximum_accepted_recovery_case_deficit_to_fixed_baseline"])
        )
        promotion = all(integrity.values()) and (accuracy_path or harmful_path) and recovery_check

        bootstrap = config["bootstrap"]
        acr_by_episode = {int(row["episode_id"]): row for row in detail_rows if row["method"] == "deterministic_action_conditional"}
        state_by_episode = {int(row["episode_id"]): row for row in detail_rows if row["method"] == "state_only_nearest_accepted"}
        memory_by_episode = {int(row["episode_id"]): row for row in detail_rows if row["method"] == strongest_memory}
        fixed_by_episode = {int(row["episode_id"]): row for row in detail_rows if row["method"] == strongest_fixed}
        confidence_intervals = {
            "decisive_accuracy_difference_acr_minus_state_only": _paired_bootstrap(
                [float(acr_by_episode[e]["decisive_correct"]) - float(state_by_episode[e]["decisive_correct"]) for e in decisive_episodes],
                seed=int(bootstrap["seed"]), resamples=int(bootstrap["resamples"]),
            ),
            "harmful_transfer_difference_acr_minus_strongest_memory": _paired_bootstrap(
                [float(acr_by_episode[e]["harmful_transfer"]) - float(memory_by_episode[e]["harmful_transfer"]) for e in pairs],
                seed=int(bootstrap["seed"]), resamples=int(bootstrap["resamples"]),
            ),
            "accepted_difference_acr_minus_strongest_fixed": _paired_bootstrap(
                [float(acr_by_episode[e]["selected_accepted"]) - float(fixed_by_episode[e]["selected_accepted"]) for e in pairs],
                seed=int(bootstrap["seed"]), resamples=int(bootstrap["resamples"]),
            ),
        }
        summary = {
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "claim_scope": "development paired counterfactual feasibility only",
            "initial_units": len(cases),
            "operational_cases": len(operational),
            "exclusive_recovery_cases": len(exclusive_episodes),
            "decisive_status_cases": len(decisive_episodes),
            "outcome_partitions": dict(partitions),
            "method_results": method_stats,
            "strongest_memory_baseline": strongest_memory,
            "strongest_fixed_baseline": strongest_fixed,
            "acr_accuracy_gain_percentage_points": accuracy_gain_pp,
            "acr_net_decisive_correct_gain": net_correct,
            "acr_harmful_transfer_absolute_reduction": harmful_absolute,
            "acr_harmful_transfer_relative_reduction": harmful_relative,
            "prediction_quality": {
                "status_accuracy": sum(status_matches) / len(status_matches),
                "acceptance_brier_score": statistics.mean(brier),
                "progress_mae": statistics.mean(progress_errors) if progress_errors else None,
                "resonance_counts": dict(Counter(row["resonance_class"] for row in resonance_rows)),
            },
            "integrity_checks": integrity,
            "accuracy_promotion_path": accuracy_path,
            "harmful_transfer_promotion_path": harmful_path,
            "recovery_noninferiority_check": recovery_check,
            "promotion_gate_passed": promotion,
            "validation_authorized": promotion,
            "confidence_intervals": confidence_intervals,
            "api_calls": 0,
            "heldout_claim_eligible": False,
        }
        output = args.output_root.resolve()
        _write_csv(output / "development_method_episode_results.csv", detail_rows)
        _write_csv(output / "development_resonance_records.csv", resonance_rows)
        (output / "development_action_outcomes.jsonl").write_text(
            "\n".join(json.dumps(item.to_dict(), sort_keys=True) for item in records) + "\n",
            encoding="utf-8",
        )
        (output / "development_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        (output / "development_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        report = [
            "# ProbeMem-ACR Deterministic Development Result",
            "",
            f"Run: `{manifest['experiment_run_id']}`",
            f"Manifest: `{manifest['manifest_id']}`",
            "",
            "## Actual result",
            "",
            f"The immutable campaign completed {len(cases)} initial units and {len(operational)} paired operational cases.",
            f"Outcome partitions: `{dict(partitions)}`.",
            f"The deterministic ACR estimator recovered {acr_stats['accepted_count']}/{len(operational)} and produced {acr_stats['harmful_transfer_count']} harmful transfers.",
            f"Its full decisive accuracy was {acr_stats['full_decisive_accuracy']}; state-only retrieval was {state_stats['full_decisive_accuracy']}.",
            f"The registered promotion gate passed: **{promotion}**.",
            "",
            "## Claim boundary",
            "",
            "This is a development-only paired counterfactual feasibility study. Counterfactual records are not naturally available online Agent experience. The result does not establish online learning, LLM memory benefit, principle learning, validation, or held-out improvement.",
        ]
        args.report.resolve().write_text("\n".join(report) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, TypeError, ValueError, ZeroDivisionError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


COMPENSATION = InterventionSkill.BOUNDED_PLANAR_COMPENSATION.value
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY.value


if __name__ == "__main__":
    raise SystemExit(main())
