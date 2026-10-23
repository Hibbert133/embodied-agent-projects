"""Evaluator-only crossed-context estimands; never an agent policy input."""
from __future__ import annotations

import math
import random
import statistics

METHODS = ("PROBE_COMPENSATION", "UNCORRECTED")
CONDITIONS = tuple(f"fault_{i:02d}" for i in range(1, 5))


def summarize_crossed(rows, seeds, *, samples=10000, bootstrap_seed=20261013):
    if not seeds or len(set(seeds)) != len(seeds) or samples < 1:
        raise ValueError("nonempty unique seeds and positive samples required")
    indexed = {}
    expected = {(k, s, t, m) for k in seeds for s in CONDITIONS for t in CONDITIONS for m in METHODS}
    for row in rows:
        key = (int(row["seed"]), row["source_context_oracle"], row["target_context_oracle"], row["method"])
        if key not in expected or key in indexed:
            raise ValueError("unexpected or duplicate crossed outcome")
        if type(row["success"]) is not bool:
            raise ValueError("success must be boolean")
        indexed[key] = int(row["success"])
    if set(indexed) != expected:
        raise ValueError("incomplete crossed population")
    clusters = []
    for seed in seeds:
        cluster = {"seed": seed}
        for target in CONDITIONS:
            if len({indexed[seed, source, target, "UNCORRECTED"] for source in CONDITIONS}) != 1:
                raise ValueError("source-independent negative control violated")
        for method in METHODS:
            cluster[method + "_aligned"] = statistics.fmean(indexed[seed, c, c, method] for c in CONDITIONS)
            cluster[method + "_independent"] = statistics.fmean(
                indexed[seed, s, t, method] for s in CONDITIONS for t in CONDITIONS)
        cluster["aligned_benefit"] = cluster["PROBE_COMPENSATION_aligned"] - cluster["UNCORRECTED_aligned"]
        cluster["independent_benefit"] = cluster["PROBE_COMPENSATION_independent"] - cluster["UNCORRECTED_independent"]
        cluster["interaction"] = cluster["aligned_benefit"] - cluster["independent_benefit"]
        clusters.append(cluster)
    generator = random.Random(bootstrap_seed)
    draws = sorted(statistics.fmean(generator.choice(clusters)["interaction"] for _ in seeds)
                   for _ in range(samples))
    mean = {key: statistics.fmean(c[key] for c in clusters) for key in clusters[0] if key != "seed"}
    interval = [draws[math.floor(.025 * (samples - 1))], draws[math.floor(.975 * (samples - 1))]]
    return {"task_clusters": len(seeds), "logical_rows": len(rows), "means": mean,
            "interaction_cluster_bootstrap_95": interval, "per_seed": clusters}
