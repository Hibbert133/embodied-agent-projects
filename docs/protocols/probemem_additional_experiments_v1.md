# ProbeMem Additional Experiments Development Protocol v1

Status: `DEVELOPMENT_FROZEN_BEFORE_EXECUTION`

This development-only protocol evaluates configuration-level marginal effects
for evidence acquisition, accepted-only chronological memory, and deterministic
verification. It does not change the robot policy, registered probe, thresholds,
skills, or verifier guard and makes no GLM calls.

Seeds 7200--7399 are scanned once in ascending order until 60 failed initial
episodes are retained. Seeds 7400--7499 remain reserved. Condition and mechanism
coverage targets are descriptive only and can never alter sequential stopping,
seed order, inclusion, or resampling.

The registered methods are Baseline, Memory-only, Evidence Acquisition Enabled,
Probe+Memory, and Full ProbeMem. Baseline and Evidence Acquisition Enabled use
the same frozen mechanism-to-recovery mapping; the latter differs only in whether
the phase gate may expose the fixed 64-step evidence result.

Each method owns an independent chronological memory timeline. Record ownership
and availability are checked at retrieval. Only accepted records completed in a
strictly earlier episode may enter actionable retrieval. Memory-only queries use
the pre-acquisition seven-field signature and reject every probe, Oracle, current,
or future field. Evaluator mechanism consistency is computed only after decisions.

Every environment branch is reset-matched from the same seed and audited through
its initial observation hash. It owns fresh environment, policy, perturbation, and
RNG objects. Decisions are persisted before evaluator-only paired outcomes. Four
realizations per distinct registered action signature estimate distributional
utility; only the first is the online-equivalent recovery outcome.

The common recovery denominator is all retained failed initial episodes. Missing,
invalid, abstained, inconclusive, and rejected recoveries remain denominator
failures. Conditional analyses cannot replace this primary metric.

The five-row ablation identifies configuration-level marginal effects, not fully
independent component causal effects. Reports must use mechanism-specific wording:
"The results support/reject/suggest that [mechanism] affects [metric] under
[evaluation setting]."
