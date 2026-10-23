"""Prospective population and historical power-planning proxy, evaluator only."""
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

TASKS = ("push-v3", "reach-v3", "door-open-v3")
METHODS = ("DIRECT_C8", "MOVE_KEEP_C8", "MOVE_INTEGRAL", "MOVE_ARX_KEEP")
CONDITIONS = ("UNCHANGED", "CHANGED")
VARIANTS = tuple(c+"_"+m for c in CONDITIONS for m in METHODS)
GROUPS = 54
CONTRASTS = (("MOVE_ARX_KEEP", "MOVE_INTEGRAL"), ("MOVE_ARX_KEEP", "MOVE_KEEP_C8"),
    ("MOVE_INTEGRAL", "MOVE_KEEP_C8"), ("MOVE_KEEP_C8", "DIRECT_C8"),
    ("MOVE_ARX_KEEP", "DIRECT_C8"), ("MOVE_INTEGRAL", "DIRECT_C8"))
INITIAL = {"matrix_xy": [[1., 0.], [0., 1.]], "bias_xy": [.12, -.08], "deadzone_xy": [0., 0.]}
HISTORICAL_SOURCE = "outputs/point8_baseline/development_v1/point8_baseline_20261015T153211Z_b9506ff0e3ae"
PLANNING_PINS = {
    HISTORICAL_SOURCE+"/summary.json": "d786f4e16f5d1baf99435abcebca1fe483c2e567b33e9ce373e3e899454f479e",
    "outputs/point8_baseline/analysis_v1/audit.json": "bbb9b14ef2cf1b8342994b6bc653b07b6304a3434fe0966b9dafeebabda62cf7",
    "outputs/point8_baseline/statistics_audit_v1/check.json": "346c767d38726d9f9338aedac19d2b0f5967afb430e400586d55f63bef768a88",
}


def require(value, message):
    if not value:raise ValueError(message)


def planning(root):
    root = Path(root);values = {}
    for name, expected in PLANNING_PINS.items():
        raw = (root/name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, "historical planning input changed: "+name)
        values[name] = json.loads(raw)
    summary, audit, checked = values.values()
    require(audit["integrity"] == checked["integrity"] == "PASSED"
            and checked["summary_sha256"] == audit["artifact_sha256"]["summary.json"] == PLANNING_PINS[HISTORICAL_SOURCE+"/summary.json"]
            and checked["record_audit_sha256"] == PLANNING_PINS["outputs/point8_baseline/analysis_v1/audit.json"], "planning source was not audited")
    for item in (audit, checked):
        require(all(item[k] == summary[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")), "planning identities differ")
    rows = summary["cases"]
    index = {(r["stream"], r["task"], r["replicate"], r["method"]): r for r in rows}
    require(len(index) == len(rows) == 672, "all historical cases required")
    paired = []
    for group in range(16):
        differences = []
        for task in TASKS:
            for replicate in range(2):
                left, right = (index[group, task, replicate, method] for method in ("DIRECT_POINT8", "POINT16_CYCLE"))
                for row in (left, right):
                    require(type(row["success"]) is bool and type(row["total_steps"]) is int and 0 <= row["total_steps"] <= 500
                            and row["deadline_loss"] == (row["total_steps"] if row["success"] else 500), "historical outcome differs")
                differences.append(left["deadline_loss"]-right["deadline_loss"])
        paired.append(sum(differences)/6)
    sd = float(np.std(paired, ddof=1));z = NormalDist().inv_cdf(.975)+NormalDist().inv_cdf(.8)
    required = math.ceil((z*sd/20)**2)
    require(required == 52 and 3*math.ceil(required/3) == GROUPS, "prospective group count must be reconsidered before data")
    return {"source_sha256": dict(PLANNING_PINS), "source_contrast": ["DIRECT_POINT8", "POINT16_CYCLE"],
        "source_streams": 16, "source_paired_stream_means": paired, "paired_stream_sd": sd,
        "target_difference_steps": 20, "two_sided_alpha": .05, "target_power": .8,
        "normal_approximation_required_groups": required, "frozen_groups": GROUPS, "boundary_strata": [18, 18, 18],
        "units_per_group": 6, "actual_method_executions": 1296,
        "scope": "Historical variance proxy, not known variance of movement-task differences or a power guarantee.",
        "new_task_outcomes_used": 0}


def population():
    return [{"unit": 3*g+i, "task": task, "seed": 25000+3*g+i, "variant": variant,
             "planned_boundary": (16,32,64)[g%3]}
        for g in range(GROUPS) for i, task in enumerate(TASKS) for variant in VARIANTS]


def method(variant):
    require(variant in VARIANTS, "unknown private allocation")
    return variant.split("_", 1)[1]


def destination(spec):
    method(spec["variant"])
    if spec["variant"].startswith("UNCHANGED_"):return json.loads(json.dumps(INITIAL))
    require(type(spec["unit"]) is int and 0 <= spec["unit"] < 3*GROUPS, "unknown operator group")
    rng = np.random.default_rng(np.random.SeedSequence([88003, spec["unit"]//3]))
    return {"matrix_xy": [[float(rng.uniform(.75,1.25)), float(rng.uniform(-.2,.2))],
                          [float(rng.uniform(-.2,.2)), float(rng.uniform(.75,1.25))]],
            "bias_xy": rng.uniform(-.2,.2,2).tolist(), "deadzone_xy": [0., 0.]}
