"""Prefix-only acquisition policies and accepted-only, method-owned evidence cache.

Action agreement is a heuristic stopping rule, not a calibrated confidence bound.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import fmean
from typing import Callable, Mapping

from src.autoresearch import RecoveryPolicyConfig
from src.planner.evidence_grounded import GroundedInterventionPlan, select_grounded_intervention

METHODS = ("FIXED_16", "FIXED_32", "FIXED_64", "STALE", "PERIODIC_4",
           "CHANGE_THRESHOLD", "DECISION_STABILITY", "UNCORRECTED")


@dataclass(frozen=True)
class Measurement:
    drift: tuple[float, float]
    gain: tuple[float, float]
    residual: float

    @classmethod
    def from_mapping(cls, value: Mapping):
        if set(value) != {"estimated_drift_per_step", "axis_response_gain", "residual"}:
            raise ValueError("probe measurement requires an exact Agent-visible schema")
        drift, gain = tuple(value["estimated_drift_per_step"]), tuple(value["axis_response_gain"])
        residual = value["residual"]
        if len(drift) != 2 or len(gain) != 2:
            raise ValueError("probe must have two axes")
        if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
               for x in (*drift, *gain, residual)):
            raise ValueError("probe measurements must be finite numbers")
        if residual < 0 or any(abs(x) < 1e-6 for x in gain):
            raise ValueError("invalid residual or unidentifiable response gain")
        return cls(drift, gain, residual)


@dataclass(frozen=True)
class CachedEvidence:
    owner: str
    stream: int
    episode: int
    available_sequence: int
    plan: GroundedInterventionPlan
    measurement: Measurement


@dataclass(frozen=True)
class RefreshDecision:
    method: str
    plan: GroundedInterventionPlan
    repetitions: int
    reason: str
    measurement: Measurement | None
    cache_source_episode: int | None
    checked_prefixes: tuple[int, ...]


def average(samples):
    if not samples:
        raise ValueError("cannot pool empty evidence")
    return Measurement(tuple(fmean(s.drift[j] for s in samples) for j in range(2)),
                       tuple(fmean(s.gain[j] for s in samples) for j in range(2)),
                       fmean(s.residual for s in samples))


def inferred_bias(measurement):
    if any(abs(g) < 1e-6 for g in measurement.gain):
        raise ValueError("pooled gain is unidentifiable")
    return tuple(d / g for d, g in zip(measurement.drift, measurement.gain))


def plan_from_samples(samples, recovery, identity):
    pooled = average(samples)
    inferred_bias(pooled)
    return select_grounded_intervention(plan_id=identity, evidence_id=identity,
        mechanism_belief="stable_bias", recovery_config=recovery,
        evidence_source="current_probe_prefix",
        correction_context={"protocol": "pooled_symmetric_probe_prefix_v1",
            "probe_environment_steps": 16 * len(samples),
            "inference": {"estimated_drift_per_step": pooled.drift,
                          "axis_response_gain": pooled.gain, "residual": pooled.residual}})


def decide(method: str, read_next: Callable[[], Measurement], *, cache: CachedEvidence | None,
           recovery: RecoveryPolicyConfig, stream: int, episode: int, decision_sequence: int,
           remaining_budget: int = 564) -> RefreshDecision:
    if method not in METHODS:
        raise ValueError("unknown acquisition method")
    if cache is not None and (cache.owner != method or cache.stream != stream or
                             cache.episode >= episode or cache.available_sequence >= decision_sequence):
        raise ValueError("cross-method, cross-stream, or non-prior cache")
    identity = f"{method}_stream{stream}_episode{episode}"
    samples = []
    checked = []

    def acquire():
        if len(samples) >= 4 or remaining_budget < (len(samples) + 1) * 16 + 500:
            raise ValueError("probe request violates reserved execution budget")
        measurement = read_next()
        if not isinstance(measurement, Measurement):
            raise ValueError("invalid measurement object")
        # Validate direct dataclass construction as well as serialized inputs.
        Measurement.from_mapping({"estimated_drift_per_step": measurement.drift,
            "axis_response_gain": measurement.gain, "residual": measurement.residual})
        samples.append(measurement)

    def finish(plan, reason):
        return RefreshDecision(method, plan, len(samples), reason,
            average(samples) if samples else None, cache.episode if cache else None, tuple(checked))

    if method == "UNCORRECTED":
        if remaining_budget < 500:
            raise ValueError("execution reserve is unavailable")
        plan = select_grounded_intervention(plan_id=identity, evidence_id=identity,
            mechanism_belief="stochastic_noise", correction_context=None,
            recovery_config=recovery, evidence_source="no_probe_control")
        return finish(plan, "NO_ACQUISITION")
    if method in {"STALE", "PERIODIC_4"} and cache is not None:
        if method == "STALE" or episode % 4 != 0:
            if remaining_budget < 500:
                raise ValueError("execution reserve is unavailable")
            return finish(cache.plan, "CACHED_ACTION")
    if method in {"FIXED_16", "FIXED_32", "FIXED_64"}:
        count = {"FIXED_16": 1, "FIXED_32": 2, "FIXED_64": 4}[method]
        for _ in range(count):
            acquire()
        return finish(plan_from_samples(samples, recovery, identity), "FIXED_PREFIX")
    if cache is None or method in {"STALE", "PERIODIC_4"}:
        for _ in range(4):
            acquire()
        return finish(plan_from_samples(samples, recovery, identity), "BOOTSTRAP_OR_PERIODIC")
    acquire()
    first = plan_from_samples(samples, recovery, identity)
    if method == "CHANGE_THRESHOLD":
        delta = math.dist(inferred_bias(samples[0]), inferred_bias(cache.measurement))
        if delta <= .04:
            return finish(cache.plan, "SMALL_PARAMETER_CHANGE")
        for _ in range(3):
            acquire()
        return finish(plan_from_samples(samples, recovery, identity), "PARAMETER_CHANGE_REFRESH")
    if first.execution_signature() == cache.plan.execution_signature():
        return finish(first, "CURRENT_ACTION_MATCHES_CACHE")
    for count in (2, 3, 4):
        acquire()
        pooled_plan = plan_from_samples(samples, recovery, identity)
        candidates = [pooled_plan] + [plan_from_samples(samples[:j] + samples[j + 1:], recovery, identity)
                                     for j in range(count)]
        checked.append(count)
        if len({p.execution_signature() for p in candidates}) == 1:
            return finish(pooled_plan, "LEAVE_ONE_OUT_ACTION_STABLE")
    return finish(pooled_plan, "MAXIMUM_PREFIX_UNRESOLVED")


def accepted_update(decision, cache, *, stream, episode, outcome_sequence, status):
    if status not in {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}:
        raise ValueError("unknown fresh-verification status")
    if status != "ACCEPTED" or decision.measurement is None:
        return cache
    return CachedEvidence(decision.method, stream, episode, outcome_sequence,
                          decision.plan, decision.measurement)
