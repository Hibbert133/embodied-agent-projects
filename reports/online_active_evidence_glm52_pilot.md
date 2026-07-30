# Online GLM-5.2 Active-Evidence Pilot

## Research Role

This pilot tests whether an online model can make a bounded evidence-acquisition
decision from leakage-safe failed-rollout evidence. It does not test direct
low-level control and is not a statistical model comparison.

GLM-5.2 could choose exactly one of `request_probe`, `update_hypothesis`, or
`abstain`. It could select only the registered `symmetric_xy` probe and could not
output actions or correction magnitudes. The deterministic executor converted
the acquired evidence into a bounded corrective intervention and evaluated it in
a verification rollout.

## Setup

- Task: MetaWorld `push-v3`
- Seed: `148`
- Controlled fault: `+x` action bias, magnitude `0.145`
- Initial and verification rollout limit: 500 steps each
- Probe cost: four directions x eight steps = 32 environment steps
- Model: `glm-5.2` through an Anthropic-compatible endpoint
- Prompt version: `active-evidence-decision-v1`
- API budget: one call
- Environment budget: 1,500 steps
- Rendering: disabled

The online request contained only the task outcome, task progress, and the
passive local-model estimate derived from schema-v2 Agent View transitions. It
did not contain perturbation type, injected axis, direction, magnitude,
perturbed action, executed action, or clipping audit fields.

## Actual Online Decision

GLM-5.2 returned:

- action: `request_probe`
- probe: `symmetric_xy`
- hypothesis: `systematic_planar_bias`, x positive
- target uncertainty: planar drift direction and magnitude
- confidence: `0.156227`

Its parsed rationale cited the passive estimate's low confidence, normalized
residuals, action excitation, and the 32-step probe cost. The response passed the
strict output schema; the raw response text was not persisted. A SHA-256 response
hash and the parsed decision were retained for audit.

## Actual Execution Result

| Metric | Value |
|---|---:|
| API calls | 1 |
| API latency | 28,851.07 ms |
| Input tokens | 645 |
| Endpoint-reported output tokens | 847 |
| Initial final object-goal distance | 0.246488 m |
| Probe environment steps | 32 |
| Verification success | true |
| Verification final object-goal distance | 0.048759 m |
| Total environment steps | 598 |

The same seed and intervention outcome match the deterministic always-probe path
from the offline integration smoke. This establishes execution consistency, not
online-policy superiority.

## Resume and Security Checks

A second invocation skipped the completed stable job ID:

```text
executed_jobs=0
skipped_completed_jobs=1
environment_steps=598
api_calls=1
```

It did not make a second API request. The local API credential was loaded from a
Git-ignored Windows DPAPI file and was absent from prompts, ledgers, audit files,
and tracked-source secret scans.

## Artifacts

- `outputs/campaigns/active_evidence_glm52_seed148_pilot_v1/run_ledger.jsonl`
- `outputs/campaigns/active_evidence_glm52_seed148_pilot_v1/summary.csv`
- `outputs/campaigns/active_evidence_glm52_seed148_pilot_v1/jobs/*/agent_decision.json`
- `outputs/campaigns/active_evidence_glm52_seed148_pilot_v1/jobs/*/online_api_audit.json`

## Reproduction

```powershell
.\scripts\run_active_evidence_campaign.ps1 `
  -Config configs\campaigns\active_evidence_glm52_pilot.json `
  -ApiTimeout 300 `
  -ApiMaxRetries 2
```

## Limitations

This is one development seed and one model call. It cannot estimate decision
accuracy, recovery rate, run-to-run stability, or evidence efficiency. The
compatible endpoint reported 847 output tokens despite a client request limit of
700; provider usage semantics therefore require further audit. Future campaigns
must use explicit API-call and wall-time limits rather than relying only on the
requested generation length.
