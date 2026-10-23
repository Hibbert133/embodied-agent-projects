"""Audit acquisition by replaying only charged prefixes and prior accepted caches."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_evidence_refresh import summarize, units, CACHED_METHODS
from scripts.run_evidence_persistence import manifest_digest
from src.autoresearch import RecoveryPolicyConfig
from src.probemem.evidence_refresh import METHODS, Measurement, decide, accepted_update
from src.probe.directional import PROBE_DIRECTIONS, ProbeResult, estimate_planar_bias


def read_rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def normalized(value):
    return json.loads(json.dumps(value))


def verify_and_replay(manifest, probes, decisions, outcomes, cache_writes, recovery):
    c = manifest["config"]
    identity = {k: manifest[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    design = units(c)
    if len(probes) != len(design) or len(decisions) != len(design) * len(METHODS):
        raise ValueError("incomplete probe or decision population")
    events = probes + decisions + outcomes
    if sorted(r["sequence"] for r in events) != list(range(1, len(events) + 1)):
        raise ValueError("missing or duplicate event sequence")
    if any(any(r.get(k) != v for k, v in identity.items()) for r in events + cache_writes):
        raise ValueError("record provenance mismatch")
    decisions_by_key, outcomes_by_key = {}, {}
    for row in decisions:
        key = (row["stream"], row["episode"], row["decision"]["method"])
        if key in decisions_by_key:
            raise ValueError("duplicate decision")
        decisions_by_key[key] = row
    for row in outcomes:
        key = (row["stream"], row["episode"], row["method"])
        if key in outcomes_by_key:
            raise ValueError("duplicate outcome")
        outcomes_by_key[key] = row
    expected = {(u["stream"], u["episode"], m) for u in design for m in METHODS}
    if set(decisions_by_key) != expected or set(outcomes_by_key) != expected:
        raise ValueError("method population mismatch")
    caches, reconstructed_writes, branches = {}, [], {}
    reasons = Counter()
    mismatch_by_prefix = Counter()
    method_changes = {m: Counter() for m in METHODS}
    physical_task_steps = physical_rollouts = 0
    for unit, probe in zip(design, probes):
        if any(probe.get(k) != v for k, v in unit.items()):
            raise ValueError("probe schedule mismatch")
        s, e = unit["stream"], unit["episode"]
        if e == 0:
            caches = {m: None for m in METHODS}
        if len(probe["repetitions"]) != 4:
            raise ValueError("missing probe repetition")
        measurements = []
        probe_start = None
        for repeat, record in enumerate(probe["repetitions"]):
            if record["repeat"] != repeat:
                raise ValueError("probe repetition order mismatch")
            transitions = [ProbeResult(**r) for r in record["transitions"]]
            if len(transitions) != 4 or sum(r.steps for r in transitions) != 16:
                raise ValueError("probe step count mismatch")
            for transition, (direction, vector) in zip(transitions, PROBE_DIRECTIONS):
                if transition.seed != unit["seed"] or transition.direction != direction or transition.steps != 4:
                    raise ValueError("probe seed/direction mismatch")
                if len(transition.commanded_action) != 4 or any(not math.isclose(x, .2 * float(v), abs_tol=1e-7)
                        for x, v in zip(transition.commanded_action, vector)):
                    raise ValueError("probe command mismatch")
                start = tuple(transition.start_gripper_position)
                if probe_start is None:
                    probe_start = start
                if start != probe_start:
                    raise ValueError("probe reset mismatch")
                if any(not math.isclose(end - begin, delta, abs_tol=1e-12) for begin, end, delta in
                       zip(start, transition.end_gripper_position, transition.gripper_displacement)):
                    raise ValueError("probe displacement mismatch")
            inferred = estimate_planar_bias(transitions).to_dict()
            if normalized(inferred) != record["inference"]:
                raise ValueError("probe inference does not reproduce")
            measurements.append(Measurement.from_mapping({k: inferred[k] for k in
                ("estimated_drift_per_step", "axis_response_gain", "residual")}))
        ds = [decisions_by_key[s, e, m] for m in METHODS]
        os = [outcomes_by_key[s, e, m] for m in METHODS]
        if not probe["sequence"] < min(r["sequence"] for r in ds) <= max(r["sequence"] for r in ds) < min(r["sequence"] for r in os):
            raise ValueError("all decisions must precede all current outcomes")
        replayed = {}
        for method in METHODS:
            row = decisions_by_key[s, e, method]
            if row["seed"] != unit["seed"]:
                raise ValueError("decision seed mismatch")
            before = normalized(asdict(caches[method])) if caches[method] else None
            if before != row["cache_before"]:
                raise ValueError("cache does not match prior selected accepted evidence")
            prefix = row["consumed_measurements"]
            if prefix != normalized([asdict(x) for x in measurements[:len(prefix)]]):
                raise ValueError("consumed prefix does not match current observations")
            consumed = []

            def read_next():
                if len(consumed) >= len(prefix):
                    raise ValueError("replay requested an uncharged suffix")
                sample = measurements[len(consumed)]
                consumed.append(sample)
                return sample

            d = decide(method, read_next, cache=caches[method], recovery=recovery, stream=s, episode=e,
                       decision_sequence=row["sequence"])
            if normalized(asdict(d)) != row["decision"] or len(consumed) != len(prefix):
                raise ValueError("decision cannot be reproduced from charged prior-only inputs")
            replayed[method] = d
        for method in METHODS:
            d = replayed[method]
            row = outcomes_by_key[s, e, method]
            if any(row.get(k) != v for k, v in unit.items()):
                raise ValueError("outcome schedule mismatch")
            if row["decision_sequence"] != decisions_by_key[s, e, method]["sequence"]:
                raise ValueError("outcome/decision association mismatch")
            if row["initial_state_hash"] != probe["initial_state_hash"]:
                raise ValueError("task reset mismatch")
            if row["probe_steps"] != 16 * d.repetitions or type(row["steps"]) is not int or not 0 <= row["steps"] <= 500:
                raise ValueError("logical budget mismatch")
            if row["success"] != (row["verification_status"] == "ACCEPTED"):
                raise ValueError("success/status mismatch")
            if row["plan_executable"] != d.plan.requires_fresh_verification:
                raise ValueError("plan execution mismatch")
            if not row["plan_executable"] and (row["steps"] or row["success"]):
                raise ValueError("nonexecuted plan cannot succeed")
            branch = hashlib.sha256(json.dumps([unit["seed"], d.plan.execution_signature()]).encode()).hexdigest()[:20]
            if branch != row["branch_id"]:
                raise ValueError("branch identity mismatch")
            fingerprint = (row["success"], row["verification_status"], row["steps"], row["initial_state_hash"])
            if row["reused_branch"]:
                if branches.get(branch) != fingerprint:
                    raise ValueError("shared branch outcome mismatch")
            else:
                if branch in branches:
                    raise ValueError("duplicate physical branch")
                branches[branch] = fingerprint
                physical_task_steps += row["steps"]
                physical_rollouts += row["steps"] > 0
            if method in CACHED_METHODS:
                updated = accepted_update(d, caches[method], stream=s, episode=e,
                    outcome_sequence=row["sequence"], status=row["verification_status"])
                if updated is not caches[method]:
                    reconstructed_writes.append({**identity, "cache": normalized(asdict(updated)),
                                                  "fresh_status": row["verification_status"]})
                caches[method] = updated
        candidate, fixed = replayed["DECISION_STABILITY"], replayed["FIXED_64"]
        for method, decision in replayed.items():
            if decision.plan.execution_signature() != fixed.plan.execution_signature():
                left, right = outcomes_by_key[s, e, method], outcomes_by_key[s, e, "FIXED_64"]
                label = "win" if left["success"] and not right["success"] else "loss" if right["success"] and not left["success"] else "tie"
                method_changes[method][label] += 1
        reasons[candidate.reason] += 1
        if candidate.plan.execution_signature() != fixed.plan.execution_signature():
            left, right = outcomes_by_key[s, e, "DECISION_STABILITY"], outcomes_by_key[s, e, "FIXED_64"]
            label = "win" if left["success"] and not right["success"] else "loss" if right["success"] and not left["success"] else "tie"
            mismatch_by_prefix[f"{candidate.repetitions}_repeats_{label}"] += 1
    if reconstructed_writes != cache_writes:
        raise ValueError("cache write log does not reproduce exactly")
    return {"independent_streams": c["streams"], "episodes": len(design), "replayed_decisions": len(decisions),
            "accepted_cache_writes": len(cache_writes), "physical_task_steps": physical_task_steps,
            "physical_task_rollouts": physical_rollouts, "physical_probe_steps": len(probes) * 64,
            "candidate_reasons": dict(reasons), "candidate_signature_changes_vs_fixed64": dict(mismatch_by_prefix),
            "method_signature_changes_vs_fixed64": {m: dict(v) for m, v in method_changes.items()},
            "prior_only_prefix_cache_chronology_budget_reset_checks": "PASSED"}


def analyze(run_dir):
    manifest = json.loads((run_dir / "manifest.json").read_text())
    status = json.loads((run_dir / "status.json").read_text())
    summary = json.loads((run_dir / "summary.json").read_text())
    if manifest_digest(manifest) != manifest["manifest_id"]:
        raise ValueError("manifest hash mismatch")
    identity = {k: manifest[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    for artifact in (status, summary):
        if any(artifact[k] != v for k, v in identity.items()):
            raise ValueError("summary identity mismatch")
    if status["status"] not in {"COMPLETED_FEASIBILITY_PASS", "COMPLETED_FEASIBILITY_FAILED"}:
        raise ValueError("run is not complete")
    for name, sha in manifest["input_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
            raise ValueError(f"frozen input changed: {name}")
    c = manifest["config"]
    if manifest["units"] != units(c):
        raise ValueError("manifest schedule mismatch")
    recovery = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / c["recovery_config"]).read_text()))
    outcomes = read_rows(run_dir / "outcomes.jsonl")
    audit = verify_and_replay(manifest, read_rows(run_dir / "evaluator_probes.jsonl"),
        read_rows(run_dir / "decisions.jsonl"), outcomes, read_rows(run_dir / "cache_writes.jsonl"), recovery)
    for key in ("physical_task_steps", "physical_task_rollouts", "physical_probe_steps"):
        if audit[key] != status[key]:
            raise ValueError(f"physical accounting mismatch: {key}")
    if status["cache_writes"] != audit["accepted_cache_writes"] or status["api_calls"] or status["complete_episodes"] != 96:
        raise ValueError("completion, scope, or cache count mismatch")
    rebuilt = summarize(outcomes, c)
    if any(summary[k] != v for k, v in rebuilt.items()):
        raise ValueError("registered statistics fail reproduction")
    expected_status = "COMPLETED_FEASIBILITY_PASS" if rebuilt["performance_gate_passed"] else "COMPLETED_FEASIBILITY_FAILED"
    if status["status"] != expected_status or summary["status"] != expected_status:
        raise ValueError("promotion status mismatch")
    if audit["physical_task_steps"] + audit["physical_probe_steps"] > c["maximum_physical_steps"]:
        raise ValueError("physical budget exceeded")
    return {**identity, "status": expected_status, "audit": audit, "statistics": rebuilt,
            "source_artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in run_dir.iterdir() if p.is_file()}}


def render(result):
    lines = ["# Prospective evidence refresh: strong-baseline result", "", f'Status: `{result["status"]}`', ""]
    lines += [f'- {k}: `{result[k]}`' for k in ("experiment_run_id", "manifest_id", "source_git_commit")]
    lines += ["", "Eight independent chronological streams; all 96 task states included. Task success, not initial-failure recovery.",
        "", "| Method | Success / 96 | Mean probe steps | Mean total path steps | Stationary / 48 | Abrupt / 48 |",
        "|---|---:|---:|---:|---:|---:|"]
    for method, row in result["statistics"]["methods"].items():
        lines.append(f'| {method} | {row["successful"]} | {row["mean_probe_steps"]:.2f} | {row["mean_path_steps"]:.2f} | '
                     f'{row["stationary_successful"]} | {row["abrupt_successful"]} |')
    contrast = result["statistics"]["candidate_minus_baseline"]["FIXED_64"]
    lines += ["", f'Candidate minus FIXED_64: {100*contrast["difference"]:+.2f} percentage points; '
              f'95% stream-bootstrap interval [{100*contrast["cluster_bootstrap_95"][0]:.2f}, {100*contrast["cluster_bootstrap_95"][1]:.2f}].',
              f'Probe saving vs FIXED_64: {result["statistics"]["probe_saving_vs_fixed64"]:.1%}.',
              f'Dominating baselines: {result["statistics"]["dominating_baselines"]}.',
              f'Frozen performance gates: {result["statistics"]["performance_gates"]}.', "",
              f'All {result["audit"]["replayed_decisions"]} decisions and {result["audit"]["accepted_cache_writes"]} '
              'accepted cache writes reproduced from charged prefixes and strictly prior method-owned state. '
              'Probe inference was recomputed from visible transitions; source hashes, sequence, branch, cost, and reset audits passed.', "",
              'This development test does not establish calibrated confidence, novelty, unseen-task generalization, or publication readiness.', ""]
    lines += ["## Paired comparisons", "", "All intervals resample eight whole streams. Comparisons beyond the frozen gate are descriptive; no multiplicity-adjusted claim.", "",
              "| Candidate minus baseline | Difference (pp) | 95% stream interval (pp) |",
              "|---|---:|---:|"]
    for method, row in result["statistics"]["candidate_minus_baseline"].items():
        low, high = row["cluster_bootstrap_95"]
        lines.append(f'| {method} | {100*row["difference"]:+.2f} | [{100*low:.2f}, {100*high:.2f}] |')
    lines += ["", "## Acquisition and action diagnostics", "",
              "These are post-collection descriptions, not new selection rules or tuned thresholds.", "",
              "| Method | 0 repeats | 1 repeat | 2 repeats | 3 repeats | 4 repeats | Different action vs fixed 64 (win/loss/tie) |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for method, row in result["statistics"]["methods"].items():
        counts = " | ".join(str(row["prefix_counts"][str(k)]) for k in range(5))
        changes = result["audit"]["method_signature_changes_vs_fixed64"][method]
        wlt = "/".join(str(changes.get(k, 0)) for k in ("win", "loss", "tie"))
        lines.append(f'| {method} | {counts} | {wlt} |')
    lines += ["", f'Candidate stopping reasons: `{result["audit"]["candidate_reasons"]}`.', "",
              f'Physical collection: {result["audit"]["physical_task_rollouts"]} task rollouts, '
              f'{result["audit"]["physical_task_steps"]} task steps and {result["audit"]["physical_probe_steps"]} probe steps.', ""]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.run_dir.resolve(), args.output.resolve()
    if output == source or source in output.parents:
        raise ValueError("audit output must be outside immutable collection")
    result = analyze(source)
    output.mkdir(parents=True, exist_ok=False)
    (output / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render(result), encoding="utf-8")
    print(render(result))
