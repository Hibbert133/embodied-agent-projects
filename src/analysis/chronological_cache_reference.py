"""Whole-stream comparisons of standard chronological cache references."""
import numpy as np
from src.probe.chronological_cache_reference import METHODS, OLD_METHODS
from src.rollout.chronological_faults import FAMILIES, SCHEDULES, population

CONTRASTS = (("UNCERTAINTY4", "ALWAYS8"), ("BALANCED4", "UNCERTAINTY4"),
             ("UNCERTAINTY4", "PLUGIN4"), ("UNCERTAINTY4", "TASK_IVR4"))


def source_fee(method):
    return (0, 0) if method == "NO_PROBE" else (21010, 288) if method in OLD_METHODS else (3840, 480)


def statistics(rows, phase):
    specifications = population(phase)
    index = {(r["stream"], r["episode"], r["method"]): r for r in rows}
    expected = {(s["stream"], c["episode"], method) for s in specifications for c in s["cases"] for method in METHODS}
    if len(rows) != len(expected) or set(index) != expected: raise ValueError("all frozen method cases required")
    methods = {}
    for method in METHODS:
        selected = [r for r in rows if r["method"] == method]; steps, resets = source_fee(method)
        methods[method] = {"cases": len(selected), "successes": sum(r["success"] for r in selected), "stops": sum(r["stopped"] for r in selected),
            **{"mean_"+name: float(np.mean([r[name] for r in selected])) for name in ("deadline_loss", "total_steps", "fixed_probe_steps", "policy_measure_steps")},
            **{name: sum(r[name] for r in selected) for name in ("online_parameter_fits", "optimizer_nfev", "cache_writes", "cache_clears", "reuse_cases",
                                                               "stale_cached_policy_steps_oracle", "same_mapping_refresh_cases_oracle")},
            "offline_source_steps": steps, "offline_source_controlled_resets": resets,
            "mean_amortized_actual_steps": float((sum(r["total_steps"] for r in selected)+steps)/len(selected)),
            "by_task": {task: {"cases": sum(r["task"] == task for r in selected),
                                "successes": sum(r["success"] for r in selected if r["task"] == task),
                                "mean_deadline_loss": float(np.mean([r["deadline_loss"] for r in selected if r["task"] == task]))}
                        for task in ("push-v3", "reach-v3", "door-open-v3")}}
        methods[method]["by_factor"] = [{"family_oracle": family, "schedule_oracle": schedule,
            "cases": sum(r["family_oracle"] == family and r["schedule_oracle"] == schedule for r in selected),
            "successes": sum(r["success"] for r in selected if r["family_oracle"] == family and r["schedule_oracle"] == schedule),
            "mean_deadline_loss": float(np.mean([r["deadline_loss"] for r in selected if r["family_oracle"] == family and r["schedule_oracle"] == schedule]))}
            for family, schedule in sorted({(s["family_oracle"], s["schedule_oracle"]) for s in specifications})]
    contrasts = []
    if phase == "MAIN":
        strata = [[s["stream"] for s in specifications if s["family_oracle"] == family and s["schedule_oracle"] == schedule]
                  for family in FAMILIES for schedule in SCHEDULES]
        rng = np.random.default_rng(20261019)
        draws = np.concatenate([rng.choice(group, (10000, 4)) for group in strata], axis=1)
        for number, (method, reference) in enumerate(CONTRASTS):
            totals = np.array([[sum(int(index[s, e, method][field])-int(index[s, e, reference][field]) for e in range(12))
                                for field in ("success", "deadline_loss", "total_steps", "fixed_probe_steps")] for s in range(36)])
            ci = np.quantile(totals[draws].sum(axis=1)/(36*12), [.025, .975], axis=0)
            contrasts.append({"method": method, "reference": reference, "role": "PRIMARY" if number == 0 else "SECONDARY_UNADJUSTED",
                "stream_values": (totals/12).tolist(), "statistics": {name: {"difference": float(totals[:, j].sum()/432),
                    "stratified_stream_percentile_95": ci[:, j].tolist()} for j, name in enumerate(("success_rate", "deadline_loss", "actual_steps", "probe_steps"))}})
    delays = []
    for stream in specifications:
        change = 3 if phase == "SMOKE" or stream["schedule_oracle"] == "GRADUAL" else 6 if stream["schedule_oracle"] == "ABRUPT" else None
        if change is None: continue
        for method in METHODS:
            selected = [index[stream["stream"], c["episode"], method] for c in stream["cases"] if c["episode"] >= change]
            first = next((r["episode"] for r in selected if r["online_parameter_fits"]), None)
            verified = next((r["episode"] for r in selected if r["cache_writes"]), None)
            delays.append({"stream": stream["stream"], "method": method, "change_episode_oracle": change,
                           "first_new_fit_delay": first-change if first is not None else len(stream["cases"])-change,
                           "first_new_fit_right_censored": first is None,
                           "first_verified_source_delay": verified-change if verified is not None else len(stream["cases"])-change,
                           "first_verified_source_right_censored": verified is None})
    return {"phase": phase, "methods": methods, "contrasts": contrasts, "refresh_delays_oracle": delays, "independent_streams": len(specifications),
            "strata": 9 if phase == "MAIN" else 1, "streams_per_stratum": 4 if phase == "MAIN" else 1,
            "algorithm_novelty_established": False, "physical_probability_qualified": False, "scope": "STANDARD_REFERENCE_DEVELOPMENT"}
