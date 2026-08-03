# ProbeMem-Online Gate C Incomplete Launch

Run ID: `probemem_online_gate_c_20260803T095434Z_f346d23912a9`

Manifest ID: `08740c5415ad8a95e85fee9f2fe661a7bc791363fd0124ae8a8e1d0478af08ef`

Source commit: `f346d23912a9`

## Result

The immutable chronological Gate-C development run was launched with the local
GLM-5.2 endpoint. Five population units began environment processing and two
operational episodes completed all four GLM decisions and paired fresh
verification. This produced 8/8 valid structured model decisions, 18 total
method rows, four paired candidate outcomes, four selected-action memory writes,
and two resonance records.

Aggregate API latency for the eight calls was approximately 458.7 seconds:
97.8 seconds for stateless GLM, 114.5 seconds for frozen bootstrap memory,
135.4 seconds for online action memory, and 111.0 seconds for the resonance
variant. This is descriptive operational evidence only; two cases cannot
support method-performance comparisons.

The launch was stopped as `INCOMPLETE_PROVIDER_LATENCY`. No prompt, timeout,
repair rule, regime, seed, or memory rule was modified during the run. No
validation or held-out data were accessed.

## Interpretation

This run provides no statistically usable evidence that online memory or GLM
reasoning improves recovery. The Gate-C promotion gate is not evaluated and
therefore does not pass. The failure is operational: at the observed mean of
roughly 57 seconds per model decision, 240 base decisions alone project to
about 3.8 hours before schema repairs and robot rollouts.

A subsequent experiment must use a new run ID and a separately preregistered
API-feasibility protocol. It must not overwrite this incomplete artifact or
quietly reinterpret it as a negative robot-performance result.
