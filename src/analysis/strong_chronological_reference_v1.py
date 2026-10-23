"""Complete-population standard-reference statistics with stream clustering."""
import numpy as np
from src.rollout.chronological_faults import FAMILIES, SCHEDULES, TASKS, states, blend, fraction

METHODS = ("NO_PROBE", "ALWAYS8", "ALWAYS16_OLD", "PASSIVE_RECENT8", "PASSIVE8_KEEP", "PASSIVE64_PERIODIC16_KEEP",
           "UNCERTAINTY4", "TASK_IVR4", "TASK_HISTORY_IVR4")
OLD_METHODS = ("ALWAYS16_OLD", "PASSIVE_RECENT8", "PASSIVE8_KEEP", "PASSIVE64_PERIODIC16_KEEP")
CONTRASTS = (("PASSIVE64_PERIODIC16_KEEP", "ALWAYS8"), ("PASSIVE8_KEEP", "PASSIVE_RECENT8"),
             ("PASSIVE64_PERIODIC16_KEEP", "PASSIVE8_KEEP"), ("TASK_HISTORY_IVR4", "TASK_IVR4"),
             ("TASK_HISTORY_IVR4", "UNCERTAINTY4"))
FIELDS = ("success", "deadline_loss", "total_steps", "fixed_probe_steps")


def population(phase):
    if phase == "SMOKE":
        a = {"matrix_xy": np.eye(2).tolist(), "bias_xy": [.12, -.08], "deadzone_xy": [0., 0.]}
        b = {**a, "bias_xy": [-.14, .1]}
        return [{"stream": 0, "family_oracle": "BIAS", "schedule_oracle": "ABRUPT_SMOKE", "cases": [
            {"episode": i, "task": TASKS[(i+1)%3], "seed": 18000+i, "fraction_oracle": float(i >= 6), "fault_oracle": a if i < 6 else b} for i in range(12)]}]
    if phase != "MAIN": raise ValueError("registered phase required")
    result = []
    for replicate in range(2):
        for fi, family in enumerate(FAMILIES):
            for si, schedule in enumerate(SCHEDULES):
                stream = len(result); a, b = states(63001+stream, family)
                cases = [{"episode": i, "task": TASKS[(i+replicate+fi+si)%3], "seed": 18100+12*stream+i,
                          "fraction_oracle": fraction(schedule, i), "fault_oracle": blend(a, b, fraction(schedule, i))} for i in range(12)]
                result.append({"stream": stream, "family_oracle": family, "schedule_oracle": schedule,
                    "generation_seed_oracle": 63001+stream, "endpoint_states_oracle": [a, b], "cases": cases})
    return result


def source_fee(method):
    if method not in METHODS: raise ValueError("registered reference required")
    return (0, 0) if method == "NO_PROBE" else (21010, 288) if method in OLD_METHODS else (3840, 480)


