# ProbeMem Phase C Decision-Trace Audit

Run: `probemem_phase_c_20260731T155344Z_f7176579eb82`
Manifest: `97fffbc4fe1c44b8b920b791d621bd574678c56593edd8312e91ec142e3582e0`
Source commit: `f7176579eb82f49adfd6ade0eeeeae2f495ac8f4`

## Question

Why did chronological episodic retrieval get acknowledged by the online model without changing the selected intervention? This is a no-API, post-hoc audit of the immutable development trace; it does not tune or rerun the registered experiment.

## Quantitative trace result

- Operational paired episodes: 10.
- Raw retrieval was available in 9 cases and acknowledged in 9 post-probe decisions.
- Verified retrieval was available in 8 cases and acknowledged in 8 post-probe decisions.
- Raw retrieval was associated with a different predicted verification status in 6 cases, but changed the intervention in 0 cases.
- Verified retrieval changed post-probe confidence in 4 cases, but changed the intervention in 0 cases.
- Exact prediction agreement was 5/10 stateless, 3/10 raw, and 5/10 verified.
- Relative to stateless prediction agreement, raw retrieval improved 2 cases and worsened 4 cases; this is descriptive, not a powered calibration comparison.
- Raw memory exposed 14 non-accepted historical records; verified memory exposed none.
- All methods selected the same bounded skill and received the same fresh verification outcome in every operational pair.

## Research interpretation

Memory context affected structured reasoning fields, especially raw-memory outcome predictions and verified-memory confidence, but this variation was compressed by the final skill decision. The registered post-probe evidence made every method infer `stable_bias`, after which the available bounded skill interface led every method to `BOUNDED_PLANAR_COMPENSATION`.

This supports a narrower diagnosis than "the model ignored memory": the current episodic representation lacks a reliable, action-discriminative utility signal. Raw rejected/inconclusive episodes changed predictions but did not safely redirect behavior. Accepted-only episodes sometimes raised confidence but did not establish when compensation should fail. Independent LLM sampling is a confound, so differences in hypotheses or predictions are associations, not causal effects of memory.

## Phase-D promotion decision

Do not promote unrestricted LLM-generated principles yet. The next development experiment should first define a falsifiable intervention-utility record: Agent-visible applicability conditions, selected skill, predicted verification status, observed fresh outcome, and explicit contradiction. It should test whether that record changes a discrete intervention on new development seeds before any held-out freeze.

## Reproduction

```bash
python scripts/analyze_probemem_phase_c_decisions.py --run-dir "C:\Users\Administrator\Desktop\embodied-agent-projects\outputs\probemem_v2\runs\probemem_phase_c_20260731T155344Z_f7176579eb82"
```
