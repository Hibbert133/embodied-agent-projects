"""Independently audit and report a completed crossed-context experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.probemem.evidence_persistence import CONDITIONS, METHODS, summarize_crossed


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verify_records(decisions, outcomes, provenance, seeds):
    if len(decisions) != 5 * len(seeds):
        raise ValueError("incomplete decision population")
    events = decisions + outcomes
    if sorted(r["sequence"] for r in events) != list(range(1, len(events) + 1)):
        raise ValueError("missing or duplicate event sequence")
    if any(any(r.get(k) != v for k, v in provenance.items()) for r in events):
        raise ValueError("record provenance mismatch")
    decisions_by_sequence = {r["sequence"]: r for r in decisions}
    branches = {}
    for seed in seeds:
        ds = [r for r in decisions if r["seed"] == seed]
        os = [r for r in outcomes if r["seed"] == seed]
        if len(ds) != 5 or len(os) != 32 or max(r["sequence"] for r in ds) >= min(r["sequence"] for r in os):
            raise ValueError("not all plans precede all target outcomes")
        if {r.get("source_context_oracle") for r in ds if "source_context_oracle" in r} != set(CONDITIONS):
            raise ValueError("decision contexts incomplete")
        if len({r["initial_state_hash"] for r in os}) != 1:
            raise ValueError("task reset mismatch")
        for row in os:
            decision = decisions_by_sequence.get(row["decision_sequence"])
            if decision is None or decision["seed"] != seed:
                raise ValueError("decision association mismatch")
            if row["method"] == "UNCORRECTED":
                if decision.get("method") != "UNCORRECTED" or row["logical_probe_steps"] != 0:
                    raise ValueError("control decision mismatch")
            elif decision.get("source_context_oracle") != row["source_context_oracle"] or row["logical_probe_steps"] != 64:
                raise ValueError("source decision mismatch")
            if type(row["steps"]) is not int or not 0 <= row["steps"] <= 500:
                raise ValueError("task budget violation")
            if row["steps"] + row["logical_probe_steps"] > 564:
                raise ValueError("logical budget violation")
            if row["success"] != (row["verification_status"] == "ACCEPTED"):
                raise ValueError("success/status mismatch")
            if row["plan_executable"] != decision["plan"]["requires_fresh_verification"]:
                raise ValueError("plan execution flag mismatch")
            if not row["plan_executable"] and (row["success"] or row["steps"] != 0):
                raise ValueError("nonexecuted plan cannot recover")
            key = row["branch_id"]
            fingerprint = (seed, row["target_context_oracle"], row["success"], row["steps"],
                           row["verification_status"], row["initial_state_hash"])
            if row["reused"]:
                if row["method"] != "UNCORRECTED" or branches.get(key) != fingerprint:
                    raise ValueError("invalid cache association")
            else:
                if key in branches:
                    raise ValueError("duplicate physical branch")
                branches[key] = fingerprint
    summarize_crossed(outcomes, seeds, samples=1)  # duplicate and full-factorial checks
    return {"decision_records": len(decisions), "logical_outcomes": len(outcomes),
            "unique_branches": len(branches), "reused_control_rows": sum(r["reused"] for r in outcomes),
            "chronology_reset_provenance_cache_budget_checks": "PASSED"}


def analyze(run_dir):
    manifest = json.loads((run_dir / "manifest.json").read_text())
    status = json.loads((run_dir / "status.json").read_text())
    summary = json.loads((run_dir / "summary.json").read_text())
    provenance = {k: manifest[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    body = {k: v for k, v in manifest.items() if k != "manifest_id"}
    if hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != manifest["manifest_id"]:
        raise ValueError("manifest hash mismatch")
    for artifact in (status, summary):
        if any(artifact[k] != v for k, v in provenance.items()):
            raise ValueError("summary identity mismatch")
    if status["status"] not in {"COMPLETED_FEASIBILITY_PASS", "COMPLETED_FEASIBILITY_FAILED"}:
        raise ValueError("only completed runs can be analyzed")
    for path, sha in manifest["input_sha256"].items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != sha:
            raise ValueError(f"frozen input changed: {path}")
    config = manifest["config"]
    seeds = list(range(config["seed_start"], config["seed_start"] + config["num_seeds"]))
    if status["complete_seeds"] != seeds or status["api_calls"] or status["memory_writes"]:
        raise ValueError("completion or scope mismatch")
    decisions, outcomes = rows(run_dir / "decisions.jsonl"), rows(run_dir / "outcomes.jsonl")
    audit = verify_records(decisions, outcomes, provenance, seeds)
    rebuilt = summarize_crossed(outcomes, seeds, samples=config["bootstrap_samples"], bootstrap_seed=config["bootstrap_seed"])
    if any(summary[k] != value for k, value in rebuilt.items()):
        raise ValueError("registered statistics do not reproduce")
    physical = [r for r in outcomes if not r["reused"]]
    if sum(r["steps"] for r in physical) != status["physical_task_steps"]:
        raise ValueError("physical cost mismatch")
    if sum(r["steps"] > 0 for r in physical) != status["physical_task_rollouts"]:
        raise ValueError("physical rollout count mismatch")
    if sum(r.get("agent_evidence", {}).get("probe_environment_steps", 0) for r in decisions) != status["probe_steps"]:
        raise ValueError("probe cost mismatch")
    tables = []
    for method in METHODS:
        for coupling in ("aligned", "independent"):
            selected = [r for r in outcomes if r["method"] == method and
                        (coupling == "independent" or r["source_context_oracle"] == r["target_context_oracle"])]
            tables.append({"method": method, "coupling": coupling, "logical_cases": len(selected),
                "successful": sum(r["success"] for r in selected),
                "success_rate": statistics.fmean(r["success"] for r in selected),
                "mean_logical_steps": statistics.fmean(r["steps"] + r["logical_probe_steps"] for r in selected)})
    return {**provenance, "status": status["status"], "audit": audit, "statistics": rebuilt,
            "table": tables, "physical_task_steps": status["physical_task_steps"],
            "probe_steps": status["probe_steps"], "physical_task_rollouts": status["physical_task_rollouts"],
            "source_artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in run_dir.iterdir() if p.is_file()}}


def render(result):
    text = ["# Evidence persistence: crossed-context result", "", f'Status: `{result["status"]}`', ""]
    text += [f'- {k}: `{result[k]}`' for k in ("experiment_run_id", "manifest_id", "source_git_commit")]
    text += ["", "Evaluator-only task-success experiment; all task states included. Not failure recovery or an online agent evaluation.",
             "", "| Method | Coupling | Success / logical cases | Rate | Mean logical steps |", "|---|---|---:|---:|---:|"]
    for row in result["table"]:
        text.append(f'| {row["method"]} | {row["coupling"]} | {row["successful"]}/{row["logical_cases"]} | '
                    f'{row["success_rate"]:.1%} | {row["mean_logical_steps"]:.2f} |')
    stats = result["statistics"]
    text += ["", f'Primary coupling interaction: **{stats["means"]["interaction"]:+.2%}**; '
             f'95% task-cluster bootstrap interval **[{stats["interaction_cluster_bootstrap_95"][0]:.2%}, '
             f'{stats["interaction_cluster_bootstrap_95"][1]:.2%}]**.', "",
             f'The independent sample unit is the task seed ({stats["task_clusters"]} clusters), not the 512 logical rows. '
             'The independent-context estimator includes the diagonal. The source-independent control has zero coupling effect.', "",
             f'Physical execution: {result["physical_task_rollouts"]} task rollouts, {result["physical_task_steps"]} task steps '
             f'and {result["probe_steps"]} probe steps. Logical control rows reuse target rollouts with an explicit branch ID.', "",
             'Independent audit: chronology, reset identity, manifest/source hashes, cached branches, complete factorial population, '
             'budgets, and registered statistics reproduced. No API calls or memory writes.', "",
             'This is development feasibility for evidence transport. It does not establish a novel algorithm, selective acquisition, '
             'memory improvement, unseen-task generalization, or paper readiness.', ""]
    return "\n".join(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, target = args.run_dir.resolve(), args.output.resolve()
    if target == source or source in target.parents:
        raise ValueError("write analysis outside immutable collection")
    result = analyze(source)
    target.mkdir(parents=True, exist_ok=False)
    (target / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (target / "report.md").write_text(render(result), encoding="utf-8")
    print(render(result))