def compact_case(record, stream):
    before, after = record["state_before"]["cache"], record["state_after"]["cache"]
    origin, decisions = None, {}
    for d in record["decisions"]:
        if d["action"] in ("RUN_POINT", "ACCEPT_UPDATE"): origin = record["episode"]
        elif d["action"] in ("RUN_CACHED", "START_CACHED", "PASSIVE8"): origin = before["source_episode"] if before else None
        elif d["action"] in ("RUN_IDENTITY", "START_IDENTITY"): origin = None
        decisions[d["sequence"]] = origin
    stale_steps = 0
    for r in record["trace"]:
        source_episode = decisions[r["decision_sequence"]]
        if r["raw_policy"] is not None and source_episode is not None and stream["cases"][source_episode]["fault_oracle"] != stream["cases"][record["episode"]]["fault_oracle"]:
            stale_steps += 1
    if "agent_record" in record:
        queries = record["outcome"]["policy_queries"]
    else:
        queries = sum(r["raw_policy"] is not None for r in record["trace"])+sum(d["at_host_calls"] == 4 for d in record["decisions"][1:])
    return {**{k: record[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit", "phase", "stream", "episode", "seed", "task", "method")},
        "family_oracle": stream["family_oracle"], "schedule_oracle": stream["schedule_oracle"], **record["outcome"],
        "policy_queries": queries, "cache_writes": int(after is not None and after["source_episode"] == record["episode"]),
        "cache_clears": int(before is not None and after is None), "stale_cached_policy_steps_oracle": stale_steps,
        "rejected_passive_updates": sum(d["action"] == "REJECT_UPDATE_KEEP" for d in record["decisions"]),
        "accepted_passive_updates": sum(d["action"] == "ACCEPT_UPDATE" for d in record["decisions"]),
        "reuse_cases": int(any(d["action"] in ("RUN_CACHED", "START_CACHED") for d in record["decisions"])),
        "history_queries_used_at_check": sum(d.get("check", {}).get("ivr", {}).get("past_policy_queries", 0) for d in record["decisions"] if d.get("check", {}).get("ivr") is not None)}


def statistics(rows, phase):
    specs = population(phase)
    index = {(r["stream"], r["episode"], r["method"]): r for r in rows}
    expected = {(s["stream"], c["episode"], m) for s in specs for c in s["cases"] for m in METHODS}
    if len(rows) != len(expected) or set(index) != expected: raise ValueError("complete frozen reference population required")
    methods = {}
    def cell(part):
        return {"cases": len(part), "successes": sum(r["success"] for r in part), "stops": sum(r["stopped"] for r in part),
            **{"mean_"+field: sum(r[field] for r in part)/len(part) for field in ("deadline_loss", "total_steps", "fixed_probe_steps")}}
    for method in METHODS:
        part = [r for r in rows if r["method"] == method]; fee, resets = source_fee(method)
        methods[method] = {**cell(part), "offline_source_steps": fee, "offline_source_controlled_resets": resets,
            "mean_amortized_actual_steps": (sum(r["total_steps"] for r in part)+fee)/len(part),
            **{k: sum(r[k] for r in part) for k in ("online_parameter_fits", "optimizer_nfev", "policy_queries", "cache_writes", "cache_clears",
                "stale_cached_policy_steps_oracle", "accepted_passive_updates", "rejected_passive_updates", "history_queries_used_at_check")},
            "by_task": {t: cell([r for r in part if r["task"] == t]) for t in TASKS},
            "by_factor": [{"family_oracle": f, "schedule_oracle": z, **cell([r for r in part if r["family_oracle"] == f and r["schedule_oracle"] == z])}
                for f, z in sorted({(s["family_oracle"], s["schedule_oracle"]) for s in specs})]}
    contrasts = []
    if phase == "MAIN":
        strata = [[s["stream"] for s in specs if s["family_oracle"] == f and s["schedule_oracle"] == z] for f in FAMILIES for z in SCHEDULES]
        rng = np.random.default_rng(20261020)
        draws = np.concatenate([rng.choice(group, (10000, 2)) for group in strata], axis=1)
        for n, (method, reference) in enumerate(CONTRASTS):
            values = np.array([[sum(int(index[s, e, method][field])-int(index[s, e, reference][field]) for e in range(12)) for field in FIELDS] for s in range(18)])
            intervals = np.quantile(values[draws].sum(axis=1)/216, [.025, .975], axis=0)
            contrasts.append({"method": method, "reference": reference, "role": "PRIMARY" if n == 0 else "SECONDARY_UNADJUSTED",
                "stream_values": (values/12).tolist(), "statistics": {name: {"difference": float(values[:, j].sum()/216),
                    "stratified_stream_percentile_95": intervals[:, j].tolist()} for j, name in enumerate(("success_rate", "deadline_loss", "actual_steps", "probe_steps"))}})
    return {"phase": phase, "methods": methods, "contrasts": contrasts, "independent_streams": len(specs),
        "streams_per_stratum": 2 if phase == "MAIN" else 1, "bootstrap_samples": 10000 if phase == "MAIN" else 0,
        "algorithm_novelty_established": False, "physical_probability_qualified": False, "scope": "STRONG_STANDARD_REFERENCE_DEVELOPMENT"}
