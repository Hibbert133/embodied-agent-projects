"""Independent raw-case counts, fees, censoring and stratified stream intervals."""
import argparse
import gzip
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import run_chronological_cache_reference as source


def reconstruct(manifest, phase, raw_records):
    specs = manifest["population_oracle"][phase]; methods = tuple(manifest["config"]["methods"])
    spec_index = {s["stream"]: s for s in specs}; rows = []
    for record in raw_records:
        stream = spec_index[record["stream"]]; cache = record["state_before"]["cache"]; updated = record["state_after"]["cache"]
        stale = cache is not None and stream["cases"][cache["source_episode"]]["fault_oracle"] != stream["cases"][record["episode"]]["fault_oracle"]
        decisions = {d["sequence"]: d for d in record["decisions"]}
        row = {**{key: record[key] for key in (*source.IDENTITY, "phase", "stream", "episode", "task", "method", "seed")},
               "family_oracle": stream["family_oracle"], "schedule_oracle": stream["schedule_oracle"], **record["outcome"],
               "cache_writes": int(updated is not None and updated["source_episode"] == record["episode"]),
               "cache_clears": int(cache is not None and updated is None),
               "reuse_cases": int(any(d["action"] == "RUN_CACHED" for d in record["decisions"])),
               "requested_refit": int(any(d["action"] in ("PROBE8", "PROBE16", "REFRESH8", "PASSIVE8") for d in record["decisions"])),
               "stale_cached_policy_steps_oracle": sum(stale and decisions[r["decision_sequence"]]["action"] in ("RUN_CACHED", "PASSIVE8") for r in record["trace"]),
               "same_mapping_refresh_cases_oracle": int(cache is not None and not stale and any(d["action"] == "REFRESH8" for d in record["decisions"]))}
        rows.append(row)
    index = {(r["stream"], r["episode"], r["method"]): r for r in rows}
    expected = {(s["stream"], c["episode"], method) for s in specs for c in s["cases"] for method in methods}
    if set(index) != expected or len(index) != len(rows): raise ValueError("independent full population mismatch")
    cells = {}
    for method in methods:
        part = [r for r in rows if r["method"] == method]
        fee, resets = (0, 0) if method == "NO_PROBE" else (21010, 288) if method in ("PASSIVE_RECENT8", "ALWAYS16_OLD") else (3840, 480)
        cell = {"cases": len(part), "successes": sum(int(r["success"]) for r in part), "stops": sum(int(r["stopped"]) for r in part)}
        for field in ("deadline_loss", "total_steps", "fixed_probe_steps", "policy_measure_steps"):
            cell["mean_"+field] = sum(r[field] for r in part)/len(part)
        for field in ("online_parameter_fits", "optimizer_nfev", "cache_writes", "cache_clears", "reuse_cases", "stale_cached_policy_steps_oracle", "same_mapping_refresh_cases_oracle"):
            cell[field] = sum(r[field] for r in part)
        cell.update(offline_source_steps=fee, offline_source_controlled_resets=resets, mean_amortized_actual_steps=(sum(r["total_steps"] for r in part)+fee)/len(part))
        cell["by_task"] = {}
        for task in manifest["config"]["tasks"]:
            target = [r for r in part if r["task"] == task]
            cell["by_task"][task] = {"cases": len(target), "successes": sum(r["success"] for r in target), "mean_deadline_loss": sum(r["deadline_loss"] for r in target)/len(target)}
        cell["by_factor"] = []
        for family, schedule in sorted({(s["family_oracle"], s["schedule_oracle"]) for s in specs}):
            target = [r for r in part if r["family_oracle"] == family and r["schedule_oracle"] == schedule]
            cell["by_factor"].append({"family_oracle": family, "schedule_oracle": schedule, "cases": len(target),
                                      "successes": sum(r["success"] for r in target), "mean_deadline_loss": sum(r["deadline_loss"] for r in target)/len(target)})
        cells[method] = cell
    contrasts = []
    if phase == "MAIN":
        groups = list(dict.fromkeys((s["family_oracle"], s["schedule_oracle"]) for s in specs))
        rng = np.random.default_rng(20261019)
        draws = np.concatenate([rng.choice([s["stream"] for s in specs if (s["family_oracle"], s["schedule_oracle"]) == key], (10000, 4)) for key in groups], axis=1)
        for number, (method, reference) in enumerate((("UNCERTAINTY4", "ALWAYS8"), ("BALANCED4", "UNCERTAINTY4"), ("UNCERTAINTY4", "PLUGIN4"), ("UNCERTAINTY4", "TASK_IVR4"))):
            stream_values = []
            for s in specs:
                stream_values.append([sum(int(index[s["stream"], c["episode"], method][field])-int(index[s["stream"], c["episode"], reference][field]) for c in s["cases"])/12
                                      for field in ("success", "deadline_loss", "total_steps", "fixed_probe_steps")])
            values = np.array(stream_values); distribution = values[draws].mean(axis=1)
            bounds = np.percentile(distribution, [2.5, 97.5], axis=0)
            contrasts.append({"method": method, "reference": reference, "role": "PRIMARY" if number == 0 else "SECONDARY_UNADJUSTED",
                              "stream_values": stream_values, "statistics": {name: {"difference": float(values[:, i].mean()), "stratified_stream_percentile_95": bounds[:, i].tolist()}
                                  for i, name in enumerate(("success_rate", "deadline_loss", "actual_steps", "probe_steps"))}})
    delays = []
    for stream in specs:
        schedule = stream["schedule_oracle"]
        if phase == "SMOKE" or schedule == "GRADUAL": change = 3
        elif schedule == "ABRUPT": change = 6
        else: continue
        for method in methods:
            future = [index[stream["stream"], c["episode"], method] for c in stream["cases"] if c["episode"] >= change]
            fits = [r["episode"] for r in future if r["online_parameter_fits"]]
            verified = [r["episode"] for r in future if r["cache_writes"]]
            delays.append({"stream": stream["stream"], "method": method, "change_episode_oracle": change,
                           "first_new_fit_delay": fits[0]-change if fits else len(stream["cases"])-change, "first_new_fit_right_censored": not fits,
                           "first_verified_source_delay": verified[0]-change if verified else len(stream["cases"])-change, "first_verified_source_right_censored": not verified})
    result = {"phase": phase, "methods": cells, "contrasts": contrasts, "refresh_delays_oracle": delays, "independent_streams": len(specs),
              "strata": 9 if phase == "MAIN" else 1, "streams_per_stratum": 4 if phase == "MAIN" else 1,
              "algorithm_novelty_established": False, "physical_probability_qualified": False, "scope": "STANDARD_REFERENCE_DEVELOPMENT"}
    return rows, result


