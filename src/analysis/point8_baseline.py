"""Registered fixed point/Gaussian controls; complete outcomes, no selector."""
import numpy as np

CONTRASTS = (("DIRECT_POINT8", "POINT16_CYCLE"), ("DIRECT_POINT8", "DIRECT_G8"),
             ("KEEP_POINT8_AFTER16", "POINT16_CYCLE"), ("UPDATE_G16", "POINT16_CYCLE"),
             ("DIRECT_POINT8", "KEEP_POINT8_AFTER16"))
LATE_PAIRS = (("KEEP_POINT8_AFTER16", "POINT16_CYCLE"), ("UPDATE_G16", "POINT16_CYCLE"))
NO_NOMINAL = ("NO_PROBE", "IDENTITY_AFTER8")


def statistics(manifest, rows, pairs, repetitions, methods, tasks):
    c = manifest["config"]
    index = {(r["stream"], r["task"], r["replicate"], r["method"]): r for r in rows}
    expected = {(s, t, f, m) for s in range(16) for t in tasks for f in range(2) for m in methods}
    if len(rows) != 672 or set(index) != expected:
        raise ValueError("complete seven-method population required")
    expected_pairs = {(s, t, f, m, "DIRECT_G8", 8) for s in range(16) for t in tasks for f in range(2) for m in c["portfolio"]}
    expected_pairs |= {(s, t, f, m, base, 16) for s in range(16) for t in tasks for f in range(2) for m, base in LATE_PAIRS}
    actual_pairs = {(r["stream"], r["task"], r["replicate"], r["method"], r["reference"], r["boundary"]) for r in pairs}
    expected_repeated = {(s, t, 1, m) for s in range(16) for t in tasks for m in methods}
    if len(pairs) != 768 or actual_pairs != expected_pairs or len(repetitions) != 336 or {(r["stream"], r["task"], r["replicate"], r["method"]) for r in repetitions} != expected_repeated:
        raise ValueError("incomplete registered prefix checks")
    for r in rows:
        if not 0 <= r["total_steps"] <= 500 or r["deadline_loss"] != (r["total_steps"] if r["success"] else 500) or r["stopped"] and r["success"]:
            raise ValueError("failure, stop or physical budget changed")
    stats = {}
    for method in methods:
        part = [r for r in rows if r["method"] == method]
        stats[method] = {"cases": 96, "successes": sum(r["success"] for r in part), "stops": sum(r["stopped"] for r in part),
            **{"mean_"+k: float(np.mean([r[k] for r in part])) for k in ("total_steps", "deadline_loss", "fixed_probe_steps", "policy_measure_steps")},
            "nominal_offline_steps": 0 if method in NO_NOMINAL else 21010,
            "nominal_offline_resets": 0 if method in NO_NOMINAL else 288,
            "by_task": {task: {"cases": 32, "successes": sum(r["success"] for r in part if r["task"] == task),
                               "mean_deadline_loss": float(np.mean([r["deadline_loss"] for r in part if r["task"] == task]))} for task in tasks}}
    rng = np.random.default_rng(c["bootstrap_seed"])
    chosen = np.concatenate((rng.choice(np.arange(0, 16, 2), size=(c["bootstrap_samples"], 8), replace=True),
                             rng.choice(np.arange(1, 16, 2), size=(c["bootstrap_samples"], 8), replace=True)), axis=1)
    contrasts = []
    for number, (method, base) in enumerate(CONTRASTS):
        matrix = np.asarray([[np.mean([float(index[(s, t, f, method)][field])-float(index[(s, t, f, base)][field]) for t in tasks for f in range(2)])
                              for field in ("success", "deadline_loss", "total_steps")] for s in range(16)])
        bounds = np.quantile(matrix[chosen].mean(axis=1), (.025, .975), axis=0)
        contrasts.append({"method": method, "reference": base, "role": "PRIMARY" if number == 0 else "SECONDARY_UNADJUSTED",
            "stream_values": matrix.tolist(), "statistics": {field: {"difference": float(matrix[:, i].mean()), "paired_stream_percentile_95": bounds[:, i].tolist()}
                for i, field in enumerate(("success_rate", "deadline_loss", "actual_steps"))},
            "success_to_failure": sum(index[(s, t, f, base)]["success"] and not index[(s, t, f, method)]["success"] for s in range(16) for t in tasks for f in range(2)),
            "failure_to_success": sum(not index[(s, t, f, base)]["success"] and index[(s, t, f, method)]["success"] for s in range(16) for t in tasks for f in range(2))})
    return {"methods": stats, "registered_contrasts": contrasts, "prefix_pairs": 768, "future_prefix_pairs": 336,
            "eight_step_pair_entries": 576, "eight_step_different_method_pairs": 480, "eight_step_self_checks": 96,
            "sixteen_step_pairs": 192, "prefix_reason_counts": {reason: sum(p["reason"] == reason for p in pairs) for reason in sorted({p["reason"] for p in pairs})},
            "independent_streams": 16, "operator_parity_strata": [8, 8], "context_futures_are_not_independent_streams": True,
            "algorithm_novelty_established": False, "online_selector_executions": 0,
            "scope": "Frozen standard baseline comparison only; controller family and probe quantity separated by explicit controls."}
