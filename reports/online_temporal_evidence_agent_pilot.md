# Online GLM-5.2 Temporal Evidence-Allocation Pilot

## Research question

Can a bounded online research agent use leakage-safe terminal and temporal evidence
to request diagnostic probes more selectively than deterministic baselines?

The online model is not a robot controller. It may only choose one structured
action: update a mechanism hypothesis, request the registered 64-step
`symmetric_xy` probe, or abstain. It cannot emit continuous robot actions or read
injected failure metadata.

## Protocol

- Split: the ten matched development cases from seeds 320–329.
- Model: GLM-5.2 through an Anthropic-compatible endpoint.
- Prompt: `active-evidence-decision-v1`.
- Evidence: terminal task outcomes and the schema-v2 Agent-visible temporal planar
  estimate.
- Candidate mechanisms: systematic planar bias, stochastic execution, or
  insufficient evidence.
- API budget: at most one request per case, ten total.
- Probe outcome: the already executed and recorded repeated symmetric probe for the
  same case; no new simulator rollout was needed for this comparison.
- Credentials: loaded from the ignored local DPAPI-encrypted configuration, never
  written to artifacts.

The persisted evidence packets were audited after the run. They contain no
`condition_id`, mechanism label, perturbation type/parameters, raw/perturbed/
executed action, or clipping fields. Oracle mechanism labels enter only the result
CSV after the online decision.

## Real online result

GLM-5.2 returned the same decision on all ten cases:

```text
action = request_probe
hypothesis_mechanism = insufficient_evidence
```

| Method | Correct | Probe requests | Probe steps | API calls |
|---|---:|---:|---:|---:|
| Passive | 6/10 | 0/10 | 0 | 0 |
| Always-probe | 10/10 | 10/10 | 640 | 0 |
| Temporal deterministic gate | 10/10 | 9/10 | 576 | 0 |
| Online GLM-5.2 | 10/10 | 10/10 | 640 | 10 |

Online confidence ranged from 0.82 to 0.92. Mean API latency was 27,719 ms per
case. The endpoint reported 6,988 input tokens and 8,992 output tokens in total;
these compatibility-endpoint usage fields are recorded as reported and are not
independently verified.

## Interpretation

The online Agent correctly recognized that the supplied global temporal evidence
was insufficient, but it did so indiscriminately. Its 100% diagnostic accuracy is
entirely inherited from always requesting the already validated probe. It provides
no evidence-cost advantage over always-probe and uses ten additional model calls.

This result establishes a real, audited online-Agent integration, but not an Agent
performance improvement. Prompt reasoning cannot compensate for an evidence packet
that lacks a calibrated phase-conditioned distinction. The next scientific step is
therefore to improve the evidence interface, not to increase model freedom or add
more prompt text.

## Operational event

The first invocation failed locally before any API request because a missing
`results.csv` was not treated as an empty checkpoint. The reader and regression
test were fixed. The resumed run then completed all ten API calls. A subsequent
resume check skipped all ten completed cases and made no additional calls.

## Limitations

- Development cases only; no held-out online claim.
- One model and prompt version.
- Probe outcomes were reused from real recorded probes rather than re-executed.
- The model was given the known limitation that the temporal fit mixes task phases;
  this may encourage conservative probing.
- The compatibility endpoint's token accounting differs from assumptions implied
  by the requested output limit and should be treated as provider-reported metadata.

## Reproduction

```powershell
.\scripts\check_agent_api_config.ps1
.\scripts\run_online_temporal_evidence_agent.ps1 -ApiTimeout 300 -ApiMaxRetries 2 -MaxApiCalls 10
python scripts/plot_online_temporal_agent.py
```

The wrapper loads the credential from local encrypted storage for the subprocess
and clears the process environment afterward.
