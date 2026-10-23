"""Versioned evaluator-only probe-support counterexample; not an agent model."""
from __future__ import annotations
import math
import numpy as np
from src.perturbations import ActionPerturbation
from src.planner.evidence_grounded import GroundedInterventionPlan, InterventionFamily

CONTEXTS = {"negative": -.5, "identity": 0., "positive": .5}
CORRECTIONS = {"negative_x": -.2, "zero": 0., "positive_x": .2}


class ProbeNullPerturbation(ActionPerturbation):
    """x -> x + k*x^2*(x^2-m^2); roots are the *float32* probe commands.

    Only the nonlinear term's argument is capped to [-1,1]. The caller retains
    its ordinary final action clipping. Other coordinates remain unchanged.
    This constructed stressor is not a realistic actuator model claim.
    """
    name = "probe_support_null_polynomial_v1"

    def __init__(self, coefficient: float):
        super().__init__((True, False, False, False))
        if isinstance(coefficient, bool) or not math.isfinite(coefficient) or coefficient not in CONTEXTS.values():
            raise ValueError("unregistered polynomial coefficient")
        self.coefficient = float(coefficient)
        self.root = float(np.float32(.2))

    @property
    def level(self):
        return abs(self.coefficient)

    def apply(self, action):
        result = self._action_copy(action)
        if not np.isfinite(result).all():
            raise ValueError("nonfinite action")
        x = float(np.clip(result[0], -1., 1.))
        result[0] += self.coefficient * x*x * (x*x - self.root*self.root)
        return result

    def build(self):
        return ProbeNullPerturbation(self.coefficient)


def candidate_plan(name):
    if name not in CORRECTIONS:
        raise ValueError("unregistered evaluator candidate")
    correction = CORRECTIONS[name]
    return GroundedInterventionPlan(name, "fixed_candidate_set", "stable_bias" if correction else "stochastic_noise",
        InterventionFamily.BIAS_COMPENSATION if correction else InterventionFamily.STOCHASTIC_RETRY,
        name, "whole", (correction, 0., 0., 0.), "fixed_evaluator_candidate", True,
        "predeclared evaluator candidate, not selected from a hidden context")


def summarize_support(probes, outcomes, seeds):
    expected_probes = {(s, c, a) for s in seeds for c in CONTEXTS for a in (.2, .8)}
    expected_outcomes = {(s, c, a) for s in seeds for c in CONTEXTS for a in CORRECTIONS}
    ps, ys = {}, {}
    for row in probes:
        key = row["seed"], row["context_oracle"], row["amplitude"]
        if key in ps:
            raise ValueError("duplicate probe")
        ps[key] = row
    for row in outcomes:
        key = row["seed"], row["context_oracle"], row["candidate"]
        if key in ys or type(row["success"]) is not bool:
            raise ValueError("duplicate or invalid outcome")
        ys[key] = row
    if set(ps) != expected_probes or set(ys) != expected_outcomes:
        raise ValueError("incomplete factorial population")
    diagnostics = []
    for seed in seeds:
        cheap = [ps[seed, c, .2]["transitions"] for c in CONTEXTS]
        indistinguishable = cheap[0] == cheap[1] == cheap[2]
        endpoints = {c: np.array([r["end_gripper_position"] for r in ps[seed, c, .8]["transitions"]]) for c in CONTEXTS}
        separation = min(float(np.max(np.abs(endpoints[a] - endpoints[b]))) for a, b in
                         (("negative", "identity"), ("negative", "positive"), ("identity", "positive")))
        accepted = {c: [a for a in CORRECTIONS if ys[seed, c, a]["success"]] for c in CONTEXTS}
        disjoint = bool(accepted["negative"] and accepted["positive"] and
                        not set(accepted["negative"]) & set(accepted["positive"]))
        best_blind = max(sum(ys[seed, c, a]["success"] for c in CONTEXTS) for a in CORRECTIONS)
        context_oracle = sum(bool(accepted[c]) for c in CONTEXTS)
        diagnostics.append({"seed": seed, "cheap_transcripts_identical": indistinguishable,
            "high_amplitude_min_pair_separation": separation, "successful_candidates_oracle": accepted,
            "opposite_context_disjoint_success_sets": disjoint,
            "best_context_blind_successes_oracle": best_blind, "context_aware_successes_oracle": context_oracle})
    gates = {"cheap_indistinguishable": all(r["cheap_transcripts_identical"] for r in diagnostics),
             "alternative_separates": all(r["high_amplitude_min_pair_separation"] > 1e-6 for r in diagnostics),
             "task_relevant_witnesses": sum(r["opposite_context_disjoint_success_sets"] for r in diagnostics) >= 4}
    return {"seeds": len(seeds), "probe_groups": len(probes), "task_rollouts": len(outcomes),
        "success_by_context_candidate": {c: {a: sum(ys[s, c, a]["success"] for s in seeds)
                                            for a in CORRECTIONS} for c in CONTEXTS},
        "diagnostics": diagnostics, "witness_count": sum(r["opposite_context_disjoint_success_sets"] for r in diagnostics),
        "best_context_blind_successes_oracle": sum(r["best_context_blind_successes_oracle"] for r in diagnostics),
        "context_aware_successes_oracle": sum(r["context_aware_successes_oracle"] for r in diagnostics),
        "gates": gates, "gate_passed": all(gates.values())}
