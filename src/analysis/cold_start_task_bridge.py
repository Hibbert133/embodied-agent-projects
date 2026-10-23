"""Frozen eight-program task bridge; descriptive development component gate."""
import numpy as np
from src.probe.cold_start_task_bridge import TASKS, METHODS, PORTFOLIO, NEW_SOURCE, OLD_SOURCE
CONTRASTS = tuple(("JOINT8", base) for base in ("OLD_POINT8", "SAME_DATA_POINT8", "JOINT_DROP2_8", "OLD_G8", "OLD_POINT16_CYCLE", "NO_PROBE", "IDENTITY_AFTER8"))
STREAMS = 56


def statistics(rows, pairs, repetitions):
    index = {(r["stream"], r["task"], r["replicate"], r["method"]): r for r in rows}
    expected = {(s, t, f, m) for s in range(STREAMS) for t in TASKS for f in range(2) for m in METHODS}
    if len(rows) != 2688 or set(index) != expected: raise ValueError("all 2688 task executions required")
    ep = {(s, t, f, m, "JOINT8") for s in range(STREAMS) for t in TASKS for f in range(2) for m in PORTFOLIO}
    er = {(s, t, 1, m) for s in range(STREAMS) for t in TASKS for m in METHODS}
    if len(pairs) != 2352 or {(r["stream"], r["task"], r["replicate"], r["method"], r["reference"]) for r in pairs} != ep:
        raise ValueError("complete common-eight-step checks required")
    if len(repetitions) != 1344 or {(r["stream"], r["task"], r["replicate"], r["method"]) for r in repetitions} != er:
        raise ValueError("complete cross-future prefix checks required")
    reasons = {"MATCHED_ACTIVE_PREFIX_8", "ENDED_AT_8"} | {f"ENDED_BEFORE_8_SHARED_{i}" for i in range(8)}
    if any(r["reason"] not in reasons for r in (*pairs, *repetitions)):
        raise ValueError("unknown prefix status")
    for r in rows:
        if type(r["success"]) is not bool or type(r["stopped"]) is not bool or type(r["total_steps"]) is not int or type(r["deadline_loss"]) is not int or r["stopped"] and r["success"] or not 0 <= r["total_steps"] <= 500 or r["deadline_loss"] != (r["total_steps"] if r["success"] else 500):
            raise ValueError("stop/failure denominator or task budget differs")
    cells = {}
    for name in METHODS:
        part = [r for r in rows if r["method"] == name]
        source_steps, source_resets = (3840, 480) if name in NEW_SOURCE else (21010, 288) if name in OLD_SOURCE else (0, 0)
        cells[name] = {"cases": 336, "successes": sum(r["success"] for r in part), "stops": sum(r["stopped"] for r in part),
                       **{"mean_"+k: float(np.mean([r[k] for r in part])) for k in ("deadline_loss", "total_steps", "fixed_probe_steps")},
                       "source_steps": source_steps, "source_controlled_resets": source_resets,
                       "mean_amortized_actual_steps": (sum(r["total_steps"] for r in part)+source_steps)/336,
                       "by_task": {t: {"cases": 112, "successes": sum(r["success"] for r in part if r["task"] == t),
                                        "mean_deadline_loss": float(np.mean([r["deadline_loss"] for r in part if r["task"] == t]))} for t in TASKS}}
    rng = np.random.default_rng(20261017)
    draws = np.concatenate((rng.choice(np.arange(0, STREAMS, 2), (10000, STREAMS//2)),
                            rng.choice(np.arange(1, STREAMS, 2), (10000, STREAMS//2))), axis=1)
    contrasts = []
    for i, (name, base) in enumerate(CONTRASTS):
        totals = np.array([[sum(int(index[s, t, f, name][field])-int(index[s, t, f, base][field]) for t in TASKS for f in range(2))
                            for field in ("success", "deadline_loss", "total_steps")] for s in range(STREAMS)], dtype=np.int64)
        values = totals/6
        bounds = np.quantile(totals[draws].sum(axis=1)/(6*STREAMS), [.025, .975], axis=0)
        contrasts.append({"method": name, "reference": base, "role": "PRIMARY" if i == 0 else "SECONDARY_UNADJUSTED",
                          "stream_values": values.tolist(), "statistics": {field: {"difference": float(totals[:, j].sum()/(6*STREAMS)), "paired_stream_percentile_95": bounds[:, j].tolist()}
                              for j, field in enumerate(("success_rate", "deadline_loss", "actual_steps"))},
                          "success_to_failure": sum(index[s, t, f, base]["success"] and not index[s, t, f, name]["success"] for s in range(STREAMS) for t in TASKS for f in range(2)),
                          "failure_to_success": sum(not index[s, t, f, base]["success"] and index[s, t, f, name]["success"] for s in range(STREAMS) for t in TASKS for f in range(2))})
    gate = {"primary_loss_upper_below_zero": bool(contrasts[0]["statistics"]["deadline_loss"]["paired_stream_percentile_95"][1] < 0),
            "success_not_below_old_point8": cells["JOINT8"]["successes"] >= cells["OLD_POINT8"]["successes"],
            "success_not_below_strong_controls": cells["JOINT8"]["successes"] >= max(cells[m]["successes"] for m in ("OLD_G8", "OLD_POINT16_CYCLE")),
            "mean_loss_not_above_strong_controls": cells["JOINT8"]["mean_deadline_loss"] <= min(cells[m]["mean_deadline_loss"] for m in ("OLD_G8", "OLD_POINT16_CYCLE"))}
    return {"methods": cells, "contrasts": contrasts, "component_gate": {"requirements": gate, "passed": all(gate.values())},
            "independent_streams": STREAMS, "parity_strata": [28, 28], "cross_method_prefix_entries": len(pairs),
            "cross_method_different_methods": 2016, "prefix_self_checks": 336, "cross_future_prefix_checks": len(repetitions),
            "algorithm_novelty_established": False, "probability_qualification": False, "new_api_calls": 0,
            "scope": "Independent task bridge for standard frozen response estimators, not a new acquisition policy."}
