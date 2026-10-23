"""Audit Gate-C memory action changes without new rollout or API calls.

The audit reconstructs the exact chronological memory available before each
changed decision. Evaluator-only segment and matched outcomes are attached only
after decisions are reconstructed and are never treated as Agent inputs.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.probemem.memory_tools import retrieve_action_memory_payload  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem.online_memory_policy import _single_decision  # noqa: E402
from src.probemem.persistent_regime import FROZEN_CONSISTENCY_THRESHOLD  # noqa: E402
from src.probemem.regime_memory import (  # noqa: E402
    RegimeActionExperience,
    RegimeActionMemory,
    SIGNATURE_FIELDS,
)


STATELESS = "STATELESS_GLM"
FULL = "GLM_ONLINE_MEMORY_RESONANCE"
COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION.value
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY.value
STATUS_UTILITY = {"ACCEPTED": 2, "INCONCLUSIVE": 1, "REJECTED": 0, "ABSTAIN": 0}


def audit_action_changes(run_dir: Path, bootstrap_path: Path) -> dict[str, Any]:
    decisions = _read_csv(run_dir / "decisions.csv")
    api = _read_json(run_dir / "api_audit.json")
    stored = _read_json(run_dir / "operational_memory_records.json")
    bootstrap = tuple(RegimeActionExperience.from_dict(row) for row in _read_json(bootstrap_path))
    full_records = tuple(
        sorted(
            (RegimeActionExperience.from_dict(_without_method(row)) for row in stored if row["method"] == FULL),
            key=lambda record: record.episode_id,
        )
    )
    decision_map = {(int(row["episode_id"]), row["method"]): row for row in decisions}
    model_map = _valid_model_decisions(api)
    changed = sorted(
        episode for episode, method in decision_map
        if method == STATELESS
        and (episode, FULL) in decision_map
        and decision_map[(episode, STATELESS)]["selected_skill"]
        != decision_map[(episode, FULL)]["selected_skill"]
    )
    cases: list[dict[str, Any]] = []
    by_episode = {record.episode_id: record for record in full_records}
    for episode in changed:
        current = by_episode[episode]
        prior = tuple(record for record in full_records if record.episode_id < episode)
        memory = RegimeActionMemory((*bootstrap, *prior))
        memory_payload = retrieve_action_memory_payload(
            memory, current.probe_signature, created_before_episode_id=episode,
        )
        stateless_row = decision_map[(episode, STATELESS)]
        full_row = decision_map[(episode, FULL)]
        stateless_model = model_map[(episode, STATELESS)]
        full_model = model_map[(episode, FULL)]
        effect = classify_change(
            stateless_row["verification_status"], full_row["verification_status"],
        )
        signature = current.probe_signature.to_dict()["features"]
        frozen_score = float(signature["estimated_bias_std_norm"])
        cases.append({
            "episode_id": episode,
            "seed": int(stateless_row["seed"]),
            "change_effect": effect,
            "stateless_skill": stateless_row["selected_skill"],
            "memory_skill": full_row["selected_skill"],
            "stateless_status": stateless_row["verification_status"],
            "memory_status": full_row["verification_status"],
            "segment_evaluator_only": stateless_row["segment_id_oracle"],
            "regime_evaluator_only": stateless_row["regime_id_oracle"],
            "probe_signature": signature,
            "frozen_variance_rule": {
                "threshold": FROZEN_CONSISTENCY_THRESHOLD,
                "score": frozen_score,
                "absolute_margin": abs(frozen_score - FROZEN_CONSISTENCY_THRESHOLD),
                "selected_skill": decision_map[(episode, "FROZEN_VARIANCE_RULE")]["selected_skill"],
            },
            "memory_snapshot": memory_payload,
            "stateless_prediction": _prediction_view(stateless_model),
            "memory_prediction": _prediction_view(full_model),
            "memory_accept_probability_margin": _selected_margin(full_model),
            "memory_reason": str(full_model["reason"]),
            "chronology_audit": {
                "cutoff_episode_id": episode,
                "maximum_retrieved_episode_id": max((record.episode_id for record in memory.prior(episode)), default=None),
                "current_or_future_record_visible": any(record.episode_id >= episode for record in memory.prior(episode)),
            },
        })
    if len(cases) != 12:
        raise RuntimeError(f"registered Gate-C action-change population changed: expected 12, found {len(cases)}")
    if any(case["chronology_audit"]["current_or_future_record_visible"] for case in cases):
        raise RuntimeError("chronology violation in reconstructed memory snapshot")
    return {
        "schema_version": 1,
        "source_run_id": run_dir.name,
        "audit_scope": "offline_existing_artifacts_only_no_rollout_no_api",
        "action_change_cases": cases,
        "summary": summarize_cases(cases),
    }


def classify_change(stateless_status: str, memory_status: str) -> str:
    delta = STATUS_UTILITY[memory_status] - STATUS_UTILITY[stateless_status]
    return "HELPFUL" if delta > 0 else "HARMFUL" if delta < 0 else "TIE"


def summarize_cases(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(cases)
    effects = Counter(str(row["change_effect"]) for row in rows)
    segments: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        segments[str(row["segment_evaluator_only"])][str(row["change_effect"])] += 1
    feature_contrasts: dict[str, dict[str, float | None]] = {}
    for feature in SIGNATURE_FIELDS:
        feature_contrasts[feature] = {
            effect.lower() + "_median": _median(
                float(row["probe_signature"][feature]) for row in rows if row["change_effect"] == effect
            )
            for effect in ("HELPFUL", "HARMFUL", "TIE")
        }
    prediction_margins = {
        effect.lower() + "_median": _median(
            float(row["memory_accept_probability_margin"])
            for row in rows if row["change_effect"] == effect
        )
        for effect in ("HELPFUL", "HARMFUL", "TIE")
    }
    return {
        "cases": len(rows),
        "effects": dict(effects),
        "all_change_directions": sorted({f'{row["stateless_skill"]}->{row["memory_skill"]}' for row in rows}),
        "by_segment_evaluator_only": {name: dict(counts) for name, counts in sorted(segments.items())},
        "feature_medians_by_effect": feature_contrasts,
        "memory_prediction_margin_by_effect": prediction_margins,
        "chronology_violations": sum(bool(row["chronology_audit"]["current_or_future_record_visible"]) for row in rows),
        "claim_boundary": (
            "Descriptive causal audit of decisions and matched outcomes. Small post-hoc groups do not identify "
            "a deployable ambiguity threshold or establish a memory benefit."
        ),
    }


def write_outputs(audit: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "action_change_audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    rows = []
    for case in audit["action_change_cases"]:
        comp = case["memory_snapshot"]["candidate_actions"][COMP]
        retry = case["memory_snapshot"]["candidate_actions"][RETRY]
        rows.append({
            "episode_id": case["episode_id"], "seed": case["seed"],
            "effect": case["change_effect"], "segment_evaluator_only": case["segment_evaluator_only"],
            "stateless_skill": case["stateless_skill"], "memory_skill": case["memory_skill"],
            "stateless_status": case["stateless_status"], "memory_status": case["memory_status"],
            "variance_score": case["frozen_variance_rule"]["score"],
            "variance_threshold_margin": case["frozen_variance_rule"]["absolute_margin"],
            "memory_prediction_margin": case["memory_accept_probability_margin"],
            "comp_global_accept": comp["global"]["accepted_probability"],
            "comp_recent_accept": comp["recent"]["accepted_probability"],
            "comp_contradictions": comp["global"]["contradiction_count"],
            "retry_global_accept": retry["global"]["accepted_probability"],
            "retry_recent_accept": retry["recent"]["accepted_probability"],
            "retry_contradictions": retry["global"]["contradiction_count"],
            "comp_retrieved_ids": json.dumps(comp["global"]["retrieved_record_ids"]),
            "retry_retrieved_ids": json.dumps(retry["global"]["retrieved_record_ids"]),
            "probe_signature": json.dumps(case["probe_signature"], sort_keys=True),
            "stateless_predictions": json.dumps(case["stateless_prediction"]["action_predictions"], sort_keys=True),
            "memory_predictions": json.dumps(case["memory_prediction"]["action_predictions"], sort_keys=True),
            "memory_reason": case["memory_reason"],
        })
    with (output_dir / "action_change_cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _valid_model_decisions(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[int, str], Mapping[str, Any]]:
    result: dict[tuple[int, str], Mapping[str, Any]] = {}
    for row in rows:
        if not bool(row.get("valid")):
            continue
        result[(int(row["episode_id"]), str(row["method"]))] = _single_decision(str(row["raw_response"]))
    return result


def _prediction_view(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "selected_skill": value["selected_skill"],
        "memory_used": value["memory_used"],
        "memory_applicable": value["memory_applicable"],
        "memory_conflict_detected": value["memory_conflict_detected"],
        "supporting_memory_ids": value["supporting_memory_ids"],
        "contradicting_memory_ids": value["contradicting_memory_ids"],
        "action_predictions": value["action_predictions"],
    }


def _selected_margin(value: Mapping[str, Any]) -> float:
    predictions = value["action_predictions"]
    selected = str(value["selected_skill"])
    other = RETRY if selected == COMP else COMP
    return float(predictions[selected]["accept_probability"]) - float(predictions[other]["accept_probability"])


def _without_method(value: Mapping[str, Any]) -> dict[str, Any]:
    return {name: item for name, item in value.items() if name != "method"}


def _median(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return None if not materialized else float(statistics.median(materialized))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    audit = audit_action_changes(args.run_dir.resolve(), args.bootstrap_records.resolve())
    write_outputs(audit, args.output_dir.resolve())
    print(f"cases: {audit['summary']['cases']}")
    print(f"effects: {audit['summary']['effects']}")
    print(f"output: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
