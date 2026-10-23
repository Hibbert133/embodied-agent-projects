"""Evaluator-only cross-future value diagnostic, never an online Agent."""
from dataclasses import dataclass
import numpy as np
from src.probe.forward_prediction import vector

PORTFOLIO = ("DIRECT_G8", "PASSIVE_G16", "POINT16_CYCLE", "UPDATE_G16", "KEEP_G8_AFTER16")


@dataclass(frozen=True)
class OfflineTrainingLosses:
    values: tuple

    def __post_init__(self):
        values = tuple(vector(row, 3) for row in self.values)
        if len(values) != 5 or any(not 0 <= x <= 500 for row in values for x in row):
            raise ValueError("five registered branches and three training-future losses required")
        object.__setattr__(self, "values", values)


def choose_training(training):
    if type(training) is not OfflineTrainingLosses:
        raise ValueError("strict evaluator-only training-loss input required")
    means = {m: sum(row)/3 for m, row in zip(PORTFOLIO, training.values)}
    branch = min(PORTFOLIO, key=lambda m: (means[m], PORTFOLIO.index(m)))
    return {"selected_branch": branch, "training_mean_losses": means, "role": "EVALUATOR_ONLY_CROSS_FUTURE_LOOKUP"}


def statistics(manifest, rows, pairs, repetitions, methods, tasks):
    c = manifest["config"]
    if tuple(c["portfolio"]) != PORTFOLIO: raise ValueError("registered feasible continuation order differs")
    indexed = {(r["stream"], r["task"], r["replicate"], r["method"]): r for r in rows}
    expected = {(s, t, r, m) for s in range(8) for t in tasks for r in range(4) for m in methods}
    paired = {(r["stream"], r["task"], r["replicate"], r["method"]): r["reason"] for r in pairs}
    repeated = {(r["stream"], r["task"], r["replicate"], r["method"]): r["reason"] for r in repetitions}
    expected_pairs = {(s,t,r,m) for s in range(8) for t in tasks for r in range(4) for m in PORTFOLIO}
    expected_repeated = {(s,t,r,m) for s in range(8) for t in tasks for r in range(1,4) for m in methods}
    if len(rows) != 672 or set(indexed) != expected or len(pairs) != 480 or set(paired) != expected_pairs or len(repetitions) != 504 or set(repeated) != expected_repeated:
        raise ValueError("complete registered conditional population and prefix checks required")
    legal = {"MATCHED_ACTIVE_PREFIX", "ENDED_BEFORE_EIGHT", "ENDED_AT_EIGHT"}
    if not set(paired.values()).issubset(legal) or not set(repeated.values()).issubset(legal):
        raise ValueError("unsupported conditional prefix")
    method_stats = {}
    for method in methods:
        part = [r for r in rows if r["method"] == method]; steps = sum(r["total_steps"] for r in part)
        offline = 0 if method == "NO_PROBE" else 21010
        method_stats[method] = {"cases": 96, "successes": sum(r["success"] for r in part), "stops": sum(r["stopped"] for r in part),
                                "total_steps": steps, "mean_steps": steps/96, "mean_deadline_loss": sum(r["deadline_loss"] for r in part)/96,
                                "mean_probe_steps": sum(r["fixed_probe_steps"] for r in part)/96,
                                "mean_policy_measure_steps": sum(r["policy_measure_steps"] for r in part)/96,
                                "point_fit_failures": sum(r["point_fit_failures"] for r in part),
                                "offline_steps": offline, "offline_resets": 0 if not offline else 288,
                                "mean_amortized_steps": (steps+offline)/96}
    contexts = []; lookup = []
    for stream in range(8):
        for task in tasks:
            reasons = {paired[(stream,task,r,m)] for r in range(4) for m in PORTFOLIO}
            if len(reasons) != 1: raise ValueError("future/method changed the common prefix eligibility")
            reason = next(iter(reasons)); active = reason == "MATCHED_ACTIVE_PREFIX"
            losses = {m: [indexed[(stream,task,r,m)]["deadline_loss"] for r in range(4)] for m in methods}
            details = {m: {"four_losses": values, "mean_loss": sum(values)/4, "range": [min(values),max(values)],
                           "mean_loss_minus_direct": sum(a-b for a,b in zip(values,losses["DIRECT_G8"]))/4,
                           "successes": sum(indexed[(stream,task,r,m)]["success"] for r in range(4))} for m,values in losses.items()}
            contexts.append({"stream": stream, "task": task, "prefix_reason": reason, "decision_required": active, "methods": details})
            for heldout in range(4):
                training_futures = [r for r in range(4) if r != heldout]
                if active:
                    training = OfflineTrainingLosses(tuple(tuple(losses[m][r] for r in training_futures) for m in PORTFOLIO))
                    choice = choose_training(training)
                else:
                    choice = {"selected_branch": "DIRECT_G8", "training_mean_losses": None, "role": "EVALUATOR_ONLY_PREFIX_TERMINAL"}
                # Only training losses enter the pure selector; all analysis is offline.
                selected = indexed[(stream,task,heldout,choice["selected_branch"])]; direct = indexed[(stream,task,heldout,"DIRECT_G8")]
                lookup.append({"stream": stream, "task": task, "held_out_future": heldout, "training_futures": training_futures if active else [],
                               "decision_required": active, **choice, "selected_success": selected["success"],
                               "selected_steps": selected["total_steps"], "selected_deadline_loss": selected["deadline_loss"],
                               "selected_probe_steps": selected["fixed_probe_steps"],
                               "success_minus_direct": int(selected["success"])-int(direct["success"]),
                               "loss_minus_direct": selected["deadline_loss"]-direct["deadline_loss"],
                               "steps_minus_direct": selected["total_steps"]-direct["total_steps"]})
    values = np.asarray([[np.mean([r[k] for r in lookup if r["stream"] == s]) for k in
                          ("success_minus_direct","loss_minus_direct","steps_minus_direct")] for s in range(8)])
    rng = np.random.default_rng(c["bootstrap_seed"])
    even = rng.choice(np.arange(0,8,2),size=(c["bootstrap_samples"],4),replace=True)
    odd = rng.choice(np.arange(1,8,2),size=(c["bootstrap_samples"],4),replace=True)
    sampled = values[np.concatenate((even,odd),axis=1)].mean(axis=1); ci = np.quantile(sampled,(.025,.975),axis=0)
    contrast = {name: {"difference": float(values[:,i].mean()), "paired_cluster_percentile_95": ci[:,i].tolist()}
                for i,name in enumerate(("success_rate","deadline_loss","actual_steps"))}
    return {"methods": method_stats, "conditional_contexts": contexts, "lookup_decisions": lookup,
            "lookup": {"role": "EVALUATOR_ONLY_CROSS_FUTURE_LOOKUP", "cases": 96, "decision_required_cases": sum(r["decision_required"] for r in lookup),
                       "successes": sum(r["selected_success"] for r in lookup), "mean_steps": sum(r["selected_steps"] for r in lookup)/96,
                       "mean_deadline_loss": sum(r["selected_deadline_loss"] for r in lookup)/96,
                       "mean_probe_steps": sum(r["selected_probe_steps"] for r in lookup)/96,
                       "selected_counts": {m: sum(r["selected_branch"]==m for r in lookup) for m in PORTFOLIO},
                       "operator_streams": 8, "strata_streams": [4,4], "stream_contrast_values": values.tolist(), "contrast_minus_direct": contrast,
                       "entire_counterfactual_study_steps": sum(r["total_steps"] for r in rows), "entire_counterfactual_study_resets": 672,
                       "portfolio_required_source_steps": sum(r["total_steps"] for r in rows if r["method"] in PORTFOLIO),
                       "new_online_lookup_executions": 0, "deployable_agent": False, "true_optimal_policy_bound": False},
            "prefix_checks": {"cross_method_pairs": 480, "across_future_pairs": 504, "contexts": 24,
                              "active_contexts": sum(r["decision_required"] for r in contexts)},
            "scope": "Conditional fixed-continuation and evaluator-only held-out-future lookup measurement, not a learned online method or realization-winner stability gate."}
