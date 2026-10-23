"""Independent raw-row fees, denominators and stratified-stream statistics."""
import argparse
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_strong_chronological_reference_v1 as io
from scripts.audit_strong_chronological_reference_v1 import lines

OLD = {"ALWAYS16_OLD", "PASSIVE_RECENT8", "PASSIVE8_KEEP", "PASSIVE64_PERIODIC16_KEEP"}
CONTRASTS = (("PASSIVE64_PERIODIC16_KEEP", "ALWAYS8"), ("PASSIVE8_KEEP", "PASSIVE_RECENT8"),
             ("PASSIVE64_PERIODIC16_KEEP", "PASSIVE8_KEEP"), ("TASK_HISTORY_IVR4", "TASK_IVR4"), ("TASK_HISTORY_IVR4", "UNCERTAINTY4"))


def row_from_raw(record, spec):
    before, after = record["state_before"]["cache"], record["state_after"]["cache"]
    sources, source = {}, None
    for d in record["decisions"]:
        action = d["action"]
        if action in {"RUN_POINT", "ACCEPT_UPDATE"}: source = record["episode"]
        elif action in {"START_CACHED", "RUN_CACHED", "PASSIVE8"}: source = before["source_episode"] if before else None
        elif action in {"RUN_IDENTITY", "START_IDENTITY"}: source = None
        sources[d["sequence"]] = source
    stale = 0
    for step in record["trace"]:
        origin = sources[step["decision_sequence"]]
        if step["raw_policy"] is not None and origin is not None:
            stale += spec["cases"][origin]["fault_oracle"] != spec["cases"][record["episode"]]["fault_oracle"]
    queries = record["outcome"].get("policy_queries")
    if queries is None:
        queries = len([s for s in record["trace"] if s["raw_policy"] is not None])+len([d for d in record["decisions"][1:] if d["at_host_calls"] == 4])
    history_queries = 0
    for d in record["decisions"]:
        if d.get("check") and d["check"].get("ivr"):
            history_queries += d["check"]["ivr"].get("past_policy_queries", 0)
    return {**{k: record[k] for k in (*io.IDENTITY, "phase", "stream", "episode", "seed", "task", "method")},
        "family_oracle": spec["family_oracle"], "schedule_oracle": spec["schedule_oracle"], **record["outcome"],
        "policy_queries": queries, "cache_writes": int(after is not None and after["source_episode"] == record["episode"]),
        "cache_clears": int(before is not None and after is None), "stale_cached_policy_steps_oracle": stale,
        "rejected_passive_updates": len([d for d in record["decisions"] if d["action"] == "REJECT_UPDATE_KEEP"]),
        "accepted_passive_updates": len([d for d in record["decisions"] if d["action"] == "ACCEPT_UPDATE"]),
        "reuse_cases": int(any(d["action"] in {"START_CACHED", "RUN_CACHED"} for d in record["decisions"])),
        "history_queries_used_at_check": history_queries}


