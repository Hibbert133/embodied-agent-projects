"""Run the frozen evaluator-only distributional probe-identifiability audit."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_mixed_regime_tuning import MixedRegime  # noqa: E402
from scripts.run_probemem_acr_utility_stability import _compensation_is_constructible  # noqa: E402
from scripts.run_probemem_v2_smoke import _probe_context, _read_jsonl, _run_verification  # noqa: E402
from src.autoresearch import RecoveryPolicyConfig  # noqa: E402
from src.planner.evidence_grounded import first_registered_probe_context, select_grounded_intervention  # noqa: E402
from src.probemem.models import InterventionSkill  # noqa: E402
from src.probemem_sciagent.compensation_probe import summarize_compensation_response  # noqa: E402
from src.probemem_sciagent.probe_identifiability import (  # noqa: E402
    build_distributional_target, build_probe_contrast, candidate_winner_reversal_count,
    roc_auc, spearman_rank_correlation, stratified_auc_bootstrap,
)
from src.probemem_sciagent.probe_registry import run_prefix_records  # noqa: E402
from src.probemem_sciagent.retry_probe import summarize_retry_repeatability  # noqa: E402
from src.reasoning import EvidenceSource, build_structured_evidence_state  # noqa: E402
from src.recovery_agent import PhaseGatedCompensatedPolicy  # noqa: E402
from src.rollout import create_push_environment, create_push_policy, run_episode  # noqa: E402


COMP = InterventionSkill.BOUNDED_PLANAR_COMPENSATION
RETRY = InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    status_path = None
    try:
        manifest, config = _validate(args.manifest.resolve())
        run = args.manifest.resolve().parent
        status_path = run / "run_status.json"
        if status_path.exists():
            raise FileExistsError("distributional audit cannot overwrite or resume")
        _write(status_path, {"status": "RUNNING", "manifest_id": manifest["manifest_id"]})
        regimes = {
            row["regime_id"]: MixedRegime(row["regime_id"], tuple(row["bias"]), float(row["noise_std"]))
            for row in config["regimes"]
        }
        recovery = RecoveryPolicyConfig.from_mapping(
            json.loads((ROOT / config["recovery_policy_config"]).read_text(encoding="utf-8"))
        )
        population: list[dict[str, Any]] = []
        probe_records: list[dict[str, Any]] = []
        candidate_outcomes: list[dict[str, Any]] = []
        cases: list[dict[str, Any]] = []
        operational = initial_units = 0
        for unit in manifest["population_units"]:
            if operational >= int(config["target_operational_cases"]):
                break
            initial_units += 1
            seed = int(unit["environment_seed"])
            regime = regimes[str(unit["regime_id_oracle"])]
            trajectory = run / "initial_trajectories" / f"unit{int(unit['unit_id']):03d}_seed{seed}.jsonl"
            trajectory.parent.mkdir(parents=True, exist_ok=True)
            env = create_push_environment(seed)
            try:
                initial = run_episode(
                    env, create_push_policy(), seed=seed, max_steps=int(config["budget"]["initial_max_steps"]),
                    perturbation=regime.build(), perturbation_seed=int(unit["initial_seed"]),
                    agent_trajectory_path=trajectory,
                )
            finally:
                env.close()
            state = build_structured_evidence_state(
                _read_jsonl(trajectory), evidence_id=f"probe_identifiability_unit{unit['unit_id']}_initial",
                source=EvidenceSource.FAILED_ROLLOUT, attempt_id=0,
            )
            population_row = {
                "unit_id": unit["unit_id"], "seed": seed, "regime_id_oracle": unit["regime_id_oracle"],
                "decision_required": state.decision_required, "eligible": False, "ineligibility_reason": "",
            }
            if not state.decision_required:
                population.append(population_row)
                _flush(run, population, probe_records, candidate_outcomes, cases)
                continue
            mandatory = _probe_context(
                regime, seed, {"registered_probe": config["mandatory_probe"]},
                int(unit["mandatory_probe_seed"]),
            )
            if int(mandatory["probe_environment_steps"]) > int(config["budget"]["mandatory_probe_max_steps"]):
                raise RuntimeError("mandatory probe exceeded budget")
            if not _compensation_is_constructible(seed=seed, probe_context=mandatory, recovery_config=recovery):
                population_row["ineligibility_reason"] = "BOUNDED_COMPENSATION_NOT_CONSTRUCTIBLE"
                population.append(population_row)
                _flush(run, population, probe_records, candidate_outcomes, cases)
                continue
            population_row["eligible"] = True
            population.append(population_row)
            operational += 1
            case_id = f"probe_identifiability_case_{operational:03d}"
            compensation_evidence, compensation_steps = _compensation_probe(
                config=config, unit=unit, seed=seed, case_id=case_id, regime=regime,
                mandatory=mandatory, recovery=recovery,
            )
            retry_evidence, retry_steps = _retry_probe(
                config=config, unit=unit, seed=seed, regime=regime,
            )
            contrast = build_probe_contrast(compensation_evidence, retry_evidence)
            probe_records.append({
                "case_id": case_id, "seed": seed,
                "compensation_probe": asdict(compensation_evidence),
                "retry_probe": asdict(retry_evidence),
                "compensation_probe_steps": compensation_steps,
                "retry_probe_steps": retry_steps,
                **asdict(contrast),
                "evaluator_only": True, "persisted_before_candidate_outcomes": True,
            })
            _flush(run, population, probe_records, candidate_outcomes, cases)
            statuses = {COMP.value: [], RETRY.value: []}
            verification_steps = 0
            for realization, verification_seed in enumerate(unit["verification_seeds"]):
                for skill in (COMP, RETRY):
                    result, execution = _run_verification(
                        seed=seed, fault=regime, skill=skill, probe_context=mandatory,
                        recovery_config=recovery, perturbation_seed=int(verification_seed),
                        max_steps=int(config["budget"]["verification_max_steps_each"]),
                        initial_distance=initial.final_object_goal_distance,
                    )
                    status = str(execution["verification_status"])
                    statuses[skill.value].append(status)
                    verification_steps += int(result.steps)
                    candidate_outcomes.append({
                        "case_id": case_id, "seed": seed, "realization": realization,
                        "candidate_skill": skill.value, "verification_seed": int(verification_seed),
                        "verification_status": status, "environment_steps": int(result.steps),
                        "final_distance": float(result.final_object_goal_distance),
                        "evaluator_only": True, "unavailable_to_agent": True,
                    })
            target = build_distributional_target(
                statuses[COMP.value], statuses[RETRY.value],
                decisive_margin=float(config["distributional_decisive_margin"]),
            )
            total_steps = (
                int(initial.steps) + int(mandatory["probe_environment_steps"])
                + compensation_steps + retry_steps + verification_steps
            )
            if total_steps > int(config["budget"]["maximum_total_steps_per_case"]):
                raise RuntimeError("evaluator case budget exceeded")
            cases.append({
                "case_id": case_id, "seed": seed, "regime_id_oracle": unit["regime_id_oracle"],
                **asdict(contrast), **asdict(target),
                "compensation_statuses": statuses[COMP.value], "retry_statuses": statuses[RETRY.value],
                "candidate_winner_reversal": candidate_winner_reversal_count(
                    statuses[COMP.value], statuses[RETRY.value],
                ),
                "initial_steps": int(initial.steps), "mandatory_probe_steps": int(mandatory["probe_environment_steps"]),
                "micro_probe_steps": compensation_steps + retry_steps,
                "verification_steps": verification_steps, "total_evaluator_steps": total_steps,
            })
            _flush(run, population, probe_records, candidate_outcomes, cases)
            _write(status_path, {
                "status": "RUNNING", "manifest_id": manifest["manifest_id"],
                "initial_units": initial_units, "operational_cases": operational,
            })
            print(f"case={case_id} seed={seed} operational={operational}", flush=True)
        summary = _analyze(
            manifest=manifest, config=config, initial_units=initial_units,
            operational=operational, probe_records=probe_records,
            candidate_outcomes=candidate_outcomes, cases=cases,
        )
        _write(run / "summary.json", summary)
        _write(status_path, summary)
        return 0 if summary["status"] == "COMPLETED_GATE_PASSED" else 2
    except Exception as exc:
        if status_path is not None:
            _write(status_path, {"status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _compensation_probe(
    *, config: Mapping[str, Any], unit: Mapping[str, Any], seed: int, case_id: str,
    regime: Any, mandatory: Mapping[str, Any], recovery: RecoveryPolicyConfig,
) -> tuple[Any, int]:
    plan = select_grounded_intervention(
        plan_id=f"{case_id}_compensation_probe_plan", evidence_id=f"{case_id}_mandatory_probe",
        mechanism_belief="stable_bias", correction_context=first_registered_probe_context(mandatory),
        recovery_config=recovery, evidence_source="registered_probe",
    )
    if not plan.requires_fresh_verification:
        raise ValueError("compensation probe is not constructible")
    records = run_prefix_records(
        env_factory=lambda: create_push_environment(seed),
        policy=PhaseGatedCompensatedPolicy(create_push_policy(), plan.correction, schedule=plan.schedule),
        seed=seed, max_steps=64, perturbation=regime.build(),
        perturbation_seed=int(unit["compensation_probe_seed"]),
    )
    evidence = summarize_compensation_response(
        records, contact_distance=float(config["probe_measurement"]["contact_distance"]),
    )
    return evidence, len(records)


def _retry_probe(
    *, config: Mapping[str, Any], unit: Mapping[str, Any], seed: int, regime: Any,
) -> tuple[Any, int]:
    trials = [
        run_prefix_records(
            env_factory=lambda: create_push_environment(seed), policy=create_push_policy(),
            seed=seed, max_steps=64, perturbation=regime.build(), perturbation_seed=int(random_seed),
        )
        for random_seed in unit["retry_probe_seeds"]
    ]
    evidence = summarize_retry_repeatability(
        trials,
        positive_progress_threshold=float(config["probe_measurement"]["positive_progress_threshold"]),
        severe_failure_threshold=float(config["probe_measurement"]["severe_failure_threshold"]),
    )
    return evidence, sum(len(trial) for trial in trials)


def _analyze(
    *, manifest: Mapping[str, Any], config: Mapping[str, Any], initial_units: int,
    operational: int, probe_records: list[dict[str, Any]],
    candidate_outcomes: list[dict[str, Any]], cases: list[dict[str, Any]],
) -> dict[str, Any]:
    decisive = [row for row in cases if row["decisive_label"] != "NON_DECISIVE"]
    compensation_count = sum(row["decisive_label"] == "COMPENSATION_SUPERIOR" for row in decisive)
    retry_count = sum(row["decisive_label"] == "RETRY_SUPERIOR" for row in decisive)
    auc = None
    interval = (None, None)
    if compensation_count and retry_count:
        labels = [int(row["decisive_label"] == "COMPENSATION_SUPERIOR") for row in decisive]
        scores = [float(row["probe_contrast"]) for row in decisive]
        auc = roc_auc(labels, scores)
        interval = stratified_auc_bootstrap(
            labels, scores, samples=int(config["bootstrap_samples"]), seed=int(config["bootstrap_seed"]),
        )
    correlation = spearman_rank_correlation(
        [float(row["probe_contrast"]) for row in cases],
        [float(row["utility_margin"]) for row in cases],
    ) if len(cases) >= 2 else None
    integrity_reasons = _integrity_violations(
        config=config, probe_records=probe_records,
        candidate_outcomes=candidate_outcomes, cases=cases,
    )
    gate = config["success_gate"]
    passed = (
        operational == int(gate["operational_cases"])
        and len(decisive) >= int(gate["minimum_decisive_cases"])
        and min(compensation_count, retry_count) >= int(gate["minimum_each_decisive_class"])
        and auc is not None and auc >= float(gate["minimum_probe_contrast_auc"])
        and interval[0] is not None and interval[0] > float(gate["minimum_bootstrap_auc_lower_exclusive"])
        and correlation is not None and correlation >= float(gate["minimum_rank_correlation"])
        and len(integrity_reasons) <= int(gate["maximum_integrity_violations"])
    )
    complete = operational >= int(config["minimum_operational_cases"])
    status = "COMPLETED_GATE_PASSED" if passed else ("COMPLETED_GATE_FAILED" if complete else "INCOMPLETE_POPULATION")
    return {
        "status": status, "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"], "initial_units": initial_units,
        "operational_cases": operational, "decisive_cases": len(decisive),
        "compensation_superior_cases": compensation_count, "retry_superior_cases": retry_count,
        "non_decisive_cases": len(cases) - len(decisive),
        "probe_contrast_auc": auc, "probe_contrast_auc_bootstrap_95": list(interval),
        "probe_contrast_utility_margin_spearman": correlation,
        "candidate_winner_reversal_cases": sum(row["candidate_winner_reversal"] for row in cases),
        "integrity_violations": len(integrity_reasons),
        "integrity_violation_reasons": integrity_reasons,
        "api_calls": 0, "agent_decisions": 0, "online_recovery_executions": 0,
        "memory_writes": 0, "hypothesis_updates": 0, "principle_updates": 0,
        "claim_boundary": config["claim_boundary"],
    }


def _integrity_violations(
    *, config: Mapping[str, Any], probe_records: list[dict[str, Any]],
    candidate_outcomes: list[dict[str, Any]], cases: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    probes_by_case = {row["case_id"]: row for row in probe_records}
    outcomes_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in candidate_outcomes:
        outcomes_by_case.setdefault(row["case_id"], []).append(row)
        if row.get("evaluator_only") is not True or row.get("unavailable_to_agent") is not True:
            reasons.append(f"OUTCOME_NOT_ISOLATED:{row['case_id']}")
    realizations = int(config["verification_realizations_per_skill"])
    for case in cases:
        case_id = case["case_id"]
        probe = probes_by_case.get(case_id)
        if probe is None or probe.get("persisted_before_candidate_outcomes") is not True:
            reasons.append(f"OUTCOME_BEFORE_PROBE_RECORD:{case_id}")
        outcomes = outcomes_by_case.get(case_id, [])
        if len(outcomes) != realizations * 2:
            reasons.append(f"INCOMPLETE_CANDIDATE_REALIZATIONS:{case_id}")
            continue
        for realization in range(realizations):
            rows = [row for row in outcomes if row["realization"] == realization]
            if {row["candidate_skill"] for row in rows} != {COMP.value, RETRY.value}:
                reasons.append(f"INVALID_PAIRED_CANDIDATES:{case_id}:{realization}")
            if len({row["verification_seed"] for row in rows}) != 1:
                reasons.append(f"UNMATCHED_RANDOM_REALIZATION:{case_id}:{realization}")
    if len(probes_by_case) != len(probe_records):
        reasons.append("DUPLICATE_PROBE_CASE_ID")
    return reasons


def _flush(
    run: Path, population: list[Any], probe_records: list[Any],
    candidate_outcomes: list[Any], cases: list[Any],
) -> None:
    _write(run / "population.json", population)
    _write(run / "probe_records_evaluator_only.json", probe_records)
    _write(run / "candidate_outcomes_evaluator_only.json", candidate_outcomes)
    _write(run / "distributional_cases.json", cases)
    _write(run / "agent_payloads.json", [])
    _write(run / "memory_writes.json", [])
    _write(run / "hypothesis_updates.json", [])
    _write(run / "principle_updates.json", [])


def _validate(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if _git("status", "--porcelain"):
        raise RuntimeError("distributional audit requires a clean worktree")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    config_path = ROOT / manifest["config_path"]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if hashlib.sha256(config_path.read_bytes()).hexdigest() != manifest["config_sha256"]:
        raise RuntimeError("config hash mismatch")
    canonical = dict(manifest)
    recorded_id = canonical.pop("manifest_id")
    if hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != recorded_id:
        raise RuntimeError("manifest ID mismatch")
    head = _git("rev-parse", "HEAD")
    source = manifest["source_git_commit"]
    ancestry = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "merge-base", "--is-ancestor", source, head], cwd=ROOT,
    )
    if ancestry.returncode != 0:
        raise RuntimeError("manifest source is not an ancestor of HEAD")
    if source != head:
        changed = set(_git("diff", "--name-only", source, head).splitlines())
        allowed = {path.relative_to(ROOT).as_posix()}
        if changed - allowed:
            raise RuntimeError(f"tracked changes after source commit: {sorted(changed - allowed)}")
    for relative, expected in {**manifest["implementation_sha256"], **manifest["input_sha256"]}.items():
        file = ROOT / relative
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"manifest-bound file changed: {relative}")
    return manifest, config


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT,
        check=True, capture_output=True, text=True,
    ).stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
