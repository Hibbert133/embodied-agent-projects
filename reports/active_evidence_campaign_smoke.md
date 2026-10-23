# Active-Evidence Campaign Integration Smoke

## Motivation

This integration run tests whether a failed rollout can trigger an explicit,
budgeted evidence-acquisition decision and whether the experiment can resume
without repeating completed environment interactions. It is not a statistical
comparison of evidence policies.

## Setup

- Task: MetaWorld `push-v3`
- Policy: `SawyerPushV3Policy`
- Fault: single-axis `+x` action bias, magnitude `0.145`
- Seed: `148`
- Maximum rollout steps: `500`
- Symmetric probe: `+x`, `-x`, `+y`, `-y`, eight steps each
- Methods: passive, always-probe, deterministic random-probe, and
  uncertainty-gated
- API calls: zero
- Rendering: disabled

The passive estimator fits the Agent-visible local model
`gripper_delta = gain * commanded_action + drift`. Its uncertainty is one minus
the mean confidence produced from action excitation and normalized fit residual.
No injected perturbation field is available to this estimator or the decision
policy. Fault axis and sign are used only after execution for audit accuracy.

## Actual Results

The campaign executed four jobs in 2,794 total environment steps.

| Method | Probe steps | Verification | Final object-goal distance (m) | Total environment steps |
|---|---:|---:|---:|---:|
| passive | 0 | failure | 0.182835 | 1000 |
| always-probe | 32 | success | 0.048759 | 598 |
| random-probe | 32 | success | 0.048759 | 598 |
| uncertainty-gated | 32 | success | 0.048759 | 598 |

The failed rollout produced passive confidence `0.156227` and uncertainty
`0.843773`. It inferred the correct dominant `+x` direction, but also selected an
unsupported y correction and failed verification. With threshold `0.55`, the
uncertainty-gated method requested a probe. The probe-derived corrective
intervention then passed verification.

The deterministic random policy also happened to request a probe for this one
seed. Therefore this run does **not** show that uncertainty gating outperforms a
random acquisition policy. It only confirms that all comparison paths execute,
record real costs, and preserve their decision provenance.

## Resume Check

Running the same command a second time produced:

```text
executed_jobs=0
skipped_completed_jobs=4
environment_steps=2794
stop_reason=all_jobs_completed
```

Thus completed job IDs were recovered from the append-only ledger and no rollout
was repeated.

## Artifacts

- `outputs/campaigns/active_evidence_smoke_v1/config.snapshot.json`
- `outputs/campaigns/active_evidence_smoke_v1/run_ledger.jsonl`
- `outputs/campaigns/active_evidence_smoke_v1/summary.csv`
- `outputs/campaigns/active_evidence_smoke_v1/jobs/*/agent_decision.json`

The output directory is intentionally Git-ignored because it contains raw rollout
trajectories. This report records the compact integration evidence; future
statistical campaigns should export separately reviewed summary artifacts.

## Reproduction

```powershell
python scripts/run_active_evidence_campaign.py `
  --config configs/campaigns/active_evidence_smoke.json
```

## Limitations and Next Experiment

One deliberately difficult seed cannot estimate success rates, uncertainty
calibration, or evidence efficiency. The next experiment must freeze multiple
tuning and held-out seeds across bias, noise, and scale faults, then compare all
four methods under equal reserved interaction budgets. Threshold selection must
use tuning seeds only.
