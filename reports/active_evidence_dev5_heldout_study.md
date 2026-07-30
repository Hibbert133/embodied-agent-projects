# Active-Evidence Development and Held-Out Study

## Question

Does an online GLM-5.2 evidence policy allocate diagnostic probes selectively,
and does a development-tuned uncertainty gate reduce probe cost without reducing
verification success on held-out single-axis bias failures?

This is a small development study, not a final statistical comparison.

## Frozen Case Selection

Cases came from the existing real 50-seed `+x 0.145` bias CSV. Failures were
sorted by final object-goal distance and selected at evenly spaced severity
ranks before the new campaigns ran.

- Development seeds: `135, 124, 136, 108, 144`
- Held-out seeds: `107, 139, 115, 103, 111, 128, 110, 113, 145, 132`
- Seed 148 was excluded from held-out selection because it had already been used
  in the one-call integration pilot.

Selection is automatically checked by
`scripts/validate_active_evidence_selection.py`. Oracle outcome columns are used
only for offline stratification and evaluation, never as Agent input.

## Development Results

All values below come from the real paired campaign ledger.

| Method | Success | Probe requests | Probe relevance precision | Mean environment steps | API calls |
|---|---:|---:|---:|---:|---:|
| passive | 4/5 | 0/5 | n/a | 652.6 | 0 |
| always-probe | 5/5 | 5/5 | 20.0% | 597.2 | 0 |
| random-probe | 5/5 | 3/5 | 33.3% | 584.8 | 0 |
| threshold gate 0.55 | 5/5 | 5/5 | 20.0% | 597.2 | 0 |
| online GLM-5.2 | 5/5 | 5/5 | 20.0% | 597.2 | 5 |

Probe relevance precision is the fraction of requested probes whose paired
passive corrective intervention failed. This is a hindsight evaluation metric,
not an Agent-visible decision feature.

GLM-5.2 requested `symmetric_xy` for all five cases. Its hypothesis fields varied,
but its evidence action did not. Therefore the online policy behaved like
always-probe rather than a selective evidence allocator.

The five calls used 3,243 input tokens and the compatible endpoint reported
5,154 output tokens. Mean latency was approximately 30.0 seconds per call. The
endpoint again reported outputs larger than the requested generation limit, so
API-call and wall-time budgets remain mandatory.

## Development Threshold Selection

Using only the real paired development outcomes, candidate thresholds were
ranked by:

1. maximum verification successes;
2. minimum mean environment steps;
3. minimum probe requests.

The selected threshold was `0.8649071032`. Counterfactual selection over the
already executed passive and always-probe paths predicted:

- 5/5 verification successes;
- one probe request;
- 572.8 mean environment steps.

This is tuning evidence only.

## Frozen Held-Out Validation

The threshold was frozen without validation retuning.

| Method | Success | Probe requests | Mean environment steps | Mean final distance |
|---|---:|---:|---:|---:|
| passive | 10/10 | 0/10 | 565.5 | 0.047478 m |
| always-probe | 10/10 | 10/10 | 594.2 | 0.048025 m |
| frozen gate | 10/10 | 3/10 | 574.6 | 0.047238 m |

The frozen gate reduced probe requests by 70% relative to always-probe, but all
ten paired passive interventions also succeeded. Consequently the three held-out
probes added no successes and increased mean interaction cost by 9.1 steps over
passive.

## Interpretation

The positive observation is engineering and behavioral: bounded online decisions,
real costs, paired controls, frozen selection, and held-out evaluation now form a
reproducible loop.

The scientific result is negative but useful. On this single-axis bias family,
ordinary failed-rollout transitions often contain enough information for passive
correction. GLM-5.2 and the initial threshold both over-probe. Active evidence
cannot be justified merely by showing successful recovery after a probe.

The next benchmark must contain *ambiguity pairs*: faults that produce similar
failed-rollout evidence but require different interventions, such as stable bias
versus stochastic action noise. A repeated probe can then have measurable value
by resolving a hypothesis that passive evidence cannot reliably distinguish.

## Reproduction

```powershell
python scripts/validate_active_evidence_selection.py `
  --config configs/campaigns/active_evidence_glm52_dev5.json

.\scripts\run_active_evidence_campaign.ps1 `
  -Config configs\campaigns\active_evidence_glm52_dev5.json `
  -ApiTimeout 300

python scripts/analyze_active_evidence_campaign.py `
  --run-dir outputs/campaigns/active_evidence_glm52_dev5_v1

python scripts/validate_active_evidence_selection.py `
  --config configs/campaigns/active_evidence_threshold_heldout10.json

python scripts/run_active_evidence_campaign.py `
  --config configs/campaigns/active_evidence_threshold_heldout10.json

python scripts/analyze_active_evidence_campaign.py `
  --run-dir outputs/campaigns/active_evidence_threshold_heldout10_v1 `
  --frozen-threshold 0.8649071032179548
```

## Artifacts

- `outputs/campaigns/active_evidence_glm52_dev5_v1/`
- `outputs/campaigns/active_evidence_threshold_heldout10_v1/`

Raw trajectories remain Git-ignored. Configurations, selection logic, analysis
code, and this compact report are tracked.