def reconstruct(rows, manifest, phase):
    specs, methods = manifest["population_oracle"][phase], manifest["config"]["methods"]
    def cell(part):
        n = len(part)
        return {"cases": n, "successes": len([r for r in part if r["success"]]), "stops": len([r for r in part if r["stopped"]]),
            "mean_deadline_loss": sum(r["deadline_loss"] for r in part)/n, "mean_total_steps": sum(r["total_steps"] for r in part)/n,
            "mean_fixed_probe_steps": sum(r["fixed_probe_steps"] for r in part)/n}
    result = {}
    for method in methods:
        part = [r for r in rows if r["method"] == method]
        fee, resets = (0, 0) if method == "NO_PROBE" else (21010, 288) if method in OLD else (3840, 480)
        result[method] = {**cell(part), "offline_source_steps": fee, "offline_source_controlled_resets": resets,
            "mean_amortized_actual_steps": (sum(r["total_steps"] for r in part)+fee)/len(part),
            **{name: sum(r[name] for r in part) for name in ("online_parameter_fits", "optimizer_nfev", "policy_queries", "cache_writes", "cache_clears", "stale_cached_policy_steps_oracle", "accepted_passive_updates", "rejected_passive_updates", "history_queries_used_at_check")},
            "by_task": {t: cell([r for r in part if r["task"] == t]) for t in ("push-v3", "reach-v3", "door-open-v3")},
            "by_factor": [{"family_oracle": f, "schedule_oracle": z, **cell([r for r in part if (r["family_oracle"], r["schedule_oracle"]) == (f, z)])}
                for f, z in sorted({(s["family_oracle"], s["schedule_oracle"]) for s in specs})]}
    contrasts = []
    if phase == "MAIN":
        ids = {s["stream"]: s for s in specs}; indexed = {(r["stream"], r["episode"], r["method"]): r for r in rows}
        groups = [[s["stream"] for s in specs if (s["family_oracle"], s["schedule_oracle"]) == (f, z)] for f in ("BIAS", "COLUMN_Y", "DEADZONE") for z in ("UNCHANGED", "ABRUPT", "GRADUAL")]
        generator = np.random.default_rng(20261020)
        draws_by_group = [generator.choice(g, (10000, 2)) for g in groups]
        for number, (method, reference) in enumerate(CONTRASTS):
            totals = {s: [sum(int(indexed[s, e, method][field])-int(indexed[s, e, reference][field]) for e in range(12))
                for field in ("success", "deadline_loss", "total_steps", "fixed_probe_steps")] for s in ids}
            matrix = np.array([totals[s] for s in sorted(ids)])
            bootstrap = np.zeros((10000, 4))
            for draws in draws_by_group:
                bootstrap += matrix[draws].sum(axis=1)
            intervals = np.quantile(bootstrap/216, [.025, .975], axis=0)
            contrasts.append({"method": method, "reference": reference, "role": "PRIMARY" if number == 0 else "SECONDARY_UNADJUSTED",
                "stream_values": (matrix/12).tolist(), "statistics": {label: {"difference": float(matrix[:, j].sum()/216),
                "stratified_stream_percentile_95": intervals[:, j].tolist()} for j, label in enumerate(("success_rate", "deadline_loss", "actual_steps", "probe_steps"))}})
    return {"phase": phase, "methods": result, "contrasts": contrasts, "independent_streams": len(specs),
        "streams_per_stratum": 2 if phase == "MAIN" else 1, "bootstrap_samples": 10000 if phase == "MAIN" else 0,
        "algorithm_novelty_established": False, "physical_probability_qualified": False, "scope": "STRONG_STANDARD_REFERENCE_DEVELOPMENT"}


def audit(path, phase, output):
    if output.exists(): raise FileExistsError("preserve independent statistics")
    manifest, _, _ = io.load(path); folder = path.parent/phase.lower(); summary = io.read(folder/"summary.json")
    raw_audit = io.read(path.parent/(phase.lower()+"_audit")/"audit.json")
    if raw_audit["integrity"] != "PASSED" or raw_audit["summary_sha256"] != io.sha(folder/"summary.json"): raise ValueError("matching physical audit required")
    rows = []
    for spec in manifest["population_oracle"][phase]:
        records = list(lines(folder/f"episodes_{spec['stream']:02}.jsonl.gz"))
        expected = [(c["episode"], method) for c in spec["cases"] for method in manifest["config"]["methods"]]
        if [(r["episode"], r["method"]) for r in records] != expected: raise ValueError("incomplete or reordered method population")
        rows.extend(row_from_raw(record, spec) for record in records)
    if rows != summary["cases"]: raise ValueError("independent raw-case flags differ")
    expected = reconstruct(rows, manifest, phase)
    count, maximum = 0, 0.
    def compare(actual, target):
        nonlocal count, maximum
        if type(target) is dict:
            if set(actual) != set(target): raise ValueError("statistics fields differ")
            for key in target: compare(actual[key], target[key])
        elif type(target) is list:
            if len(actual) != len(target): raise ValueError("statistics list population differs")
            for a, b in zip(actual, target): compare(a, b)
        elif type(target) in (float, int):
            if not np.isfinite(actual) or abs(actual-target) > 1e-10: raise ValueError("independent numeric statistics differ")
            count += 1; maximum = max(maximum, abs(actual-target))
        elif type(target) is bool:
            if actual is not target: raise ValueError("statistics qualification flag differs")
        elif actual != target: raise ValueError("statistics scope or labels differ")
    compare(summary["statistics"], expected)
    result = {**{k: manifest[k] for k in io.IDENTITY}, "phase": phase, "integrity": "PASSED", "executions": len(rows),
        "numeric_fields_checked": count, "max_absolute_difference": maximum, "summary_sha256": io.sha(folder/"summary.json"),
        "record_audit_sha256": io.sha(path.parent/(phase.lower()+"_audit")/"audit.json"), "script_sha256": io.sha(Path(__file__)),
        "new_environment_steps": 0, "new_api_calls": 0, "scope": "Independent raw-case flags, all denominators/fees, task/factor cells and clustered contrasts; shares source loading and parser only."}
    output.parent.mkdir(parents=True, exist_ok=True); io.write(output, result, exclusive=True)
    print(result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--phase", choices=("SMOKE", "MAIN"), required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); audit(args.manifest.resolve(), args.phase, args.output.resolve())