def compare(actual, expected):
    count = 0; maximum = 0.
    def visit(a, b):
        nonlocal count, maximum
        if isinstance(b, dict):
            if type(a) is not dict or set(a) != set(b): raise ValueError("statistics schema mismatch")
            for key in b: visit(a[key], b[key])
        elif isinstance(b, list):
            if type(a) is not list or len(a) != len(b): raise ValueError("statistics population mismatch")
            for x, y in zip(a, b): visit(x, y)
        elif isinstance(b, (bool, str)) or b is None:
            if a != b: raise ValueError("statistics label mismatch")
        else:
            if not np.isfinite(a) or not np.isclose(a, b, rtol=1e-10, atol=1e-10): raise ValueError("independent statistic differs")
            count += 1; maximum = max(maximum, abs(float(a)-float(b)))
    visit(actual, expected); return count, maximum


def audit(path, phase, output):
    if output.exists(): raise FileExistsError("preserve statistics audit")
    manifest, _, _ = source.load(path); folder = path.parent/phase.lower()
    record_audit = source.read(output.with_name("audit.json"))
    if record_audit["integrity"] != "PASSED" or record_audit["manifest_id"] != manifest["manifest_id"] or record_audit["summary_sha256"] != source.sha(folder/"summary.json"):
        raise ValueError("matching complete record audit required")
    def records():
        for stream in manifest["population_oracle"][phase]:
            with gzip.open(folder/f"episodes_{stream['stream']:02}.jsonl.gz", "rt", encoding="utf-8") as handle:
                for line in handle: yield json.loads(line)
    rows, statistics = reconstruct(manifest, phase, records()); summary = source.read(folder/"summary.json")
    if rows != summary["cases"]: raise ValueError("independently reconstructed rows differ")
    count, difference = compare(summary["statistics"], statistics)
    result = {**{key: manifest[key] for key in source.IDENTITY}, "phase": phase, "integrity": "PASSED", "executions": len(rows),
              "numeric_fields_checked": count, "max_absolute_difference": difference, "summary_sha256": source.sha(folder/"summary.json"),
              "record_audit_sha256": source.sha(output.with_name("audit.json")), "script_sha256": source.sha(Path(__file__)), "new_environment_steps": 0,
              "scope": "Independent row flags, fees, all method/task/factor totals, censoring and stream intervals; shares source-loading only."}
    source.write(output, result, exclusive=True); print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", required=True, type=Path); parser.add_argument("--phase", required=True, choices=("SMOKE", "MAIN")); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); audit(args.manifest.resolve(), args.phase, args.output.resolve())
