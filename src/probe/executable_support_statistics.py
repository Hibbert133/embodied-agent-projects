"""Registered complete-population and parity-stratified operator contrasts."""
from collections import Counter
import numpy as np


def statistics(manifest, rows, pairings, methods, tasks):
    c = manifest["config"]
    indexed = {(r["stream"], r["task"], r["replicate"], r["method"]): r for r in rows}
    expected = {(s, t, r, m) for s in range(16) for t in tasks for r in range(2) for m in methods}
    expected_pairs = {(s, t, r) for s in range(16) for t in tasks for r in range(2)}
    pairs = {(r["stream"], r["task"], r["replicate"]): r["reason"] for r in pairings}
    if len(rows) != 864 or set(indexed) != expected or len(pairings) != 96 or set(pairs) != expected_pairs:
        raise ValueError("complete registered executable-support population required")
    result = {}
    for method in methods:
        part = [r for r in rows if r["method"] == method]
        steps = sum(r["total_steps"] for r in part)
        offline = 0 if method == "NO_PROBE" else 21010
        result[method] = {"cases": 96, "successes": sum(r["success"] for r in part), "stops": sum(r["stopped"] for r in part),
                          "total_steps": steps, "mean_steps": steps / 96,
                          "mean_deadline_loss": sum(r["deadline_loss"] for r in part) / 96,
                          "mean_probe_steps": sum(r["fixed_probe_steps"] + r["ivr_probe_steps"] for r in part) / 96,
                          "point_fit_failures": sum(r["point_fit_failures"] for r in part),
                          "offline_steps": offline, "offline_resets": 0 if not offline else 288,
                          "mean_amortized_steps": (steps + offline) / 96,
                          "selected_program_sequences": dict(Counter("/".join(r["selected_ivr_programs"]) for r in part)) if method.startswith("IVR_") else {}}
    target = c["primary_target"]
    contrasts = {}
    for reference in methods:
        if reference == target:
            continue
        stream_values = []
        for stream in range(16):
            differences = []
            for task in tasks:
                for repeat in range(2):
                    a, b = indexed[(stream, task, repeat, target)], indexed[(stream, task, repeat, reference)]
                    differences.append((int(a["success"]) - int(b["success"]), a["deadline_loss"] - b["deadline_loss"], a["total_steps"] - b["total_steps"]))
            stream_values.append(np.mean(differences, axis=0))
        values = np.asarray(stream_values)
        rng = np.random.default_rng(c["bootstrap_seed"])
        even = rng.choice(np.arange(0, 16, 2), size=(c["bootstrap_samples"], 8), replace=True)
        odd = rng.choice(np.arange(1, 16, 2), size=(c["bootstrap_samples"], 8), replace=True)
        sampled = values[np.concatenate((even, odd), axis=1)].mean(axis=1)
        ci = np.quantile(sampled, (.025, .975), axis=0)
        point = values.mean(axis=0)
        contrasts[reference] = {"candidate": target, "reference": reference, "operator_streams": 16,
                                "strata_streams": [8, 8], "stream_values": values.tolist(),
                                **{name: {"difference": float(point[i]), "paired_cluster_percentile_95": ci[:, i].tolist()}
                                   for i, name in enumerate(("success_rate", "deadline_loss", "actual_steps"))}}
    candidate = result[target]
    dominators = [m for m, r in result.items() if m != target and r["successes"] >= candidate["successes"]
                  and r["mean_deadline_loss"] <= candidate["mean_deadline_loss"]
                  and (r["successes"] > candidate["successes"] or r["mean_deadline_loss"] < candidate["mean_deadline_loss"])]
    matched = sum(reason == "MATCHED_CONTINUATION" for reason in pairs.values())
    upper = contrasts[c["primary_reference"]]["deadline_loss"]["paired_cluster_percentile_95"][1]
    passed = matched == 96 and upper < 0 and candidate["successes"] >= result[c["primary_reference"]]["successes"] and not dominators
    changes = sum(indexed[(*k, target)]["selected_ivr_programs"] != indexed[(*k, c["primary_reference"])]["selected_ivr_programs"] for k in expected_pairs)
    return {"methods": result, "candidate_contrasts": contrasts,
            "development_signal": {"matched_initial_eight": matched, "required_pairs": 96,
                                   "primary_loss_interval_upper": upper, "dominated_by": dominators,
                                   "candidate_success_no_lower": candidate["successes"] >= result[c["primary_reference"]]["successes"],
                                   "selected_sequence_differences": changes, "passed": passed}}
