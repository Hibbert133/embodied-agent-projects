"""Run a resumable, bounded active-evidence comparison on MetaWorld push-v3."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.diagnosis import estimate_passive_planar_drift  # noqa: E402
from src.evaluation import (  # noqa: E402
    CampaignBudget,
    CampaignJob,
    CampaignLedger,
    CampaignOutcome,
    run_campaign,
)
from src.perturbations import (  # noqa: E402
    ActionBiasPerturbation,
    ActionScalePerturbation,
    GaussianNoisePerturbation,
)
from src.planar_recovery import estimate_planar_correction  # noqa: E402
from src.probe import (  # noqa: E402
    build_agent_probe_context,
    estimate_planar_bias,
    run_symmetric_probes,
)
from src.recovery_agent import (  # noqa: E402
    DEFAULT_CORRECTION_MAGNITUDES,
    PhaseGatedCompensatedPolicy,
)
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402
from src.uncertainty import (  # noqa: E402
    EvidenceAction,
    ThresholdEvidencePolicy,
    UncertaintyEstimate,
)


METHODS = ("passive", "always_probe", "random_probe", "uncertainty_gated")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs" / "campaigns" / "active_evidence_smoke.json",
    )
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    required = {
        "campaign_id", "seeds", "conditions", "methods", "max_steps",
        "probe_steps", "probe_magnitude", "uncertainty_threshold", "budget",
    }
    missing = required - set(payload)
    if missing:
        raise ValueError(f"campaign config missing fields: {sorted(missing)}")
    if not set(payload["methods"]).issubset(METHODS):
        raise ValueError(f"unsupported methods: {sorted(set(payload['methods']) - set(METHODS))}")
    if not payload["seeds"] or not payload["conditions"] or not payload["methods"]:
        raise ValueError("campaign requires seeds, conditions, and methods")
    return payload


def build_perturbation(condition: Mapping[str, Any]) -> Any:
    kind = condition["kind"]
    if kind == "action_bias":
        return ActionBiasPerturbation(condition["bias"])
    if kind == "gaussian_noise":
        return GaussianNoisePerturbation(float(condition["std"]))
    if kind == "action_scale":
        return ActionScalePerturbation(float(condition["scale"]))
    raise ValueError(f"unsupported perturbation kind: {kind}")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


def atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def should_probe(
    method: str,
    *,
    uncertainty: float,
    threshold: float,
    seed: int,
    repeat: int,
    random_probe_probability: float,
    probe_budget: int,
) -> tuple[bool, str]:
    estimate = UncertaintyEstimate(
        estimate_id=f"uncertainty_{seed}_{repeat}_{method}",
        based_on_evidence_ids=(f"failed_rollout_{seed}_{repeat}",),
        epistemic=uncertainty,
        aleatoric=0.0,
        overall=uncertainty,
        missing_evidence=("symmetric directional response",),
        rationale="passive local-model confidence derived from Agent View transitions",
    )
    if method == "passive":
        return False, EvidenceAction.UPDATE_HYPOTHESIS.value
    if method == "always_probe":
        return True, EvidenceAction.REQUEST_PROBE.value
    if method == "random_probe":
        rng = np.random.default_rng(np.random.SeedSequence([seed, repeat, 0xE71D]))
        requested = bool(rng.random() < random_probe_probability)
        return requested, (
            EvidenceAction.REQUEST_PROBE.value
            if requested else EvidenceAction.UPDATE_HYPOTHESIS.value
        )
    if method == "uncertainty_gated":
        decision = ThresholdEvidencePolicy(threshold).decide(
            estimate,
            decision_id=f"decision_{seed}_{repeat}_{method}",
            available_probe_steps=probe_budget,
        )
        return decision.action is EvidenceAction.REQUEST_PROBE, decision.action.value
    raise ValueError(f"unsupported method: {method}")


class MetaWorldCampaignExecutor:
    def __init__(
        self, config: Mapping[str, Any], output_dir: Path,
        conditions: Mapping[str, Mapping[str, Any]],
    ) -> None:
        self.config = config
        self.output_dir = output_dir
        self.conditions = conditions

    def __call__(self, job: CampaignJob) -> CampaignOutcome:
        condition = self.conditions[job.condition_id]
        job_dir = self.output_dir / "jobs" / job.job_id
        agent_path = job_dir / "initial_agent_trajectory.jsonl"
        max_steps = int(self.config["max_steps"])
        probe_steps_each = int(self.config["probe_steps"])
        probe_budget = 4 * probe_steps_each

        env = create_push_environment(job.seed)
        try:
            initial = run_episode(
                env,
                create_push_policy(),
                seed=job.seed,
                max_steps=max_steps,
                perturbation=build_perturbation(condition),
                agent_trajectory_path=agent_path,
            )
        finally:
            env.close()

        if initial.success:
            decision_payload = {
                "job_id": job.job_id,
                "method": job.method,
                "initial_success": True,
                "probe_requested": False,
                "reason": "no diagnosis or corrective intervention required",
            }
            atomic_json(job_dir / "agent_decision.json", decision_payload)
            return CampaignOutcome(
                job.job_id, True, initial.steps, 0,
                {
                    "initial_success": True,
                    "verification_success": True,
                    "probe_requested": False,
                    "probe_environment_steps": 0,
                    "final_object_goal_distance": initial.final_object_goal_distance,
                },
            )

        passive = estimate_passive_planar_drift(load_jsonl(agent_path))
        requested, decision_action = should_probe(
            job.method,
            uncertainty=passive.uncertainty,
            threshold=float(self.config["uncertainty_threshold"]),
            seed=job.seed,
            repeat=job.repeat,
            random_probe_probability=float(self.config.get("random_probe_probability", 0.5)),
            probe_budget=probe_budget,
        )

        probe_environment_steps = 0
        if requested:
            probes = run_symmetric_probes(
                lambda: create_push_environment(job.seed),
                seed=job.seed,
                perturbation_factory=lambda: build_perturbation(condition),
                magnitude=float(self.config["probe_magnitude"]),
                steps=probe_steps_each,
            )
            inference = estimate_planar_bias(probes)
            diagnostic_context = build_agent_probe_context(probes, inference)
            probe_environment_steps = int(diagnostic_context["probe_environment_steps"])
            evidence_source = "diagnostic_probe"
        else:
            diagnostic_context = {
                "protocol": "passive_planar_local_model_v1",
                "probe_environment_steps": 0,
                "inference": passive.to_probe_inference(),
            }
            evidence_source = "failed_rollout"

        correction = estimate_planar_correction(
            diagnostic_context,
            allowed_magnitudes=DEFAULT_CORRECTION_MAGNITUDES,
        )
        policy = PhaseGatedCompensatedPolicy(
            create_push_policy(), correction.simultaneous_correction, schedule="whole"
        )
        env = create_push_environment(job.seed)
        try:
            verification = run_episode(
                env,
                policy,
                seed=job.seed,
                max_steps=max_steps,
                perturbation=build_perturbation(condition),
            )
        finally:
            env.close()

        agent_decision = {
            "job_id": job.job_id,
            "method": job.method,
            "initial_success": False,
            "passive_estimate": passive.to_dict(),
            "evidence_action": decision_action,
            "probe_requested": requested,
            "evidence_source": evidence_source,
            "selected_correction": list(correction.simultaneous_correction),
            "verification_success": verification.success,
        }
        atomic_json(job_dir / "agent_decision.json", agent_decision)

        expected_axis = condition.get("oracle_axis")
        expected_direction = condition.get("oracle_direction")
        inferred = diagnostic_context["inference"]
        diagnostic_correct = (
            None
            if expected_axis is None or expected_direction is None
            else inferred["dominant_axis"] == expected_axis
            and inferred["estimated_direction"] == expected_direction
        )
        return CampaignOutcome(
            job.job_id,
            verification.success,
            initial.steps + probe_environment_steps + verification.steps,
            0,
            {
                "initial_success": False,
                "verification_success": verification.success,
                "probe_requested": requested,
                "probe_environment_steps": probe_environment_steps,
                "uncertainty": passive.uncertainty,
                "passive_confidence": passive.overall_confidence,
                "diagnostic_axis": inferred["dominant_axis"],
                "diagnostic_direction": inferred["estimated_direction"],
                "diagnostic_correct": diagnostic_correct,
                "initial_final_object_goal_distance": initial.final_object_goal_distance,
                "final_object_goal_distance": verification.final_object_goal_distance,
                "rollout_improvement": (
                    initial.final_object_goal_distance
                    - verification.final_object_goal_distance
                ),
            },
        )


def build_jobs(config: Mapping[str, Any]) -> list[CampaignJob]:
    max_steps = int(config["max_steps"])
    probe_reservation = 4 * int(config["probe_steps"])
    jobs = []
    for condition in config["conditions"]:
        for seed in config["seeds"]:
            for repeat in range(1, int(config.get("repeats", 1)) + 1):
                for method in config["methods"]:
                    possible_probe = method != "passive"
                    reservation = 2 * max_steps + (probe_reservation if possible_probe else 0)
                    jobs.append(
                        CampaignJob(
                            job_id=(
                                f"{condition['condition_id']}__seed{seed}__"
                                f"r{repeat}__{method}"
                            ),
                            method=method,
                            condition_id=condition["condition_id"],
                            seed=int(seed),
                            repeat=repeat,
                            reserved_environment_steps=reservation,
                        )
                    )
    return jobs


def write_summary(ledger: CampaignLedger, path: Path) -> None:
    outcomes = ledger.outcomes()
    rows = []
    for method in METHODS:
        selected = [item for item in outcomes if f"__{method}" in item.job_id]
        if not selected:
            continue
        rows.append(
            {
                "method": method,
                "jobs": len(selected),
                "verification_successes": sum(item.success for item in selected),
                "verification_success_rate": sum(item.success for item in selected) / len(selected),
                "mean_environment_steps": mean(item.environment_steps for item in selected),
                "mean_probe_environment_steps": mean(
                    int(item.metrics.get("probe_environment_steps", 0)) for item in selected
                ),
                "mean_final_object_goal_distance": mean(
                    float(item.metrics["final_object_goal_distance"]) for item in selected
                ),
            }
        )
    atomic_csv(path, rows)


def main() -> int:
    args = parse_args()
    try:
        config = load_config(args.config)
        output_dir = (
            args.output_dir.expanduser().resolve()
            if args.output_dir
            else PROJECT_ROOT / "outputs" / "campaigns" / config["campaign_id"]
        )
        snapshot = output_dir / "config.snapshot.json"
        if snapshot.exists():
            existing = json.loads(snapshot.read_text(encoding="utf-8"))
            if existing != config:
                raise ValueError("output directory contains a different config snapshot")
        else:
            atomic_json(snapshot, config)

        conditions = {row["condition_id"]: row for row in config["conditions"]}
        budget = CampaignBudget(**config["budget"])
        ledger = CampaignLedger(output_dir / "run_ledger.jsonl")
        summary = run_campaign(
            build_jobs(config),
            ledger=ledger,
            budget=budget,
            executor=MetaWorldCampaignExecutor(config, output_dir, conditions),
        )
        write_summary(ledger, output_dir / "summary.csv")
        atomic_json(output_dir / "status.json", asdict(summary))
        print(json.dumps(asdict(summary), indent=2))
        print(f"ledger: {(output_dir / 'run_ledger.jsonl').resolve()}")
        print(f"summary: {(output_dir / 'summary.csv').resolve()}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
