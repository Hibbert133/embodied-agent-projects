"""Run a bounded GLM-5.2 evidence-allocation pilot on development cases."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reasoning import EvidencePacket, EvidenceSource  # noqa: E402
from src.uncertainty import AnthropicEvidencePolicy, EvidenceAction  # noqa: E402
from src.uncertainty.online_policy import OnlineEvidenceDecision  # noqa: E402


def build_online_evidence_packet(
    case: Mapping[str, Any], temporal: Mapping[str, Any]
) -> EvidencePacket:
    """Build an explicit allowlist payload without evaluator-side truth fields."""
    payload = {
        "task": "MetaWorld push-v3 mechanism diagnosis after a failed rollout",
        "decision_objective": (
            "request the 64-step symmetric_xy probe only when current evidence is "
            "insufficient to distinguish stable systematic planar bias from "
            "stochastic execution; otherwise state the supported hypothesis"
        ),
        "outcome": {
            "steps": int(float(temporal["sample_count"])),
            "episode_return": float(case["episode_return"]),
            "final_object_goal_distance": float(case["final_object_goal_distance"]),
            "progress_to_goal": float(case["progress_to_goal"]),
        },
        "temporal_response": {
            "model": (
                "gripper_delta_xy = response_gain_xy * commanded_action_xy + "
                "execution_drift_xy"
            ),
            "uncertainty": float(temporal["temporal_uncertainty"]),
            "normalized_residual": [
                float(temporal["normalized_residual_x"]),
                float(temporal["normalized_residual_y"]),
            ],
            "response_gain": [
                float(temporal["response_gain_x"]),
                float(temporal["response_gain_y"]),
            ],
            "estimated_drift_per_step": [
                float(temporal["estimated_drift_x"]),
                float(temporal["estimated_drift_y"]),
            ],
            "action_excitation": [
                float(temporal["action_excitation_x"]),
                float(temporal["action_excitation_y"]),
            ],
            "known_limitation": (
                "global fit mixes free-space approach and contact push phases"
            ),
        },
        "registered_probe": {
            "kind": "symmetric_xy",
            "cost_environment_steps": 64,
            "observes": "repeatable directional response consistency",
        },
    }
    return EvidencePacket(
        evidence_id=f"online_temporal_{case['case_id']}",
        source=EvidenceSource.FAILED_ROLLOUT,
        episode_id=1,
        step_count=int(float(temporal["sample_count"])),
        payload=payload,
    )


def build_phase_online_evidence_packet(
    case: Mapping[str, Any], temporal: Mapping[str, Any], phase: Mapping[str, Any]
) -> EvidencePacket:
    """Add phase-conditioned response evidence without exposing tuned thresholds."""
    base = build_online_evidence_packet(case, temporal)
    payload = dict(base.payload)
    temporal_payload = dict(payload["temporal_response"])
    temporal_payload["known_limitation"] = (
        "global fit is provided for context; phase-conditioned fits reduce phase mixing"
    )
    payload["temporal_response"] = temporal_payload

    def optional_float(value: Any) -> float | None:
        return None if value is None or str(value).strip() == "" else float(value)

    payload["phase_conditioned_response"] = {
        "score_semantics": (
            "phase_inconsistency is the sample-weighted normalized within-phase "
            "response residual; higher means less repeatable response"
        ),
        "phase_inconsistency": float(phase["phase_inconsistency"]),
        "eligible_sample_fraction": float(phase["eligible_sample_fraction"]),
        "phases": {
            name: {
                "sample_count": int(phase[f"{name}_sample_count"]),
                "eligible": str(phase[f"{name}_eligible"]).lower() == "true",
                "normalized_residual_norm": optional_float(
                    phase[f"{name}_residual_norm"]
                ),
            }
            for name in ("approach", "push", "near_goal")
        },
        "known_limitations": (
            "phase classification uses visible geometry and residuals may still "
            "reflect contact dynamics or workspace constraints"
        ),
    }
    return EvidencePacket(
        evidence_id=f"online_phase_temporal_{case['case_id']}",
        source=EvidenceSource.FAILED_ROLLOUT,
        episode_id=1,
        step_count=int(float(temporal["sample_count"])),
        payload=payload,
    )


def decision_prediction(
    decision: OnlineEvidenceDecision, probe_prediction: str
) -> tuple[str, bool]:
    """Resolve a bounded decision into an evaluator-side mechanism prediction."""
    requested = decision.action is EvidenceAction.REQUEST_PROBE
    if requested:
        return probe_prediction, True
    if decision.action is EvidenceAction.ABSTAIN:
        return "no_prediction", False
    mapping = {
        "systematic_planar_bias": "stable_bias",
        "stochastic_execution": "stochastic_noise",
        "insufficient_evidence": "no_prediction",
    }
    return mapping[decision.hypothesis_mechanism], False


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _atomic_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def summarize_results(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("online results are required")
    requests = sum(bool(row["probe_requested"]) for row in rows)
    correct = sum(bool(row["correct"]) for row in rows)
    predictions = [row for row in rows if row["prediction"] != "no_prediction"]
    return {
        "cases": len(rows),
        "correct": correct,
        "accuracy": correct / len(rows),
        "coverage": len(predictions) / len(rows),
        "probe_requests": requests,
        "probe_request_rate": requests / len(rows),
        "probe_environment_steps": requests * 64,
        "api_calls": len(rows),
        "mean_latency_ms": mean(float(row["latency_ms"]) for row in rows),
        "endpoint_reported_input_tokens": sum(int(row.get("input_tokens", 0)) for row in rows),
        "endpoint_reported_output_tokens": sum(int(row.get("output_tokens", 0)) for row in rows),
        "claim_boundary": "development online pilot; no held-out performance claim",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="glm-5.2")
    parser.add_argument("--base-url")
    parser.add_argument("--api-timeout", type=float, default=300.0)
    parser.add_argument("--api-max-retries", type=int, default=2)
    parser.add_argument("--max-api-calls", type=int, default=10)
    parser.add_argument(
        "--evidence-mode", choices=("global", "phase_conditioned"), default="global"
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/bias_noise_temporal_development_v1/cases.csv",
    )
    parser.add_argument(
        "--probe-audit",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/bias_noise_temporal_development_v1/probe_audit.csv",
    )
    parser.add_argument(
        "--temporal-features",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/temporal_development_rollouts/temporal_features.csv",
    )
    parser.add_argument(
        "--phase-features",
        type=Path,
        default=ROOT
        / "outputs/ambiguity_benchmark/temporal_development_rollouts/phase_features.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/online_evidence_agent/glm52_temporal_development_v1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        cases = _read_csv(args.cases)
        if not cases or len(cases) > args.max_api_calls:
            raise ValueError("case count must be positive and within max-api-calls")
        temporal = {row["case_id"]: row for row in _read_csv(args.temporal_features)}
        phases = (
            {row["case_id"]: row for row in _read_csv(args.phase_features)}
            if args.evidence_mode == "phase_conditioned"
            else {}
        )
        probes = {row["case_id"]: row for row in _read_csv(args.probe_audit)}
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        config = {
            "protocol": (
                "online-phase-conditioned-evidence-allocation-v1"
                if args.evidence_mode == "phase_conditioned"
                else "online-temporal-evidence-allocation-v1"
            ),
            "model": args.model,
            "base_url": args.base_url or "environment",
            "case_ids": [row["case_id"] for row in cases],
            "max_api_calls": args.max_api_calls,
            "available_probe": "symmetric_xy",
            "probe_cost_environment_steps": 64,
            "agent_view_only": True,
        }
        if args.evidence_mode == "phase_conditioned":
            config["evidence_mode"] = args.evidence_mode
            config["tuned_phase_threshold_visible_to_model"] = False
        config_path = output / "run_config.json"
        if config_path.exists() and json.loads(config_path.read_text(encoding="utf-8")) != config:
            raise RuntimeError("existing run config differs; use a new output directory")
        _atomic_json(config_path, config)
        results = _read_csv(output / "results.csv")
        audits = _read_jsonl(output / "planner_audit.jsonl")
        completed = {row["case_id"] for row in results}
        if completed != {row["case_id"] for row in audits}:
            raise RuntimeError("result and audit checkpoints are inconsistent")
        audit_by_case = {row["case_id"]: row for row in audits}
        for result in results:
            usage = audit_by_case[result["case_id"]]["api_audit"].get("usage", {})
            result["input_tokens"] = int(usage.get("input_tokens", 0))
            result["output_tokens"] = int(usage.get("output_tokens", 0))
        if results:
            _atomic_csv(output / "results.csv", results)
        policy = AnthropicEvidencePolicy(
            model=args.model,
            base_url=args.base_url,
            timeout_seconds=args.api_timeout,
            max_retries=args.api_max_retries,
        )
        for case in cases:
            case_id = case["case_id"]
            if case_id in completed:
                print(f"case={case_id} status=already_complete")
                continue
            if case_id not in temporal or case_id not in probes:
                raise ValueError(f"missing temporal or probe evidence for {case_id}")
            if args.evidence_mode == "phase_conditioned" and case_id not in phases:
                raise ValueError(f"missing phase evidence for {case_id}")
            packet = (
                build_phase_online_evidence_packet(
                    case, temporal[case_id], phases[case_id]
                )
                if args.evidence_mode == "phase_conditioned"
                else build_online_evidence_packet(case, temporal[case_id])
            )
            decision, api_audit = policy.decide(packet, available_probe_steps=64)
            prediction, requested = decision_prediction(
                decision, probes[case_id]["predicted_mechanism"]
            )
            truth = case["mechanism_class"]
            result = {
                "case_id": case_id,
                "seed": int(case["seed"]),
                "evidence_mode": args.evidence_mode,
                "action": decision.action.value,
                "probe_requested": requested,
                "hypothesis_mechanism": decision.hypothesis_mechanism,
                "confidence": decision.confidence,
                "prediction": prediction,
                "mechanism_class_oracle": truth,
                "correct": prediction == truth,
                "probe_environment_steps": 64 if requested else 0,
                "latency_ms": float(api_audit["latency_ms"]),
                "input_tokens": int(api_audit.get("usage", {}).get("input_tokens", 0)),
                "output_tokens": int(api_audit.get("usage", {}).get("output_tokens", 0)),
            }
            results.append(result)
            audits.append(
                {
                    "case_id": case_id,
                    "evidence_packet": packet.to_dict(),
                    "decision": decision.to_dict(),
                    "api_audit": api_audit,
                }
            )
            _atomic_csv(output / "results.csv", results)
            _atomic_jsonl(output / "planner_audit.jsonl", audits)
            print(
                f"case={case_id} action={decision.action.value} "
                f"hypothesis={decision.hypothesis_mechanism} correct={prediction == truth}"
            )
        summary = summarize_results(results)
        _atomic_json(output / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
